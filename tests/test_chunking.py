"""
Tests for rag_core/chunking.py.

The two things most worth guarding here: (1) should_ingest_file's filtering,
since a regression could either bloat the index with junk (lockfiles,
node_modules) or silently drop real source files; and (2) line-number
resolution in chunk_file, since a citation with the wrong start/end line is
worse than no citation at all -- it actively misleads whoever clicks it.
"""
from rag_core.chunking import CodeChunk, chunk_file, should_ingest_file


class TestShouldIngestFile:
    def test_accepts_known_source_extensions(self):
        assert should_ingest_file("rag_core/chunking.py") is True
        assert should_ingest_file("frontend/app/page.tsx") is True
        assert should_ingest_file("README.md") is True

    def test_rejects_unknown_extensions(self):
        assert should_ingest_file("model.bin") is False
        assert should_ingest_file("photo.png") is False
        assert should_ingest_file("no_extension") is False

    def test_rejects_ignored_directories(self):
        assert should_ingest_file("node_modules/react/index.js") is False
        assert should_ingest_file("frontend/.next/server/page.js") is False
        assert should_ingest_file("venv/lib/python3.11/site.py") is False
        assert should_ingest_file(".git/config") is False

    def test_rejects_lockfiles_even_with_ingestible_extension(self):
        # package-lock.json ends in .json, which is otherwise ingestible --
        # the filename-based exclusion has to run regardless of extension.
        assert should_ingest_file("package-lock.json") is False
        assert should_ingest_file("frontend/package-lock.json") is False
        assert should_ingest_file("Cargo.lock") is False

    def test_handles_windows_style_paths(self):
        assert should_ingest_file("node_modules\\react\\index.js") is False
        assert should_ingest_file("rag_core\\chunking.py") is True


class TestChunkFileLineNumbers:
    def test_empty_content_returns_no_chunks(self):
        assert chunk_file("empty.py", "") == []
        assert chunk_file("whitespace.py", "   \n  \n") == []

    def test_single_small_file_line_numbers_are_1_indexed_and_span_content(self):
        content = "def foo():\n    return 1\n"
        chunks = chunk_file("small.py", content)
        assert len(chunks) >= 1
        first = chunks[0]
        assert isinstance(first, CodeChunk)
        assert first.start_line == 1
        # end_line should never be before start_line
        assert first.end_line >= first.start_line

    def test_line_numbers_match_actual_content_position(self):
        # Pad with filler lines so the real content doesn't start at line 1 --
        # this is the case that would catch an off-by-N bug in the line
        # counting, which content starting at line 1 would mask.
        filler = "\n".join(f"# filler line {i}" for i in range(20))
        target = "def target_function():\n    return 42\n"
        content = filler + "\n" + target

        chunks = chunk_file("padded.py", content)
        target_chunks = [c for c in chunks if "target_function" in c.text]
        assert target_chunks, "expected a chunk containing target_function"

        chunk = target_chunks[0]
        lines = content.split("\n")
        # start_line is 1-indexed; the line at index (start_line - 1) should
        # be part of the chunk's own text, not just adjacent to it.
        assert chunk.start_line is not None
        actual_line = lines[chunk.start_line - 1]
        assert actual_line in chunk.text or chunk.text.startswith(actual_line.strip()[:10])

    def test_language_is_recorded_on_chunks(self):
        chunks = chunk_file("sample.py", "x = 1\n")
        assert all(c.language == "python" for c in chunks)

    def test_unrecognized_extension_falls_back_to_text_language(self):
        chunks = chunk_file("notes.xyz", "some plain text content here\n")
        assert all(c.language == "text" for c in chunks)
