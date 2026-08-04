"""
Local cross-encoder reranking.

Vector similarity search gets you "semantically close" candidates fast, but cross-encoders score (query, chunk) pairs jointly and are meaningfully better at judging actual relevance. We over-fetch from the vector store (top_k_retrieve) and rerank down to a smaller, higher-precision set (top_k_final) before it goes into the LLM prompt. Fully local, no API cost.
"""
from __future__ import annotations

import os
from functools import lru_cache

DEFAULT_RERANKER_MODEL = os.environ.get(
    "RERANKER_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2"
)


class Reranker:
    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL):
        from sentence_transformers import CrossEncoder 
        self.model = CrossEncoder(model_name)

    def score(self, query: str, candidates: list[dict]) -> list[dict]:
        """
        Scores every candidate (adds a "rerank_score" field) and returns them
        sorted descending by relevance — no slicing. Exposed separately from
        rerank() so callers that need the full pool (e.g. for a relative
        confidence signal — see retrieval.py's _compute_confidence) aren't
        stuck with only the top_k that rerank() would have kept.
        """
        if not candidates:
            return []

        pairs = [(query, c["text"]) for c in candidates]
        scores = self.model.predict(pairs)

        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)

        candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
        return candidates

    def rerank(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        """
        candidates: list of dicts each containing at least a "text" key.
        Returns the top_k candidates sorted by cross-encoder relevance score,
        with a "rerank_score" field added.
        """
        return self.score(query, candidates)[:top_k]


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    return Reranker()
