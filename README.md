# Grounded Q&A System for Internal Codebases (RAG)

Ask natural-language questions about a public GitHub repository and get
streamed, grounded answers with clickable citations back to the exact lines
they came from.

**FastAPI + Next.js** (`api/` + `frontend/`) — the in-progress production
  path: a real REST/SSE API backend with a React frontend. Both work off the
  same `rag_core/` — nothing about the Streamlit app breaks as the Next.js
  side develops.

## Stack (all free)

| Component | Choice | Why |
|---|---|---|
| Chunking | LangChain `RecursiveCharacterTextSplitter.from_language()` | Splits on function/class boundaries; lockfiles (`package-lock.json`, `yarn.lock`, etc.) are excluded entirely — they're noise that can out-rank real source code in retrieval |
| Embeddings | `sentence-transformers` (`BAAI/bge-small-en-v1.5`), lazy-imported | Runs 100% locally, no API, no rate limits; import deferred to first use so it doesn't block UI startup |
| Vector store | ChromaDB, local + process-level singleton | Embedded, zero-infra, free; singleton avoids re-paying `PersistentClient`'s warmup cost on every question |
| Reranking | Local cross-encoder (`ms-marco-MiniLM-L-6-v2`) | Precision pass on top-k before generation; also feeds the groundedness indicator |
| Generation (primary) | Google AI Studio — Gemini (`GEMINI_MODEL`, default `gemini-3.5-flash`) | Free tier, no card |
| Generation (fallback) | OpenRouter — optional pinned model → `openrouter/free` auto-router | Auto-router self-heals as OpenRouter's free lineup changes; free slugs get pulled with little notice, so this is the default, not a pinned model |
| Backend API | FastAPI, SSE streaming | REST + Server-Sent Events for ingestion progress and chat tokens |
| Frontend | Next.js (App Router, TypeScript, Tailwind v4) | Dark mode, markdown rendering, stop/retry, all covered below |

## Features

**Answering**
- Streamed answers (token-by-token, both UIs)
- Full **markdown rendering** in the Next.js UI — bold, lists, tables, and
  syntax-highlighted code blocks, with a streaming-safe renderer that
  auto-closes incomplete `**`/`` ` ``/`~~` mid-stream so partial tokens never
  show as literal asterisks
- **Stop generation** (button or `Escape`) and **retry on error** (button
  resubmits the same question) — Next.js UI
- Copy-to-clipboard on whole messages and on individual code blocks
- Follow-up question handling — a question like *"what about its error
  handling?"* is rewritten into a standalone query using recent chat
  history before retrieval; falls back to the raw question if that rewrite
  fails for any reason
- Retrieval routing — greetings and meta questions skip retrieval and the
  LLM entirely instead of returning an awkward "nothing relevant found"
- Source citations with expandable code previews and GitHub permalinks
  (`.../blob/<commit-sha>/path#L12-L20`) when ingested from `github.com`
- Groundedness indicator — a heuristic "Strong / Moderate / Weak" badge (see
  [Grounding score](#grounding-score-the-math) below for exactly how it's computed)
- Multi-provider resilience — Gemini → optional pinned OpenRouter model →
  OpenRouter auto-router, with retry-with-backoff on transient errors before
  failing over

**Next.js UI specifically**
- Dark mode (persisted, respects system preference on first visit)
- "Thinking" indicator with rotating status text during retrieval, before
  the first token arrives
- Loading screen while checking backend connectivity; a distinct
  "can't reach the server" screen (with retry) if the backend is down,
  instead of silently showing "no repos ingested"
- `Ctrl`/`Cmd`+`K` focuses the question input
- Collapsible sources list (collapsed by default)

## Setup and Installation FastAPI + Next.js

**Terminal 1 — backend**, from the project root:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn api.main:app --reload --port 8000
```
Check it's alive at `http://localhost:8000/docs` (interactive Swagger UI).

**Terminal 2 — frontend**, from `frontend/`:
```bash
cd frontend
npm install
npm run dev
```
Opens at `http://localhost:3000`. Talks to the backend at `localhost:8000`
by default — only need `frontend/.env.local` (copy from
`.env.local.example`) if the backend is running somewhere else.

The backend needs to be running before you try ingesting/chatting — if it
isn't, the frontend shows the "can't reach the server" screen rather than
failing silently. `.env` at the project root: `GEMINI_API_KEY` and/or
`OPENROUTER_API_KEY` (free, no card — links in `.env.example`), and
optionally `HF_TOKEN` to silence a harmless Hugging Face Hub rate-limit
warning on first model download.

> **Free-tier model IDs rotate.** If you get a 404 like "no longer
> available" or "unavailable for free," the pinned model name in `.env` is
> stale — check https://ai.google.dev/gemini-api/docs/models and
> https://openrouter.ai/models?order=pricing-low-to-high and update there.
> No code changes needed.

## Usage

1. Paste a public GitHub repo URL into the sidebar and click **Ingest repo**.
2. Select the ingested repo from the dropdown.
3. Ask a question. Ask a follow-up and it resolves pronouns/context from the
   conversation automatically (shown as "Interpreted as: ..." when it
   rewrites your question).
4. The answer streams in with a provider badge, a groundedness badge, and an
   expandable **Sources** list — each source shows the actual retrieved code
   and links to the exact commit/lines on GitHub.

## Grounding score: the math

The confidence badge (Strong / Moderate / Weak) is a heuristic, not a
calibrated probability — worth understanding exactly what it does and
doesn't mean before trusting it.

**What it's built from:** every retrieval fetches `top_k_retrieve = 15`
candidates from the vector store, reranks all 15 with a local cross-encoder,
and keeps the top `top_k_final = 5` as the cited/prompted chunks. That
leaves 10 "discarded" candidates that were retrieved but not used.

**The formula** (`rag_core/retrieval.py::_compute_confidence`):

```
top_avg      = mean(rerank_score for the 5 cited chunks)
baseline     = mean(rerank_score for the 10 discarded chunks)
margin       = top_avg − baseline
confidence   = 1 / (1 + e^(−margin))        # sigmoid, maps margin to (0, 1)

label = "Strong"   if confidence ≥ 0.75
        "Moderate" if confidence ≥ 0.50
        "Weak"     otherwise
```

**Why relative, not absolute:** the cross-encoder's raw scores are
un-normalized logits with a range that depends heavily on how close the
content is to what the model was trained on. `ms-marco-MiniLM-L-6-v2` was
trained on MS MARCO — web search queries against natural-language prose —
and has never seen source code, so its scores for code chunks run
systematically lower than for the prose it was calibrated on. An early
version of this feature compared `top_avg` against a fixed threshold picked
by eyeballing generic score ranges, and it read "Weak" almost universally
for exactly this reason — the domain mismatch, not the actual answer
quality. Comparing the top 5 against the bottom 10 *from the same retrieval
call* sidesteps that: whatever the model's absolute range happens to be for
this content, "meaningfully better than what got discarded" is a comparison
against itself, not against a number tuned for a different domain.

**Worked example**, using real numbers from testing this fix: a pool where
every single score was negative — top 5 averaging around **−2.2**, discarded
10 averaging around **−8.9**:

```
margin     = −2.2 − (−8.9) = 6.7
confidence = 1 / (1 + e^−6.7) ≈ 0.9988
label      = "Strong"
```

Despite every raw score being negative, the *margin* is large, so this
correctly reads Strong — the old absolute-threshold version would have
called this "Weak" purely because every number was negative, regardless of
how well-separated the top chunks actually were from the noise.

**Edge case:** if fewer than 5 candidates exist at all (tiny ingested repo),
there's no discarded tail to compare against — `baseline` falls back to
`top_avg`, making `margin = 0` and `confidence = sigmoid(0) = 0.5` exactly,
landing in "Moderate." That's deliberate: it's "can't assess distinctiveness
here," not a claim of either strong or weak grounding.

**Known limitation, stated plainly:** the `0.75`/`0.5` cutoffs are still a
judgment call — margin-based rather than absolute fixes the *domain
mismatch* bug, but the exact bucket boundaries haven't been validated
against a labeled dataset of real question/answer pairs. If "Weak" or
"Strong" starts looking miscalibrated once you've used this on real repos
for a while, those two numbers are what to adjust — not the underlying
relative-margin approach.

## Project Structure

```
.
├── .env.example
├── ingest.py              # CLI: clone, chunk, embed, store a repo
├── api/                   # FastAPI backend
│   ├── main.py            # 5 endpoints: health, repos, ingest (+SSE progress), chat (SSE)
│   ├── jobs.py            # in-memory background ingestion job tracking (no Celery/Redis — not needed at this scale)
│   └── schemas.py         # Pydantic request models
├── frontend/              # Next.js UI
│   ├── app/               # layout, page, global styles/design tokens
│   ├── components/        # Sidebar, ChatPanel, ChatMessage, CitationCard,
│   │                        MarkdownMessage, Badges, ThinkingOrbs, ThemeToggle,
│   │                        LoadingScreen, DeadScreen, CopyButton, IngestStepper
│   ├── lib/               # api.ts (typed client + SSE parsing), theme.tsx,
│   │                        incompleteMarkdown.ts (streaming markdown buffering)
│   └── README.md          # frontend-specific setup notes
└── rag_core/              # Shared business logic — used by BOTH app.py and api/
    ├── chunking.py        # language-aware splitting, line-number resolution, lockfile exclusion
    ├── embeddings.py      # local sentence-transformers wrapper (lazy-imported)
    ├── vector_store.py    # ChromaDB wrapper: per-repo collections, singleton, commit_sha metadata
    ├── reranker.py        # local cross-encoder reranking (lazy-imported)
    ├── llm_client.py      # Gemini + OpenRouter clients: streaming, retry/failover, query condensation
    ├── ingestion.py       # orchestrates clone -> chunk -> embed -> store, captures commit SHA
    └── retrieval.py       # orchestrates routing -> condense -> retrieve -> rerank -> generate
```

A few implementation details worth knowing if you're extending this:

- **`embeddings.py`/`reranker.py` import `sentence_transformers` lazily**,
  inside `__init__`, not at module level. That import drags in `torch`,
  which is slow (seconds, not milliseconds) — importing it at module level
  would block the UI from rendering anything until it finished.
- **`get_vector_store()` is a process-level singleton** (`functools.lru_cache`).
  `chromadb.PersistentClient` has a real one-time warmup cost; without this,
  that cost would be paid on every question / every Streamlit rerun.
- **Ingestion is a full rebuild, not incremental.** Re-running ingest on a
  repo re-clones and re-embeds everything. Also: ingestion shallow-clones
  (`git clone --depth 1`), so no git history exists locally beyond the
  ingested commit — worth knowing if you ever build a "explain this diff"
  feature, since that needs history this pipeline doesn't keep.

## Scope

**In scope:** public repo ingestion, language-aware chunking (with lockfile
exclusion), local embeddings, semantic retrieval + reranking, streamed
grounded answer generation with markdown rendering, file/line citations with
previews and GitHub permalinks, follow-up question handling, retrieval
routing, a groundedness indicator, multi-provider failover, stop/retry, dark
mode.

**Out of scope:** private repos, multiple repos queried simultaneously,
control/data-flow analysis, code generation/modification, incremental
re-ingestion, conversation history persistence (each session is in-memory
only — see the project's architecture-planning doc for what that would take).