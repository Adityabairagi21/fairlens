"""Persistent storage for candidates, roles, screening configurations and audit history.

``DataManager`` is the single place that reads and writes the JSON files in
``data/``. The UI never touches files directly.

    candidates.json          candidate records, including project evidence
    jobs.json                job roles and their requirements
    screening_configs.json   named weight configurations + which two are compared
    screening_history.json   one summary row per screening audit that was run
    skills_taxonomy.json     synonyms and related terms for the competence audit (read-only here)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO, Any, Iterable

from modules import file_handler, validator
from modules.candidate import Candidate
from modules.exceptions import (
    DataFileError,
    DuplicateCandidateError,
    DuplicateJobError,
    RecordNotFoundError,
    ValidationError,
)
from modules.job import JobRole
from modules.taxonomy import SkillTaxonomy
from modules.screening_engine import (
    DEFAULT_ALTERNATIVE_ID,
    DEFAULT_BASELINE_ID,
    DEFAULT_CONFIGS,
    ScreeningConfig,
)

MAX_HISTORY = 500        # keep screening_history.json from growing forever
MAX_CONFIGS = 8          # every configuration is part of the sensitivity test


def default_config_file() -> dict[str, Any]:
    return {
        "baseline": DEFAULT_BASELINE_ID,
        "alternative": DEFAULT_ALTERNATIVE_ID,
        "configs": [c.to_dict() for c in DEFAULT_CONFIGS],
    }


@dataclass
class ImportSummary:
    """What happened during a CSV import, row by row."""

    added: list[str] = field(default_factory=list)
    skipped: list[tuple[int, str]] = field(default_factory=list)  # (row number, reason)


class DataManager:
    """Loads, validates, stores and saves all application data."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.paths: dict[str, Path] = {
            "candidates": self.data_dir / "candidates.json",
            "jobs": self.data_dir / "jobs.json",
            "configs": self.data_dir / "screening_configs.json",
            "history": self.data_dir / "screening_history.json",
            "taxonomy": self.data_dir / "skills_taxonomy.json",
        }
        # Dicts keyed by ID give O(1) lookup and make duplicate checks trivial.
        self.candidates: dict[str, Candidate] = {}
        self.jobs: dict[str, JobRole] = {}
        self.configs: dict[str, ScreeningConfig] = {c.config_id: c for c in DEFAULT_CONFIGS}
        self.baseline_id = DEFAULT_BASELINE_ID
        self.alternative_id = DEFAULT_ALTERNATIVE_ID
        self.history: list[dict[str, Any]] = []
        self.taxonomy = SkillTaxonomy()     # replaced by the file's contents in load()
        self.taxonomy_loaded = False
        self.load_errors: dict[str, str] = {}      # file key -> message, for corrupt files
        self.skipped_records: list[str] = []       # invalid records found inside valid files
        self.load()

    # --- loading & saving -------------------------------------------------------------

    def load(self) -> None:
        """Load every file. One corrupted file does not stop the others loading."""
        self.load_errors.clear()
        self.skipped_records.clear()

        defaults = {"jobs": [], "candidates": [], "configs": default_config_file(), "history": []}
        for key, default in defaults.items():
            try:
                raw = file_handler.load_json(self.paths[key], default)
                self._apply_loaded(key, raw)
            except DataFileError as error:
                self.load_errors[key] = str(error)

        # The taxonomy is reference data edited by hand, so it is never recreated automatically.
        # If it is missing or invalid the competence audit falls back to exact wording plus the
        # built-in spelling aliases, and the problem is reported like any other file error.
        # A missing file (e.g. a fresh data folder) is not an error; the UI says which mode is active.
        self.taxonomy, self.taxonomy_loaded = SkillTaxonomy(), False
        if not self.paths["taxonomy"].exists():
            return
        try:
            self.taxonomy = SkillTaxonomy.from_file(self.paths["taxonomy"])
            self.taxonomy_loaded = True
        except DataFileError as error:
            self.taxonomy = SkillTaxonomy()
            self.load_errors["taxonomy"] = f"{error} The competence audit is using exact wording only."

    def _apply_loaded(self, key: str, raw: Any) -> None:
        if key == "configs":
            self._apply_configs(raw)
            return

        if not isinstance(raw, list):
            raise DataFileError(f"{self.paths[key].name} should contain a list of records.")

        if key == "history":
            self.history = [row for row in raw if isinstance(row, dict) and "run_at" in row]
            return

        model, store, id_field = (
            (Candidate, self.candidates, "candidate_id") if key == "candidates" else (JobRole, self.jobs, "job_id")
        )
        store.clear()
        for index, record in enumerate(raw, start=1):
            try:
                if not isinstance(record, dict):
                    raise ValidationError(id_field, "record is not an object")
                item = model.from_dict(record)
                item_id = getattr(item, id_field)
                if item_id in store:
                    raise ValidationError(id_field, f"duplicate ID {item_id}")
                store[item_id] = item
            except ValidationError as error:
                self.skipped_records.append(f"{self.paths[key].name} record {index}: {error.message}")

    def _apply_configs(self, raw: Any) -> None:
        name = self.paths["configs"].name
        if not isinstance(raw, dict) or not isinstance(raw.get("configs"), list):
            raise DataFileError(f"{name} should contain a 'configs' list.")
        loaded: dict[str, ScreeningConfig] = {}
        for index, record in enumerate(raw["configs"], start=1):
            try:
                if not isinstance(record, dict):
                    raise ValidationError("config", "record is not an object")
                config = ScreeningConfig.from_dict(record)
                if config.config_id in loaded:
                    raise ValidationError("config_id", f"duplicate ID {config.config_id}")
                if any(c.name.casefold() == config.name.casefold() for c in loaded.values()):
                    raise ValidationError("name", f"duplicate name '{config.name}'")
                loaded[config.config_id] = config
            except ValidationError as error:
                self.skipped_records.append(f"{name} record {index}: {error.message}")

        # Comparing needs two configurations; fall back to the presets otherwise.
        if len(loaded) < 2:
            self.skipped_records.append(f"{name}: fewer than two valid configurations, presets used instead")
            loaded = {c.config_id: c for c in DEFAULT_CONFIGS}
        self.configs = loaded
        ids = list(loaded)
        baseline = str(raw.get("baseline", "")).upper()
        alternative = str(raw.get("alternative", "")).upper()
        self.baseline_id = baseline if baseline in loaded else ids[0]
        if alternative in loaded and alternative != self.baseline_id:
            self.alternative_id = alternative
        else:
            self.alternative_id = next(i for i in ids if i != self.baseline_id)

    def save_candidates(self) -> None:
        file_handler.save_json(self.paths["candidates"], [c.to_dict() for c in self.candidates.values()])

    def save_jobs(self) -> None:
        file_handler.save_json(self.paths["jobs"], [j.to_dict() for j in self.jobs.values()])

    def save_configs(self) -> None:
        file_handler.save_json(self.paths["configs"], {
            "baseline": self.baseline_id,
            "alternative": self.alternative_id,
            "configs": [c.to_dict() for c in self.configs.values()],
        })

    def save_history(self) -> None:
        file_handler.save_json(self.paths["history"], self.history[-MAX_HISTORY:])

    def reset_file(self, key: str) -> Path | None:
        """Replace a corrupted file with a fresh one, keeping a backup copy."""
        if key == "taxonomy":
            raise DataFileError("skills_taxonomy.json is edited by hand. Fix or restore it, then reload the data.")
        path = self.paths[key]
        backup = file_handler.backup_file(path) if path.exists() else None
        file_handler.save_json(path, default_config_file() if key == "configs" else [])
        self.load()
        return backup

    # --- ID generation -----------------------------------------------------------------

    @staticmethod
    def _next_id(existing: Iterable[str], prefix: str) -> str:
        numbers = [int(i[len(prefix):]) for i in existing if i.startswith(prefix) and i[len(prefix):].isdigit()]
        return f"{prefix}{max(numbers, default=0) + 1:03d}"

    def next_candidate_id(self) -> str:
        return self._next_id(self.candidates, "C")

    def next_job_id(self) -> str:
        return self._next_id(self.jobs, "J")

    # --- candidates ----------------------------------------------------------------------

    def get_candidate(self, candidate_id: str) -> Candidate:
        try:
            return self.candidates[candidate_id]
        except KeyError:
            raise RecordNotFoundError(f"No candidate with ID {candidate_id}.") from None

    def _check_candidate_unique(self, candidate: Candidate, ignore_id: str | None = None) -> None:
        if candidate.candidate_id in self.candidates and candidate.candidate_id != ignore_id:
            raise DuplicateCandidateError(f"A candidate with ID {candidate.candidate_id} already exists.")
        for other in self.candidates.values():
            if other.email == candidate.email and other.candidate_id != ignore_id:
                raise DuplicateCandidateError(
                    f"{other.name} ({other.candidate_id}) is already registered with {candidate.email}."
                )
        if candidate.target_job_id and candidate.target_job_id not in self.jobs:
            raise RecordNotFoundError(f"Target role {candidate.target_job_id} does not exist.")

    def add_candidate(self, candidate: Candidate, save: bool = True) -> Candidate:
        self._check_candidate_unique(candidate)
        self.candidates[candidate.candidate_id] = candidate
        if save:
            self.save_candidates()
        return candidate

    def create_candidate(self, **fields: Any) -> Candidate:
        """Build a candidate from form fields with a fresh ID, then store it."""
        fields.setdefault("candidate_id", self.next_candidate_id())
        return self.add_candidate(Candidate(**fields))

    def update_candidate(self, candidate_id: str, **changes: Any) -> Candidate:
        current = self.get_candidate(candidate_id)
        # Validate the edit on a copy first so a failure leaves the stored record untouched.
        edited = Candidate.from_dict({**current.to_dict(), **changes, "candidate_id": candidate_id})
        self._check_candidate_unique(edited, ignore_id=candidate_id)
        self.candidates[candidate_id] = edited
        self.save_candidates()
        return edited

    def record_review(self, candidate_id: str, assessment: str, notes: str) -> Candidate:
        """Store a human reviewer's own assessment. FairLens never fills this in itself."""
        review = {"assessment": assessment, "reviewed_at": datetime.now().isoformat(timespec="seconds")}
        return self.update_candidate(candidate_id, review=review, notes=notes)

    def delete_candidate(self, candidate_id: str) -> None:
        # Audit history rows are aggregate snapshots, so they are kept.
        candidate = self.get_candidate(candidate_id)
        del self.candidates[candidate.candidate_id]
        self.save_candidates()

    # --- jobs ------------------------------------------------------------------------------

    def get_job(self, job_id: str) -> JobRole:
        try:
            return self.jobs[job_id]
        except KeyError:
            raise RecordNotFoundError(f"No job role with ID {job_id}.") from None

    def _check_job_unique(self, job: JobRole, ignore_id: str | None = None) -> None:
        if job.job_id in self.jobs and job.job_id != ignore_id:
            raise DuplicateJobError(f"A job role with ID {job.job_id} already exists.")
        for other in self.jobs.values():
            if other.title.casefold() == job.title.casefold() and other.job_id != ignore_id:
                raise DuplicateJobError(f"A job role called '{job.title}' already exists.")

    def create_job(self, **fields: Any) -> JobRole:
        fields.setdefault("job_id", self.next_job_id())
        job = JobRole(**fields)
        self._check_job_unique(job)
        self.jobs[job.job_id] = job
        self.save_jobs()
        return job

    def update_job(self, job_id: str, **changes: Any) -> JobRole:
        current = self.get_job(job_id)
        edited = JobRole.from_dict({**current.to_dict(), **changes, "job_id": job_id})
        self._check_job_unique(edited, ignore_id=job_id)
        self.jobs[job_id] = edited
        self.save_jobs()
        return edited

    def delete_job(self, job_id: str) -> int:
        """Delete a job and un-assign it from candidates. Returns how many were affected."""
        self.get_job(job_id)
        del self.jobs[job_id]
        affected = 0
        for candidate in self.candidates.values():
            if candidate.target_job_id == job_id:
                candidate.target_job_id = None
                affected += 1
        self.save_jobs()
        self.save_candidates()
        return affected

    def find_job_by_title(self, title: str) -> JobRole | None:
        wanted = " ".join(title.split()).casefold()
        return next((job for job in self.jobs.values() if job.title.casefold() == wanted), None)

    # --- screening configurations --------------------------------------------------------------

    @property
    def baseline(self) -> ScreeningConfig:
        return self.configs[self.baseline_id]

    @property
    def alternative(self) -> ScreeningConfig:
        return self.configs[self.alternative_id]

    def get_config(self, config_id: str) -> ScreeningConfig:
        try:
            return self.configs[config_id]
        except KeyError:
            raise RecordNotFoundError(f"No screening configuration with ID {config_id}.") from None

    def _check_config_name(self, name: str, ignore_id: str | None = None) -> None:
        for other in self.configs.values():
            if other.name.casefold() == name.casefold() and other.config_id != ignore_id:
                raise ValidationError("name", f"A configuration called '{other.name}' already exists.")

    def create_config(self, name: str, weights: dict[str, object], description: str = "") -> ScreeningConfig:
        if len(self.configs) >= MAX_CONFIGS:
            raise ValidationError("config", f"At most {MAX_CONFIGS} configurations can be compared. Delete one first.")
        config = ScreeningConfig.create(self._next_id(self.configs, "CFG"), name, weights, description)
        self._check_config_name(config.name)
        self.configs[config.config_id] = config
        self.save_configs()
        return config

    def update_config(self, config_id: str, name: str, weights: dict[str, object],
                      description: str = "") -> ScreeningConfig:
        self.get_config(config_id)
        config = ScreeningConfig.create(config_id, name, weights, description)
        self._check_config_name(config.name, ignore_id=config_id)
        self.configs[config_id] = config
        self.save_configs()
        return config

    def delete_config(self, config_id: str) -> None:
        config = self.get_config(config_id)
        if config_id in (self.baseline_id, self.alternative_id):
            raise ValidationError("config", f"'{config.name}' is in use as the baseline or alternative. "
                                            "Choose a different one first.")
        del self.configs[config_id]
        self.save_configs()

    def set_comparison(self, baseline_id: str, alternative_id: str) -> None:
        """Choose the two configurations the product compares everywhere."""
        self.get_config(baseline_id)
        self.get_config(alternative_id)
        if baseline_id == alternative_id:
            raise ValidationError("config", "Choose two different configurations to compare.")
        self.baseline_id, self.alternative_id = baseline_id, alternative_id
        self.save_configs()

    # --- audit history ---------------------------------------------------------------------------

    def record_audit(self, record: dict[str, Any]) -> None:
        self.history.append(dict(record))
        self.save_history()

    # --- import / export ----------------------------------------------------------------------

    def import_candidates_csv(self, source: Path | IO) -> ImportSummary:
        """Import candidates row by row; invalid rows are reported, not fatal."""
        frame = file_handler.read_csv(source)
        required_columns = {"name", "email", "experience_years", "education_level", "degree", "skills"}
        missing_columns = required_columns - set(frame.columns)
        if missing_columns:
            raise DataFileError(f"The CSV is missing these columns: {', '.join(sorted(missing_columns))}.")

        summary = ImportSummary()
        for row_number, row in enumerate(frame.to_dict(orient="records"), start=2):  # row 1 is the header
            try:
                target = str(row.get("target_role", "")).strip()
                job = None
                if target:  # accept either the job title or its ID
                    job = self.find_job_by_title(target) or self.jobs.get(target.upper())
                if target and job is None:
                    raise ValidationError("target_role", f"unknown target role '{target}'")
                candidate = Candidate(
                    candidate_id=row.get("candidate_id") or self.next_candidate_id(),
                    name=row["name"],
                    email=row["email"],
                    phone=row.get("phone", ""),
                    experience_years=row["experience_years"],
                    education_level=row["education_level"],
                    degree=row["degree"],
                    # Semicolons are allowed inside the cell so the CSV needs no quoting.
                    skills=str(row["skills"]).replace(";", ","),
                    target_job_id=job.job_id if job else None,
                    projects=row.get("projects") or None,                    # optional column
                    experience_summary=row.get("experience_summary") or "",  # optional column
                )
                self.add_candidate(candidate, save=False)
                summary.added.append(candidate.candidate_id)
            except ValidationError as error:
                summary.skipped.append((row_number, error.message))
            except (DuplicateCandidateError, RecordNotFoundError) as error:
                summary.skipped.append((row_number, str(error)))

        if summary.added:
            self.save_candidates()
        return summary

    def export_json(self) -> dict[str, Any]:
        return {
            "candidates": [c.to_dict() for c in self.candidates.values()],
            "jobs": [j.to_dict() for j in self.jobs.values()],
            "screening_configs": [c.to_dict() for c in self.configs.values()],
        }


# --- search, filter and sort ----------------------------------------------------------------
# Plain functions over lists so they can be reused and tested without any UI.

def search_candidates(candidates: Iterable[Candidate], query: str) -> list[Candidate]:
    """Case-insensitive match on ID, name, email, degree or any skill."""
    terms = query.casefold().split()
    if not terms:
        return list(candidates)

    def haystack(c: Candidate) -> str:
        return " ".join([c.candidate_id, c.name, c.email, c.degree, *c.skills]).casefold()

    return [c for c in candidates if all(term in haystack(c) for term in terms)]


def filter_candidates(
    candidates: Iterable[Candidate],
    job_id: str | None = None,
    education_levels: Iterable[str] | None = None,
    min_experience: float = 0,
    must_have_skills: Iterable[str] | None = None,
    statuses: Iterable[str] | None = None,
    status_lookup: dict[str, str] | None = None,
) -> list[Candidate]:
    """Keep candidates that satisfy every filter that is set."""
    levels = set(education_levels or [])
    skill_keys = {validator.skill_key(s) for s in (must_have_skills or [])}
    wanted_statuses = set(statuses or [])
    status_lookup = status_lookup or {}

    result = []
    for c in candidates:
        if job_id and c.target_job_id != job_id:
            continue
        if levels and c.education_level not in levels:
            continue
        if c.experience_years < min_experience:
            continue
        if skill_keys and not skill_keys <= c.skill_keys:  # subset test
            continue
        if wanted_statuses and status_lookup.get(c.candidate_id, "Not screened") not in wanted_statuses:
            continue
        result.append(c)
    return result


SORT_KEYS: dict[str, str] = {
    "Match score": "score",
    "Name": "name",
    "Experience": "experience_years",
    "Date added": "created_at",
}


def sort_candidates(
    candidates: Iterable[Candidate],
    by: str = "Match score",
    descending: bool = True,
    scores: dict[str, float] | None = None,
) -> list[Candidate]:
    attribute = SORT_KEYS.get(by)
    if attribute is None:
        raise ValueError(f"Cannot sort by '{by}'. Choose one of: {', '.join(SORT_KEYS)}.")
    scores = scores or {}

    def key(c: Candidate):
        if attribute == "score":
            return scores.get(c.candidate_id, -1)  # unscored candidates sink to the bottom
        if attribute == "name":
            return c.name.casefold()
        return getattr(c, attribute)

    return sorted(candidates, key=key, reverse=descending)
