import subprocess
import sys
from pathlib import Path

repository_root = Path(__file__).resolve().parents[1]
backend_dir = repository_root / "backend"

raise SystemExit(
    subprocess.call(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
    )
)
