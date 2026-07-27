"""
Retrieval + generation pipeline (PRD FR-4, FR-5, FR-6).

Flow: vector search (over-fetch) -> cross-encoder rerank (precision pass) ->
build cited context -> LLM generation (Gemini -> OpenRouter fallback).
"""
from __future__ import annotations

from dataclasses import dataclass

from rag_core.llm_client import LLMClient, build_user_prompt
from rag_core.reranker import get_reranker
from rag_core.vector_store import VectorStore

TOP_K_RETRIEVE = 15  # cast a wide net from the vector store
TOP_K_FINAL = 5  # narrow down after reranking to keep the prompt tight


@dataclass
class Citation:
    file_path: str
    start_line: int
    end_line: int
    rerank_score: float


@dataclass
class AnswerResult:
    answer: str
    citations: list[Citation]
    provider: str
    model: str


def answer_question(
    collection_name: str,
    question: str,
    top_k_retrieve: int = TOP_K_RETRIEVE,
    top_k_final: int = TOP_K_FINAL,
) -> AnswerResult:
    store = VectorStore()
    candidates = store.query(collection_name, question, top_k=top_k_retrieve)

    if not candidates:
        return AnswerResult(
            answer=(
                "I couldn't find anything relevant in the ingested repository for "
                "this question. Try rephrasing, or confirm the repo was ingested "
                "successfully."
            ),
            citations=[],
            provider="none",
            model="none",
        )

    reranker = get_reranker()
    top_chunks = reranker.rerank(question, candidates, top_k=top_k_final)

    llm = LLMClient()
    prompt = build_user_prompt(question, top_chunks)
    result = llm.generate(user_prompt=prompt)

    citations = [
        Citation(
            file_path=c["file_path"],
            start_line=c["start_line"],
            end_line=c["end_line"],
            rerank_score=c.get("rerank_score", 0.0),
        )
        for c in top_chunks
    ]

    return AnswerResult(
        answer=result.answer,
        citations=citations,
        provider=result.provider,
        model=result.model,
    )
