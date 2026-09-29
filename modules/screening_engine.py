"""Transparent, configurable candidate screening.

A score is a weighted sum of four components, each a percentage:

    skills      required skills the resume shows (listed or used in a project)
    projects    required skills demonstrated in at least one described project
    experience  years against the role's minimum, capped at 100%
    education   level against the role's minimum

    final = sum(component% * weight%) / 100

The weights come from a ``ScreeningConfig``. Different configurations are
different, equally legitimate ways of screening; FairLens compares them
rather than declaring one correct. No machine-learning model is involved:
every number can be recomputed by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping

from modules import validator
from modules.candidate import Candidate
from modules.job import JobRole

COMPONENTS: tuple[str, ...] = validator.SCORE_COMPONENTS
COMPONENT_LABELS: dict[str, str] = {
    "skills": "Skills",
    "projects": "Project evidence",
    "experience": "Experience",
    "education": "Education",
}

# (lower bound, label) pairs checked from the top down. Labels describe the
# score band only; they are not hiring recommendations.
STATUS_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (75, "Strong match"),
    (50, "Possible match"),
    (0, "Weak match"),
)


def classify_score(score: float) -> str:
    """Turn a 0-100 score into a score-band label."""
    for lower_bound, label in STATUS_THRESHOLDS:
        if score >= lower_bound:
            return label
    return STATUS_THRESHOLDS[-1][1]


@dataclass(frozen=True)
class ScreeningConfig:
    """A named set of component weights.

    Frozen, and the weights are a tuple in ``COMPONENTS`` order, so a
    configuration cannot be changed after it has been used to score someone.
    """

    config_id: str
    name: str
    weights: tuple[float, ...]
    description: str = ""

    @classmethod
    def create(cls, config_id: str, name: str, weights: Mapping[str, object], description: str = "") -> "ScreeningConfig":
        """Validate raw input and build a configuration."""
        cleaned = validator.validate_weights(weights)
        return cls(
            config_id=validator.validate_record_id(config_id, field="config_id"),
            name=validator.validate_config_name(name),
            weights=tuple(cleaned[c] for c in COMPONENTS),
            description=" ".join(str(description or "").split())[:200],
        )

    @property
    def weight_map(self) -> dict[str, float]:
        return dict(zip(COMPONENTS, self.weights))

    @property
    def short_label(self) -> str:
        """e.g. "Skills 60, Experience 25, Education 15" (zero weights left out)."""
        return ", ".join(f"{COMPONENT_LABELS[c]} {w:g}" for c, w in self.weight_map.items() if w)

    def to_dict(self) -> dict[str, Any]:
        return {"config_id": self.config_id, "name": self.name,
                "weights": self.weight_map, "description": self.description}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScreeningConfig":
        return cls.create(data.get("config_id", ""), data.get("name", ""),
                          data.get("weights") or {}, data.get("description", ""))


# Shipped presets. "Traditional" mirrors how resumes are commonly screened;
# the others shift weight towards or away from demonstrated evidence.
DEFAULT_CONFIGS: tuple[ScreeningConfig, ...] = (
    ScreeningConfig("TRADITIONAL", "Traditional", (60, 0, 25, 15),
                    "Listed skills, years of experience and education, as resumes are commonly screened."),
    ScreeningConfig("SKILLS-FIRST", "Skills-first", (70, 20, 10, 0),
                    "Weights demonstrated skill evidence, including projects, above tenure and credentials."),
    ScreeningConfig("EXPERIENCE", "Experience-weighted", (50, 0, 35, 15),
                    "Gives more weight to years of experience."),
    ScreeningConfig("BALANCED", "Balanced evidence", (45, 20, 20, 15),
                    "Spreads weight across all four components."),
)
DEFAULT_BASELINE_ID = "TRADITIONAL"
DEFAULT_ALTERNATIVE_ID = "SKILLS-FIRST"


@dataclass(frozen=True)
class ScreeningResult:
    """Outcome of screening one candidate against one role under one configuration."""

    candidate_id: str
    candidate_name: str
    job_id: str
    job_title: str
    config_id: str
    config_name: str
    weights: dict[str, float]
    components: dict[str, float]              # component -> percent (0-100)
    final_score: float
    matched_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
    extra_skills: tuple[str, ...]
    evidenced_skills: tuple[str, ...]         # required skills used in a project
    explanation: str
    screened_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    # Named accessors keep call sites readable.
    @property
    def skill_score(self) -> float:
        return self.components["skills"]

    @property
    def project_score(self) -> float:
        return self.components["projects"]

    @property
    def experience_score(self) -> float:
        return self.components["experience"]

    @property
    def education_score(self) -> float:
        return self.components["education"]

    @property
    def status(self) -> str:
        return classify_score(self.final_score)

    @property
    def contributions(self) -> dict[str, float]:
        """Points each component adds to the final score, e.g. {'skills': 52.0, ...}."""
        return {c: self.components[c] * self.weights[c] / 100 for c in COMPONENTS}

    @property
    def points_lost(self) -> dict[str, float]:
        """Points each component could have added but did not."""
        return {c: self.weights[c] - self.contributions[c] for c in COMPONENTS}

    @property
    def drivers(self) -> list[tuple[str, float]]:
        """Weighted components, largest contribution first."""
        weighted = [(c, v) for c, v in self.contributions.items() if self.weights[c] > 0]
        return sorted(weighted, key=lambda item: item[1], reverse=True)

    @property
    def largest_shortfall(self) -> tuple[str, float] | None:
        """The component that cost the most points, if any were lost."""
        component, lost = max(self.points_lost.items(), key=lambda item: item[1])
        return (component, lost) if lost > 0.05 else None

    def rescored(self, component: str, percent: float) -> float:
        """The final score with one component's percentage replaced and the same weights.

        Used for the two-pass comparison: only the way skills are matched changes.
        """
        parts = {**self.components, component: percent}
        return round(sum(parts[c] * self.weights[c] for c in COMPONENTS) / 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_name": self.candidate_name,
            "job_id": self.job_id,
            "job_title": self.job_title,
            "config_id": self.config_id,
            "config_name": self.config_name,
            "weights": dict(self.weights),
            "components": dict(self.components),
            "final_score": self.final_score,
            "status": self.status,
            "matched_skills": list(self.matched_skills),
            "missing_skills": list(self.missing_skills),
            "evidenced_skills": list(self.evidenced_skills),
            "screened_at": self.screened_at,
        }


class ScreeningEngine:
    """Scores candidates against job roles under one screening configuration."""

    def __init__(self, config: ScreeningConfig | Mapping[str, object] | None = None):
        if config is None:
            config = DEFAULT_CONFIGS[0]
        elif not isinstance(config, ScreeningConfig):  # a plain {component: weight} mapping
            config = ScreeningConfig.create("CUSTOM", "Custom", config)
        self.config = config
        self.weights = config.weight_map

    # --- individual components ---------------------------------------------------------

    @staticmethod
    def match_skills(candidate: Candidate, job: JobRole) -> tuple[list[str], list[str], list[str]]:
        """Return (matched, missing, extra) skills using set operations.

        A required skill is matched if it is listed or used in a project.
        """
        required = job.required_skill_map            # key -> display name
        required_keys = set(required)
        matched_keys = candidate.evidence_skill_keys & required_keys
        missing_keys = required_keys - matched_keys

        # Keep the job's original ordering so results read naturally.
        matched = [name for key, name in required.items() if key in matched_keys]
        missing = [name for key, name in required.items() if key in missing_keys]
        extra = [s for s in candidate.skills if validator.skill_key(s) not in required_keys]
        return matched, missing, extra

    @staticmethod
    def evidenced_skills(candidate: Candidate, job: JobRole) -> list[str]:
        """Required skills that appear in at least one of the candidate's projects."""
        project_keys = candidate.project_skill_keys
        return [name for key, name in job.required_skill_map.items() if key in project_keys]

    @staticmethod
    def skill_score(matched_count: int, required_count: int) -> float:
        if required_count == 0:
            return 100.0
        return matched_count / required_count * 100

    @staticmethod
    def project_score(evidenced_count: int, required_count: int) -> float:
        # Same ratio as skills, but only project-backed skills count.
        return ScreeningEngine.skill_score(evidenced_count, required_count)

    @staticmethod
    def experience_score(candidate_years: float, required_years: float) -> float:
        """Full marks once the minimum is met; proportional below it."""
        if required_years <= 0:
            return 100.0
        return min(candidate_years / required_years, 1.0) * 100

    @staticmethod
    def education_score(candidate_rank: int, required_rank: int) -> float:
        """100 if the requirement is met, 50 if one level short, otherwise 0."""
        gap = required_rank - candidate_rank
        if gap <= 0:
            return 100.0
        if gap == 1:
            return 50.0
        return 0.0

    # --- full analysis ---------------------------------------------------------------------

    def analyze(self, candidate: Candidate, job: JobRole) -> ScreeningResult:
        matched, missing, extra = self.match_skills(candidate, job)
        evidenced = self.evidenced_skills(candidate, job)
        required = len(job.required_skills)

        components = {
            "skills": self.skill_score(len(matched), required),
            "projects": self.project_score(len(evidenced), required),
            "experience": self.experience_score(candidate.experience_years, job.min_experience),
            "education": self.education_score(candidate.education_rank, job.min_education_rank),
        }
        final = sum(components[c] * self.weights[c] for c in COMPONENTS) / 100

        return ScreeningResult(
            candidate_id=candidate.candidate_id,
            candidate_name=candidate.name,
            job_id=job.job_id,
            job_title=job.title,
            config_id=self.config.config_id,
            config_name=self.config.name,
            weights=dict(self.weights),
            components={c: round(v, 1) for c, v in components.items()},
            final_score=round(final, 1),
            matched_skills=tuple(matched),
            missing_skills=tuple(missing),
            extra_skills=tuple(extra),
            evidenced_skills=tuple(evidenced),
            explanation=self.explain(candidate, job, len(matched), len(evidenced)),
        )

    def rank_candidates(self, candidates: Iterable[Candidate], job: JobRole) -> list[ScreeningResult]:
        """Screen many candidates against one job, best first."""
        results = [self.analyze(candidate, job) for candidate in candidates]
        return sorted(results, key=lambda r: (r.final_score, r.skill_score), reverse=True)

    @staticmethod
    def explain(candidate: Candidate, job: JobRole, matched_count: int, evidenced_count: int) -> str:
        """A factual sentence built only from the inputs used in scoring."""
        required_count = len(job.required_skills)
        first_name = candidate.name.split()[0]
        parts = [f"{first_name} shows {matched_count} of {required_count} required skills",
                 f"{evidenced_count} of them used in a described project"]

        years = candidate.experience_years
        if job.min_experience <= 0:
            parts.append("the role sets no minimum experience")
        else:
            parts.append(f"has {years:g} year{'' if years == 1 else 's'} of experience against a {job.min_experience:g}-year minimum")

        if candidate.education_rank >= job.min_education_rank:
            parts.append(f"meets the {job.min_education} education minimum")
        else:
            parts.append(f"holds a {candidate.education_level} qualification where {job.min_education} is the minimum")
        return ", ".join(parts[:-1]) + " and " + parts[-1] + "."
