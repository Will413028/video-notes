"""在附件內隔離副本交換匯出 start/end，要求具名 assertion 攔下。"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(
    prefix="subtitle-mutation-", dir=ROOT / "docs/plans/2026-10-01-rebuild"
) as temporary:
    copied = Path(temporary)
    for directory in ["app", "tests"]:
        shutil.copytree(
            ROOT / "backend" / directory,
            copied / directory,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    shutil.copyfile(ROOT / "backend/pyproject.toml", copied / "pyproject.toml")
    target = copied / "app/subtitles.py"
    original = target.read_text()
    assert original.count("format_time(segment.start, separator)") == 1
    assert original.count("format_time(segment.end, separator)") == 1
    mutated = original.replace("format_time(segment.start, separator)", "MUTATION_START")
    mutated = mutated.replace(
        "format_time(segment.end, separator)", "format_time(segment.start, separator)"
    )
    mutated = mutated.replace("MUTATION_START", "format_time(segment.end, separator)")
    assert mutated.count("format_time(segment.start, separator)") == 1
    assert mutated.count("format_time(segment.end, separator)") == 1
    target.write_text(mutated)
    result = subprocess.run(
        [
            str(ROOT / "backend/.venv/bin/python"),
            "-m",
            "pytest",
            "-k",
            "test_subtitles_export_interval_mapping",
            "--tb=short",
        ],
        cwd=copied,
        env={key: value for key, value in os.environ.items() if key != "VIDEO_NOTES_DATABASE_URL"},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if (
        result.returncode != 1
        or "SUBTITLE_INTERVAL_ASSERTION" not in result.stdout
        or "1 failed" not in result.stdout
    ):
        raise SystemExit(
            f"字幕 mutation 未被預期 assertion 攔下：\n{result.stdout}\n{result.stderr}"
        )
    print("PASS：交換字幕 start/end 被 SUBTITLE_INTERVAL_ASSERTION 攔下")
