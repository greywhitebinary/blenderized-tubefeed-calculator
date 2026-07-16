"""Quick check that app/streamlit_app.py imports resolve without error."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Importing the module exercises all its imports (src.*, streamlit, pandas, etc.)
import app.streamlit_app  # noqa: F401

print("IMPORTS OK")