"""
LLM generation client — free-tier only, with automatic failover.

Free tiers get rate-limited or occasionally deprecate models without warning,
so every call falls through to the next provider on failure rather than
surfacing an error straight to the user (PRD FR-7 / NFR-1 reliability).
"""
from __future__ import annotations

import os
import time
from collections.abc import Iterator 
from dataclasses import dataclass
from functools import lru_cache

from openai import OpenAI

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
EXPLICIT_OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL")
OPENROUTER_AUTO_FREE_MODEL = "openrouter/free"

# Transient errors (rate limits, momentary overload) are worth a quick retry on the SAME provider before burning a fallback tier on them.
RETRYABLE_STATUS_CODES = {429, 503}
MAX_RETRIES_PER_PROVIDER = 2
RETRY_BACKOFF_SECONDS = 2

SYSTEM_PROMPT = """You are a grounded Q&A assistant for a codebase. Answer ONLY using \
the provided context chunks (retrieved code/documentation snippets). Every claim you \
make must be traceable to a specific chunk.

Rules:
- If the context does not contain enough information to answer, say so explicitly \
instead of guessing or using outside knowledge.
- When you reference code behavior, cite the chunk number it came from, e.g. [chunk 2].
- Be concise and technical. Assume the reader is a developer familiar with the domain.
- Do not invent file paths, function names, or line numbers that are not present in \
the provided context.
"""

CONDENSE_SYSTEM_PROMPT = """Given a conversation history and a follow-up question, \
rewrite the follow-up as a fully standalone question that makes sense with no \
knowledge of the conversation history. Preserve the original intent and phrasing \
style exactly — do not add new claims or narrow/broaden the scope. If the follow-up \
is already standalone, return it completely unchanged. Output ONLY the rewritten \
question and nothing else — no preamble, no quotes, no explanation."""


@dataclass
class GenerationResult:
    answer: str
    provider: str
    model: str

@dataclass
class GenerationHandle:
    """Mutable sidecar for streaming generation: which provider/model ended up
    answering, and any terminal error — populated once the stream from
    generate_stream() is fully consumed."""
    provider: str | None = None
    model: str | None = None
    error: str | None = None

@dataclass
class _Provider:
    name: str
    client: OpenAI
    model: str


class LLMClient:
    def __init__(self):
        self._providers: list[_Provider] = []

        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            self._providers.append(
                _Provider(
                    name="gemini",
                    client=OpenAI(base_url=GEMINI_BASE_URL, api_key=gemini_key),
                    model=DEFAULT_GEMINI_MODEL,
                )
            )

        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if openrouter_key:
            openrouter_client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=openrouter_key)
            if EXPLICIT_OPENROUTER_MODEL:
                self._providers.append(
                    _Provider(
                        name="openrouter",
                        client=openrouter_client,
                        model=EXPLICIT_OPENROUTER_MODEL,
                    )
                )
            # Always present when a key exists: the auto-router picks whatever
            # free model is actually alive right now, so this tier keeps
            # working even as the free lineup changes underneath us.
            self._providers.append(
                _Provider(
                    name="openrouter-auto",
                    client=openrouter_client,
                    model=OPENROUTER_AUTO_FREE_MODEL,
                )
            )

        if not self._providers:
            raise RuntimeError(
                "No LLM provider configured. Set GEMINI_API_KEY and/or "
                "OPENROUTER_API_KEY in your .env file."
            )

    def generate(
        self,
        user_prompt: str,
        system_prompt: str = SYSTEM_PROMPT,
        max_tokens: int = 1000,
        temperature: float = 0.2,
    ) -> GenerationResult:
        errors = []
        for provider in self._providers:
            for attempt in range(1, MAX_RETRIES_PER_PROVIDER + 1):
                try:
                    response = provider.client.chat.completions.create(
                        model=provider.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    answer = response.choices[0].message.content
                    return GenerationResult(answer=answer, provider=provider.name, model=provider.model)
                except Exception as exc:  # noqa: BLE001 - deliberately broad: any provider failure should fail over
                    status_code = getattr(exc, "status_code", None)
                    is_retryable = status_code in RETRYABLE_STATUS_CODES
                    if is_retryable and attempt < MAX_RETRIES_PER_PROVIDER:
                        time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                        continue
                    errors.append(f"{provider.name} ({provider.model}): {exc}")
                    break

        raise RuntimeError(
            "All configured LLM providers failed.\n" + "\n".join(errors)
        )
    def condense_query(self, question: str, history: list[tuple[str, str]]) -> str:
        """
        Rewrite a follow-up question into a standalone one using recent chat
        history, so retrieval (which only sees the rewritten text) actually
        finds relevant chunks for questions like "what about its error
        handling?" that make no sense in isolation.

        history: list of (question, answer) tuples, oldest first. Only the
        last 3 turns are used to keep this cheap and fast.

        Fails open: if this call errors for any reason (rate limit, network,
        all providers down), returns the original question unchanged rather
        than blocking the whole pipeline on a non-essential step.
        """
        if not history:
            return question

        recent = history[-3:]
        history_text = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in recent)
        prompt = (
            f"Conversation history:\n{history_text}\n\n"
            f"Follow-up question: {question}\n\nStandalone question:"
        )
        try:
            result = self.generate(
                user_prompt=prompt,
                system_prompt=CONDENSE_SYSTEM_PROMPT,
                max_tokens=150,
                temperature=0.0,
            )
            condensed = (result.answer or "").strip().strip('"')
            return condensed if condensed else question
        except Exception:  # noqa: BLE001
            return question
        
    def generate_stream(
        self,
        user_prompt: str,
        system_prompt: str = SYSTEM_PROMPT,
        max_tokens: int = 1000,
        temperature: float = 0.2,
    ) -> tuple[Iterator[str], GenerationHandle]:
        handle = GenerationHandle()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        def _generator() -> Iterator[str]:
            errors = []
            for provider in self._providers:
                for attempt in range(1, MAX_RETRIES_PER_PROVIDER + 1):
                    try:
                        stream = provider.client.chat.completions.create(
                            model=provider.model,
                            messages=messages,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            stream=True,
                        )
                        # Pulling the first chunk here (still inside the try)
                        # is what actually fires the HTTP request and surfaces
                        # provider-level errors (bad model, rate limit, etc.)
                        # before we've shown the user anything.
                        first_chunk = next(stream, None)
                    except Exception as exc:  # noqa: BLE001
                        status_code = getattr(exc, "status_code", None)
                        is_retryable = status_code in RETRYABLE_STATUS_CODES
                        if is_retryable and attempt < MAX_RETRIES_PER_PROVIDER:
                            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                            continue
                        errors.append(f"{provider.name} ({provider.model}): {exc}")
                        break

                    handle.provider = provider.name
                    handle.model = provider.model

                    if first_chunk is not None and first_chunk.choices:
                        delta = getattr(first_chunk.choices[0].delta, "content", None)
                        if delta:
                            yield delta                
                    for chunk in stream:
                        if not chunk.choices:
                            continue
                        delta = getattr(chunk.choices[0].delta, "content", None)
                        if delta:
                            yield delta
                    return

            handle.error = "All configured LLM providers failed.\n" + "\n".join(errors)

        return _generator(), handle


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """Cached singleton, same pattern as get_vector_store()/get_reranker().
    Raises RuntimeError (uncached, per functools.lru_cache semantics) if no
    provider is configured -- callers should catch that at the point where
    a missing provider should actually surface as a user-facing error."""
    return LLMClient()


def build_context_block(chunks: list[dict]) -> str:
    """Turn retrieved/reranked chunks into a numbered context block for the prompt,
    and return the formatted string. Citation mapping (chunk number -> source) is
    handled separately by the caller so the UI can render clickable-looking refs."""
    lines = []
    for i, c in enumerate(chunks, start=1):
        loc = f"{c['file_path']}:{c['start_line']}-{c['end_line']}"
        lines.append(f"[chunk {i}] ({loc})\n{c['text']}\n")
    return "\n".join(lines)


def build_user_prompt(question: str, chunks: list[dict]) -> str:
    context_block = build_context_block(chunks)
    return (
        f"Context chunks retrieved from the codebase:\n\n{context_block}\n"
        f"---\n\nQuestion: {question}\n\nAnswer using only the context above."
    )