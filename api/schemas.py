from __future__ import annotations

from pydantic import BaseModel


class IngestRequest(BaseModel):
    repo_url: str


class HistoryTurn(BaseModel):
    """A past (question, answer) pair. Modeled explicitly rather than as a
    raw tuple/array over the wire — self-documenting and avoids ambiguity
    about which position means what in a JSON array."""
    question: str
    answer: str


class ChatRequest(BaseModel):
    collection: str
    question: str
    history: list[HistoryTurn] = []
