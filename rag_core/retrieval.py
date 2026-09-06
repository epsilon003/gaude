"""
Retrieval orchestration: routing -> condense -> multi-query retrieve -> rerank -> generate.
Matches the synchronous (text_iter, handle) interface expected by api/main.py.
"""
from __future__ import annotations
import math
import re
import json
import os
import time
from dataclasses import dataclass, field
from typing import Generator
from openai import OpenAI

from rag_core.vector_store import get_vector_store
from rag_core.reranker import get_reranker

@dataclass
class Citation:
    file_path: str
    start_line: int
    end_line: int
    rerank_score: float
    text: str
    github_url: str | None = None

@dataclass
class Handle:
    provider: str = ""
    model: str = ""
    confidence: float = 0.0
    confidence_label: str = "Weak"
    resolved_question: str = ""
    retrieval_seconds: float = 0.0
    error: str | None = None
    citations: list[Citation] = field(default_factory=list)

def _is_greeting_or_meta(query: str) -> bool:
    q = query.lower().strip()
    return q in ["hi", "hello", "hey", "thanks", "thank you", "what can you do", "help"] or len(q) < 5

def _expand_query(query: str) -> list[str]:
    """Generate 2 alternative phrasings for multi-query retrieval."""
    try:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/" if os.getenv("GEMINI_API_KEY") else "https://openrouter.ai/api/v1"
        model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash") if os.getenv("GEMINI_API_KEY") else os.getenv("OPENROUTER_MODEL", "openrouter/free")
        
        client = OpenAI(api_key=api_key, base_url=base_url)
        prompt = f"""Generate 2 alternative versions of this code search query to improve recall. 
Focus on technical synonyms and different phrasings. Return ONLY a JSON array of 2 strings.
Query: "{query}"
"""
        response = client.chat.completions.create(
            model=model, 
            messages=[{"role": "user", "content": prompt}], 
            temperature=0.2,
            timeout=5.0
        )
        match = re.search(r'\[.*\]', response.choices[0].message.content, re.DOTALL)
        if match: 
            return json.loads(match.group(0))
    except Exception:
        pass # Fallback silently
    return []

def retrieve_and_rerank(
    collection_name: str, 
    query: str, 
    top_k_retrieve: int = 15, 
    top_k_final: int = 5,
    where_filter: dict | None = None, 
    use_hybrid: bool = True,
) -> list[dict]:
    store = get_vector_store()
    reranker = get_reranker()
    
    # 1. Multi-query expansion
    alt_queries = _expand_query(query)
    all_queries = [query] + alt_queries
    
    # 2. Retrieve and deduplicate
    seen = set()
    raw_results = []
    for q in all_queries:
        results = store.query(collection_name, q, top_k=top_k_retrieve, where_filter=where_filter, use_hybrid=use_hybrid)
        for r in results:
            doc_id = f"{r['file_path']}:{r['start_line']}-{r['end_line']}"
            if doc_id not in seen:
                seen.add(doc_id)
                raw_results.append(r)
                
    raw_results = raw_results[:top_k_retrieve * 2]
    
    # 3. Rerank
    reranked = reranker.rerank(query, raw_results, top_k=top_k_final)
    return reranked

def _compute_confidence(reranked_results: list[dict], top_k_final: int = 5) -> tuple[float, str]:
    """Computes the relative margin confidence score."""
    cited = reranked_results[:top_k_final]
    discarded = reranked_results[top_k_final:]
    
    if not cited: 
        return 0.5, "Moderate"
        
    top_avg = sum(r.get("rerank_score", 0) for r in cited) / len(cited)
    baseline = sum(r.get("rerank_score", 0) for r in discarded) / len(discarded) if discarded else top_avg
    
    margin = top_avg - baseline
    confidence = 1 / (1 + math.exp(-margin))
    
    if confidence >= 0.75: 
        label = "Strong"
    elif confidence >= 0.50: 
        label = "Moderate"
    else: 
        label = "Weak"
        
    return confidence, label

def _build_github_url(source_url: str | None, commit_sha: str | None, file_path: str, start_line: int, end_line: int) -> str | None:
    if not source_url or not commit_sha or not source_url.startswith("https://github.com/"):
        return None
    return f"{source_url}/blob/{commit_sha}/{file_path}#L{start_line}-L{end_line}"

def answer_question_stream(
    collection_name: str,
    query: str,
    chat_history: list[tuple[str, str]] | None = None,
    where_filter: dict | None = None,
) -> tuple[Generator[str, None, None], Handle]:
    """
    Returns a tuple of (text_generator, handle).
    text_generator yields raw text tokens.
    handle is populated with metadata as the generator is exhausted.
    """
    handle = Handle()
    handle.resolved_question = query
    
    # 1. Handle greetings/meta queries without retrieval
    if _is_greeting_or_meta(query):
        def greeting_iter():
            handle.confidence = 1.0
            handle.confidence_label = "Strong"
            handle.provider = "system"
            handle.model = "routing"
            yield "Hello! I can help you understand this codebase. What would you like to know?"
        return greeting_iter(), handle

    # 2. Retrieve and Rerank
    start_time = time.time()
    try:
        reranked = retrieve_and_rerank(
            collection_name, query, top_k_retrieve=15, top_k_final=5, 
            where_filter=where_filter, use_hybrid=True
        )
    except Exception as exc:
        # Capture the error message in a variable that survives the except block
        err_msg = str(exc)
        handle.error = err_msg
        
        def err_iter():
            yield f"Error during retrieval: {err_msg}"
            
        return err_iter(), handle
        
    handle.retrieval_seconds = time.time() - start_time
    
    confidence, label = _compute_confidence(reranked)
    handle.confidence = confidence
    handle.confidence_label = label
    
    # 3. Populate citations (need collection metadata for GitHub URLs)
    store = get_vector_store()
    collection = store.get_or_create_collection(collection_name)
    meta = collection.metadata or {}
    source_url = meta.get("source_url")
    commit_sha = meta.get("commit_sha")

    for r in reranked:
        handle.citations.append(Citation(
            file_path=r["file_path"],
            start_line=r["start_line"],
            end_line=r["end_line"],
            rerank_score=r.get("rerank_score", 0.0),
            text=r["text"],
            github_url=_build_github_url(source_url, commit_sha, r["file_path"], r["start_line"], r["end_line"])
        ))

    # 4. Format prompt for LLM
    context = "\n\n".join([
        f"File: {r['file_path']} (Lines {r['start_line']}-{r['end_line']})\n```{r.get('language', 'text')}\n{r['text']}\n```"
        for r in reranked
    ])
    
    history_text = ""
    if chat_history:
        history_text = "\n".join([f"User: {q}\nAssistant: {a}" for q, a in chat_history[-4:]])

    prompt = f"""You are an expert software engineer answering questions about a codebase.
Answer the user's question based *only* on the provided context. 
If the context does not contain the answer, say "I don't have enough information in the provided code to answer that."
Cite the file and line numbers in your answer like [File: `path/to/file.py`, Lines: X-Y].

Context:
{context}

Chat History:
{history_text}

User Question: {query}
"""

    # 5. Stream LLM response
    api_key = os.getenv("GEMINI_API_KEY")
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    
    if not api_key:
        api_key = os.getenv("OPENROUTER_API_KEY")
        base_url = "https://openrouter.ai/api/v1"
        model = os.getenv("OPENROUTER_MODEL", "openrouter/free")
        
    handle.provider = "Gemini" if os.getenv("GEMINI_API_KEY") else "OpenRouter"
    handle.model = model

    def token_generator():
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                temperature=0.2
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            handle.error = str(exc)
            # Yield is safe here because it executes *during* the except block
            yield f"\n\nError generating response: {str(exc)}"

    return token_generator(), handle