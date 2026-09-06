"""
Local sentence-transformers wrapper. Lazy-imported to avoid blocking UI startup.
Provides embed_documents and embed_query methods to match the interface 
expected by rag_core/vector_store.py.
"""
from __future__ import annotations
import os
from functools import lru_cache

DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5")

class LocalEmbeddings:
    """Wrapper around sentence-transformers to provide the embed_documents/embed_query interface."""
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of documents (used during ingestion)."""
        # encode returns a numpy array; we convert to a standard Python list of lists for ChromaDB
        embeddings = self.model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query (used during retrieval)."""
        embedding = self.model.encode([text], show_progress_bar=False, convert_to_numpy=True)
        return embedding[0].tolist()

@lru_cache(maxsize=1)
def get_embedding_model() -> LocalEmbeddings:
    """Lazy-loads the embedding model. 
    Importing sentence_transformers at module level drags in torch and blocks startup."""
    return LocalEmbeddings(DEFAULT_MODEL)