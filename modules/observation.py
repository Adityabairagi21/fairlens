"""The Observation record shared by the screening audit and the competence audit."""

from __future__ import annotations

from dataclasses import dataclass

# Observations of these kinds make a candidate a "potential blind spot" in the screening audit.
BLIND_SPOT_CODES: frozenset[str] = frozenset({"HIGH_EVIDENCE_LOW_BASELINE", "SINGLE_CRITERION", "UNCREDITED_PROJECTS"})


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


@dataclass(frozen=True)
class Observation:
    """One neutral, rule-based finding about how a candidate was scored."""

    code: str
    title: str
    text: str
    kind: str   # "blind_spot", "sensitivity", "ranking", "evidence" or "competence"

    @property
    def is_blind_spot(self) -> bool:
        return self.code in BLIND_SPOT_CODES
