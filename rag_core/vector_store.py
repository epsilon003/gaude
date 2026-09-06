"""
ChromaDB wrapper with Hybrid Search (BM25 + Vector), Metadata Filtering, 
and Collection Info listing.
"""
from __future__ import annotations
import re
import os
import pickle
from functools import lru_cache
import chromadb
from chromadb.config import Settings
from rag_core.embeddings import get_embedding_model

PERSIST_DIR = "vector_store"

def repo_url_to_collection_name(repo_url: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", repo_url.rstrip("/")).strip("-").lower()
    slug = slug[-63:] if len(slug) > 63 else slug
    return slug or "default-collection"

class VectorStore:
    def __init__(self, persist_dir: str = PERSIST_DIR):
        self.client = chromadb.PersistentClient(
            path=persist_dir, 
            settings=Settings(anonymized_telemetry=False)
        )
        self._bm25_cache = {}

    def get_or_create_collection(self, collection_name: str, source_url: str | None = None, commit_sha: str | None = None):
        if collection_name in [c.name for c in self.client.list_collections()]:
            return self.client.get_collection(collection_name)
        return self.client.create_collection(
            name=collection_name, 
            metadata={"source_url": source_url, "commit_sha": commit_sha}
        )

    def add_chunks(self, collection_name: str, chunks: list, source_url: str | None = None, commit_sha: str | None = None, batch_size: int = 64) -> int:
        collection = self.get_or_create_collection(collection_name, source_url=source_url, commit_sha=commit_sha)
        embedder = get_embedding_model()
        total_added = 0
        all_texts = []
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i+batch_size]
            texts = [c.text for c in batch]
            embeddings = embedder.embed_documents(texts)
            ids = [f"{collection_name}-{i+j}" for j in range(len(batch))]
            metadatas = [{
                "file_path": c.file_path,
                "start_line": c.start_line if c.start_line is not None else -1,
                "end_line": c.end_line if c.end_line is not None else -1,
                "language": c.language or "text",
            } for c in batch]
            
            collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
            total_added += len(batch)
            all_texts.extend(texts)
            
        self._build_bm25_index(collection_name, all_texts)
        return total_added

    def _build_bm25_index(self, collection_name: str, texts: list[str]):
        from rank_bm25 import BM25Okapi
        tokenized = [re.findall(r'\w+', text.lower()) for text in texts]
        self._bm25_cache[collection_name] = BM25Okapi(tokenized)
        
        os.makedirs(PERSIST_DIR, exist_ok=True)
        cache_path = os.path.join(PERSIST_DIR, f"{collection_name}_bm25.pkl")
        with open(cache_path, "wb") as f:
            pickle.dump(self._bm25_cache[collection_name], f)

    def _load_bm25_index(self, collection_name: str):
        if collection_name in self._bm25_cache:
            return self._bm25_cache[collection_name]
        cache_path = os.path.join(PERSIST_DIR, f"{collection_name}_bm25.pkl")
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                self._bm25_cache[collection_name] = pickle.load(f)
                return self._bm25_cache[collection_name]
        return None

    def delete_by_file_path(self, collection_name: str, file_path: str) -> int:
        """Delete all chunks for a specific file (for incremental ingestion)."""
        collection = self.get_or_create_collection(collection_name)
        res = collection.delete(where={"file_path": file_path})
        if collection_name in self._bm25_cache: 
            del self._bm25_cache[collection_name]
        cache_path = os.path.join(PERSIST_DIR, f"{collection_name}_bm25.pkl")
        if os.path.exists(cache_path): 
            os.remove(cache_path)
        return len(res.get("ids", [])) if res else 0

    def list_collections_with_info(self) -> list[dict]:
        """List all collections with basic info for the UI."""
        collections = self.client.list_collections()
        result = []
        for c in collections:
            meta = c.metadata or {}
            chunk_count = 0
            try:
                # ChromaDB collections have a count() method
                chunk_count = c.count()
            except Exception:
                pass
            
            result.append({
                "collection_name": c.name,
                "source_url": meta.get("source_url", "Unknown"),
                "commit_sha": meta.get("commit_sha", "Unknown"),
                "chunk_count": chunk_count
            })
        result.sort(key=lambda x: x["collection_name"])
        return result

    def query(self, collection_name: str, query_text: str, top_k: int = 15, where_filter: dict | None = None, use_hybrid: bool = True) -> list[dict]:
        collection = self.get_or_create_collection(collection_name)
        embedder = get_embedding_model()
        query_embedding = embedder.embed_query(query_text)
        
        query_kwargs = {"query_embeddings": [query_embedding], "n_results": top_k * 2 if use_hybrid else top_k}
        if where_filter: 
            query_kwargs["where"] = where_filter

        vec_results = collection.query(**query_kwargs)
        if not vec_results["ids"] or not vec_results["ids"][0]: 
            return []

        if use_hybrid:
            bm25_index = self._load_bm25_index(collection_name)
            if bm25_index is None:
                all_docs = collection.get()["documents"]
                self._build_bm25_index(collection_name, all_docs)
                bm25_index = self._bm25_cache[collection_name]
                
            query_tokens = re.findall(r'\w+', query_text.lower())
            
            # Fetch all docs to map BM25 scores
            all_data = collection.get(include=["documents", "metadatas"])
            all_ids, all_texts, all_metas = all_data["ids"], all_data["documents"], all_data["metadatas"]
            
            if where_filter:
                all_ids, all_texts, all_metas = self._apply_python_filter(all_ids, all_texts, all_metas, where_filter)
                
            bm25_scores = bm25_index.get_scores(query_tokens)
            
            # Reciprocal Rank Fusion (RRF)
            vec_scores = {doc_id: 1.0 / (1.0 + dist) for doc_id, dist in zip(vec_results["ids"][0], vec_results["distances"][0])}
            bm25_scores_dict = {doc_id: bm25_scores[i] for i, doc_id in enumerate(all_ids)}
            
            k = 60
            rrf_scores = {}
            vec_ranked = sorted(vec_scores.items(), key=lambda x: x[1], reverse=True)
            bm25_ranked = sorted(bm25_scores_dict.items(), key=lambda x: x[1], reverse=True)
            
            for rank, (doc_id, _) in enumerate(vec_ranked):
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
            for rank, (doc_id, _) in enumerate(bm25_ranked):
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
                
            top_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:top_k]
            
            out = []
            id_to_data = {doc_id: (text, meta) for doc_id, text, meta in zip(all_ids, all_texts, all_metas)}
            for doc_id in top_ids:
                if doc_id in id_to_data:
                    text, meta = id_to_data[doc_id]
                    out.append({
                        "text": text, 
                        "file_path": meta.get("file_path"),
                        "start_line": meta.get("start_line"), 
                        "end_line": meta.get("end_line"),
                        "language": meta.get("language"), 
                        "rrf_score": rrf_scores[doc_id],
                    })
            return out

        # Fallback to pure vector search
        out = []
        for doc, meta, dist in zip(vec_results["documents"][0], vec_results["metadatas"][0], vec_results["distances"][0]):
            out.append({
                "text": doc, 
                "file_path": meta.get("file_path"),
                "start_line": meta.get("start_line"), 
                "end_line": meta.get("end_line"),
                "language": meta.get("language"), 
                "vector_distance": dist,
            })
        return out

    def _apply_python_filter(self, ids, texts, metas, where_filter):
        filtered_ids, filtered_texts, filtered_metas = [], [], []
        for i, meta in enumerate(metas):
            match = True
            for key, condition in where_filter.items():
                if isinstance(condition, dict):
                    for op, val in condition.items():
                        meta_val = meta.get(key)
                        if op == "$eq" and meta_val != val: match = False
                        elif op == "$ne" and meta_val == val: match = False
                        elif op == "$in" and meta_val not in val: match = False
                        elif op == "$contains" and val not in str(meta_val): match = False
                        elif op == "$not_contains" and val in str(meta_val): match = False
                else:
                    if meta.get(key) != condition: match = False
            if match:
                filtered_ids.append(ids[i])
                filtered_texts.append(texts[i])
                filtered_metas.append(metas[i])
        return filtered_ids, filtered_texts, filtered_metas

@lru_cache(maxsize=1)
def get_vector_store(persist_dir: str = PERSIST_DIR) -> VectorStore:
    return VectorStore(persist_dir)