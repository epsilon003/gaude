"""
LLM generation client — free-tier only, with automatic failover.

Primary: Google AI Studio (Gemini), via its OpenAI-compatible endpoint.
Fallback: OpenRouter's free-tier models (":free" suffix models, no cost).

Both providers speak the OpenAI chat-completions API, so we use the `openai`
SDK for both and just swap base_url/api_key/model. This makes it trivial to
add a third provider (Groq, Cerebras, etc.) later — just add another tier to
the `_PROVIDERS` list.

Free tiers get rate-limited or occasionally deprecate models without warning,
so every call falls through to the next provider on failure rather than
surfacing an error straight to the user (PRD FR-7 / NFR-1 reliability).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
DEFAULT_OPENROUTER_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
)

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


@dataclass
class GenerationResult:
    answer: str
    provider: str
    model: str


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
            self._providers.append(
                _Provider(
                    name="openrouter",
                    client=OpenAI(base_url=OPENROUTER_BASE_URL, api_key=openrouter_key),
                    model=DEFAULT_OPENROUTER_MODEL,
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
                errors.append(f"{provider.name} ({provider.model}): {exc}")
                continue

        raise RuntimeError(
            "All configured LLM providers failed.\n" + "\n".join(errors)
        )


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
