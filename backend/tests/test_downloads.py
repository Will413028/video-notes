import asyncio
import json
import socket
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.downloads import (
    DownloadError,
    DownloadStore,
    ManagedDownloadResponse,
    VideoService,
    execute_worker,
)
from app.main import app
from app.url_policy import UnsafeURL, require_public_ip, resolve_public, validate_url
from app.worker import native_formats


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost",
        "http://127.0.0.1",
        "https://youtube.com.evil.org/watch",
        "https://youtube.com@evil.org",
        "file:///tmp/video",
        "https://youtube.com:8443/watch",
        "https://youtube.com\\@evil.org",
        "https://youtube.com/%0a\n",
    ],
)
def test_entry_rejects_bypass(url):
    with pytest.raises(UnsafeURL):
        validate_url(url, entry=True)


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1", "::ffff:127.0.0.1", "192.0.2.1"],
)
def test_private_ip_is_rejected(ip):
    with pytest.raises(UnsafeURL):
        require_public_ip(ip)


def test_mixed_dns_answers_rejected():
    def resolver(*args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
            for ip in ["8.8.8.8", "127.0.0.1"]
        ]

    with pytest.raises(UnsafeURL):
        resolve_public("cdn.example", 443, resolver)


def test_actual_socket_guards_private_redirect_and_rebinding():
    # A fresh process avoids changing TestClient or the test runner's socket class.
    program = """
from app.url_policy import install_socket_guard, UnsafeURL, resolve_public
import socket
current_ip = '8.8.8.8'
def resolver(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (current_ip, 443))]
resolve_public('rebinding.example', 443, resolver)
socket.getaddrinfo = resolver
install_socket_guard()
current_ip = '127.0.0.1'
for target in [('rebinding.example', 443), ('127.0.0.1', 80), ('169.254.169.254', 80), ('::1', 443, 0, 0)]:
    s = socket.socket(socket.AF_INET6 if len(target) == 4 else socket.AF_INET)
    try:
        s.connect(target)
    except UnsafeURL:
        pass
    else:
        raise AssertionError('private target reached connect')
    finally:
        s.close()
"""
    import sys

    subprocess.run([sys.executable, "-c", program], check=True)


def test_formats_only_offer_native_muxed_or_compatible_merge():
    def track(id, ext, vcodec, acodec, protocol="https", **kwargs):
        return dict(
            format_id=id, ext=ext, vcodec=vcodec, acodec=acodec, protocol=protocol, **kwargs
        )

    formats = native_formats(
        {
            "formats": [
                track("muxed", "mp4", "h264", "aac", height=360),
                track("video", "mp4", "h264", "none", height=1080),
                track("audio", "m4a", "none", "aac", abr=128),
                track("hls", "mp4", "h264", "aac", "m3u8_native"),
                track("unsafe/select", "mp4", "h264", "aac"),
                track("drm", "mp4", "h264", "aac", has_drm=True),
            ]
        }
    )
    assert [item.format_id for item in formats] == ["video+audio", "muxed"]
    assert [item.requires_merge for item in formats] == [True, False]


def test_store_unique_restart_cleanup_and_foreign_root(tmp_path):
    root = tmp_path / "owned"
    store = DownloadStore(root)
    store.open()
    first, second = store.create(), store.create()
    assert first != second
    (first / "media.mp4").write_bytes(b"fixture")
    with pytest.raises(BlockingIOError):
        DownloadStore(root).open()
    store.close()
    store.open()
    assert not first.exists() and not second.exists()
    with pytest.raises(RuntimeError):
        store.cleanup(tmp_path)
    store.close()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("user data")
    with pytest.raises(RuntimeError):
        DownloadStore(foreign).open()
    assert (foreign / "keep.txt").read_text() == "user data"


def test_download_fixture_has_video_audio_and_cleans_up(tmp_path, monkeypatch):
    root = tmp_path / "downloads"
    monkeypatch.setenv("VIDEO_NOTES_DOWNLOAD_DIR", str(root))
    with TestClient(app) as client:
        response = client.post(
            "/api/download", json={"url": "fixture://learning-demo", "format_id": "demo-360"}
        )
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
        assert len(response.content) == int(response.headers["content-length"])
        artifact = tmp_path / "fixture.mp4"
        artifact.write_bytes(response.content)
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "json",
                str(artifact),
            ],
            capture_output=True,
            check=True,
        )
        assert {item["codec_type"] for item in json.loads(probe.stdout)["streams"]} == {
            "video",
            "audio",
        }
        assert not list(root.glob("job-*"))
        failed = client.post(
            "/api/download", json={"url": "fixture://learning-demo", "format_id": "not-available"}
        )
        assert failed.status_code == 502
        assert not list(root.glob("job-*"))
        assert (
            client.post(
                "/api/direct", json={"url": "fixture://learning-demo", "format_id": "demo-360"}
            ).status_code
            == 502
        )


def test_transmission_error_still_cleans_directory(tmp_path):
    store = DownloadStore(tmp_path / "downloads")
    store.open()
    directory = store.create()
    path = directory / "media.mp4"
    path.write_bytes(b"fixture" * 20000)
    response = ManagedDownloadResponse(path, "title", "mp4", store, directory)

    async def run():
        async def receive():
            return {"type": "http.request"}

        async def send(message):
            if message["type"] == "http.response.body":
                raise OSError("client disconnected")

        from starlette.requests import ClientDisconnect

        with pytest.raises(ClientDisconnect):
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)

    asyncio.run(run())
    assert not directory.exists()
    store.close()


def test_worker_timeout_disconnect_and_service_error_cleanup(tmp_path):
    async def run():
        with pytest.raises(DownloadError):
            await execute_worker(
                {"action": "parse", "url": "fixture://learning-demo"}, None, 0.00001
            )

        class Disconnected:
            async def is_disconnected(self):
                return True

        with pytest.raises(DownloadError):
            await execute_worker(
                {"action": "parse", "url": "fixture://learning-demo"}, Disconnected(), 5
            )
        store = DownloadStore(tmp_path / "downloads")
        store.open()

        async def fail(payload, request, timeout):
            (store.root / "outside.mp4").write_bytes(b"outside")
            return {"path": str(store.root / "outside.mp4"), "title": "title", "ext": "mp4"}

        service = VideoService(store, executor=fail)
        with pytest.raises(DownloadError):
            await service.download("fixture://learning-demo", "demo-360")
        assert not list(store.root.glob("job-*"))
        assert (store.root / "outside.mp4").exists()
        store.close()

    asyncio.run(run())


def test_disconnect_stops_worker_and_child_process(tmp_path, monkeypatch):
    import os
    import sys

    pid_file = tmp_path / "child-pid"
    program = (
        "import subprocess,sys,time; from pathlib import Path; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        f"marker=Path({str(pid_file)!r}); temporary=marker.with_suffix('.tmp'); "
        "temporary.write_text(str(child.pid)); temporary.replace(marker); time.sleep(60)"
    )
    real_spawn = asyncio.create_subprocess_exec

    async def spawn(*args, **kwargs):
        return await real_spawn(sys.executable, "-c", program, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)

    class DisconnectAfterSpawn:
        async def is_disconnected(self):
            return pid_file.exists()

    async def run():
        with pytest.raises(DownloadError):
            await execute_worker(
                {"action": "parse", "url": "fixture://learning-demo"}, DisconnectAfterSpawn(), 5
            )
        child = int(pid_file.read_text())
        for _ in range(40):
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                return
            await asyncio.sleep(0.05)
        pytest.fail("取消後 child process 仍存活")

    asyncio.run(run())


def test_workspace_budget_stops_worker(tmp_path, monkeypatch):
    import sys

    directory = tmp_path / "job-budget"
    directory.mkdir()
    monkeypatch.setenv("VIDEO_NOTES_MAX_DOWNLOAD_BYTES", "1024")
    program = f"from pathlib import Path; import time; Path({str(directory / 'growing')!r}).write_bytes(b'x'*(2*1024+1024*1024+1)); time.sleep(60)"
    real_spawn = asyncio.create_subprocess_exec

    async def spawn(*args, **kwargs):
        return await real_spawn(sys.executable, "-c", program, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)

    async def run():
        with pytest.raises(DownloadError, match="暫存大小上限"):
            await execute_worker({"action": "download", "directory": str(directory)}, None, 5)

    asyncio.run(run())
