import asyncio
import fcntl
import json
import os
import re
import shutil
import signal
import sys
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import Request
from starlette.responses import StreamingResponse

from app.subtitles import MAX_RESULT_BYTES, Transcript
from app.url_policy import validate_url
from app.video import DEMO_URL, VideoInfo


class DownloadError(ValueError):
    pass


class DownloadStore:
    def __init__(self, root: Path):
        self.root = root
        self.lock = None

    def open(self):
        self.root.mkdir(parents=True, exist_ok=True)
        marker = self.root / ".video-notes-owned"
        if not marker.exists() and any(self.root.iterdir()):
            raise RuntimeError("下載目錄不是 video-notes 的獨占目錄。")
        if marker.exists() and marker.read_text() != "video-notes-v1":
            raise RuntimeError("下載目錄標記不符。")
        self.lock = (self.root / ".lock").open("a")
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        marker.write_text("video-notes-v1")
        for child in self.root.iterdir():
            if child.name.startswith("job-") and child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)

    def close(self):
        if self.lock:
            self.lock.close()
            self.lock = None

    def create(self) -> Path:
        directory = self.root / f"job-{uuid4().hex}"
        directory.mkdir()
        return directory

    def cleanup(self, directory: Path):
        if directory.parent != self.root or not directory.name.startswith("job-"):
            raise RuntimeError("拒絕清理下載目錄以外的路徑。")
        shutil.rmtree(directory, ignore_errors=True)


async def stop_process(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), 0.5)
    except TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()
    # A worker may have exited while a descendant still holds the process group.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


async def execute_worker(payload: dict, request: Request | None, timeout: float) -> dict:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    limit = MAX_RESULT_BYTES if payload.get("action") == "subtitles" else 64 * 1024

    async def communicate():
        process.stdin.write(json.dumps(payload).encode())
        await process.stdin.drain()
        process.stdin.close()
        output = bytearray()
        while chunk := await process.stdout.read(64 * 1024):
            output.extend(chunk)
            if len(output) > limit:
                raise DownloadError("影片資訊超過大小上限。")
        await process.wait()
        return bytes(output), None

    communication = asyncio.create_task(communicate())
    monitoring_finished = asyncio.Event()

    async def disconnected():
        while not monitoring_finished.is_set():
            if request is not None and await request.is_disconnected():
                return
            if payload.get("directory"):
                directory = Path(payload["directory"])
                budget = (
                    2
                    * int(os.environ.get("VIDEO_NOTES_MAX_DOWNLOAD_BYTES", str(128 * 1024 * 1024)))
                    + 1024 * 1024
                )
                try:
                    used = sum(
                        path.stat().st_size for path in directory.iterdir() if path.is_file()
                    )
                except FileNotFoundError:
                    return
                if used > budget:
                    return
            await asyncio.sleep(0.05)

    monitor = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait(
            {communication, monitor}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        if communication not in done:
            raise DownloadError("下載已取消或超過時間／暫存大小上限。")
        stdout, _ = await communication
        if len(stdout) > limit:
            raise DownloadError("影片資訊超過大小上限。")
        result = json.loads(stdout)
        if process.returncode != 0 or not result.get("ok"):
            raise DownloadError(result.get("error") or "影片處理失敗。")
        return result["data"]
    finally:
        monitoring_finished.set()
        if not communication.done():
            communication.cancel()
        await asyncio.gather(communication, return_exceptions=True)

        async def discard_output():
            while await process.stdout.read(64 * 1024):
                pass

        # A failed bounded reader may leave a paused pipe. Drain without retaining
        # bytes while terminating, so Process.wait() can observe pipe closure.
        draining = asyncio.create_task(discard_output())
        try:
            await stop_process(process)
        finally:
            draining.cancel()
            await asyncio.gather(draining, return_exceptions=True)
        await asyncio.gather(monitor, communication, return_exceptions=True)


class ManagedDownloadResponse(StreamingResponse):
    def __init__(
        self, path: Path, title: str, ext: str, store: DownloadStore, directory: Path, release=None
    ):
        async def chunks():
            with path.open("rb") as stream:
                while chunk := await asyncio.to_thread(stream.read, 64 * 1024):
                    yield chunk

        filename = re.sub(r"[^\w\s.-]", "_", title)[:100].strip(". ") or "video"
        super().__init__(
            chunks(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename + '.' + ext)}",
                "Content-Length": str(path.stat().st_size),
                "Cache-Control": "no-store",
            },
        )
        self.store, self.directory = store, directory
        self.release = release

    async def __call__(self, scope, receive, send):
        try:
            async with asyncio.timeout(120):
                await super().__call__(scope, receive, send)
        finally:
            try:
                await self.body_iterator.aclose()
                self.store.cleanup(self.directory)
            finally:
                if self.release is not None:
                    self.release()


class VideoService:
    def __init__(self, store: DownloadStore, executor=execute_worker):
        self.store, self.executor = store, executor
        self.slots = asyncio.Semaphore(2)

    def validate(self, url: str):
        if url != DEMO_URL:
            validate_url(url, entry=True)

    async def parse(self, url: str, request: Request | None = None) -> VideoInfo:
        self.validate(url)
        async with self.slots:
            result = await self.executor({"action": "parse", "url": url}, request, 45)
        return VideoInfo.model_validate(result)

    async def direct(self, url: str, format_id: str, request: Request | None = None):
        self.validate(url)
        async with self.slots:
            result = await self.executor(
                {"action": "direct", "url": url, "format_id": format_id}, request, 45
            )
        return result

    async def subtitles(self, url: str, track_id: str | None, request: Request | None = None):
        self.validate(url)
        async with self.slots:
            result = await self.executor(
                {"action": "subtitles", "url": url, "track_id": track_id}, request, 45
            )
        return Transcript.model_validate(result)

    async def download(self, url: str, format_id: str, request: Request | None = None):
        self.validate(url)
        await self.slots.acquire()
        directory = None
        try:
            directory = self.store.create()
            result = await self.executor(
                {
                    "action": "download",
                    "url": url,
                    "format_id": format_id,
                    "directory": str(directory),
                },
                request,
                120,
            )
            path = Path(result["path"])
            if path.parent != directory or path.is_symlink() or not path.is_file():
                raise DownloadError("下載結果不在任務目錄內。")
            return ManagedDownloadResponse(
                path, result["title"], result["ext"], self.store, directory, self.slots.release
            )
        except BaseException:
            if directory is not None:
                self.store.cleanup(directory)
            self.slots.release()
            raise
