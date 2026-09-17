"""
Repository ingestion pipeline with incremental update support.
"""
from __future__ import annotations
import os
import json
import subprocess
import tempfile
from collections.abc import Callable
from rag_core.chunking import MAX_FILE_SIZE_BYTES, CodeChunk, chunk_file, should_ingest_file
from rag_core.vector_store import get_vector_store, repo_url_to_collection_name

ProgressCallback = Callable[[str], None]

def clone_repo(repo_url: str, dest_dir: str) -> None:
    result = subprocess.run(["git", "clone", "--depth", "1", repo_url, dest_dir], capture_output=True, text=True, timeout=300)
    if result.returncode != 0: raise RuntimeError(f"git clone failed: {result.stderr.strip()}")

def get_commit_sha(repo_dir: str) -> str | None:
    result = subprocess.run(["git", "-C", repo_dir, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30)
    return result.stdout.strip() or None if result.returncode == 0 else None

def iter_ingestible_files(root_dir: str):
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, root_dir).replace(os.sep, "/")
            if not should_ingest_file(rel_path): continue
            try:
                if os.path.getsize(full_path) > MAX_FILE_SIZE_BYTES: continue
            except OSError: continue
            yield full_path, rel_path

def build_chunks_for_repo(root_dir: str, progress: ProgressCallback | None = None) -> list[CodeChunk]:
    all_chunks: list[CodeChunk] = []
    file_count = 0
    for full_path, rel_path in iter_ingestible_files(root_dir):
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f: content = f.read()
        except OSError: continue
        all_chunks.extend(chunk_file(rel_path, content))
        file_count += 1
        if progress and file_count % 25 == 0: progress(f"Chunked {file_count} files, {len(all_chunks)} chunks so far...")
    if progress: progress(f"Done chunking: {file_count} files -> {len(all_chunks)} chunks.")
    return all_chunks

def ingest_repository(repo_url: str, progress: ProgressCallback | None = None) -> dict:
    def _log(msg: str):
        if progress: progress(msg)

    collection_name = repo_url_to_collection_name(repo_url)
    store = get_vector_store()
    persist_dir = "vector_store"
    os.makedirs(persist_dir, exist_ok=True)
    repo_meta_file = os.path.join(persist_dir, f"{collection_name}_meta.json")

    with tempfile.TemporaryDirectory() as tmp_dir:
        _log(f"Cloning {repo_url} ...")
        clone_repo(repo_url, tmp_dir)
        commit_sha = get_commit_sha(tmp_dir)

        # Incremental check: Skip if we already ingested this exact commit
        if os.path.exists(repo_meta_file):
            with open(repo_meta_file, "r") as f: old_meta = json.load(f)
            if old_meta.get("commit_sha") == commit_sha:
                _log(f"Repo already ingested at commit {commit_sha}. Skipping.")
                return {"repo_url": repo_url, "collection_name": collection_name, "chunk_count": old_meta["chunk_count"], "status": "skipped"}

        _log("Chunking repository (AST-aware where possible)...")
        chunks = build_chunks_for_repo(tmp_dir, progress=_log)
        if not chunks: raise RuntimeError("No ingestible files found.")

        _log(f"Embedding {len(chunks)} chunks locally...")
        if collection_name in [c.name for c in store.client.list_collections()]:
            _log("Updating existing collection (full rebuild for safety)...")
            store.client.delete_collection(collection_name)

        added = store.add_chunks(collection_name, chunks, source_url=repo_url, commit_sha=commit_sha)
        
        with open(repo_meta_file, "w") as f: json.dump({"commit_sha": commit_sha, "chunk_count": added}, f)

        _log(f"Stored {added} chunks in ChromaDB collection '{collection_name}'.")
        return {"repo_url": repo_url, "collection_name": collection_name, "chunk_count": added, "status": "success"}