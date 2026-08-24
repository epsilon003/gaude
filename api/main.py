"""
FastAPI backend for the Grounded Q&A RAG system.

Endpoints:
  POST /api/repos/ingest              {repo_url}                    -> {job_id}
  GET  /api/repos/ingest/{job_id}/events                             -> SSE progress stream
  GET  /api/repos                                                    -> list of ingested repos
  POST /api/chat                      {collection, question, history} -> SSE token stream + final event
  GET  /api/health                                                   -> {status: "ok"}

Run locally:  uvicorn api.main:app --reload --port 8000
Docs (Swagger UI, auto-generated): http://localhost:8000/docs
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from api.jobs import create_job, get_job, run_ingestion
from api.schemas import ChatRequest, IngestRequest
from rag_core.retrieval import answer_question_stream
from rag_core.vector_store import get_vector_store

load_dotenv()

app = FastAPI(title="Grounded Q&A RAG API", version="0.1.0")

# Comma-separated list so both the Next.js dev server and a deployed prod
# origin can be allowed at once, e.g. FRONTEND_ORIGINS="http://localhost:3000,https://myapp.vercel.app"
# Both localhost and 127.0.0.1 variants are included by default: browsers
# treat them as different origins for CORS purposes even though they're the
# same machine, and which one gets used depends on how the dev server URL
# was opened/typed.
_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
_frontend_origins = os.environ.get("FRONTEND_ORIGINS", _default_origins).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _frontend_origins if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/repos/ingest")
def start_ingest(payload: IngestRequest, background_tasks: BackgroundTasks):
    if not payload.repo_url.strip():
        raise HTTPException(status_code=400, detail="repo_url is required")
    job = create_job()
    background_tasks.add_task(run_ingestion, job, payload.repo_url.strip())
    return {"job_id": job.id}


@app.get("/api/repos/ingest/{job_id}/events")
def ingest_events(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    def _stream():
        # Plain (sync) generator — Starlette runs sync generators passed to
        # StreamingResponse in a thread pool, so the blocking queue.get()
        # below doesn't block the server's event loop.
        while True:
            item = job.events.get()
            if item is None:  # sentinel set by run_ingestion() when finished
                break
            yield _sse(item)

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.get("/api/repos")
def list_repos():
    store = get_vector_store()
    return store.list_collections_with_info()


@app.post("/api/chat")
def chat(payload: ChatRequest):
    history = [(turn.question, turn.answer) for turn in payload.history]

    try:
        text_iter, handle = answer_question_stream(
            payload.collection, payload.question, chat_history=history
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    def _stream():
        for piece in text_iter:
            yield _sse({"event": "token", "text": piece})

        # `handle` is only fully populated once text_iter is exhausted, which
        # has just happened via the loop above.
        yield _sse(
            {
                "event": "done",
                "provider": handle.provider,
                "model": handle.model,
                "confidence": handle.confidence,
                "confidence_label": handle.confidence_label,
                "resolved_question": handle.resolved_question,
                "retrieval_seconds": handle.retrieval_seconds,
                "error": handle.error,
                "citations": [
                    {
                        "file_path": c.file_path,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                        "rerank_score": c.rerank_score,
                        "text": c.text,
                        "github_url": c.github_url,
                    }
                    for c in handle.citations
                ],
            }
        )

    return StreamingResponse(_stream(), media_type="text/event-stream")
