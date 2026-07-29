"""
Streamlit UI for the Grounded Q&A System for Internal Codebases (RAG) MVP.

Two panes:
  - Sidebar: paste a public GitHub repo URL, ingest it into the local vector store.
  - Main: pick an ingested repo, ask questions, see grounded answers with citations.

This file is UI/presentation only — all RAG logic lives in rag_core/.
"""
import time

import streamlit as st
from dotenv import load_dotenv

from rag_core.ingestion import ingest_repository
from rag_core.retrieval import answer_question
from rag_core.vector_store import get_vector_store

load_dotenv()

st.set_page_config(
    page_title="Codebase Q&A (RAG)",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* Tighten Streamlit's default top padding so the header sits higher */
    .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 900px; }

    /* Hero header */
    .rag-hero { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.1rem; }
    .rag-hero h1 { font-size: 1.7rem; margin: 0; font-weight: 700; }
    .rag-subtitle { opacity: 0.65; font-size: 0.95rem; margin-bottom: 1.4rem; }

    /* Sidebar section headers */
    .sidebar-section-label {
        font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em;
        text-transform: uppercase; opacity: 0.55; margin: 1.1rem 0 0.5rem 0;
    }

    /* Repo card in sidebar (selected + list) */
    .repo-card {
        border: 1px solid rgba(128,128,128,0.25); border-radius: 10px;
        padding: 0.55rem 0.75rem; margin-bottom: 0.4rem; font-size: 0.85rem;
    }
    .repo-card .repo-name { font-weight: 600; }
    .repo-card .repo-meta { opacity: 0.6; font-size: 0.75rem; margin-top: 0.15rem; }

    /* Citation pills */
    .citation-pill {
        display: inline-flex; align-items: center; gap: 0.35rem;
        border: 1px solid rgba(128,128,128,0.3); border-radius: 999px;
        padding: 0.15rem 0.65rem; margin: 0.15rem 0.3rem 0.15rem 0;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        font-size: 0.78rem; background: rgba(128,128,128,0.08);
    }
    .citation-pill .score { opacity: 0.55; font-family: inherit; }

    .provider-badge {
        display: inline-block; font-size: 0.72rem; font-weight: 600;
        padding: 0.1rem 0.55rem; border-radius: 999px;
        background: rgba(46,204,113,0.15); color: #1e8449; margin-bottom: 0.6rem;
    }

    /* Ingestion stepper */
    .stepper { display: flex; gap: 0.4rem; margin: 0.6rem 0 0.5rem 0; }
    .step {
        flex: 1; text-align: center; font-size: 0.68rem; font-weight: 600;
        padding: 0.35rem 0.2rem; border-radius: 6px; opacity: 0.4;
        background: rgba(128,128,128,0.12); transition: all 0.2s ease;
    }
    .step.active { opacity: 1; background: rgba(52,152,219,0.2); color: #2471a3; }
    .step.done { opacity: 0.85; background: rgba(46,204,113,0.18); color: #1e8449; }

    /* Empty state */
    .empty-state {
        text-align: center; padding: 3.5rem 1.5rem; opacity: 0.75;
        border: 1px dashed rgba(128,128,128,0.3); border-radius: 14px; margin-top: 1rem;
    }
    .empty-state .emoji { font-size: 2.2rem; margin-bottom: 0.6rem; }
    .empty-state .title { font-weight: 600; font-size: 1.05rem; margin-bottom: 0.3rem; }
    .empty-state .desc { font-size: 0.88rem; opacity: 0.75; max-width: 420px; margin: 0 auto; }

    .suggestion-chip {
        display: inline-block; border: 1px solid rgba(128,128,128,0.3); border-radius: 8px;
        padding: 0.3rem 0.7rem; margin: 0.2rem; font-size: 0.82rem; opacity: 0.85;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="rag-hero"><h1>🔍 Grounded Q&A for Internal Codebases</h1></div>
    <div class="rag-subtitle">
        Ask natural-language questions about a GitHub repo. Answers are grounded in
        retrieved code/doc chunks with file + line citations — free-tier stack only.
    </div>
    """,
    unsafe_allow_html=True,
)

if "history" not in st.session_state:
    st.session_state.history = []  # list of (question, AnswerResult)

INGEST_STEPS = ["Clone", "Chunk", "Embed", "Store"]
STEP_KEYWORDS = {
    "Clone": ("cloning",),
    "Chunk": ("chunking", "chunked", "done chunking"),
    "Embed": ("embedding",),
    "Store": ("stored",),
}


def _current_step_index(log_lines: list[str]) -> int:
    """Best-effort mapping of the latest progress line to a stepper stage."""
    if not log_lines:
        return -1
    latest = log_lines[-1].lower()
    for i, step in enumerate(INGEST_STEPS):
        if any(kw in latest for kw in STEP_KEYWORDS[step]):
            return i
    return -1


def _render_stepper(current_index: int) -> str:
    cells = []
    for i, step in enumerate(INGEST_STEPS):
        css_class = "step"
        if i < current_index:
            css_class += " done"
        elif i == current_index:
            css_class += " active"
        cells.append(f'<div class="{css_class}">{step}</div>')
    return f'<div class="stepper">{"".join(cells)}</div>'


# ---------------------------------------------------------------------------
# Sidebar: ingestion + repo selection
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="sidebar-section-label">1 · Ingest a repository</div>', unsafe_allow_html=True)
    repo_url = st.text_input(
        "Public GitHub repo URL",
        placeholder="https://github.com/owner/repo_name",
        label_visibility="collapsed",
    )
    ingest_clicked = st.button("Ingest repo", type="primary", use_container_width=True)

    if ingest_clicked:
        if not repo_url.strip():
            st.error("Enter a repo URL first.")
        else:
            stepper_box = st.empty()
            status_box = st.empty()
            log_lines: list[str] = []

            def _progress(msg: str) -> None:
                log_lines.append(msg)
                stepper_box.markdown(_render_stepper(_current_step_index(log_lines)), unsafe_allow_html=True)
                status_box.caption(msg)

            stepper_box.markdown(_render_stepper(0), unsafe_allow_html=True)
            status_box.caption("Starting...")
            try:
                start = time.time()
                summary = ingest_repository(repo_url.strip(), progress=_progress)
                elapsed = time.time() - start
                stepper_box.markdown(_render_stepper(len(INGEST_STEPS)), unsafe_allow_html=True)
                status_box.success(
                    f"Ingested {summary['chunk_count']} chunks in {elapsed:.1f}s.", icon="✅"
                )
            except Exception as exc:  # noqa: BLE001
                status_box.error(f"Ingestion failed: {exc}", icon="⚠️")

    st.markdown('<div class="sidebar-section-label">2 · Choose repo to query</div>', unsafe_allow_html=True)
    store = get_vector_store()
    repo_infos = store.list_collections_with_info()

    if not repo_infos:
        st.caption("No repos ingested yet — add one above to get started.")
        selected_collection = None
    else:
        options = {info["name"]: info for info in repo_infos}
        selected_name = st.selectbox(
            "Ingested repositories",
            list(options.keys()),
            format_func=lambda n: options[n]["display_name"],
            label_visibility="collapsed",
        )
        selected_collection = selected_name
        info = options[selected_name]
        st.markdown(
            f"""
            <div class="repo-card">
                <div class="repo-name">📦 {info['display_name']}</div>
                <div class="repo-meta">{info['chunk_count']} chunks indexed</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="sidebar-section-label">Stack</div>', unsafe_allow_html=True)
    st.caption(
        "sentence-transformers (embeddings) · ChromaDB (vector store) · "
        "cross-encoder reranking · Gemini/OpenRouter (generation) — all free-tier."
    )

# ---------------------------------------------------------------------------
# Main: Q&A
# ---------------------------------------------------------------------------
if not repo_infos:
    st.markdown(
        """
        <div class="empty-state">
            <div class="emoji">📂</div>
            <div class="title">No repositories ingested yet</div>
            <div class="desc">
                Paste a public GitHub URL into the sidebar and click <b>Ingest repo</b>
                to build a searchable knowledge base you can ask questions against.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

if not st.session_state.history:
    st.markdown(
        f"""
        <div class="empty-state">
            <div class="emoji">💬</div>
            <div class="title">Ask something about {options[selected_collection]['display_name']}</div>
            <div class="desc">Try one of these to get started, or type your own question below.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    suggestions = [
        "What does this repo do, at a high level?",
        "Where is the main entry point?",
        "How is authentication handled?",
    ]
    st.markdown(
        "".join(f'<span class="suggestion-chip">{s}</span>' for s in suggestions),
        unsafe_allow_html=True,
    )

question = st.chat_input("Ask a question about the selected repo...")


def _render_citations(result) -> None:
    if not result.citations:
        return
    st.markdown(f'<span class="provider-badge">{result.provider} · {result.model}</span>', unsafe_allow_html=True)
    with st.expander(f"Sources ({len(result.citations)})", expanded=False):
        pills = "".join(
            f'<span class="citation-pill">{c.file_path}:{c.start_line}-{c.end_line} '
            f'<span class="score">{c.rerank_score:.2f}</span></span>'
            for c in result.citations
        )
        st.markdown(pills, unsafe_allow_html=True)


for past_question, result in st.session_state.history:
    with st.chat_message("user"):
        st.write(past_question)
    with st.chat_message("assistant"):
        st.write(result.answer)
        _render_citations(result)

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
                _render_citations(result)
                st.session_state.history.append((question, result))