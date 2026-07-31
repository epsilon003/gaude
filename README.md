# Grounded Q&A System for Internal Codebases (RAG) MVP

Ask natural-language questions about a public GitHub repository and get
streamed, grounded answers with clickable citations back to the exact lines
they came from — built as a fully **free-tier** stack, no paid APIs, no paid
infra.

## Stack

| Component | Choice | Why |
|---|---|---|
| Chunking | LangChain `RecursiveCharacterTextSplitter.from_language()` | Splits on function/class boundaries instead of blind fixed-size cuts; lockfiles (`package-lock.json`, `yarn.lock`, etc.) are excluded entirely — they're noise that can out-rank real source code in retrieval |
| Embeddings | `sentence-transformers` (`BAAI/bge-small-en-v1.5`) | Runs 100% locally, no API, no rate limits |
| Vector store | ChromaDB (persisted locally, process-level singleton) | Embedded, zero-infra, free |
| Reranking | Local cross-encoder (`ms-marco-MiniLM-L-6-v2`) | Precision pass on top-k before generation; also feeds the groundedness indicator |
| Generation (primary) | Google AI Studio — Gemini (`GEMINI_MODEL`, default `gemini-3.5-flash`) | Free tier, no card |
| Generation (fallback) | OpenRouter — pinned model (optional) → `openrouter/free` auto-router | Auto-router self-heals as OpenRouter's free lineup changes; free slugs get pulled with little notice, so this is the default rather than a pinned model |
| UI | Streamlit, with streaming responses | Deploys free on Hugging Face Spaces |

## Features

- **Streamed answers** — text appears token-by-token instead of all at once (`st.write_stream`).
- **Source citations with previews** — each citation is an expandable panel showing the actual retrieved code snippet, syntax-highlighted, plus a permalink to the exact commit/lines on GitHub (`.../blob/<commit-sha>/path#L12-L20`) when the repo was ingested from `github.com`.
- **Follow-up questions** — a question like *"what about its error handling?"* gets rewritten into a standalone query using recent chat history before retrieval, so the vector search actually has something to work with. Falls back to the raw question if that rewrite step fails for any reason — never blocks the answer.
- **Retrieval routing** — greetings and meta questions ("thanks", "what can you do?") skip retrieval and the LLM entirely instead of returning an awkward "nothing relevant found."
- **Groundedness indicator** — a heuristic "Strong / Moderate / Weak" badge derived from the reranker's relevance scores, giving a rough visual cue for how well-supported an answer actually is. This is *not* a calibrated confidence score, just a rough signal.
- **Multi-provider resilience** — Gemini → pinned OpenRouter model (if set) → OpenRouter auto-router, with retry-with-backoff on transient errors (429/503) before failing over. Free-tier model IDs get deprecated or pulled with little warning; this stack is built assuming that will keep happening.

## Setup and Installation

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd <your-repo-name>
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
   > If you hit `ModuleNotFoundError: No module named 'torchvision'` — `transformers` (pulled in by `sentence-transformers`) probes for it on import even for our text-only embedding model. It's pinned in `requirements.txt`, so a fresh install should be fine; if you're on an older `venv`, just `pip install torchvision`.

3. **Set up environment variables:**
   ```bash
   cp .env.example .env
   ```
   Then fill in:
   - `GEMINI_API_KEY` — free key, no card required: https://aistudio.google.com/apikey
   - `OPENROUTER_API_KEY` — free key, no card required: https://openrouter.ai/keys

   You only strictly need one of the two, but both is recommended so the fallback
   actually has somewhere to fall back to. Leave `OPENROUTER_MODEL` unset (default) —
   it uses OpenRouter's `openrouter/free` auto-router, which stays working even
   as OpenRouter's specific free-model lineup changes underneath you.

   > **Free-tier model IDs rotate.** If you get a 404 like "no longer available"
   > or "unavailable for free," the pinned model name is stale — check
   > https://ai.google.dev/gemini-api/docs/models and
   > https://openrouter.ai/models?order=pricing-low-to-high and update `.env`.
   > No code changes needed.

4. **Ingest a GitHub repository** (CLI):
   ```bash
   python ingest.py --repo_url "https://github.com/owner/repo_name"
   ```
   This clones the repo, chunks it, embeds it locally, and stores it in
   `vector_store/` (a Chroma collection named after the repo, tagged with the
   source URL and the commit SHA that was cloned — used for GitHub permalinks
   in citations).

   You can also ingest directly from the Streamlit sidebar (step 5).

   > **Already ingested a repo before this update?** Its citations won't have
   > GitHub links or benefit from the lockfile-exclusion fix until you
   > re-ingest it — the collection metadata those features need didn't exist
   > yet when it was first indexed. Just re-run the ingest command.

5. **Start the app:**
   ```bash
   streamlit run app.py
   ```
   Open the local URL Streamlit prints (default `http://localhost:8501`).
   Ingest a repo from the sidebar, or pick one you already ingested via the CLI,
   then ask questions in the chat box. Answers stream in. Expand a citation to
   see the actual code and jump to it on GitHub.

## Usage

1. Paste a public GitHub repo URL into the sidebar and click **Ingest repo**.
2. Select the ingested repo from the dropdown.
3. Ask a question about the codebase in plain English. Ask a follow-up and it'll
   automatically resolve pronouns/context from the conversation so far (you'll
   see "Interpreted as: ..." if your question got rewritten).
4. The answer streams in with a provider badge, a groundedness badge, and an
   expandable **Sources** list — each source shows the actual retrieved code
   and links to the exact commit/lines on GitHub.

## Project Structure

```
.
├── .env.example
├── .gitignore
├── requirements.txt
├── ingest.py              # CLI: clone, chunk, embed, store a repo
├── app.py                 # Streamlit UI: ingest + streaming chat + citations
├── rag_core/
│   ├── chunking.py         # Language-aware splitting, line-number resolution, lockfile exclusion
│   ├── embeddings.py       # Local sentence-transformers wrapper (lazy-imported — see below)
│   ├── vector_store.py     # ChromaDB wrapper: per-repo collections, process-level singleton, commit_sha metadata
│   ├── reranker.py         # Local cross-encoder reranking (lazy-imported — see below)
│   ├── llm_client.py       # Gemini + OpenRouter clients: streaming, retry/failover, query condensation
│   ├── ingestion.py        # Orchestrates clone -> chunk -> embed -> store, captures commit SHA
│   └── retrieval.py        # Orchestrates routing -> condense -> retrieve -> rerank -> generate
└── vector_store/           # Local Chroma persistence (gitignored)
```

A couple of implementation details worth knowing if you're extending this:

- **`embeddings.py`/`reranker.py` import `sentence_transformers` lazily**, inside
  `__init__`, not at module level. That import drags in `torch`, which is slow
  (seconds, not milliseconds) — importing it at module level would block
  Streamlit from rendering *anything* until it finished. The heavy load now
  only happens on first actual use (first ingest or first question), not at
  page load.
- **`get_vector_store()` is a process-level singleton** (`functools.lru_cache`),
  not re-created per Streamlit rerun or per question. `chromadb.PersistentClient`
  has a real one-time warmup cost; without this, that cost would be paid
  repeatedly since Streamlit reruns the whole script on every interaction.

## Scope (MVP)

**In scope:** public repo ingestion, language-aware chunking (with lockfile
exclusion), local embeddings, semantic retrieval + reranking, streamed
grounded answer generation, file/line citations with previews and GitHub
permalinks, follow-up question handling, retrieval routing, a groundedness
indicator, multi-provider failover.

**Out of scope (per PRD):** private repos, multiple repos queried
simultaneously, control/data-flow analysis, code generation/modification,
real-time re-ingestion (re-running `ingest.py` does a full re-index, not an
incremental diff).
