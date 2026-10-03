"""在隔離 backend 副本破壞 title mapping，要求 browser E2E 拒絕。"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATTACHMENTS = ROOT / "docs/plans/2026-10-01-rebuild"

with tempfile.TemporaryDirectory(prefix="title-mutation-", dir=ATTACHMENTS) as temporary:
    copied = Path(temporary) / "backend"
    shutil.copytree(
        ROOT / "backend/app", copied / "app", ignore=shutil.ignore_patterns("__pycache__")
    )
    target = copied / "app/video.py"
    original = target.read_text()
    needle = 'title="用 AI 建立你的學習工作流"'
    assert original.count(needle) == 1, "mutation target 已改變，需更新 mutation"
    target.write_text(original.replace(needle, 'title="title-removed"'))
    env = {
        **{key: value for key, value in os.environ.items() if key != "VIDEO_NOTES_DATABASE_URL"},
        "VIDEO_NOTES_BACKEND_APP_DIR": str(copied),
        "VIDEO_NOTES_E2E_OUTPUT_DIR": str(Path(temporary) / "test-results"),
        "VIDEO_NOTES_TITLE_MUTATION": "1",
    }
    result = subprocess.run(
        [
            "pnpm",
            "--dir",
            str(ROOT / "frontend"),
            "exec",
            "playwright",
            "test",
            "--grep",
            "真實前後端",
            "--reporter=json",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(result.stderr)
        raise SystemExit("mutation reporter 未提供可解析 JSON")

    def all_results(suite):
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                yield from test.get("results", [])
        for child in suite.get("suites", []):
            yield from all_results(child)

    results = [item for suite in report.get("suites", []) for item in all_results(suite)]
    errors = results[0].get("errors", []) if len(results) == 1 else []
    valid_failure = (
        result.returncode == 1
        and len(results) == 1
        and results[0].get("status") == "failed"
        and len(errors) == 1
        and errors[0].get("message", "").startswith("Error: TITLE_MAPPING_ASSERTION")
    )
    if not valid_failure:
        print(json.dumps(report.get("stats", {}), ensure_ascii=False))
        for error in errors:
            print(error.get("message", "")[:2000])
        for error in report.get("errors", []):
            print(error.get("message", "")[:2000])
        print(result.stderr)
        raise SystemExit("mutation 未由預期標題斷言攔下")
    print("PASS：移除 title mapping 後，browser E2E 的標題斷言失敗。原始 backend 未修改。")
