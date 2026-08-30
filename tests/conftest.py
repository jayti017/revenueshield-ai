"""
Makes `backend/` importable as the root of the `app` package when pytest is
run from the project root (RevenueShield/), so tests can simply do:

    from app.main import app

without needing to install the backend as a package.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
