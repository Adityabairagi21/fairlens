"""Score sensitivity and scenario simulation.

Sensitivity: the same candidate is scored under every saved configuration.
If the score moves a lot, the result depends heavily on which legitimate
configuration was chosen. That is a property of the *evaluation*, not a
judgement about the candidate.

Scenarios: a copy of the candidate is edited (one more year of experience,
one more skill) and re-scored with the real ``ScreeningEngine``. These are
simulations of the scoring rules, not predictions about the person.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from modules.candidate import Candidate
from modules.job import JobRole
from modules.screening_engine import ScreeningConfig, ScreeningEngine, ScreeningResult

# A spread of this many points or more between the lowest and highest
# configuration score is reported as high sensitivity.
HIGH_SENSITIVITY_POINTS = 20.0


@dataclass(frozen=True)
class Scenario:
    """One simulated change and the score the engine gives it."""

    label: str
    score: float
    baseline: float
    result: ScreeningResult

    @property
    def change(self) -> float:
        return round(self.score - self.baseline, 1)


class SensitivityAnalyzer:
    """Re-scores candidates under several configurations and simulated changes."""

    def __init__(self, configs: Sequence[ScreeningConfig]):
        if len(configs) < 2:
            raise ValueError("Sensitivity analysis needs at least two configurations.")
        self.configs = tuple(configs)
        self.engines = {c.config_id: ScreeningEngine(c) for c in self.configs}

    # --- sensitivity across configurations -------------------------------------------------

    def scores_for(self, candidate: Candidate, job: JobRole) -> dict[str, float]:
        """config_id -> final score for one candidate."""
        return {cid: engine.analyze(candidate, job).final_score for cid, engine in self.engines.items()}

    def score_matrix(self, pairs: Iterable[tuple[Candidate, JobRole]]) -> pd.DataFrame:
        """Rows are candidates, columns are configuration IDs, cells are scores."""
        rows = {candidate.candidate_id: self.scores_for(candidate, job) for candidate, job in pairs}
        return pd.DataFrame.from_dict(rows, orient="index", columns=list(self.engines))

    def sensitivity_frame(self, pairs: Iterable[tuple[Candidate, JobRole]]) -> pd.DataFrame:
        """Per-candidate spread statistics computed with NumPy over the score matrix."""
        matrix = self.score_matrix(pairs)
        if matrix.empty:
            return pd.DataFrame(columns=["candidate_id", "min_score", "max_score", "score_range",
                                         "score_std", "lowest_config", "highest_config", "high_sensitivity"])
        values = matrix.to_numpy(dtype=float)
        config_ids = np.asarray(matrix.columns)
        names = {c.config_id: c.name for c in self.configs}
        frame = pd.DataFrame({
            "candidate_id": matrix.index,
            "min_score": values.min(axis=1),
            "max_score": values.max(axis=1),
            "score_range": np.ptp(values, axis=1),          # max - min per row
            "score_std": values.std(axis=1),
            "lowest_config": [names[c] for c in config_ids[values.argmin(axis=1)]],
            "highest_config": [names[c] for c in config_ids[values.argmax(axis=1)]],
        })
        frame["score_range"] = frame["score_range"].round(1)
        frame["score_std"] = frame["score_std"].round(1)
        frame["high_sensitivity"] = frame["score_range"] >= HIGH_SENSITIVITY_POINTS
        # Keep the per-configuration scores next to the statistics.
        return frame.join(matrix.reset_index(drop=True))

    # --- scenario simulation ------------------------------------------------------------------

    @staticmethod
    def simulate(engine: ScreeningEngine, candidate: Candidate, job: JobRole, label: str,
                 **changes: Any) -> Scenario:
        """Score an edited copy of the candidate. The stored record is never touched.

        The copy goes through ``Candidate.from_dict``, so a simulated value is
        validated exactly like a real one (e.g. negative experience is rejected).
        """
        current = engine.analyze(candidate, job).final_score
        edited = Candidate.from_dict({**candidate.to_dict(), **changes})
        result = engine.analyze(edited, job)
        return Scenario(label=label, score=result.final_score, baseline=current, result=result)

    def experience_scenarios(self, engine: ScreeningEngine, candidate: Candidate, job: JobRole,
                             extra_years: Iterable[float] = (1, 2, 3)) -> list[Scenario]:
        return [
            self.simulate(engine, candidate, job, f"Experience {candidate.experience_years + y:g} yrs",
                          experience_years=candidate.experience_years + y)
            for y in extra_years
        ]

    def skill_scenarios(self, engine: ScreeningEngine, candidate: Candidate, job: JobRole) -> list[Scenario]:
        """One scenario per missing required skill, largest change first."""
        missing = engine.analyze(candidate, job).missing_skills
        scenarios = [
            self.simulate(engine, candidate, job, f"Add {skill}", skills=[*candidate.skills, skill])
            for skill in missing
        ]
        return sorted(scenarios, key=lambda s: s.change, reverse=True)

    @staticmethod
    def experience_curve(engine: ScreeningEngine, candidate: Candidate, job: JobRole,
                         max_years: float | None = None, step: float = 0.5) -> pd.DataFrame:
        """Projected score at each experience value from 0 to ``max_years`` (NumPy arange)."""
        top = max_years if max_years is not None else max(job.min_experience + 2, candidate.experience_years + 1, 4)
        years = np.round(np.arange(0, top + step / 2, step), 1)
        base = candidate.to_dict()
        scores = [engine.analyze(Candidate.from_dict({**base, "experience_years": float(y)}), job).final_score
                  for y in years]
        return pd.DataFrame({"experience_years": years, "score": scores})
