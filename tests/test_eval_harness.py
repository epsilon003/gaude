"""
Tests for rag_core/eval_harness.py.

These stub out retrieve_and_rerank entirely, so they exercise only the
harness's own logic (hit/miss detection, MRR, dataset validation, CLI exit
codes) -- not retrieval quality itself. Retrieval quality is what the
harness measures when pointed at a real ingested collection; these tests
just make sure the measuring stick is correct.
"""
import json
from unittest.mock import patch

import pytest

from rag_core.eval_harness import (
    load_dataset,
    main,
    run_eval,
    run_query,
    summarize,
)


def _fake_result(file_path: str) -> dict:
    return {"file_path": file_path, "text": "...", "rerank_score": 1.0}


class TestLoadDataset:
    def test_loads_valid_dataset(self, tmp_path):
        data = [{"question": "q", "collection_name": "c", "expected_files": ["f.py"]}]
        p = tmp_path / "ds.json"
        p.write_text(json.dumps(data))
        loaded = load_dataset(p)
        assert loaded == data

    def test_rejects_empty_array(self, tmp_path):
        p = tmp_path / "ds.json"
        p.write_text("[]")
        with pytest.raises(ValueError):
            load_dataset(p)

    def test_rejects_missing_required_keys(self, tmp_path):
        p = tmp_path / "ds.json"
        p.write_text(json.dumps([{"question": "q"}]))  # missing collection_name, expected_files
        with pytest.raises(ValueError, match="missing required keys"):
            load_dataset(p)

    def test_the_actual_bundled_golden_dataset_is_valid(self):
        # Regression guard: the real dataset shipped in eval/golden_dataset.json
        # should always load cleanly.
        loaded = load_dataset("eval/golden_dataset.json")
        assert len(loaded) > 0
        for item in loaded:
            assert item["question"]
            assert item["collection_name"]
            assert item["expected_files"]


class TestRunQuery:
    def test_hit_when_expected_file_in_top_k(self):
        item = {"question": "q", "collection_name": "c", "expected_files": ["rag_core/chunking.py"]}
        with patch("rag_core.eval_harness.retrieve_and_rerank") as mock_retrieve:
            mock_retrieve.return_value = [
                _fake_result("rag_core/retrieval.py"),
                _fake_result("rag_core/chunking.py"),
            ]
            result = run_query(item, top_k=5)
        assert result.hit is True
        assert result.reciprocal_rank == pytest.approx(0.5)  # rank 2
        assert result.error is None

    def test_miss_when_expected_file_absent(self):
        item = {"question": "q", "collection_name": "c", "expected_files": ["rag_core/chunking.py"]}
        with patch("rag_core.eval_harness.retrieve_and_rerank") as mock_retrieve:
            mock_retrieve.return_value = [_fake_result("rag_core/retrieval.py")]
            result = run_query(item, top_k=5)
        assert result.hit is False
        assert result.reciprocal_rank == 0.0

    def test_retrieval_exception_is_captured_not_raised(self):
        item = {"question": "q", "collection_name": "missing-collection", "expected_files": ["x.py"]}
        with patch("rag_core.eval_harness.retrieve_and_rerank") as mock_retrieve:
            mock_retrieve.side_effect = RuntimeError("collection does not exist")
            result = run_query(item, top_k=5)  # must not raise
        assert result.error == "collection does not exist"
        assert result.hit is False

    def test_substring_match_on_file_path(self):
        # expected_files entries are substrings (e.g. "rag_core/chunking.py"),
        # matched against whatever full path retrieval returns -- this
        # tolerates repo-root prefixes without requiring exact equality.
        item = {"question": "q", "collection_name": "c", "expected_files": ["chunking.py"]}
        with patch("rag_core.eval_harness.retrieve_and_rerank") as mock_retrieve:
            mock_retrieve.return_value = [_fake_result("some/repo/rag_core/chunking.py")]
            result = run_query(item, top_k=5)
        assert result.hit is True


class TestSummarize:
    def test_hit_rate_and_mrr_over_mixed_results(self):
        from rag_core.eval_harness import QueryResult

        results = [
            QueryResult("q1", "c", ["a"], hit=True, reciprocal_rank=1.0),
            QueryResult("q2", "c", ["b"], hit=False, reciprocal_rank=0.0),
            QueryResult("q3", "c", ["c"], hit=True, reciprocal_rank=0.5),
        ]
        metrics = summarize(results)
        assert metrics["total_queries"] == 3
        assert metrics["errored_queries"] == 0
        assert metrics["hit_rate"] == pytest.approx(2 / 3)
        assert metrics["mrr"] == pytest.approx((1.0 + 0.0 + 0.5) / 3)

    def test_errored_queries_count_toward_total_but_not_hit_rate_numerator(self):
        from rag_core.eval_harness import QueryResult

        results = [
            QueryResult("q1", "c", ["a"], hit=True, reciprocal_rank=1.0),
            QueryResult("q2", "c", ["b"], error="boom"),
        ]
        metrics = summarize(results)
        assert metrics["total_queries"] == 2
        assert metrics["errored_queries"] == 1
        assert metrics["hit_rate"] == pytest.approx(0.5)  # 1 hit / 2 total, not / 1 scored

    def test_empty_results_do_not_divide_by_zero(self):
        metrics = summarize([])
        assert metrics == {
            "total_queries": 0,
            "errored_queries": 0,
            "hit_rate": 0.0,
            "mrr": 0.0,
            "avg_latency_seconds": 0.0,
        }


class TestRunEval:
    def test_run_eval_end_to_end_with_stubbed_retrieval(self):
        dataset = [
            {"question": "q1", "collection_name": "c", "expected_files": ["a.py"]},
            {"question": "q2", "collection_name": "c", "expected_files": ["z.py"]},
        ]
        with patch("rag_core.eval_harness.retrieve_and_rerank") as mock_retrieve:
            mock_retrieve.return_value = [_fake_result("a.py")]
            results, metrics = run_eval(dataset, top_k=5)
        assert len(results) == 2
        assert metrics["hit_rate"] == pytest.approx(0.5)


class TestMainCLI:
    def test_fail_under_returns_nonzero_when_hit_rate_too_low(self, tmp_path):
        dataset = [{"question": "q", "collection_name": "c", "expected_files": ["a.py"]}]
        p = tmp_path / "ds.json"
        p.write_text(json.dumps(dataset))

        with patch("rag_core.eval_harness.retrieve_and_rerank") as mock_retrieve:
            mock_retrieve.return_value = [_fake_result("unrelated.py")]  # guaranteed miss
            exit_code = main(["--dataset", str(p), "--fail-under", "0.5"])
        assert exit_code == 1

    def test_missing_dataset_file_returns_exit_code_2(self, tmp_path):
        exit_code = main(["--dataset", str(tmp_path / "does_not_exist.json")])
        assert exit_code == 2

    def test_json_report_is_written_when_requested(self, tmp_path):
        dataset = [{"question": "q", "collection_name": "c", "expected_files": ["a.py"]}]
        ds_path = tmp_path / "ds.json"
        ds_path.write_text(json.dumps(dataset))
        out_path = tmp_path / "report.json"

        with patch("rag_core.eval_harness.retrieve_and_rerank") as mock_retrieve:
            mock_retrieve.return_value = [_fake_result("a.py")]
            main(["--dataset", str(ds_path), "--json", str(out_path)])

        report = json.loads(out_path.read_text())
        assert "metrics" in report
        assert "results" in report
        assert report["metrics"]["hit_rate"] == 1.0
