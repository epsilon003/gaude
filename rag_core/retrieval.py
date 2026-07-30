"""
Retrieval + generation pipeline (PRD FR-4, FR-5, FR-6).

Flow: vector search (over-fetch) -> cross-encoder rerank (precision pass) ->
build cited context -> LLM generation (Gemini -> OpenRouter fallback).
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from rag_core.llm_client import GenerationHandle, LLMClient, build_user_prompt
from rag_core.reranker import get_reranker
from rag_core.vector_store import get_vector_store

TOP_K_RETRIEVE = 15  # cast a wide net from the vector store
TOP_K_FINAL = 5  # narrow down after reranking to keep the prompt tight

NO_CONTEXT_MESSAGE = (
    "I couldn't find anything relevant in the ingested repository for this "
    "question. Try rephrasing, or confirm the repo was ingested successfully."
)

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

@dataclass
class StreamAnswerHandle:
    """Mutable sidecar returned alongside the streaming text iterator.
    citations are known immediately (retrieval/rerank happen eagerly, before
    any streaming starts); provider/model/error are only known once the
    iterator has been fully consumed."""
    citations: list[Citation] = field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    error: str | None = None


def _retrieve_and_rerank(
    collection_name: str, question: str, top_k_retrieve: int, top_k_final: int
) -> tuple[list[dict], list[Citation]]:
    """Shared by answer_question and answer_question_stream. Returns
    (top_chunks, citations) — top_chunks is empty if nothing was retrieved."""
    store = get_vector_store()
    candidates = store.query(collection_name, question, top_k=top_k_retrieve)
    if not candidates:
        return [], []

    reranker = get_reranker()
    top_chunks = reranker.rerank(question, candidates, top_k=top_k_final)

    citations = [
        Citation(
            file_path=c["file_path"],
            start_line=c["start_line"],
            end_line=c["end_line"],
            rerank_score=c.get("rerank_score", 0.0),
        )
        for c in top_chunks
    ]
    return top_chunks, citations

def answer_question(
    collection_name: str,
    question: str,
    top_k_retrieve: int = TOP_K_RETRIEVE,
    top_k_final: int = TOP_K_FINAL,
) -> AnswerResult:
    top_chunks, citations = _retrieve_and_rerank(
        collection_name, question, top_k_retrieve, top_k_final
    )
    if not top_chunks:
        return AnswerResult(answer=NO_CONTEXT_MESSAGE, citations=[], provider="none", model="none")

    llm = LLMClient()
    prompt = build_user_prompt(question, top_chunks)
    result = llm.generate(user_prompt=prompt)

    return AnswerResult(
        answer=result.answer,
        citations=citations,
        provider=result.provider,
        model=result.model,
    )

def answer_question_stream(
    collection_name: str,
    question: str,
    top_k_retrieve: int = TOP_K_RETRIEVE,
    top_k_final: int = TOP_K_FINAL,
) -> tuple[Iterator[str], StreamAnswerHandle]:
    """
    Streaming counterpart to answer_question(). Retrieval + reranking happen
    eagerly (fast — not worth streaming), so handle.citations is populated
    before this function even returns. Only LLM generation is streamed;
    iterate the returned generator (e.g. via st.write_stream) to get text as
    it arrives. handle.provider/handle.model/handle.error are populated once
    the iterator is exhausted.
    """
    top_chunks, citations = _retrieve_and_rerank(
        collection_name, question, top_k_retrieve, top_k_final
    )
    handle = StreamAnswerHandle(citations=citations)

    if not top_chunks:
        def _no_context() -> Iterator[str]:
            handle.provider = "none"
            handle.model = "none"
            yield NO_CONTEXT_MESSAGE

        return _no_context(), handle

    llm = LLMClient()
    prompt = build_user_prompt(question, top_chunks)
    text_iter, gen_handle = llm.generate_stream(user_prompt=prompt)

    def _wrapped() -> Iterator[str]:
        yield from text_iter
        handle.provider = gen_handle.provider
        handle.model = gen_handle.model
        handle.error = gen_handle.error

    return _wrapped(), handle
