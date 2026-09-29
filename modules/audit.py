"""Screening audit: runs a role's candidates through two configurations,
measures sensitivity and ranking stability, and records rule-based observations.

Every observation comes from a fixed, documented rule over numbers that
the screening engine already calculated. Observations describe how the
*screening configuration* treats the evidence. They are not hiring
recommendations and do not say whether any real process is discriminatory.
Nothing here looks at names, locations, colleges or any personal attribute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from modules import analytics
from modules.competence import CompetenceAuditEngine, CompetenceResult
from modules.data_manager import DataManager
from modules.observation import Observation, ordinal
from modules.screening_engine import COMPONENT_LABELS, ScreeningConfig, ScreeningEngine, ScreeningResult
from modules.sensitivity import HIGH_SENSITIVITY_POINTS, SensitivityAnalyzer

# --- rule thresholds (all in percentage points unless noted) -------------------------------------
STRONG_COVERAGE = 80.0          # skill coverage treated as "strong"
COVERAGE_GAP = 15.0             # baseline this far below coverage is worth a look
DOMINANT_SHARE = 0.60           # one criterion causing >= 60% of the points lost ...
DOMINANT_MIN_POINTS = 10.0      # ... and at least this many points
RANK_SHIFT = 2                  # places moved between baseline and alternative
MIN_GROUP_FOR_RANKING = 3       # ranking is meaningless with fewer candidates
STRONG_PROJECTS = 50.0          # share of required skills shown in projects
UNBACKED_COVERAGE = 70.0
UNBACKED_PROJECTS = 25.0


@dataclass
class AuditReport:
    """Everything one audit run produced, including the competence audit per candidate."""

    scope: str                                   # role title or "All roles"
    job_id: str | None
    baseline: ScreeningConfig
    alternative: ScreeningConfig
    configs: tuple[ScreeningConfig, ...]
    table: pd.DataFrame
    observations: dict[str, list[Observation]]
    baseline_results: dict[str, ScreeningResult]
    alternative_results: dict[str, ScreeningResult]
    competence: dict[str, CompetenceResult] = field(default_factory=dict)
    run_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def empty(self) -> bool:
        return self.table.empty

    @property
    def summary(self) -> dict[str, Any]:
        """Headline numbers, all computed from the audit table with NumPy."""
        if self.table.empty:
            return {"candidates": 0}
        baseline = self.table["baseline_score"].to_numpy(dtype=float)
        alternative = self.table["alternative_score"].to_numpy(dtype=float)
        coverage = self.table["skill_coverage"].to_numpy(dtype=float)
        ranges = self.table["score_range"].to_numpy(dtype=float)
        return {
            "candidates": int(baseline.size),
            "average_score": float(np.mean(baseline)),
            "median_score": float(np.median(baseline)),
            "score_std": float(np.std(baseline)),
            "min_score": float(np.min(baseline)),
            "max_score": float(np.max(baseline)),
            "score_range": float(np.ptp(baseline)),
            "average_alternative": float(np.mean(alternative)),
            "average_change": float(np.mean(alternative - baseline)),
            "average_coverage": float(np.mean(coverage)),
            "average_sensitivity": float(np.mean(ranges)),
            "high_sensitivity": int(self.table["high_sensitivity"].sum()),
            "blind_spots": int(self.table["blind_spot"].sum()),
            "ranking_changes": int((self.table["rank_change"] != 0).sum()),
            # competence audit
            "average_vocabulary": float(np.mean(self.table["vocabulary_match"].to_numpy(dtype=float))),
            "average_evidence": float(np.mean(self.table["evidence_coverage"].to_numpy(dtype=float))),
            "semantic_gaps": int(self.table["semantic_gap"].sum()),
        }

    def to_history_record(self) -> dict[str, Any]:
        s = self.summary
        return {
            "run_at": self.run_at,
            "scope": self.scope,
            "job_id": self.job_id,
            "baseline": self.baseline.name,
            "baseline_weights": self.baseline.weight_map,
            "alternative": self.alternative.name,
            "alternative_weights": self.alternative.weight_map,
            "candidates": s["candidates"],
            "average_score": round(s.get("average_score", 0.0), 1),
            "average_coverage": round(s.get("average_coverage", 0.0), 1),
            "high_sensitivity": s.get("high_sensitivity", 0),
            "blind_spots": s.get("blind_spots", 0),
            "ranking_changes": s.get("ranking_changes", 0),
            "semantic_gaps": s.get("semantic_gaps", 0),
            "average_evidence": round(s.get("average_evidence", 0.0), 1),
        }

    def to_csv_frame(self) -> pd.DataFrame:
        """Flat table for audit_results.csv (lists joined with '; ')."""
        out = self.table.drop(columns=[c.config_id for c in self.configs], errors="ignore").copy()
        for config in self.configs:
            out[f"score_{config.name}"] = self.table[config.config_id]
        out["observations"] = out["candidate_id"].map(
            lambda cid: "; ".join(o.title for o in self.observations.get(cid, []))
        )
        out.insert(0, "audit_run_at", self.run_at)
        out.insert(1, "baseline_config", self.baseline.name)
        out.insert(2, "alternative_config", self.alternative.name)
        return out


class AuditEngine:
    """Compares a baseline and an alternative configuration over a candidate pool."""

    def __init__(self, baseline: ScreeningConfig, alternative: ScreeningConfig,
                 configs: Sequence[ScreeningConfig]):
        ids = [c.config_id for c in configs]
        if baseline.config_id not in ids or alternative.config_id not in ids:
            raise ValueError("The baseline and alternative must be among the audited configurations.")
        self.baseline = baseline
        self.alternative = alternative
        self.configs = tuple(configs)
        self.baseline_engine = ScreeningEngine(baseline)
        self.alternative_engine = ScreeningEngine(alternative)
        self.sensitivity = SensitivityAnalyzer(self.configs)

    # --- rules ---------------------------------------------------------------------------------

    def observe(self, base: ScreeningResult, alt: ScreeningResult, spread: Mapping[str, Any],
                base_rank: int, alt_rank: int, group_size: int) -> list[Observation]:
        """Apply every rule to one candidate. Returns the observations that fire."""
        found: list[Observation] = []
        coverage = base.skill_score
        lost = base.points_lost
        total_lost = sum(lost.values())
        required = len(base.matched_skills) + len(base.missing_skills)

        if coverage >= STRONG_COVERAGE and base.final_score <= coverage - COVERAGE_GAP:
            found.append(Observation(
                "HIGH_EVIDENCE_LOW_BASELINE", "High evidence / low baseline score",
                f"Skill coverage is {coverage:.0f}%, but the {base.config_name} score is "
                f"{base.final_score:.0f}%. Most of the {total_lost:.0f} points not awarded come from "
                f"criteria other than skills.",
                "blind_spot",
            ))

        non_skill = {c: v for c, v in lost.items() if c != "skills"}
        component, points = max(non_skill.items(), key=lambda item: item[1])
        if total_lost > 0 and points >= DOMINANT_MIN_POINTS and points / total_lost >= DOMINANT_SHARE:
            label = COMPONENT_LABELS[component]
            found.append(Observation(
                "SINGLE_CRITERION", f"Score shaped mainly by {label.lower()}",
                f"{label} accounts for {points:.0f} of the {total_lost:.0f} points not awarded "
                f"({points / total_lost:.0%}) under {base.config_name}, while skill coverage is {coverage:.0f}%.",
                "blind_spot",
            ))

        # Only worth noting when a configuration that does weight projects scores the candidate higher.
        if (base.weights["projects"] == 0 and alt.weights["projects"] > 0
                and base.project_score >= STRONG_PROJECTS and alt.final_score > base.final_score):
            found.append(Observation(
                "UNCREDITED_PROJECTS", "Project evidence not weighted",
                f"Projects demonstrate {len(base.evidenced_skills)} of {required} required skills. "
                f"{base.config_name} gives project evidence 0% weight; {alt.config_name}, which weights it at "
                f"{alt.weights['projects']:g}%, scores this candidate {alt.final_score - base.final_score:.0f} points higher.",
                "blind_spot",
            ))

        if spread["score_range"] >= HIGH_SENSITIVITY_POINTS:
            found.append(Observation(
                "HIGH_SENSITIVITY", "High score sensitivity",
                f"Scores range from {spread['min_score']:.0f}% ({spread['lowest_config']}) to "
                f"{spread['max_score']:.0f}% ({spread['highest_config']}) across {len(self.configs)} "
                f"configurations, a {spread['score_range']:.0f}-point spread. The result depends "
                f"substantially on the configuration chosen.",
                "sensitivity",
            ))

        if group_size >= MIN_GROUP_FOR_RANKING and abs(base_rank - alt_rank) >= RANK_SHIFT:
            found.append(Observation(
                "RANK_SHIFT", "Ranking changes with configuration",
                f"Ranked {ordinal(base_rank)} of {group_size} under {base.config_name} and "
                f"{ordinal(alt_rank)} under {alt.config_name}.",
                "ranking",
            ))

        if coverage >= UNBACKED_COVERAGE and base.project_score < UNBACKED_PROJECTS:
            found.append(Observation(
                "UNBACKED_SKILLS", "Listed skills without project evidence",
                f"Skill coverage of {coverage:.0f}% rests mostly on listed skills: "
                f"{len(base.evidenced_skills)} of {required} required skills appear in a described project.",
                "evidence",
            ))
        return found

    # --- the audit ------------------------------------------------------------------------------

    def run(self, manager: DataManager, job_id: str | None = None) -> AuditReport:
        pairs = analytics.screening_pairs(manager, job_id)
        scope = manager.jobs[job_id].title if job_id else "All roles"
        base_results = {c.candidate_id: self.baseline_engine.analyze(c, j) for c, j in pairs}
        alt_results = {c.candidate_id: self.alternative_engine.analyze(c, j) for c, j in pairs}

        if not pairs:
            return AuditReport(scope, job_id, self.baseline, self.alternative, self.configs,
                               pd.DataFrame(), {}, base_results, alt_results)

        table = pd.DataFrame([{
            "candidate_id": c.candidate_id,
            "name": c.name,
            "target_role": job.title,
            "experience_years": c.experience_years,
            "skill_coverage": base_results[c.candidate_id].skill_score,
            "project_evidence": base_results[c.candidate_id].project_score,
            "baseline_score": base_results[c.candidate_id].final_score,
            "alternative_score": alt_results[c.candidate_id].final_score,
        } for c, job in pairs])
        table["score_change"] = (table["alternative_score"] - table["baseline_score"]).round(1)

        # Ranks are within each role: candidates for different roles are never compared.
        table["baseline_rank"] = analytics.rank_within_groups(table, "baseline_score")
        table["alternative_rank"] = analytics.rank_within_groups(table, "alternative_score")
        table["rank_change"] = table["baseline_rank"] - table["alternative_rank"]   # + = moves up
        table["role_size"] = table.groupby("target_role")["candidate_id"].transform("count")

        spread = self.sensitivity.sensitivity_frame(pairs)
        table = table.merge(spread, on="candidate_id", how="left")

        # Competence audit: what the baseline's wording rules capture versus the evidence present.
        competence_engine = CompetenceAuditEngine(manager.taxonomy, self.baseline)
        competence = {r.candidate_id: r for r in competence_engine.assess_many(pairs)}
        competence_frame = CompetenceAuditEngine.frame(competence.values()).drop(
            columns=["name", "target_role", "baseline_score"])
        table = table.merge(competence_frame, on="candidate_id", how="left")

        observations: dict[str, list[Observation]] = {}
        for row in table.to_dict(orient="records"):
            cid = row["candidate_id"]
            observations[cid] = self.observe(
                base_results[cid], alt_results[cid], row,
                int(row["baseline_rank"]), int(row["alternative_rank"]), int(row["role_size"]),
            ) + list(competence[cid].observations)
        table["observation_count"] = table["candidate_id"].map(lambda cid: len(observations[cid]))
        table["blind_spot"] = table["candidate_id"].map(
            lambda cid: any(o.is_blind_spot for o in observations[cid])
        )
        table = table.sort_values(["target_role", "baseline_rank", "name"]).reset_index(drop=True)
        return AuditReport(scope, job_id, self.baseline, self.alternative, self.configs,
                           table, observations, base_results, alt_results, competence)
