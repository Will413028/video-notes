"""破壞下載邊界的隔離副本，確認具名測試攔下各項 mutation。"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    (
        "app/worker.py",
        'info.pop("requested_formats", None)',
        "pass",
        "test_muxed_selection_discards_preprocessed_merge_tracks",
        "FileNotFoundError",
    ),
    (
        "app/url_policy.py",
        "if not address.is_global or (mapped is not None and not mapped.is_global):",
        "if False:",
        "test_private_ip_is_rejected",
        "DID NOT RAISE",
    ),
    (
        "app/downloads.py",
        "self.store.cleanup(self.directory)",
        "pass",
        "test_transmission_error_still_cleans_directory",
        "AssertionError",
    ),
    (
        "app/downloads.py",
        'directory = self.root / f"job-{uuid4().hex}"',
        'directory = self.root / "job-fixed"',
        "test_store_unique_restart_cleanup_and_foreign_root",
        "FileExistsError",
    ),
    (
        "app/worker.py",
        'downloader.params["format"] = chosen.format_id',
        'chosen = video.formats[0]\n        downloader.params["format"] = chosen.format_id',
        "test_selected_format_overrides_ytdlp_default",
        "SELECTED_FORMAT_ASSERTION",
    ),
]

for filename, needle, replacement, test_name, expected in CASES:
    with tempfile.TemporaryDirectory(
        prefix="download-mutation-", dir=ROOT / "docs/plans/2026-10-01-rebuild"
    ) as temporary:
        copied = Path(temporary)
        for directory in ["app", "tests"]:
            shutil.copytree(
                ROOT / "backend" / directory,
                copied / directory,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        shutil.copyfile(ROOT / "backend/pyproject.toml", copied / "pyproject.toml")
        target = copied / filename
        original = target.read_text()
        assert original.count(needle) == 1, f"mutation target 已改變：{filename}"
        target.write_text(original.replace(needle, replacement))
        result = subprocess.run(
            [str(ROOT / "backend/.venv/bin/python"), "-m", "pytest", "-k", test_name, "--tb=short"],
            cwd=copied,
            env={
                key: value for key, value in os.environ.items() if key != "VIDEO_NOTES_DATABASE_URL"
            },
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        expected_count = 7 if test_name == "test_private_ip_is_rejected" else 1
        if (
            result.returncode != 1
            or expected not in result.stdout
            or f"{expected_count} failed" not in result.stdout
        ):
            raise SystemExit(
                f"mutation 未被預期測試攔下：{test_name}\n{result.stdout}\n{result.stderr}"
            )
        print(f"PASS：{test_name} 拒絕 {filename} mutation")
