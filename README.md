# Grounded Q&A System for Internal Codebases (RAG) MVP

Ask natural-language questions about a public GitHub repository and get answers
grounded in the actual code and docs, with file + line-number citations you can
verify. Built as a fully **free-tier** stack — no paid APIs, no paid infra.

## Stack (all free)

| Component | Choice | Why |
|---|---|---|
| Chunking | LangChain `RecursiveCharacterTextSplitter.from_language()` | Splits on function/class boundaries instead of blind fixed-size cuts |
| Embeddings | `sentence-transformers` (`BAAI/bge-small-en-v1.5`) | Runs 100% locally, no API, no rate limits |
| Vector store | ChromaDB (persisted locally) | Embedded, zero-infra, free |
| Reranking | Local cross-encoder (`ms-marco-MiniLM-L-6-v2`) | Precision pass on top-k before generation |
| Generation (primary) | Google AI Studio — Gemini 2.5 Flash | Free tier, no card, 1M-token context if needed |
| Generation (fallback) | OpenRouter `:free` models (Llama 3.3 70B, etc.) | Automatic failover if Gemini's free quota is hit |
| UI | Streamlit | Simple chat UI, deploys free on Hugging Face Spaces |

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

3. **Set up environment variables:**
   ```bash
   cp .env.example .env
   ```
   Then fill in:
   - `GEMINI_API_KEY` — free key, no card required: https://aistudio.google.com/apikey
   - `OPENROUTER_API_KEY` — free key, no card required: https://openrouter.ai/keys

   You only strictly need one of the two, but both is recommended so the fallback
   actually has somewhere to fall back to.

4. **Ingest a GitHub repository** (CLI):
   ```bash
   python ingest.py --repo_url "https://github.com/owner/repo_name"
   ```
   This clones the repo, chunks it, embeds it locally, and stores it in
   `vector_store/` (a Chroma collection named after the repo).

   You can also ingest directly from the Streamlit sidebar (step 5).

5. **Start the app:**
   ```bash
   streamlit run app.py
   ```
   Open the local URL Streamlit prints (default `http://localhost:8501`).
   Ingest a repo from the sidebar, or pick one you already ingested via the CLI,
   then ask questions in the chat box.

## Usage

1. Paste a public GitHub repo URL into the sidebar and click **Ingest repo**.
2. Select the ingested repo from the dropdown.
3. Ask a question about the codebase in plain English.
4. The answer streams back with an expandable **Sources** section showing the
   exact `file_path:start_line-end_line` chunks it was grounded in.

## Deploying for free (Hugging Face Spaces)

1. Create a new Space at https://huggingface.co/new-space, SDK = **Streamlit**.
2. Push this repo's contents to the Space's git remote (the YAML frontmatter at
   the top of this README is what HF Spaces reads to configure the app).
3. In the Space's **Settings → Repository secrets**, add `GEMINI_API_KEY` and
   `OPENROUTER_API_KEY` (never commit `.env` — it's already gitignored).
4. The Space will build and serve `app.py` automatically.

Note: Spaces' free CPU tier persists storage only for the Space's lifetime and
resets on some restarts — fine for a demo/MVP, not for long-term production
storage of ingested repos.

## Project Structure

```
.
├── .env.example
├── .gitignore
├── requirements.txt
├── ingest.py              # CLI: clone, chunk, embed, store a repo
├── app.py                 # Streamlit UI: ingest + chat
├── rag_core/
│   ├── chunking.py         # Language-aware splitting + line-number resolution
│   ├── embeddings.py       # Local sentence-transformers wrapper
│   ├── vector_store.py     # ChromaDB wrapper (per-repo collections)
│   ├── reranker.py         # Local cross-encoder reranking
│   ├── llm_client.py       # Gemini primary + OpenRouter fallback, OpenAI-SDK based
│   ├── ingestion.py        # Orchestrates the ingest pipeline
│   └── retrieval.py        # Orchestrates retrieve -> rerank -> generate
└── vector_store/           # Local Chroma persistence (gitignored)
```

## Scope (MVP)

**In scope:** public repo ingestion, language-aware chunking, local embeddings,
semantic retrieval + reranking, grounded answer generation, file/line citations.

**Out of scope (per PRD):** private repos, multiple repos queried simultaneously,
control/data-flow analysis, code generation/modification, real-time re-ingestion.

## License

MIT License — see `LICENSE` (to be added).
