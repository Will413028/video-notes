import asyncio
import io
import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from yt_dlp import YoutubeDL
from yt_dlp.networking.common import Response

from app import worker
from app.downloads import DownloadError, execute_worker
from app.main import app
from app.subtitles import (
    MAX_SUBTITLE_BYTES,
    ExportRequest,
    Segment,
    available_tracks,
    export_subtitles,
    fetch_subtitles,
    parse_subtitles,
)
from app.video import DEMO_URL


@pytest.fixture
def subtitles_client(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_NOTES_DOWNLOAD_DIR", str(tmp_path / "jobs"))
    monkeypatch.delenv("VIDEO_NOTES_DATABASE_URL", raising=False)
    with TestClient(app) as client:
        yield client


def test_subtitles_worker_api_multilingual_priority_and_repetition(subtitles_client):
    response = subtitles_client.post("/api/subtitles", json={"url": DEMO_URL})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["selected"] == "manual:zh-Hant"
    assert [(s["start"], s["end"]) for s in data["segments"]] == [(0, 2.125), (3.5, 5), (6, 8)]
    assert data["segments"][0]["text"] == data["segments"][1]["text"]
    english = subtitles_client.post(
        "/api/subtitles", json={"url": DEMO_URL, "track_id": "automatic:en"}
    ).json()
    assert english["selected"] == "automatic:en"
    assert english["segments"][0]["text"] == "Understand the problem first."


def test_subtitles_bilibili_srt_and_ai_language():
    info = {
        "subtitles": {
            "danmaku": [{"ext": "xml", "url": "https://comment.bilibili.com/1.xml"}],
            "ai-zh": [
                {
                    "ext": "srt",
                    "data": "1\n00:00:00,000 --> 00:00:01,125\n你好\n\n2\n00:00:02,000 --> 00:00:03,000\n你好\n",
                }
            ],
            "en": [
                {
                    "ext": "json",
                    "data": json.dumps({"body": [{"from": 0, "to": 1, "content": "Hello"}]}),
                }
            ],
        }
    }
    result = fetch_subtitles(info, None, "automatic:ai-zh")
    assert result["segments"] == [
        {"start": 0, "end": 1.125, "text": "你好"},
        {"start": 2, "end": 3, "text": "你好"},
    ]
    assert [track.id for track, _ in available_tracks(info)] == ["manual:en", "automatic:ai-zh"]


@pytest.mark.parametrize(
    "info,status",
    [
        ({}, "unavailable"),
        ({"subtitles": {"danmaku": [{"ext": "xml"}]}}, "unavailable"),
        ({"subtitles": {"en": [{"ext": "ass"}]}}, "unsupported"),
        (
            {"automatic_captions": {"ja": [{"ext": "json3", "data": '{"events":[]}'}]}},
            "unavailable",
        ),
    ],
)
def test_subtitles_empty_unsupported_and_automatic_fallback(info, status):
    result = fetch_subtitles(info, None, None)
    assert result["status"] == status
    assert result["segments"] == []
    if result["tracks"]:
        assert result["selected"] == "automatic:ja"


@pytest.mark.parametrize("format", ["srt", "vtt", "txt"])
def test_subtitles_exports_roundtrip_api(subtitles_client, format):
    segments = [
        {"start": 0.125, "end": 1.75, "text": "你好 <朋友> & world\n第二行"},
        {"start": 3601.005, "end": 3602.999, "text": "你好 <朋友> & world\n第二行"},
    ]
    response = subtitles_client.post(
        "/api/subtitles/export", json={"format": format, "segments": segments}
    )
    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith(f'subtitles.{format}"')
    assert response.headers["cache-control"] == "no-store"
    if format == "txt":
        assert response.text == "\n".join(s["text"] for s in segments) + "\n"
    else:
        assert [
            segment.model_dump() for segment in parse_subtitles(response.text, format)
        ] == segments, "SUBTITLE_INTERVAL_ASSERTION"
        assert "01:00:01" in response.text


def test_subtitles_vtt_settings_ids_markup_crlf_overlap():
    data = "WEBVTT\r\n\r\nNOTE ignore\r\ncomment\r\n\r\ncue-a\r\n00:01.000 --> 00:03.000 align:start\r\n<v Speaker><b>你好</b> &amp; hello\r\n\r\n00:02.000 --> 00:04.000\r\n你好\r\n"
    assert parse_subtitles(data, "vtt") == [
        Segment(start=1, end=3, text="你好 & hello"),
        Segment(start=2, end=4, text="你好"),
    ]


@pytest.mark.parametrize(
    "start,end", [(2, 1), (1, 1), (float("nan"), 1), (0, float("inf")), (0, 0.0001)]
)
def test_subtitles_invalid_intervals(start, end):
    with pytest.raises(ValidationError):
        Segment(start=start, end=end, text="hello")


def test_subtitles_bounds_order_and_request_validation(subtitles_client):
    with pytest.raises(ValueError):
        parse_subtitles("x" * (MAX_SUBTITLE_BYTES + 1), "srt")
    with pytest.raises(ValueError):
        ExportRequest(
            format="txt",
            segments=[Segment(start=2, end=3, text="a"), Segment(start=1, end=2, text="b")],
        )
    for payload in [
        {"format": "exe", "segments": []},
        {"format": "txt", "segments": []},
        {"format": "vtt", "segments": [{"start": 0, "end": 1, "text": "a\n\nb"}]},
    ]:
        assert subtitles_client.post("/api/subtitles/export", json=payload).status_code == 422
    assert subtitles_client.post("/api/subtitles", content=b"x" * 8193).status_code == 413
    assert (
        subtitles_client.post(
            "/api/subtitles/export", content=b"x" * (4 * 1024 * 1024 + 1)
        ).status_code
        == 413
    )
    assert (
        subtitles_client.post(
            "/api/subtitles", json={"url": "http://localhost/private"}
        ).status_code
        == 422
    )


def test_subtitles_ytdlp_fetch_without_network(monkeypatch):
    info = {
        "id": "fixture",
        "title": "fixture",
        "subtitles": {"en": [{"ext": "vtt", "url": "https://cdn.example/sub.vtt"}]},
    }
    monkeypatch.setattr(worker, "install_socket_guard", lambda: None)
    monkeypatch.setattr(YoutubeDL, "extract_info", lambda *args, **kwargs: info)
    requested = []

    def local_response(self, request):
        requested.append(request.url)
        return Response(io.BytesIO(b"WEBVTT\n\n00:00.000 --> 00:01.000\nhello\n"), request.url, {})

    monkeypatch.setattr(YoutubeDL, "urlopen", local_response)
    result = worker.run({"action": "subtitles", "url": "https://youtube.com/watch?v=fixture"})
    assert result["segments"] == [{"start": 0, "end": 1, "text": "hello"}]
    assert requested == ["https://cdn.example/sub.vtt"]
    info["subtitles"]["en"][0]["url"] = "file:///etc/passwd"
    with pytest.raises(ValueError):
        worker.run({"action": "subtitles", "url": "https://youtube.com/watch?v=fixture"})


def test_subtitles_export_interval_mapping():
    text = export_subtitles(
        ExportRequest(format="srt", segments=[Segment(start=1.25, end=2.5, text="hi")])
    )
    assert "00:00:01,250 --> 00:00:02,500" in text, "SUBTITLE_INTERVAL_ASSERTION"


def test_subtitles_vtt_reserved_prefix_identifiers_preserved():
    cues = [
        f"{identifier}\n00:00:00.000 --> 00:00:01.000\n{identifier}\n"
        for identifier in ["NOTE-1", "STYLE-caption", "REGION-42", "WEBVTT-1"]
    ]
    segments = parse_subtitles("WEBVTT\n\n" + "\n".join(cues), "vtt")
    assert [segment.text for segment in segments] == [
        "NOTE-1",
        "STYLE-caption",
        "REGION-42",
        "WEBVTT-1",
    ]


def test_subtitles_automatic_fallback_and_invalid_selection():
    info = {
        "automatic_captions": {
            "en": [
                {
                    "ext": "json3",
                    "data": json.dumps(
                        {
                            "events": [
                                {"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "auto"}]}
                            ]
                        }
                    ),
                }
            ]
        }
    }
    assert fetch_subtitles(info, None, None)["selected"] == "automatic:en"
    with pytest.raises(ValueError, match="已不可用"):
        fetch_subtitles(info, None, "manual:en")


def test_subtitles_fixed_bilibili_converter():
    from yt_dlp.extractor.bilibili import BiliBiliIE

    data = BiliBiliIE().json2srt({"body": [{"from": 0, "to": 2.125, "content": "你好"}]})
    assert parse_subtitles(data, "srt") == [Segment(start=0, end=2.125, text="你好")]


@pytest.mark.parametrize("action,limit", [("parse", 64 * 1024), ("subtitles", 4 * 1024 * 1024)])
def test_subtitles_worker_stdout_bound_before_process_exit(monkeypatch, action, limit):
    spawn = asyncio.create_subprocess_exec

    async def fixture_process(*args, **kwargs):
        program = f"import sys,time; sys.stdin.read(); sys.stdout.write('x'*{limit * 10}); sys.stdout.flush(); time.sleep(60)"
        return await spawn(sys.executable, "-c", program, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fixture_process)

    async def run():
        with pytest.raises(DownloadError, match="大小上限"):
            await execute_worker({"action": action, "url": DEMO_URL}, None, 30)

    asyncio.run(run())


def test_subtitles_repeated_requests_finish_disconnect_cleanup(tmp_path, monkeypatch):
    monkeypatch.delenv("VIDEO_NOTES_DATABASE_URL", raising=False)
    monkeypatch.setenv("VIDEO_NOTES_DOWNLOAD_DIR", str(tmp_path / "jobs"))
    # A separate process puts a deadline around TestClient teardown as well as the request.
    # Before the ASGI-only header middleware, a completed worker could leave the
    # disconnect monitor inside BaseHTTPMiddleware.receive_or_disconnect indefinitely.
    program = r"""
import asyncio, sys
from fastapi.testclient import TestClient
from app.main import app
spawn = asyncio.create_subprocess_exec
async def lightweight_worker(*args, **kwargs):
    code = 'import sys; sys.stdin.read(); print(\'{"ok":true,"data":{"status":"unavailable","tracks":[],"selected":null,"segments":[]}}\')'
    return await spawn(sys.executable, '-c', code, **kwargs)
asyncio.create_subprocess_exec = lightweight_worker
for _ in range(10):
    with TestClient(app) as client:
        response = client.post('/api/subtitles', json={'url': 'fixture://learning-demo'})
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
print('CLEANUP_COMPLETED')
"""
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, timeout=90, check=False
    )
    assert result.returncode == 0 and result.stdout.strip() == "CLEANUP_COMPLETED", (
        "SUBTITLE_CLEANUP_ASSERTION"
    )


def test_subtitles_cleanup_does_not_repoll_request_that_swallows_cancellation(monkeypatch):
    async def run():
        entered = asyncio.Event()

        class Request:
            polls = 0

            async def is_disconnected(self):
                self.polls += 1
                if self.polls > 1:
                    return True
                entered.set()
                try:
                    await asyncio.sleep(0.02)
                except asyncio.CancelledError:
                    # Request.is_disconnected uses an AnyIO cancel scope, which
                    # can absorb an external task cancellation during a poll.
                    return False
                return False

        class Input:
            def write(self, data):
                pass

            async def drain(self):
                pass

            def close(self):
                pass

        class Output:
            reads = 0

            async def read(self, size):
                self.reads += 1
                if self.reads > 1:
                    return b""
                await entered.wait()
                return b'{"ok":true,"data":{"completed":true}}'

        class Process:
            stdin = Input()
            stdout = Output()
            returncode = 0

            async def wait(self):
                return 0

        async def spawn(*args, **kwargs):
            return Process()

        async def stop(process):
            pass

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr("app.downloads.stop_process", stop)
        request = Request()
        assert await execute_worker({"action": "subtitles", "url": DEMO_URL}, request, 1) == {
            "completed": True
        }
        assert request.polls == 1, "SUBTITLE_CLEANUP_POLL_ASSERTION"

    asyncio.run(run())
