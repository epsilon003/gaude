"""
Retrieval evaluation harness.

`rag_core/eval.py` calibrates the confidence *thresholds* on a couple of
hand-picked examples. This module answers a different, more basic question:
is retrieval itself any good? A change to chunking, embeddings, or reranking
won't crash anything if it quietly makes retrieval worse -- nothing raises,
the LLM just gets weaker context and produces a plausible-sounding but
less-grounded answer. This harness catches that by checking, for a set of
known questions, whether the expected source file actually shows up in the
top-k retrieved-and-reranked chunks.

Usage:
    python -m rag_core.eval_harness
    python -m rag_core.eval_harness --dataset eval/golden_dataset.json --top-k 3
    python -m rag_core.eval_harness --json report.json
    python -m rag_core.eval_harness --fail-under 0.8   # for CI: non-zero exit if hit rate drops

Dataset format (JSON array):
    [{"question": str, "collection_name": str, "expected_files": [str, ...]}, ...]

A "hit" means at least one expected file substring appears in the file_path
of one of the top-k retrieved chunks. Substring match (not exact equality)
so "rag_core/chunking.py" matches regardless of repo root prefixing.

Requires a collection that has already been ingested (see ingest.py / the
Next.js UI's ingest flow) -- this harness measures retrieval quality against
whatever is already in the vector store, it doesn't ingest anything itself.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rag_core.retrieval import retrieve_and_rerank

DEFAULT_DATASET_PATH = "eval/golden_dataset.json"
DEFAULT_TOP_K_RETRIEVE = 15


@dataclass
class QueryResult:
    question: str
    collection_name: str
    expected_files: list[str]
    retrieved_files: list[str] = field(default_factory=list)
    hit: bool = False
    reciprocal_rank: float = 0.0
    latency_seconds: float = 0.0
    error: str | None = None


def load_dataset(path: str | Path) -> list[dict]:
    """Load and validate a golden dataset. Raises ValueError with a clear
    message on malformed entries rather than failing deep inside a query."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list) or not data:
        raise ValueError(f"{path}: expected a non-empty JSON array of eval cases")
    required = {"question", "collection_name", "expected_files"}
    for i, item in enumerate(data):
        if not isinstance(item, dict) or not required.issubset(item):
            missing = required - (item.keys() if isinstance(item, dict) else set())
            raise ValueError(f"{path}[{i}]: missing required keys {sorted(missing)}")
    return data


def _first_hit_rank(retrieved_files: list[str], expected_files: list[str]) -> int | None:
    """1-based rank of the first retrieved file matching any expected file, else None."""
    for rank, path in enumerate(retrieved_files, start=1):
        if path and any(exp in path for exp in expected_files):
            return rank
    return None


def run_query(item: dict, top_k: int) -> QueryResult:
    """Run a single eval case. Never raises -- a bad/missing collection for
    one question shouldn't abort the whole eval run, it should just show up
    as an error in the report."""
    result = QueryResult(
        question=item["question"],
        collection_name=item["collection_name"],
        expected_files=list(item["expected_files"]),
    )
    start = time.time()
    try:
        reranked = retrieve_and_rerank(
            collection_name=item["collection_name"],
            query=item["question"],
            top_k_retrieve=DEFAULT_TOP_K_RETRIEVE,
            top_k_final=top_k,
        )
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, see docstring
        result.error = str(exc)
        result.latency_seconds = time.time() - start
        return result

    result.latency_seconds = time.time() - start
    result.retrieved_files = [r.get("file_path", "") for r in reranked]
    rank = _first_hit_rank(result.retrieved_files, result.expected_files)
    result.hit = rank is not None
    result.reciprocal_rank = 1.0 / rank if rank else 0.0
    return result


def summarize(results: list[QueryResult]) -> dict:
    n = len(results)
    scored = [r for r in results if r.error is None]
    errored = n - len(scored)
    hits = sum(1 for r in scored if r.hit)
    return {
        "total_queries": n,
        "errored_queries": errored,
        "hit_rate": (hits / n) if n else 0.0,
        "mrr": (sum(r.reciprocal_rank for r in scored) / n) if n else 0.0,
        "avg_latency_seconds": (sum(r.latency_seconds for r in results) / n) if n else 0.0,
    }


def run_eval(dataset: list[dict], top_k: int = 5) -> tuple[list[QueryResult], dict]:
    """Reusable entry point -- also what tests call directly with a stubbed
    retrieve_and_rerank, without needing a live vector store."""
    results = [run_query(item, top_k) for item in dataset]
    return results, summarize(results)


def _print_report(results: list[QueryResult], metrics: dict, top_k: int) -> None:
    print(f"Retrieval eval -- top_k={top_k}\n")
    for r in results:
        if r.error:
            print(f"  ERROR  '{r.question}'")
            print(f"         {r.error}")
            continue
        mark = "PASS" if r.hit else "FAIL"
        print(f"  {mark}  '{r.question}'")
        print(f"         expected: {r.expected_files}")
        print(f"         got:      {r.retrieved_files}")
    print()
    print(f"Queries:      {metrics['total_queries']} ({metrics['errored_queries']} errored)")
    print(f"Hit rate@{top_k}:  {metrics['hit_rate']:.1%}")
    print(f"MRR:          {metrics['mrr']:.3f}")
    print(f"Avg latency:  {metrics['avg_latency_seconds']:.2f}s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality against a golden dataset.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET_PATH, help="Path to a JSON eval dataset.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of final reranked chunks checked for a hit.")
    parser.add_argument("--json", dest="json_out", default=None, help="Optional path to write a machine-readable report.")
    parser.add_argument("--fail-under", type=float, default=None, help="Exit 1 if hit_rate is below this (0-1), for CI.")
    args = parser.parse_args(argv)

    try:
        dataset = load_dataset(args.dataset)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Could not load dataset: {exc}", file=sys.stderr)
        return 2

    results, metrics = run_eval(dataset, top_k=args.top_k)
    _print_report(results, metrics, args.top_k)

    if args.json_out:
        report = {"metrics": metrics, "results": [asdict(r) for r in results]}
        Path(args.json_out).write_text(json.dumps(report, indent=2))
        print(f"\nWrote {args.json_out}")

    if args.fail_under is not None and metrics["hit_rate"] < args.fail_under:
        print(f"\nFAIL: hit_rate {metrics['hit_rate']:.1%} is below --fail-under {args.fail_under:.1%}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())