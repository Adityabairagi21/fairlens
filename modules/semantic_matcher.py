"""Optional similarity-based hints: character-trigram TF-IDF + cosine similarity, in NumPy.

This is a *separate*, optional layer. It never changes a score, a status or a
coverage figure. It only suggests, for a required skill with no rule-based
evidence, the closest wording in the candidate's record, e.g. "Postgre SQL"
for "PostgreSQL" or "Restful service" for "REST APIs". A reviewer decides
whether the hint means anything.

Character trigrams measure *spelling* similarity, not meaning. That limit is
stated in the UI next to every hint. No external service or API key is used.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

import numpy as np

from modules.taxonomy import normalize

DEFAULT_THRESHOLD = 0.45


def trigrams(text: str) -> list[str]:
    padded = f"  {normalize(text)} "
    return [padded[i:i + 3] for i in range(len(padded) - 2)]


class SemanticMatcher:
    """TF-IDF over character trigrams; cosine similarity between short phrases."""

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.threshold = threshold

    @staticmethod
    def vectorize(texts: list[str]) -> np.ndarray:
        """Rows are L2-normalised TF-IDF vectors (smoothed idf, as in scikit-learn)."""
        counts = [Counter(trigrams(t)) for t in texts]
        vocabulary = {gram: i for i, gram in enumerate(sorted({g for c in counts for g in c}))}
        tf = np.zeros((len(texts), len(vocabulary)))
        for row, counter in enumerate(counts):
            for gram, n in counter.items():
                tf[row, vocabulary[gram]] = n
        df = np.count_nonzero(tf, axis=0)
        idf = np.log((1 + len(texts)) / (1 + df)) + 1
        weighted = tf * idf
        norms = np.linalg.norm(weighted, axis=1, keepdims=True)
        return np.divide(weighted, norms, out=np.zeros_like(weighted), where=norms > 0)

    def similarity(self, queries: list[str], terms: list[str]) -> np.ndarray:
        """Cosine similarity matrix, queries x terms."""
        if not queries or not terms:
            return np.zeros((len(queries), len(terms)))
        vectors = self.vectorize([*queries, *terms])
        return vectors[:len(queries)] @ vectors[len(queries):].T

    def suggest(self, required: Iterable[str], terms: Iterable[str]) -> list[tuple[str, str, float]]:
        """(required skill, closest wording, similarity) for each skill whose best match clears the threshold."""
        required, terms = list(required), list(dict.fromkeys(terms))
        matrix = self.similarity(required, terms)
        hints = []
        for i, skill in enumerate(required):
            if matrix.shape[1] == 0:
                break
            j = int(np.argmax(matrix[i]))
            if matrix[i, j] >= self.threshold and normalize(terms[j]) != normalize(skill):
                hints.append((skill, terms[j], round(float(matrix[i, j]), 2)))
        return hints
