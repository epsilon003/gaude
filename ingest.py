#!/usr/bin/env python3
"""
CLI entrypoint for repo ingestion (PRD FR-1/2/3).

Usage:
    python ingest.py --repo_url "https://github.com/owner/repo_name"
"""
import argparse
import sys

from dotenv import load_dotenv

from rag_core.ingestion import ingest_repository

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Ingest a public GitHub repo into the vector store.")
    parser.add_argument("--repo_url", required=True, help="Public GitHub repository URL")
    args = parser.parse_args()

    try:
        summary = ingest_repository(args.repo_url, progress=print)
    except Exception as exc:  # noqa: BLE001
        print(f"\nIngestion failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\nIngestion complete.")
    print(f"  Repo:        {summary['repo_url']}")
    print(f"  Collection:  {summary['collection_name']}")
    print(f"  Chunks:      {summary['chunk_count']}")
    print("\nRun `streamlit run app.py` to ask questions about this repo.")


if __name__ == "__main__":
    main()
