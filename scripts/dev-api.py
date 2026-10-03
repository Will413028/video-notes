"""專案獨占、持久化的本機 PostgreSQL 與 FastAPI；不使用外部憑證。"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
runtime = ROOT / "backend/.runtime-db"
if runtime.is_symlink():
    raise SystemExit("拒絕 symlink 資料庫目錄。")
runtime.mkdir(exist_ok=True, mode=0o700)
runtime.chmod(0o700)
data, socket = runtime / "data", runtime / "socket"
socket.mkdir(exist_ok=True)
env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
if data.exists():
    if not (runtime / ".video-notes-owned").exists():
        raise SystemExit("拒絕使用不是此腳本建立的資料庫目錄。")
else:
    subprocess.run(
        [
            "initdb",
            "-D",
            str(data),
            "-U",
            "video_notes_local",
            "--auth=trust",
            "--encoding=UTF8",
            "--no-locale",
        ],
        check=True,
        env=env,
    )
    (runtime / ".video-notes-owned").write_text("video-notes-v1")
subprocess.run(
    [
        "pg_ctl",
        "-D",
        str(data),
        "-l",
        str(runtime / "postgres.log"),
        "-o",
        f"-k {socket} -c listen_addresses=''",
        "-w",
        "start",
    ],
    check=True,
    env=env,
)
try:
    env["VIDEO_NOTES_DATABASE_URL"] = (
        f"postgresql+psycopg://video_notes_local@/postgres?host={socket}"
    )
    subprocess.run(
        [
            "uv",
            "run",
            "--directory",
            str(ROOT / "backend"),
            "--no-sync",
            "alembic",
            "upgrade",
            "head",
        ],
        check=True,
        env=env,
    )
    subprocess.run(
        [
            "uv",
            "run",
            "--directory",
            str(ROOT / "backend"),
            "--no-sync",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8422",
            "--reload",
        ],
        env=env,
        check=False,
    )
except KeyboardInterrupt:
    pass
finally:
    subprocess.run(["pg_ctl", "-D", str(data), "-m", "fast", "-w", "stop"], env=env, check=True)
