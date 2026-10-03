import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from app.auth import Attempts, AuthSettings, cleanup_expired, router
from app.database import build_engine
from app.downloads import DownloadError, DownloadStore, VideoService
from app.subtitles import ExportRequest, SubtitleBodyLimit, Transcript, export_subtitles
from app.video import VideoInfo


@asynccontextmanager
async def lifespan(app: FastAPI):
    root = Path(
        os.environ.get(
            "VIDEO_NOTES_DOWNLOAD_DIR", str(Path(__file__).resolve().parents[1] / ".runtime")
        )
    )
    store = DownloadStore(root)
    store.open()
    app.state.videos = VideoService(store)
    app.state.database = None
    try:
        app.state.auth_settings = AuthSettings(
            os.environ.get("VIDEO_NOTES_ORIGIN", "http://127.0.0.1:3422"),
            os.environ.get("VIDEO_NOTES_SECURE_COOKIE", "false") == "true",
        )
        app.state.auth_attempts = Attempts()
        if url := os.environ.get("VIDEO_NOTES_DATABASE_URL"):
            app.state.database = build_engine(url)
            await asyncio.to_thread(cleanup_expired, app.state.database)
        yield
    finally:
        if app.state.database is not None:
            app.state.database.dispose()
        store.close()


app = FastAPI(title="video-notes", version="0.2.0", lifespan=lifespan)
app.include_router(router)
app.add_middleware(SubtitleBodyLimit)


class NoStoreResponses:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def send_headers(message):
            if message["type"] == "http.response.start" and scope["path"].startswith(
                ("/api/auth/", "/api/subtitles")
            ):
                headers = [
                    (key, value)
                    for key, value in message["headers"]
                    if key.lower() != b"cache-control"
                ]
                message = {**message, "headers": [*headers, (b"cache-control", b"no-store")]}
            await send(message)

        await self.app(scope, receive, send_headers)


app.add_middleware(NoStoreResponses)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {key: item[key] for key in ("loc", "type", "msg")} for item in error.errors()
            ]
        },
    )


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    url: str = Field(min_length=1, max_length=2048)


class DownloadRequest(ParseRequest):
    format_id: str = Field(min_length=1, max_length=129, pattern=r"^[A-Za-z0-9_.+-]+$")


class SubtitleRequest(ParseRequest):
    track_id: str | None = Field(
        default=None, max_length=100, pattern=r"^(manual|automatic):[A-Za-z0-9_.-]+$"
    )


@app.exception_handler(ValueError)
async def invalid_value(request: Request, error: ValueError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=502 if isinstance(error, DownloadError) else 422, content={"detail": str(error)}
    )


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/parse", response_model=VideoInfo)
async def parse_video(payload: ParseRequest, request: Request) -> VideoInfo:
    return await request.app.state.videos.parse(payload.url, request)


@app.post("/api/direct")
async def direct_video(payload: DownloadRequest, request: Request):
    from fastapi.responses import JSONResponse

    data = await request.app.state.videos.direct(payload.url, payload.format_id, request)
    return JSONResponse(data, headers={"Cache-Control": "no-store"})


@app.post("/api/download")
async def download_video(payload: DownloadRequest, request: Request):
    return await request.app.state.videos.download(payload.url, payload.format_id, request)


@app.post("/api/subtitles", response_model=Transcript)
async def subtitles(payload: SubtitleRequest, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await request.app.state.videos.subtitles(payload.url, payload.track_id, request)


@app.post("/api/subtitles/export")
async def subtitle_export(payload: ExportRequest):
    return Response(
        export_subtitles(payload),
        media_type={"srt": "application/x-subrip", "vtt": "text/vtt", "txt": "text/plain"}[
            payload.format
        ],
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="subtitles.{payload.format}"',
        },
    )
