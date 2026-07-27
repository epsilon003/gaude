"""
Language-aware chunking for source code and docs.

Uses LangChain's RecursiveCharacterTextSplitter.from_language(), which splits on
syntactic boundaries (function/class defs, etc.) rather than blindly cutting every
N characters. Falls back to a generic recursive splitter for unrecognized extensions.

Each chunk is tagged with file_path, start_line, and end_line so the citation
feature (FR-6) has real source locations to point to.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

# Map file extensions to LangChain's Language enum. Anything not listed here
# falls back to the generic text splitter.
EXTENSION_LANGUAGE_MAP: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".js": Language.JS,
    ".jsx": Language.JS,
    ".mjs": Language.JS,
    ".ts": Language.TS,
    ".tsx": Language.TS,
    ".java": Language.JAVA,
    ".go": Language.GO,
    ".rb": Language.RUBY,
    ".php": Language.PHP,
    ".cpp": Language.CPP,
    ".cc": Language.CPP,
    ".cxx": Language.CPP,
    ".c": Language.CPP,
    ".h": Language.CPP,
    ".hpp": Language.CPP,
    ".cs": Language.CSHARP,
    ".rs": Language.RUST,
    ".kt": Language.KOTLIN,
    ".kts": Language.KOTLIN,
    ".scala": Language.SCALA,
    ".swift": Language.SWIFT,
    ".md": Language.MARKDOWN,
    ".markdown": Language.MARKDOWN,
    ".rst": Language.RST,
    ".html": Language.HTML,
    ".htm": Language.HTML,
    ".sol": Language.SOL,
}

# Extensions we bother ingesting at all. Keeps binary junk, lockfiles, etc. out
# of the vector store.
INGESTIBLE_EXTENSIONS = set(EXTENSION_LANGUAGE_MAP.keys()) | {
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".sql",
    ".sh",
    ".toml",
    ".cfg",
    ".ini",
}

# Directories that are never worth ingesting.
IGNORED_DIR_NAMES = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "vendor",
    "target",
    ".idea",
    ".vscode",
    "coverage",
    ".pytest_cache",
}

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150
MAX_FILE_SIZE_BYTES = 500_000  # skip anything larger; almost certainly generated/binary


@dataclass
class CodeChunk:
    text: str
    file_path: str
    start_line: Optional[int]
    end_line: Optional[int]
    language: Optional[str] = None
    metadata: dict = field(default_factory=dict)


def should_ingest_file(path: str) -> bool:
    """Filter out directories we don't care about and non-text/oversized files."""
    parts = path.replace("\\", "/").split("/")
    if any(p in IGNORED_DIR_NAMES for p in parts):
        return False
    ext = os.path.splitext(path)[1].lower()
    if ext not in INGESTIBLE_EXTENSIONS:
        return False
    return True


def get_splitter_for_file(
    file_path: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> RecursiveCharacterTextSplitter:
    ext = os.path.splitext(file_path)[1].lower()
    lang = EXTENSION_LANGUAGE_MAP.get(ext)
    if lang is not None:
        return RecursiveCharacterTextSplitter.from_language(
            language=lang, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )


def chunk_file(
    file_path: str,
    content: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[CodeChunk]:
    """Split a single file's content into CodeChunks with resolved line numbers."""
    if not content.strip():
        return []

    splitter = get_splitter_for_file(file_path, chunk_size, chunk_overlap)
    raw_chunks = splitter.split_text(content)

    ext = os.path.splitext(file_path)[1].lower()
    lang = EXTENSION_LANGUAGE_MAP.get(ext)
    lang_name = lang.value if lang is not None else "text"

    results: list[CodeChunk] = []
    search_from = 0
    for chunk_text in raw_chunks:
        idx = content.find(chunk_text, search_from)
        if idx == -1:
            # Overlap can make forward-only search miss; fall back to a full search.
            idx = content.find(chunk_text)

        if idx == -1:
            start_line, end_line = None, None
        else:
            start_line = content.count("\n", 0, idx) + 1
            end_line = start_line + chunk_text.count("\n")
            # Advance search cursor conservatively so overlapping chunks are still found,
            # but we don't re-match the exact same span repeatedly.
            search_from = idx + max(1, len(chunk_text) - chunk_overlap)

        results.append(
            CodeChunk(
                text=chunk_text,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                language=lang_name,
            )
        )
    return results
