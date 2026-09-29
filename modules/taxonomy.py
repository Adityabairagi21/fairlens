"""Skill taxonomy: synonyms and related terms, loaded from data/skills_taxonomy.json.

The taxonomy turns different wordings of one skill into one *concept*:

    "Python", "python programming", "Python 3"   -> concept "python"   (synonyms)
    "PostgreSQL", "MySQL"                        -> related evidence for "sql"

It is plain data, deliberately small, and meant to be extended by editing
the JSON. It is not a language model: a wording the taxonomy does not list
is simply not recognised.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from modules import file_handler, validator
from modules.exceptions import DataFileError

# How a candidate's wording relates to a required skill, strongest first.
MATCH_KINDS: tuple[str, ...] = ("exact", "synonym", "related")

# Terms this short ("ml", "tf", "js") are fine as a listed skill but too ambiguous
# to look for inside free text, so text search skips them.
MIN_TEXT_TERM_LENGTH = 3


def normalize(text: object) -> str:
    """Case-folded, single-spaced, trimmed of surrounding punctuation: ' Scikit-Learn. ' -> 'scikit-learn'."""
    return " ".join(str(text or "").casefold().split()).strip(" .,;:()")


@dataclass(frozen=True)
class TermMatch:
    """How one piece of candidate wording relates to one required skill."""

    kind: str          # "exact", "synonym" or "related"
    term: str          # the candidate's own wording
    concept: str       # the required skill's concept label


class SkillTaxonomy:
    """Concepts with synonym terms and one-directional related terms.

    ``entries`` maps a concept id to {"label": str, "terms": [...], "related": [...]}.
    Validation errors are collected and raised together as ``DataFileError``
    so a broken taxonomy file produces one readable message.
    """

    def __init__(self, entries: Mapping[str, Any] | None = None):
        self._labels: dict[str, str] = {}
        self._terms: dict[str, tuple[str, ...]] = {}
        self._term_index: dict[str, str] = {}          # normalised term -> concept id
        raw_related: dict[str, list[str]] = {}
        problems: list[str] = []

        for concept_id, entry in (entries or {}).items():
            if not isinstance(entry, Mapping):
                problems.append(f"'{concept_id}' must be an object")
                continue
            label = " ".join(str(entry.get("label", "")).split())
            terms = entry.get("terms")
            if not label:
                problems.append(f"'{concept_id}' has no label")
                continue
            if not isinstance(terms, list) or not all(isinstance(t, str) and t.strip() for t in terms):
                problems.append(f"'{concept_id}' needs a list of non-empty 'terms'")
                continue
            normalised = tuple(dict.fromkeys([normalize(label), *map(normalize, terms)]))
            for term in normalised:
                owner = self._term_index.get(term)
                if owner and owner != concept_id:
                    problems.append(f"term '{term}' is listed under both '{owner}' and '{concept_id}'")
                self._term_index[term] = concept_id
            self._labels[concept_id] = label
            self._terms[concept_id] = normalised
            related = entry.get("related", [])
            if not isinstance(related, list):
                problems.append(f"'{concept_id}' related must be a list")
                continue
            raw_related[concept_id] = [normalize(r) for r in related if str(r).strip()]

        if problems:
            raise DataFileError("The skills taxonomy has problems: " + "; ".join(problems[:5]) + ".")

        # Spelling aliases used elsewhere in the app ("sklearn", "js") are synonyms here
        # too, so the taxonomy never disagrees with the rest of the product.
        for alias, target in validator.SKILL_ALIASES.items():
            concept = self._term_index.get(target)
            if concept and alias not in self._term_index:
                self._term_index[alias] = concept
                self._terms[concept] = (*self._terms[concept], alias)

        # A related entry may name a concept id or any term; unknown terms become their own concept.
        self._related: dict[str, frozenset[str]] = {
            cid: frozenset(self.concept_of(r) for r in related) for cid, related in raw_related.items()
        }

    # --- loading -----------------------------------------------------------------------------------

    @classmethod
    def from_file(cls, path: Path) -> "SkillTaxonomy":
        raw = file_handler.load_json(Path(path))       # DataFileError if missing/malformed
        if not isinstance(raw, Mapping) or not isinstance(raw.get("skills"), Mapping):
            raise DataFileError(f"{Path(path).name} must contain a 'skills' object.")
        return cls(raw["skills"])

    # --- lookups ---------------------------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._labels)

    def concept_of(self, term: str) -> str:
        """Concept id for a wording; an unknown wording is its own concept."""
        key = normalize(term)
        return self._term_index.get(key) or self._term_index.get(validator.skill_key(key)) or f"raw:{key}"

    def label(self, concept: str) -> str:
        return self._labels.get(concept, concept.removeprefix("raw:"))

    def terms(self, concept: str) -> tuple[str, ...]:
        return self._terms.get(concept, (concept.removeprefix("raw:"),))

    def related(self, concept: str) -> frozenset[str]:
        return self._related.get(concept, frozenset())

    def is_known(self, term: str) -> bool:
        return not self.concept_of(term).startswith("raw:")

    # --- matching ------------------------------------------------------------------------------------

    def compare(self, required: str, offered: str) -> str | None:
        """'exact', 'synonym', 'related' or None for one required skill vs one candidate wording."""
        if normalize(required) == normalize(offered):
            return "exact"
        want, have = self.concept_of(required), self.concept_of(offered)
        if want == have:
            return "synonym"
        if have in self.related(want):
            return "related"
        return None

    def best_match(self, required: str, offered: Iterable[str]) -> TermMatch | None:
        """The strongest match among many candidate wordings (exact beats synonym beats related)."""
        best: TermMatch | None = None
        for term in offered:
            kind = self.compare(required, term)
            if kind and (best is None or MATCH_KINDS.index(kind) < MATCH_KINDS.index(best.kind)):
                best = TermMatch(kind, term, self.label(self.concept_of(required)))
        return best

    def find_in_text(self, required: str, text: str) -> TermMatch | None:
        """Look for the required skill (its synonyms, then related terms) inside free text."""
        haystack = normalize(text)
        if not haystack:
            return None
        concept = self.concept_of(required)
        groups = [("synonym", self.terms(concept))]
        groups += [("related", self.terms(r)) for r in sorted(self.related(concept))]
        for kind, terms in groups:
            for term in sorted(terms, key=len, reverse=True):          # longest wording first
                if len(term) < MIN_TEXT_TERM_LENGTH:
                    continue
                if re.search(rf"(?<![\w+#]){re.escape(term)}(?![\w+#])", haystack):
                    return TermMatch(kind, term, self.label(concept))
        return None

    def to_frame(self) -> pd.DataFrame:
        """The taxonomy as a table for display."""
        return pd.DataFrame([{
            "concept": self._labels[cid],
            "synonyms": ", ".join(t for t in self._terms[cid] if t != normalize(self._labels[cid])),
            "related": ", ".join(sorted(self.label(r) for r in self.related(cid))),
        } for cid in self._labels])
