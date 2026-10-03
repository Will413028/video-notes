"""在隔離 backend 副本破壞認證／CSRF／過期／錯誤清理。"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if os.environ.get("VIDEO_NOTES_ISOLATED_TEST_DB") != "1":
    raise SystemExit("請用 with-test-postgres.py 啟動隔離 DB，再執行 auth mutation。")
CASES = [
    (
        "auth.py",
        "def current_user(request: Request, response: Response, db: Database):",
        'def current_user(request: Request, response: Response, db: Database):\n    return User(id=__import__("uuid").UUID(int=0), email="forged@example.test")',
        "test_auth_forged_session_rejected",
        1,
        "AUTH_GUARD_ASSERTION",
    ),
    (
        "auth.py",
        "def csrf(request: Request):",
        "def csrf(request: Request):\n    return",
        "test_auth_csrf_rejected",
        5,
        "AssertionError",
    ),
    (
        "auth.py",
        "or session.absolute_expires_at <= clock\n        or session.last_seen_at + IDLE <= clock",
        "or False",
        "test_auth_expired_session_rejected",
        2,
        "AssertionError",
    ),
    (
        "main.py",
        "@app.exception_handler(RequestValidationError)",
        "# Restore the default validation handler",
        "test_auth_validation_does_not_echo_password",
        2,
        "PASSWORD_REDACTION_ASSERTION",
    ),
]

for filename, needle, replacement, name, count, assertion in CASES:
    with tempfile.TemporaryDirectory(
        prefix="auth-mutation-", dir=ROOT / "docs/plans/2026-10-01-rebuild"
    ) as temporary:
        copied = Path(temporary)
        for directory in ["app", "tests", "migrations"]:
            shutil.copytree(
                ROOT / "backend" / directory,
                copied / directory,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        for file in ["pyproject.toml", "alembic.ini"]:
            shutil.copyfile(ROOT / "backend" / file, copied / file)
        target = copied / "app" / filename
        original = target.read_text()
        assert original.count(needle) == 1, f"mutation target 改變：{filename}"
        target.write_text(original.replace(needle, replacement))
        result = subprocess.run(
            [str(ROOT / "backend/.venv/bin/python"), "-m", "pytest", "-k", name, "--tb=short"],
            cwd=copied,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if (
            result.returncode != 1
            or f"{count} failed" not in result.stdout
            or assertion not in result.stdout
        ):
            raise SystemExit(f"mutation 未被指定測試攔下：{name}\n{result.stdout}\n{result.stderr}")
        print(f"PASS：{name} 拒絕 mutation", flush=True)
