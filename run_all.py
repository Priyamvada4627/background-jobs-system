"""
Root forwarder for backend/run_all.py
Allows Render or any cloud host to run either 'python run_all.py' or 'python backend/run_all.py'.
"""
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import run_all

if __name__ == "__main__":
    run_all.main()
