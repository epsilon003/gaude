"""
Tests for rag_core/ingestion.py.

The one test here pins down a real bug found via the eval harness: on
Windows, os.path.relpath returns backslash-separated paths, which used to
flow straight through into chunk metadata as file_path. That value later
builds GitHub permalinks (which need forward slashes -- a backslash there is
just a broken URL) and is compared against the eval harness's golden dataset
(authored with forward slashes), so every retrieval on Windows silently
"missed" even when it found the right file.
"""
from unittest.mock import patch

from rag_core import ingestion


class TestIterIngestibleFilesPathNormalization:
    def test_windows_style_separators_are_normalized_to_forward_slashes(self, tmp_path):
        sub = tmp_path / "rag_core"
        sub.mkdir()
        (sub / "chunking.py").write_text("x = 1\n")

        # Mocks os.sep and os.path.relpath (both read at call time inside
        # iter_ingestible_files) to behave exactly as they would on Windows,
        # so this exercises the real normalization line regardless of which
        # OS the test suite happens to run on.
        with (
            patch.object(ingestion.os, "sep", "\\"),
            patch.object(ingestion.os.path, "relpath", return_value="rag_core\\chunking.py"),
        ):
            results = list(ingestion.iter_ingestible_files(str(tmp_path)))

        assert len(results) == 1
        _full_path, rel_path = results[0]
        assert rel_path == "rag_core/chunking.py"
        assert "\\" not in rel_path

    def test_posix_style_separators_pass_through_unchanged(self, tmp_path):
        sub = tmp_path / "rag_core"
        sub.mkdir()
        (sub / "chunking.py").write_text("x = 1\n")

        results = list(ingestion.iter_ingestible_files(str(tmp_path)))

        assert len(results) == 1
        _full_path, rel_path = results[0]
        assert rel_path == "rag_core/chunking.py"

    def test_excluded_files_are_still_filtered_after_normalization(self, tmp_path):
        # should_ingest_file must see the normalized (forward-slash) path,
        # not the raw OS-native one, since its own exclusion patterns
        # (node_modules/, .git/, etc.) are written with forward slashes.
        nm = tmp_path / "node_modules" / "react"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("// noop\n")

        results = list(ingestion.iter_ingestible_files(str(tmp_path)))

        assert results == []