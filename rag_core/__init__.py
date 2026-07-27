"""
rag_core: Grounded Q&A System for Internal Codebases (RAG) MVP

All-free-tier stack:
- Embeddings: sentence-transformers (local, no API)
- Vector store: ChromaDB (local, embedded)
- Reranking: local cross-encoder
- Generation: Google AI Studio (Gemini) primary, OpenRouter free models as fallback
"""
