"""
FastAPI backend — wraps rag_core for the planned Next.js frontend.

This is the first half of the Streamlit -> FastAPI + Next.js migration
(see the project's future-architecture-plans doc). It runs ALONGSIDE the
existing app.py Streamlit UI, not as a replacement — app.py is untouched.
Once this backend is verified working (via curl / the auto-generated
/docs page), the Next.js frontend gets built against it.
"""
