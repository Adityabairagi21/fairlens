"""Competence audit: did the screening capture the evidence, or only the vocabulary?

For every required skill of a role, the candidate's record is searched in a
fixed order and the skill gets one evidence status:

    EXPLICIT   the exact wording is in the skills list
    SUPPORTED  not listed exactly, but used in a project (technologies, description,
               outcomes) or named in the experience summary
    RELATED    listed under different wording: a synonym ("ML") or a related term
               ("PostgreSQL" for SQL) from the skills taxonomy
    MISSING    no evidence anywhere in the record

Three coverages follow, from strictest to broadest:

    vocabulary match   EXPLICIT skills only                      "does the wording match?"
    normalized match   listed skills after taxonomy mapping       "does it match after synonyms?"
    evidence coverage  any status except MISSING                  "is relevant evidence present?"

None of these replaces the screening score. They show how much of the
evidence the baseline method's wording rules can see. Everything is
rule-based (taxonomy + text search); no language model is involved.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pandas as pd

from modules.candidate import Candidate
from modules.job import JobRole
from modules.observation import Observation
from modules.screening_engine import ScreeningConfig, ScreeningEngine, ScreeningResult
from modules.taxonomy import SkillTaxonomy

EVIDENCE_STATUSES: tuple[str, ...] = ("EXPLICIT", "SUPPORTED", "RELATED", "MISSING")
STATUS_MEANING: dict[str, str] = {
    "EXPLICIT": "Named in the skills list with the exact wording",
    "SUPPORTED": "Used in a project or named in the experience summary",
    "RELATED": "Listed under different wording (synonym or related term)",
    "MISSING": "No evidence found in the record",
}

# --- rule thresholds (percentage points) -------------------------------------------------------------
LOW_VOCABULARY = 60.0          # vocabulary match at or below this ...
SEMANTIC_GAP_POINTS = 25.0     # ... with evidence coverage at least this much higher -> potential semantic gap
WORDING_GAP_POINTS = 25.0      # normalized - vocabulary -> possible semantic mismatch
CONSISTENT_POINTS = 15.0       # evidence within this of vocabulary -> consistent
LIMITED_EVIDENCE = 50.0        # evidence coverage below this -> limited evidence
LARGE_PASS_DIFFERENCE = 15.0   # evidence-aware pass minus exact pass

SIGNALS: dict[str, str] = {
    "Review recommended": "Relevant evidence appears stronger than exact keyword coverage.",
    "Partial gap": "Evidence coverage is higher than exact terminology coverage, below the review threshold.",
    "Consistent": "Exact terminology and evidence coverage agree closely.",
    "Limited evidence": "Evidence was found for fewer than half of the required skills.",
}


@dataclass(frozen=True)
class EvidenceSource:
    """Where one piece of evidence for a required skill was found."""

    place: str        # "Skills list", "Project: <name>" or "Experience summary"
    field: str        # "listed skill", "technologies", "description", "outcomes", "summary"
    term: str         # the wording found
    match: str        # "exact", "synonym" or "related"

    def describe(self) -> str:
        how = {"exact": "exact wording", "synonym": "synonym", "related": "related term"}[self.match]
        return f"{self.place} · {self.field}: '{self.term}' ({how})"


@dataclass(frozen=True)
class SkillEvidence:
    """The evidence found for one required skill."""

    skill: str
    status: str
    sources: tuple[EvidenceSource, ...]

    @property
    def exact(self) -> bool:
        return any(s.place == "Skills list" and s.match == "exact" for s in self.sources)

    @property
    def listed(self) -> bool:
        return any(s.place == "Skills list" for s in self.sources)

    @property
    def listed_term(self) -> str | None:
        """The candidate's own wording in the skills list, if the skill is listed at all."""
        return next((s.term for s in self.sources if s.place == "Skills list"), None)

    @property
    def evidenced(self) -> bool:
        return self.status != "MISSING"

    @property
    def summary(self) -> str:
        return self.sources[0].describe() if self.sources else "No evidence found"


@dataclass(frozen=True)
class CompetenceResult:
    """The competence audit for one candidate against one role."""

    candidate_id: str
    candidate_name: str
    job_id: str
    job_title: str
    config_name: str
    skills: tuple[SkillEvidence, ...]
    vocabulary_match: float
    normalized_match: float
    evidence_coverage: float
    baseline: ScreeningResult
    exact_pass_score: float
    evidence_pass_score: float
    observations: tuple[Observation, ...]
    signal: str
    hints: tuple[tuple[str, str, float], ...] = field(default=())   # optional similarity hints, never scored

    @property
    def status_counts(self) -> dict[str, int]:
        counts = Counter(s.status for s in self.skills)
        return {status: counts.get(status, 0) for status in EVIDENCE_STATUSES}

    @property
    def missed_by_exact(self) -> list[SkillEvidence]:
        return [s for s in self.skills if not s.exact]

    @property
    def recovered(self) -> list[SkillEvidence]:
        return [s for s in self.missed_by_exact if s.evidenced]

    @property
    def unsupported(self) -> list[SkillEvidence]:
        return [s for s in self.skills if s.status == "MISSING"]

    @property
    def pass_difference(self) -> float:
        return round(self.evidence_pass_score - self.exact_pass_score, 1)

    @property
    def semantic_gap(self) -> bool:
        return any(o.code == "SEMANTIC_GAP" for o in self.observations)

    @property
    def reason(self) -> str:
        return SIGNALS[self.signal]


class CompetenceAuditEngine:
    """Compares exact keyword evidence, taxonomy-normalized evidence and project/experience evidence."""

    def __init__(self, taxonomy: SkillTaxonomy, config: ScreeningConfig, semantic=None):
        self.taxonomy = taxonomy
        self.engine = ScreeningEngine(config)
        self.semantic = semantic          # optional SemanticMatcher; its output is never scored

    # --- evidence per skill ------------------------------------------------------------------------

    def skill_evidence(self, candidate: Candidate, required: str) -> SkillEvidence:
        tax = self.taxonomy
        sources: list[EvidenceSource] = []

        listed = tax.best_match(required, candidate.skills)
        if listed:
            sources.append(EvidenceSource("Skills list", "listed skill", listed.term, listed.kind))

        for project in candidate.projects:
            place = f"Project: {project['project_name']}"
            used = tax.best_match(required, project["technologies"])
            if used:
                sources.append(EvidenceSource(place, "technologies", used.term, used.kind))
            for text_field in ("description", "outcomes"):
                found = tax.find_in_text(required, project[text_field])
                if found:
                    sources.append(EvidenceSource(place, text_field, found.term, found.kind))

        found = tax.find_in_text(required, candidate.experience_summary)
        if found:
            sources.append(EvidenceSource("Experience summary", "summary", found.term, found.kind))

        supported = any(s.place != "Skills list" for s in sources)
        if listed and listed.kind == "exact":
            status = "EXPLICIT"
        elif supported:
            status = "SUPPORTED"
        elif listed:
            status = "RELATED"
        else:
            status = "MISSING"
        # Strongest evidence first: listed exact, then projects/experience, then listed synonyms.
        sources.sort(key=lambda s: 0 if (s.place == "Skills list" and s.match == "exact")
                     else 1 if s.place != "Skills list" else 2)
        return SkillEvidence(required, status, tuple(sources))

    # --- the audit ---------------------------------------------------------------------------------

    def assess(self, candidate: Candidate, job: JobRole) -> CompetenceResult:
        skills = tuple(self.skill_evidence(candidate, required) for required in job.required_skills)
        n = len(skills) or 1
        vocabulary = sum(s.exact for s in skills) / n * 100
        normalized = sum(s.listed for s in skills) / n * 100
        evidence = sum(s.evidenced for s in skills) / n * 100
        baseline = self.engine.analyze(candidate, job)

        # Two passes with the baseline weights; only the skills percentage changes.
        exact_pass = baseline.rescored("skills", vocabulary)
        evidence_pass = baseline.rescored("skills", evidence)

        observations = self.observe(skills, vocabulary, normalized, evidence, exact_pass, evidence_pass)
        signal = self.signal(vocabulary, evidence, observations)
        hints = ()
        if self.semantic is not None:
            missing = [s.skill for s in skills if s.status == "MISSING"]
            hints = tuple(self.semantic.suggest(missing, self.candidate_terms(candidate)))

        return CompetenceResult(
            candidate_id=candidate.candidate_id, candidate_name=candidate.name,
            job_id=job.job_id, job_title=job.title, config_name=self.engine.config.name,
            skills=skills, vocabulary_match=round(vocabulary, 1), normalized_match=round(normalized, 1),
            evidence_coverage=round(evidence, 1), baseline=baseline,
            exact_pass_score=exact_pass, evidence_pass_score=evidence_pass,
            observations=tuple(observations), signal=signal, hints=hints,
        )

    def assess_many(self, pairs: Iterable[tuple[Candidate, JobRole]]) -> list[CompetenceResult]:
        return [self.assess(candidate, job) for candidate, job in pairs]

    @staticmethod
    def candidate_terms(candidate: Candidate) -> list[str]:
        """Every wording in the record: listed skills, technologies, and words/pairs from the text."""
        terms = [*candidate.skills, *(t for p in candidate.projects for t in p["technologies"])]
        texts = [candidate.experience_summary, *(p["description"] + " " + p["outcomes"] for p in candidate.projects)]
        for text in texts:
            words = [w.strip(".,;:()") for w in text.split()]
            terms += [w for w in words if len(w) > 2]
            terms += [f"{a} {b}" for a, b in zip(words, words[1:])]
        return list(dict.fromkeys(terms))

    # --- rules -------------------------------------------------------------------------------------------

    @staticmethod
    def observe(skills, vocabulary: float, normalized: float, evidence: float,
                exact_pass: float, evidence_pass: float) -> list[Observation]:
        found: list[Observation] = []
        n = len(skills)
        if vocabulary <= LOW_VOCABULARY and evidence - vocabulary >= SEMANTIC_GAP_POINTS:
            found.append(Observation(
                "SEMANTIC_GAP", "Potential semantic gap",
                f"Exact terminology covers {vocabulary:.0f}% of the required skills, while evidence coverage is "
                f"{evidence:.0f}%. The record contains relevant evidence that is not fully captured by exact "
                f"skill matching. Evidence-aware pass: {evidence_pass:.1f}% vs exact pass {exact_pass:.1f}%.",
                "competence",
            ))
        wording = [s for s in skills if s.listed and not s.exact]
        if normalized - vocabulary >= WORDING_GAP_POINTS and wording:
            examples = ", ".join(f"'{s.listed_term}' for {s.skill}" for s in wording[:3])
            found.append(Observation(
                "WORDING_MISMATCH", "Possible semantic mismatch",
                f"{len(wording)} of {n} required skills are listed under different wording ({examples}). "
                "Strict keyword matching does not count them.",
                "competence",
            ))
        text_only = [s for s in skills if s.status == "SUPPORTED" and not s.listed]
        if text_only:
            names = ", ".join(s.skill for s in text_only)
            found.append(Observation(
                "PROJECT_EVIDENCE", "Evidence outside the skills list",
                f"{names} {'appears' if len(text_only) == 1 else 'appear'} in project or experience evidence "
                "but not in the skills list.",
                "competence",
            ))
        missing = [s for s in skills if s.status == "MISSING"]
        if missing:
            found.append(Observation(
                "NO_EVIDENCE", "Required skills without evidence",
                f"No evidence found for {', '.join(s.skill for s in missing)} in the skills list, projects or "
                "experience summary.",
                "competence",
            ))
        return found

    @staticmethod
    def signal(vocabulary: float, evidence: float, observations: Iterable[Observation]) -> str:
        if any(o.code == "SEMANTIC_GAP" for o in observations):
            return "Review recommended"
        if evidence < LIMITED_EVIDENCE:
            return "Limited evidence"
        if evidence - vocabulary < CONSISTENT_POINTS:
            return "Consistent"
        return "Partial gap"

    # --- tables and statistics -----------------------------------------------------------------------

    @staticmethod
    def frame(results: Iterable[CompetenceResult]) -> pd.DataFrame:
        """One row per candidate: the audit comparison table (Pandas)."""
        rows = [{
            "candidate_id": r.candidate_id,
            "name": r.candidate_name,
            "target_role": r.job_title,
            "vocabulary_match": r.vocabulary_match,
            "normalized_match": r.normalized_match,
            "evidence_coverage": r.evidence_coverage,
            "baseline_score": r.baseline.final_score,
            "exact_pass_score": r.exact_pass_score,
            "evidence_pass_score": r.evidence_pass_score,
            "pass_difference": r.pass_difference,
            "semantic_gap": r.semantic_gap,
            "signal": r.signal,
            **{f"n_{status.lower()}": count for status, count in r.status_counts.items()},
            "missing_skills": "; ".join(s.skill for s in r.unsupported),
            "supported_skills": "; ".join(s.skill for s in r.skills if s.status == "SUPPORTED"),
            "related_skills": "; ".join(s.skill for s in r.skills if s.status == "RELATED"),
        } for r in results]
        return pd.DataFrame(rows)

    @staticmethod
    def statistics(frame: pd.DataFrame) -> dict[str, Any] | None:
        """NumPy summary of the gap between vocabulary and evidence across candidates."""
        if frame.empty:
            return None
        vocabulary = frame["vocabulary_match"].to_numpy(dtype=float)
        evidence = frame["evidence_coverage"].to_numpy(dtype=float)
        gap = evidence - vocabulary
        return {
            "candidates": int(vocabulary.size),
            "mean_vocabulary": float(np.mean(vocabulary)),
            "mean_normalized": float(np.mean(frame["normalized_match"].to_numpy(dtype=float))),
            "mean_evidence": float(np.mean(evidence)),
            "mean_gap": float(np.mean(gap)),
            "median_gap": float(np.median(gap)),
            "max_gap": float(np.max(gap)),
            "mean_pass_difference": float(np.mean(frame["pass_difference"].to_numpy(dtype=float))),
            "semantic_gaps": int(frame["semantic_gap"].sum()),
            "high_evidence": int((evidence >= 80).sum()),
            "large_pass_difference": int((frame["pass_difference"] >= LARGE_PASS_DIFFERENCE).sum()),
        }
