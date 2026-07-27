"""
Repository ingestion pipeline (PRD FR-1, FR-2, FR-3):
  clone public repo -> walk files -> language-aware chunk -> embed locally -> store in Chroma
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable

from rag_core.chunking import (
    MAX_FILE_SIZE_BYTES,
    CodeChunk,
    chunk_file,
    should_ingest_file,
)
from rag_core.vector_store import VectorStore, repo_url_to_collection_name

ProgressCallback = Callable[[str], None]


def clone_repo(repo_url: str, dest_dir: str) -> None:
    """Shallow-clone a public repo. Raises RuntimeError with git's stderr on failure
    (e.g. private repo, bad URL — both explicitly out of scope per the PRD)."""
    result = subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, dest_dir],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr.strip()}")


def iter_ingestible_files(root_dir: str):
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, root_dir)
            if not should_ingest_file(rel_path):
                continue
            try:
                if os.path.getsize(full_path) > MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue
            yield full_path, rel_path


def build_chunks_for_repo(root_dir: str, progress: ProgressCallback | None = None) -> list[CodeChunk]:
    all_chunks: list[CodeChunk] = []
    file_count = 0
    for full_path, rel_path in iter_ingestible_files(root_dir):
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError:
            continue

        file_chunks = chunk_file(rel_path, content)
        all_chunks.extend(file_chunks)
        file_count += 1
        if progress and file_count % 25 == 0:
            progress(f"Chunked {file_count} files, {len(all_chunks)} chunks so far...")

    if progress:
        progress(f"Done chunking: {file_count} files -> {len(all_chunks)} chunks.")
    return all_chunks


def ingest_repository(repo_url: str, progress: ProgressCallback | None = None) -> dict:
    """
    Full pipeline: clone -> chunk -> embed -> persist to Chroma.
    Returns a summary dict (collection_name, file_count-ish stats, chunk_count).
    """

    def _log(msg: str):
        if progress:
            progress(msg)

    collection_name = repo_url_to_collection_name(repo_url)

    with tempfile.TemporaryDirectory() as tmp_dir:
        _log(f"Cloning {repo_url} ...")
        clone_repo(repo_url, tmp_dir)

        _log("Chunking repository (language-aware splitting)...")
        chunks = build_chunks_for_repo(tmp_dir, progress=_log)

        if not chunks:
            raise RuntimeError(
                "No ingestible files found. Check the repo URL and that it contains "
                "recognized source/doc file types."
            )

        _log(f"Embedding {len(chunks)} chunks locally (sentence-transformers)...")
        store = VectorStore()
        # Fresh ingest of this repo: drop any previous collection with the same slug
        if collection_name in store.list_collections():
            store.delete_collection(collection_name)
        added = store.add_chunks(collection_name, chunks)

        _log(f"Stored {added} chunks in ChromaDB collection '{collection_name}'.")

    return {
        "repo_url": repo_url,
        "collection_name": collection_name,
        "chunk_count": added,
    }
