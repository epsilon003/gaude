"""
ChromaDB wrapper: local, embedded, persisted-to-disk vector store. No API/cost.

One Chroma collection per ingested repo (collection name derived from the repo
slug) so re-ingesting a different repo doesn't clobber a previous one, and the
PRD's "single repo at a time for MVP" scope still leaves room to browse repos
you've already ingested.
"""
from __future__ import annotations

import re
from functools import lru_cache
import chromadb
from chromadb.config import Settings

from rag_core.embeddings import get_embedding_model

PERSIST_DIR = "vector_store"


def repo_url_to_collection_name(repo_url: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", repo_url.rstrip("/")).strip("-").lower()
    slug = slug[-63:] if len(slug) > 63 else slug  # Chroma collection name limit
    return slug or "default-collection"

def _repo_display_name(repo_url: str) -> str:
    """'https://github.com/owner/repo' -> 'owner/repo', for nicer sidebar display."""
    parts = repo_url.rstrip("/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return repo_url

class VectorStore:
    def __init__(self, persist_dir: str = PERSIST_DIR):
        self.client = chromadb.PersistentClient(
            path=persist_dir, settings=Settings(anonymized_telemetry=False)
        )

    def get_or_create_collection(self, name: str, source_url: str | None = None):
        metadata = {"hnsw:space": "cosine"}
        if source_url:
            metadata["source_url"] = source_url
        return self.client.get_or_create_collection(name=name, metadata=metadata)

    def list_collections(self) -> list[str]:
        return [c.name for c in self.client.list_collections()]

    def list_collections_with_info(self) -> list[dict]:
        """Display-friendly info per collection: name, original repo URL (if we
        have it), and a live chunk count."""
        infos = []
        for c in self.client.list_collections():
            collection = self.client.get_collection(name=c.name)
            source_url = (collection.metadata or {}).get("source_url")
            infos.append(
                {
                    "name": c.name,
                    "source_url": source_url,
                    "display_name": _repo_display_name(source_url) if source_url else c.name,
                    "chunk_count": collection.count(),
                }
            )
        return infos

    def delete_collection(self, name: str) -> None:
        self.client.delete_collection(name=name)

    def add_chunks(self, collection_name: str, chunks: list, source_url: str | None = None, batch_size: int = 64) -> int:
        """chunks: list of rag_core.chunking.CodeChunk"""
        collection = self.get_or_create_collection(collection_name, source_url=source_url)
        embedder = get_embedding_model()

        total_added = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.text for c in batch]
            embeddings = embedder.embed_documents(texts)
            ids = [f"{collection_name}-{i + j}" for j in range(len(batch))]
            metadatas = [
                {
                    "file_path": c.file_path,
                    "start_line": c.start_line if c.start_line is not None else -1,
                    "end_line": c.end_line if c.end_line is not None else -1,
                    "language": c.language or "text",
                }
                for c in batch
            ]
            collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
            total_added += len(batch)
        return total_added

    def query(self, collection_name: str, query_text: str, top_k: int = 15) -> list[dict]:
        collection = self.get_or_create_collection(collection_name)
        embedder = get_embedding_model()
        query_embedding = embedder.embed_query(query_text)

        results = collection.query(query_embeddings=[query_embedding], n_results=top_k)
        if not results["ids"] or not results["ids"][0]:
            return []

        out = []
        for doc, meta, dist in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        ):
            out.append(
                {
                    "text": doc,
                    "file_path": meta.get("file_path"),
                    "start_line": meta.get("start_line"),
                    "end_line": meta.get("end_line"),
                    "language": meta.get("language"),
                    "vector_distance": dist,
                }
            )
        return out
@lru_cache(maxsize=1)
def get_vector_store(persist_dir: str = PERSIST_DIR) -> VectorStore:
    """Process-level singleton. chromadb.PersistentClient() has a real one-time
    warmup cost (internal lazy imports, on-disk manifest reads) — this ensures
    that cost is paid once per process instead of on every question asked /
    every Streamlit script rerun."""
    return VectorStore(persist_dir)
