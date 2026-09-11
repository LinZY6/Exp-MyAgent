"""Tiny BM25 (no extra dependency)."""

from __future__ import annotations

import math
from typing import Sequence

from expmem.node import tokenize


class BM25:
    def __init__(self, docs: Sequence[str], *, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = [tokenize(d) for d in docs]
        self.n = len(self.docs)
        self.avgdl = (sum(len(d) for d in self.docs) / self.n) if self.n else 0.0
        df: dict[str, int] = {}
        for doc in self.docs:
            for tok in set(doc):
                df[tok] = df.get(tok, 0) + 1
        self.idf = {
            t: math.log((self.n - c + 0.5) / (c + 0.5) + 1.0) for t, c in df.items()
        }

    def score(self, query: str) -> list[float]:
        q = tokenize(query)
        if not q or not self.docs:
            return [0.0] * self.n
        scores: list[float] = []
        for doc in self.docs:
            dl = len(doc) or 1
            tf: dict[str, int] = {}
            for t in doc:
                tf[t] = tf.get(t, 0) + 1
            s = 0.0
            for t in q:
                if t not in tf:
                    continue
                idf = self.idf.get(t, 0.0)
                freq = tf[t]
                s += idf * (freq * (self.k1 + 1)) / (
                    freq + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                )
            scores.append(s)
        return scores
