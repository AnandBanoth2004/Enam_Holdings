import subprocess
import sys
from pathlib import Path

repository_root = Path(__file__).resolve().parents[1]
backend_dir = repository_root / "backend"
seed_file = repository_root / "data" / "seed" / "demo_seed.json"

raise SystemExit(
    subprocess.call(
        [
            sys.executable,
            "-m",
            "finn_api.db.seed",
            "--file",
            str(seed_file),
        ],
        cwd=backend_dir,
    )
)
