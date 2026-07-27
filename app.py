"""
Streamlit UI for the Grounded Q&A System for Internal Codebases (RAG) MVP.

Two panes:
  - Sidebar: paste a public GitHub repo URL, ingest it into the local vector store.
  - Main: pick an ingested repo, ask questions, see grounded answers with citations.
"""
import time

import streamlit as st
from dotenv import load_dotenv

from rag_core.ingestion import ingest_repository
from rag_core.retrieval import answer_question
from rag_core.vector_store import VectorStore, repo_url_to_collection_name

load_dotenv()

st.set_page_config(page_title="Codebase Q&A (RAG)", page_icon="🔍", layout="wide")

st.title("🔍 Grounded Q&A for Internal Codebases")
st.caption(
    "Ask natural-language questions about a GitHub repo. Answers are grounded in "
    "retrieved code/doc chunks with file + line citations — free-tier stack only."
)

if "history" not in st.session_state:
    st.session_state.history = []  # list of (question, AnswerResult)

# ---------------------------------------------------------------------------
# Sidebar: ingestion
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("1. Ingest a repository")
    repo_url = st.text_input(
        "Public GitHub repo URL", placeholder="https://github.com/owner/repo_name"
    )
    ingest_clicked = st.button("Ingest repo", type="primary", use_container_width=True)

    if ingest_clicked:
        if not repo_url.strip():
            st.error("Enter a repo URL first.")
        else:
            log_box = st.empty()
            log_lines: list[str] = []

            def _progress(msg: str) -> None:
                log_lines.append(msg)
                log_box.code("\n".join(log_lines[-8:]), language=None)

            with st.spinner("Ingesting repository..."):
                try:
                    start = time.time()
                    summary = ingest_repository(repo_url.strip(), progress=_progress)
                    elapsed = time.time() - start
                    st.success(
                        f"Ingested {summary['chunk_count']} chunks from "
                        f"{summary['repo_url']} in {elapsed:.1f}s."
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Ingestion failed: {exc}")

    st.divider()
    st.header("2. Choose repo to query")
    store = VectorStore()
    collections = store.list_collections()

    if not collections:
        st.info("No repos ingested yet. Ingest one above to get started.")
        selected_collection = None
    else:
        selected_collection = st.selectbox("Ingested repositories", collections)

    st.divider()
    st.caption(
        "Stack: sentence-transformers (embeddings) + ChromaDB (vector store) + "
        "cross-encoder reranking + Gemini/OpenRouter (generation) — all free-tier."
    )

# ---------------------------------------------------------------------------
# Main: Q&A
# ---------------------------------------------------------------------------
if not collections:
    st.stop()

question = st.chat_input("Ask a question about the selected repo...")

for past_question, result in st.session_state.history:
    with st.chat_message("user"):
        st.write(past_question)
    with st.chat_message("assistant"):
        st.write(result.answer)
        if result.citations:
            with st.expander(f"Sources ({result.provider}/{result.model})"):
                for c in result.citations:
                    st.markdown(f"- `{c.file_path}:{c.start_line}-{c.end_line}`  (score: {c.rerank_score:.2f})")

if question:
    if not selected_collection:
        st.error("Select an ingested repo from the sidebar first.")
    else:
        with st.chat_message("user"):
            st.write(question)

        with st.chat_message("assistant"):
            with st.spinner("Retrieving context and generating answer..."):
                try:
                    result = answer_question(selected_collection, question)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Failed to answer: {exc}")
                    result = None

            if result is not None:
                st.write(result.answer)
                if result.citations:
                    with st.expander(f"Sources ({result.provider}/{result.model})"):
                        for c in result.citations:
                            st.markdown(
                                f"- `{c.file_path}:{c.start_line}-{c.end_line}`  "
                                f"(score: {c.rerank_score:.2f})"
                            )
                st.session_state.history.append((question, result))
