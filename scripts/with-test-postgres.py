"""以專案內獨占 PostgreSQL cluster 執行驗收；不用既有 DB／憑證。"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: with-test-postgres.py <command> [args...]")
    for tool in ["initdb", "pg_ctl", "createdb"]:
        if not shutil.which(tool):
            raise SystemExit(f"需要 PATH 中的 {tool}；此腳本不下載 PostgreSQL。")
    runtime = ROOT / "backend/.runtime-tests"
    runtime.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pg-", dir=runtime) as temporary:
        directory = Path(temporary)
        data, socket_dir = directory / "data", directory / "socket"
        socket_dir.mkdir()
        env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
        # Keep socket path short enough for PostgreSQL's Unix domain socket limit.
        socket_alias = Path(tempfile.mkdtemp(prefix="vn-pg-"))
        link = socket_alias / "s"
        link.symlink_to(socket_dir, target_is_directory=True)
        started = False
        try:
            subprocess.run(
                [
                    "initdb",
                    "-D",
                    str(data),
                    "-U",
                    "video_notes_test",
                    "--auth=trust",
                    "--no-locale",
                    "--encoding=UTF8",
                ],
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                [
                    "pg_ctl",
                    "-D",
                    str(data),
                    "-l",
                    str(directory / "postgres.log"),
                    "-o",
                    f"-F -k {link} -c listen_addresses=''",
                    "-w",
                    "start",
                ],
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            started = True
            subprocess.run(
                ["createdb", "-h", str(link), "-U", "video_notes_test", "video_notes_test"],
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            env["VIDEO_NOTES_DATABASE_URL"] = (
                f"postgresql+psycopg://video_notes_test@/video_notes_test?host={link}"
            )
            env["VIDEO_NOTES_ISOLATED_TEST_DB"] = "1"
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
                env=env,
                check=True,
            )
            result = subprocess.run(sys.argv[1:], cwd=ROOT, env=env, check=False)
            return result.returncode
        finally:
            if started:
                subprocess.run(
                    ["pg_ctl", "-D", str(data), "-m", "immediate", "-w", "stop"],
                    env=env,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            link.unlink(missing_ok=True)
            socket_alias.rmdir()


if __name__ == "__main__":
    raise SystemExit(main())
