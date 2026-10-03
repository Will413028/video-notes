import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
subprocess.run(
    ["uv", "run", "--directory", str(ROOT / "backend"), "--no-sync", "alembic", "upgrade", "head"],
    check=True,
)
raise SystemExit(subprocess.run(sys.argv[1:], cwd=ROOT, check=False).returncode)
