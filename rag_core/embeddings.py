"""
Local embeddings via sentence-transformers. No API calls, no cost, no rate limits.

Default model (BAAI/bge-small-en-v1.5) is a good general-purpose retrieval model
that also handles code reasonably well and runs fine on CPU for MVP-sized repos.
Swap EMBEDDING_MODEL_NAME in .env if you want to try a code-specialized model
(e.g. "jinaai/jina-embeddings-v2-base-code").
"""
from __future__ import annotations

import os
from functools import lru_cache

from sentence_transformers import SentenceTransformer

DEFAULT_MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5")


class EmbeddingModel:
    def __init__(self, model_name: str = DEFAULT_MODEL_NAME):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 50,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        vector = self.model.encode([text], normalize_embeddings=True, show_progress_bar=False)
        return vector[0].tolist()


@lru_cache(maxsize=1)
def get_embedding_model() -> EmbeddingModel:
    """Singleton so we don't reload the model weights on every call."""
    return EmbeddingModel()
