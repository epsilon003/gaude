import os
import sys

# Ensures `import rag_core...` / `import api...` resolve when pytest is run
# from any working directory (e.g. `pytest` from repo root, or an IDE that
# runs individual test files directly).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
