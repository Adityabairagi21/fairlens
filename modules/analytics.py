"""Statistics (NumPy) and tabular analysis (Pandas) over the stored data.

NumPy is used for numeric summaries of score arrays; Pandas is used where
the data is naturally a table that needs grouping, ranking, exploding or
counting. ``AnalyticsEngine`` ties the pipeline together:

    candidates + roles -> ScreeningEngine -> candidate DataFrame -> statistics
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from modules.data_manager import DataManager
from modules.screening_engine import ScreeningConfig, ScreeningEngine, ScreeningResult
from modules.validator import EDUCATION_LEVELS, skill_key

SCORE_BINS: tuple[int, ...] = (0, 20, 40, 60, 80, 100)
EXPERIENCE_BINS: tuple[float, ...] = (0, 1, 3, 5, 8, float("inf"))
EXPERIENCE_LABELS: tuple[str, ...] = ("< 1 yr", "1–3 yrs", "3–5 yrs", "5–8 yrs", "8+ yrs")

FRAME_COLUMNS: list[str] = [
    "candidate_id", "name", "email", "phone", "education_level", "degree", "experience_years",
    "skills", "skill_count", "project_count", "target_job_id", "target_role", "match_score", "skill_score",
    "project_score", "experience_score", "education_score", "status", "matched_skills", "missing_skills",
    "evidenced_skills", "created_at",
]


# --- screening every candidate --------------------------------------------------------------

def screening_pairs(manager: DataManager, job_id: str | None = None) -> list:
    """(candidate, role) pairs for everyone with a target role, optionally one role only."""
    pairs = []
    for candidate in manager.candidates.values():
        job = manager.jobs.get(candidate.target_job_id or "")
        if job is not None and (job_id is None or job.job_id == job_id):
            pairs.append((candidate, job))
    return pairs


def screen_all(manager: DataManager, engine: ScreeningEngine) -> dict[str, ScreeningResult]:
    """Score every candidate against their own target role (if they have one)."""
    return {c.candidate_id: engine.analyze(c, job) for c, job in screening_pairs(manager)}


def build_candidate_frame(manager: DataManager, results: dict[str, ScreeningResult]) -> pd.DataFrame:
    """One row per candidate, joined with their screening result."""
    rows = []
    for c in manager.candidates.values():
        result = results.get(c.candidate_id)
        job = manager.jobs.get(c.target_job_id or "")
        rows.append({
            "candidate_id": c.candidate_id,
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "education_level": c.education_level,
            "degree": c.degree,
            "experience_years": c.experience_years,
            "skills": list(c.skills),
            "skill_count": len(c.skills),
            "project_count": len(c.projects),
            "target_job_id": c.target_job_id,
            "target_role": job.title if job else "Unassigned",
            "match_score": result.final_score if result else np.nan,
            "skill_score": result.skill_score if result else np.nan,
            "project_score": result.project_score if result else np.nan,
            "experience_score": result.experience_score if result else np.nan,
            "education_score": result.education_score if result else np.nan,
            "status": result.status if result else "Not screened",
            "matched_skills": list(result.matched_skills) if result else [],
            "missing_skills": list(result.missing_skills) if result else [],
            "evidenced_skills": list(result.evidenced_skills) if result else [],
            "created_at": pd.to_datetime(c.created_at, errors="coerce"),
        })
    return pd.DataFrame(rows, columns=FRAME_COLUMNS)


# --- NumPy statistics -------------------------------------------------------------------------

def score_statistics(scores: Iterable[float]) -> dict[str, float] | None:
    """Summary statistics for a set of match scores, or None if there are none."""
    values = np.asarray([s for s in scores if s is not None], dtype=float)
    values = values[~np.isnan(values)]
    if values.size == 0:
        return None
    return {
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "std": float(np.std(values)),  # population std: we have every applicant, not a sample
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "p25": float(np.percentile(values, 25)),
        "p75": float(np.percentile(values, 75)),
    }


def sensitivity_statistics(ranges: Iterable[float]) -> dict[str, float] | None:
    """How far scores move across configurations, summarised over candidates."""
    values = np.asarray(list(ranges), dtype=float)
    values = values[~np.isnan(values)]
    if values.size == 0:
        return None
    return {
        "mean_range": float(np.mean(values)),
        "median_range": float(np.median(values)),
        "max_range": float(np.max(values)),
        "std_range": float(np.std(values)),
    }


def score_distribution(scores: Iterable[float]) -> pd.DataFrame:
    """Count scores in 20-point buckets using np.histogram."""
    values = np.asarray(list(scores), dtype=float)
    values = values[~np.isnan(values)]
    counts, edges = np.histogram(values, bins=SCORE_BINS)
    labels = [f"{int(lo)}–{int(hi)}" for lo, hi in zip(edges[:-1], edges[1:])]
    return pd.DataFrame({"range": labels, "candidates": counts.astype(int)})


def percentile_rank(score: float, peer_scores: Iterable[float]) -> float | None:
    """Share of peers (same role) who scored strictly lower, as a percentage."""
    peers = np.asarray(list(peer_scores), dtype=float)
    if peers.size < 2:
        return None
    return float(np.mean(peers < score) * 100)


def experience_score_correlation(frame: pd.DataFrame) -> float | None:
    """Pearson correlation between years of experience and match score."""
    scored = frame.dropna(subset=["match_score"])
    if len(scored) < 3:
        return None
    x = scored["experience_years"].to_numpy(dtype=float)
    y = scored["match_score"].to_numpy(dtype=float)
    if np.std(x) == 0 or np.std(y) == 0:  # correlation is undefined for a constant series
        return None
    return float(np.corrcoef(x, y)[0, 1])


# --- Pandas analysis ---------------------------------------------------------------------------

def average_score_by_role(frame: pd.DataFrame) -> pd.DataFrame:
    scored = frame.dropna(subset=["match_score"])
    if scored.empty:
        return pd.DataFrame(columns=["target_role", "candidates", "avg_score", "best_score", "avg_experience"])
    grouped = (
        scored.groupby("target_role")
        .agg(
            candidates=("candidate_id", "count"),
            avg_score=("match_score", "mean"),
            best_score=("match_score", "max"),
            avg_experience=("experience_years", "mean"),
        )
        .reset_index()
        .sort_values("avg_score", ascending=False)
    )
    return grouped.round(1)


def candidates_per_role(frame: pd.DataFrame) -> pd.DataFrame:
    counts = frame["target_role"].value_counts().rename_axis("target_role").reset_index(name="candidates")
    return counts


def skill_frequency(frame: pd.DataFrame, column: str = "skills", top: int | None = 15) -> pd.DataFrame:
    """How many candidates list each skill. Aliases like 'sklearn' are merged."""
    exploded = frame[["candidate_id", column]].explode(column).dropna(subset=[column])
    if exploded.empty:
        return pd.DataFrame(columns=["skill", "candidates"])
    exploded["key"] = exploded[column].map(skill_key)
    # Display each skill with its most common spelling.
    display = exploded.groupby("key")[column].agg(lambda s: s.mode().iat[0])
    counts = exploded.drop_duplicates(["candidate_id", "key"])["key"].value_counts()
    result = pd.DataFrame({"skill": display[counts.index].values, "candidates": counts.values})
    return result.head(top) if top else result


def missing_skill_frequency(frame: pd.DataFrame, top: int | None = 10) -> pd.DataFrame:
    """Required skills candidates most often lack — the biggest hiring gaps."""
    return skill_frequency(frame, column="missing_skills", top=top)


def experience_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    buckets = pd.cut(frame["experience_years"], bins=EXPERIENCE_BINS, labels=EXPERIENCE_LABELS, right=False)
    counts = buckets.value_counts().reindex(EXPERIENCE_LABELS, fill_value=0)
    return counts.rename_axis("experience").reset_index(name="candidates")


def education_breakdown(frame: pd.DataFrame) -> pd.DataFrame:
    counts = frame["education_level"].value_counts().reindex(EDUCATION_LEVELS, fill_value=0)
    return counts.rename_axis("education_level").reset_index(name="candidates")


def status_breakdown(frame: pd.DataFrame) -> pd.DataFrame:
    order = ["Strong match", "Possible match", "Weak match", "Not screened"]
    counts = frame["status"].value_counts().reindex(order, fill_value=0)
    return counts.rename_axis("status").reset_index(name="candidates")


def rank_within_groups(frame: pd.DataFrame, score_column: str, group_column: str = "target_role") -> pd.Series:
    """Rank 1 = highest score within each group. Ties share the better rank."""
    return frame.groupby(group_column)[score_column].rank(method="min", ascending=False).astype(int)


def high_evidence_low_score(frame: pd.DataFrame, min_coverage: float = 80, gap: float = 15) -> pd.Series:
    """Boolean mask: strong skill coverage, but a baseline score well below it."""
    return (frame["skill_score"] >= min_coverage) & (frame["match_score"] <= frame["skill_score"] - gap)


def top_candidates(frame: pd.DataFrame, n: int = 5, job_id: str | None = None) -> pd.DataFrame:
    scored = frame.dropna(subset=["match_score"])
    if job_id:
        scored = scored[scored["target_job_id"] == job_id]
    return scored.nlargest(n, ["match_score", "skill_score"])


def numeric_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Pandas describe() on the numeric columns, relabelled for display."""
    columns = {
        "experience_years": "Experience (yrs)",
        "skill_count": "Skills listed",
        "match_score": "Match score",
    }
    if frame.empty:
        return pd.DataFrame()
    summary = frame[list(columns)].describe().rename(columns=columns)
    return summary.round(1)


# --- pipeline -----------------------------------------------------------------------------------

class AnalyticsEngine:
    """Runs the candidate pool through one screening configuration and analyses it.

    The UI and the command line both go through this class, so the same
    DataFrame backs every table, chart and statistic.
    """

    def __init__(self, manager: DataManager, config: ScreeningConfig):
        self.manager = manager
        self.engine = ScreeningEngine(config)
        self._results: dict[str, ScreeningResult] | None = None

    @property
    def results(self) -> dict[str, ScreeningResult]:
        if self._results is None:
            self._results = screen_all(self.manager, self.engine)
        return self._results

    def candidate_frame(self) -> pd.DataFrame:
        return build_candidate_frame(self.manager, self.results)

    def summary(self) -> dict[str, float] | None:
        """Headline NumPy statistics for the current pool."""
        frame = self.candidate_frame()
        stats = score_statistics(frame["match_score"])
        if stats is None:
            return None
        coverage = frame["skill_score"].dropna().to_numpy(dtype=float)
        stats["mean_coverage"] = float(np.mean(coverage))
        return stats
