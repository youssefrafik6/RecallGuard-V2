"""Read-only Streamlit Community Cloud entry point."""

import runpy
import sys
from pathlib import Path

dashboard = Path(__file__).resolve().parent
source = str(dashboard.parent / "src")
if source not in sys.path:
    sys.path.insert(0, source)
runpy.run_path(str(dashboard / "app.py"), init_globals={"PUBLIC_DEMO": True})
