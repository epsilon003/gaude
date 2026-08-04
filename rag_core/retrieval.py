"""
Retrieval + generation pipeline (PRD FR-4, FR-5, FR-6), plus:
  - retrieval routing: skip the vector store entirely for greetings/meta questions
  - conversation-aware follow-ups: condense a follow-up into a standalone query
    using recent chat history before retrieval
  - citation previews + GitHub permalinks
  - a heuristic groundedness ("confidence") indicator

Flow: route check -> (condense follow-up) -> vector search (over-fetch) ->
cross-encoder rerank (precision pass) -> build cited context -> LLM generation
(Gemini -> OpenRouter fallback).
"""
from __future__ import annotations

import math
import re
import time
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

# --- Retrieval routing -------------------------------------------------------
# Cheap, no-LLM-call heuristic to skip retrieval entirely for greetings/meta
# questions, instead of running a real search and awkwardly returning
# NO_CONTEXT_MESSAGE for something like "thanks!".
_GREETING_RE = re.compile(
    r"^(hi|hello|hey+|hiya|yo|sup|good\s?(morning|afternoon|evening)|"
    r"thanks?( you)?|ok(ay)?|cool|nice|great|awesome|bye|goodbye|see ya)[\s!.,]*$",
    re.IGNORECASE,
)
_META_RE = re.compile(
    r"^(what can you do\??|who are you\??|what are you\??|how do you work\??|"
    r"help\??|what is this\??|how does this work\??)$",
    re.IGNORECASE,
)
_GREETING_RESPONSE = (
    "Hey! Ask me anything about the ingested codebase — I'll answer using the "
    "actual retrieved code and cite my sources."
)
_META_RESPONSE = (
    "I'm a grounded Q&A assistant for this codebase. Ask a natural-language "
    "question (e.g. \"how does auth work?\" or \"where is X handled?\") and I'll "
    "retrieve relevant code/doc chunks and answer using only that context, with "
    "file + line citations you can verify."
)


def _route_question(question: str) -> str | None:
    """Returns a canned response if the question doesn't need retrieval at
    all, else None (meaning: proceed with real retrieval)."""
    normalized = question.strip()
    if not normalized:
        return _META_RESPONSE
    if _GREETING_RE.match(normalized):
        return _GREETING_RESPONSE
    if _META_RE.match(normalized):
        return _META_RESPONSE
    return None


# --- Confidence / groundedness -----------------------------------------------
def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _compute_confidence(all_scored: list[dict], top_k_final: int) -> tuple[float, str]:
    """Heuristic groundedness signal — NOT a calibrated probability.

    Deliberately RELATIVE, not absolute: it measures how much better the
    cited (top_k_final) chunks scored than the rest of the retrieved-but-
    discarded pool, rather than comparing the raw score against a fixed
    threshold.

    Why: cross-encoder rerank scores are un-normalized logits whose actual
    range depends heavily on how close the content is to what the model was
    trained on. ms-marco-MiniLM-L-6-v2 was trained on MS MARCO — web search
    queries against natural-language prose — and has never seen source code,
    so its scores for code chunks run in a different (typically lower) range
    than for the prose it was calibrated on. A fixed absolute threshold
    picked by eyeballing generic score ranges will systematically misjudge
    domains the model wasn't trained on (this is exactly what caused
    groundedness to read "Weak" almost universally for a code Q&A tool).
    Comparing top-scored vs. bottom-scored chunks from the SAME retrieval
    call sidesteps that: whatever the model's absolute range is for this
    content, "meaningfully better than the discarded tail" is a comparison
    against itself, not against a number tuned for a different domain.

    all_scored: every candidate returned by Reranker.score() (already sorted
    descending, includes ones NOT selected as citations).
    """
    if not all_scored:
        return 0.0, "None"

    top = all_scored[:top_k_final]
    discarded = all_scored[top_k_final:]

    top_avg = sum(c["rerank_score"] for c in top) / len(top)
    if discarded:
        baseline = sum(c["rerank_score"] for c in discarded) / len(discarded)
    else:
        # Fewer candidates existed than top_k_final — nothing to compare
        # against, so we can't judge distinctiveness. Defaults to Moderate
        # via margin=0 below rather than claiming false confidence.
        baseline = top_avg

    margin = top_avg - baseline  # >= 0 by construction (top is always the highest-scored subset)
    confidence = _sigmoid(margin)
    if confidence >= 0.75:
        label = "Strong"
    elif confidence >= 0.5:
        label = "Moderate"
    else:
        label = "Weak"
    return confidence, label


# --- GitHub permalinks --------------------------------------------------------
def _build_github_url(
    source_url: str | None, commit_sha: str | None, file_path: str, start_line: int, end_line: int
) -> str | None:
    """None if we don't have enough info (older collections ingested before
    commit_sha was tracked, or a non-GitHub source) — callers fall back to
    plain file:line text in that case."""
    if not source_url or not commit_sha or "github.com" not in source_url:
        return None
    base = source_url.rstrip("/")
    if base.endswith(".git"):
        base = base[:-4]
    return f"{base}/blob/{commit_sha}/{file_path}#L{start_line}-L{end_line}"


@dataclass
class Citation:
    file_path: str
    start_line: int
    end_line: int
    rerank_score: float
    text: str = ""
    github_url: str | None = None


@dataclass
class AnswerResult:
    answer: str
    citations: list[Citation]
    provider: str
    model: str
    confidence: float = 0.0
    confidence_label: str = "N/A"
    resolved_question: str | None = None  # the standalone/condensed question actually used, if different
    retrieval_seconds: float = 0.0  # time spent in vector search + reranking, excludes generation


@dataclass
class StreamAnswerHandle:
    """Mutable sidecar returned alongside the streaming text iterator.
    citations/confidence/retrieval_seconds are known immediately (retrieval/
    rerank happen eagerly, before any streaming starts); provider/model/error
    are only known once the iterator has been fully consumed."""
    citations: list[Citation] = field(default_factory=list)
    confidence: float = 0.0
    confidence_label: str = "N/A"
    resolved_question: str | None = None
    retrieval_seconds: float = 0.0
    provider: str | None = None
    model: str | None = None
    error: str | None = None


def _retrieve_and_rerank(
    collection_name: str, question: str, top_k_retrieve: int, top_k_final: int
) -> tuple[list[dict], list[dict], list[Citation]]:
    """Shared by answer_question and answer_question_stream. `question` here
    should already be the resolved/standalone question (post-condensation).
    Returns (top_chunks, all_scored, citations):
      - top_chunks: the top_k_final chunks used for the LLM prompt
      - all_scored: the full retrieved-and-scored pool (for _compute_confidence)
      - citations: Citation objects for top_chunks
    All three are empty if nothing was retrieved."""
    store = get_vector_store()
    candidates = store.query(collection_name, question, top_k=top_k_retrieve)
    if not candidates:
        return [], [], []

    reranker = get_reranker()
    all_scored = reranker.score(question, candidates)
    top_chunks = all_scored[:top_k_final]

    collection_meta = store.get_collection_metadata(collection_name)
    source_url = collection_meta.get("source_url")
    commit_sha = collection_meta.get("commit_sha")

    citations = [
        Citation(
            file_path=c["file_path"],
            start_line=c["start_line"],
            end_line=c["end_line"],
            rerank_score=c.get("rerank_score", 0.0),
            text=c.get("text", ""),
            github_url=_build_github_url(
                source_url, commit_sha, c["file_path"], c["start_line"], c["end_line"]
            ),
        )
        for c in top_chunks
    ]
    return top_chunks, all_scored, citations


def _resolve_question(llm: LLMClient, question: str, chat_history: list[tuple[str, str]] | None) -> str:
    """Condense a follow-up into a standalone question using recent chat
    history. Returns `question` unchanged if there's no history to work with
    (condense_query itself also fails open on any LLM error)."""
    if not chat_history:
        return question
    return llm.condense_query(question, chat_history)


def answer_question(
    collection_name: str,
    question: str,
    chat_history: list[tuple[str, str]] | None = None,
    top_k_retrieve: int = TOP_K_RETRIEVE,
    top_k_final: int = TOP_K_FINAL,
) -> AnswerResult:
    routed = _route_question(question)
    if routed is not None:
        return AnswerResult(answer=routed, citations=[], provider="none", model="none")

    llm = LLMClient()
    t0 = time.perf_counter()
    resolved_question = _resolve_question(llm, question, chat_history)

    top_chunks, all_scored, citations = _retrieve_and_rerank(
        collection_name, resolved_question, top_k_retrieve, top_k_final
    )
    retrieval_seconds = time.perf_counter() - t0
    if not top_chunks:
        return AnswerResult(answer=NO_CONTEXT_MESSAGE, citations=[], provider="none", model="none")

    prompt = build_user_prompt(resolved_question, top_chunks)
    result = llm.generate(user_prompt=prompt)
    confidence, confidence_label = _compute_confidence(all_scored, top_k_final)

    return AnswerResult(
        answer=result.answer,
        citations=citations,
        provider=result.provider,
        model=result.model,
        confidence=confidence,
        confidence_label=confidence_label,
        resolved_question=resolved_question if resolved_question != question else None,
        retrieval_seconds=retrieval_seconds,
    )


def answer_question_stream(
    collection_name: str,
    question: str,
    chat_history: list[tuple[str, str]] | None = None,
    top_k_retrieve: int = TOP_K_RETRIEVE,
    top_k_final: int = TOP_K_FINAL,
) -> tuple[Iterator[str], StreamAnswerHandle]:
    """
    Streaming counterpart to answer_question(). Routing, condensation,
    retrieval, and reranking all happen eagerly (fast — not worth streaming),
    so handle.citations/confidence/resolved_question/retrieval_seconds are populated before
    this function even returns. Only LLM generation is streamed; iterate the
    returned generator (e.g. via st.write_stream) to get text as it arrives.
    handle.provider/handle.model/handle.error are populated once the
    iterator is exhausted.
    """
    routed = _route_question(question)
    if routed is not None:
        handle = StreamAnswerHandle(provider="none", model="none")

        def _routed() -> Iterator[str]:
            yield routed

        return _routed(), handle

    llm = LLMClient()
    t0 = time.perf_counter()
    resolved_question = _resolve_question(llm, question, chat_history)

    top_chunks, all_scored, citations = _retrieve_and_rerank(
        collection_name, resolved_question, top_k_retrieve, top_k_final
    )
    retrieval_seconds = time.perf_counter() - t0
    confidence, confidence_label = _compute_confidence(all_scored, top_k_final)
    handle = StreamAnswerHandle(
        citations=citations,
        confidence=confidence,
        confidence_label=confidence_label,
        resolved_question=resolved_question if resolved_question != question else None,
        retrieval_seconds=retrieval_seconds,
    )

    if not top_chunks:
        def _no_context() -> Iterator[str]:
            handle.provider = "none"
            handle.model = "none"
            yield NO_CONTEXT_MESSAGE

        return _no_context(), handle

    prompt = build_user_prompt(resolved_question, top_chunks)
    text_iter, gen_handle = llm.generate_stream(user_prompt=prompt)

    def _wrapped() -> Iterator[str]:
        yield from text_iter
        # gen_handle is only fully populated once text_iter is exhausted,
        # which has just happened via the yield from above.
        handle.provider = gen_handle.provider
        handle.model = gen_handle.model
        handle.error = gen_handle.error

    return _wrapped(), handle