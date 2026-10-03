"""平台字幕轉為毫秒精度 segments；不合併、不去除重複句。"""

import html
import json
import re
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_SUBTITLE_BYTES = 2 * 1024 * 1024
MAX_RESULT_BYTES = 4 * 1024 * 1024
SUPPORTED = {"json3", "json", "vtt", "srt"}


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    start: float = Field(ge=0, le=360_000)
    end: float = Field(gt=0, le=360_000)
    text: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end <= self.start:
            raise ValueError("字幕結束時間必須晚於開始時間。")
        if milliseconds(self.end) <= milliseconds(self.start):
            raise ValueError("字幕時間間隔必須至少一毫秒。")
        if any(not line.strip() for line in self.text.split("\n")):
            raise ValueError("字幕文字不可含空白行。")
        if any(ord(char) < 32 and char != "\n" for char in self.text):
            raise ValueError("字幕含有不支援的控制字元。")
        return self


class Track(BaseModel):
    id: str
    language: str
    source: Literal["manual", "automatic"]


class Transcript(BaseModel):
    status: Literal["ready", "unavailable", "unsupported"]
    tracks: list[Track]
    selected: str | None = None
    segments: list[Segment] = Field(default_factory=list, max_length=10_000)


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["srt", "vtt", "txt"]
    segments: list[Segment] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def valid_segments(self):
        check_segments(self.segments)
        return self


def check_segments(segments: list[Segment]):
    if len(segments) > 10_000 or sum(len(s.text.encode()) for s in segments) > MAX_SUBTITLE_BYTES:
        raise ValueError("字幕超過大小上限。")
    if any(a.start > b.start for a, b in pairwise(segments)):
        raise ValueError("字幕時間必須依序排列。")


def milliseconds(value) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def plain_text(value: str, *, markup: bool = False) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    if markup:
        value = re.sub(r"<[^>]*>", "", value)
        value = html.unescape(value)
    return "\n".join(line.strip() for line in value.splitlines() if line.strip()).strip()


def timestamp(value: str) -> float:
    match = re.fullmatch(r"(?:(\d{2,}):)?([0-5]\d):([0-5]\d)[.,](\d{3})", value)
    if not match:
        raise ValueError("字幕時間格式不正確。")
    hours, minutes, seconds, millis = match.groups()
    return (int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)) + int(millis) / 1000


def parse_subtitles(data: str, ext: str) -> list[Segment]:
    if len(data.encode()) > MAX_SUBTITLE_BYTES:
        raise ValueError("字幕超過大小上限。")
    rows = []
    if ext in {"json", "json3"}:
        document = json.loads(data)
        if ext == "json":
            for row in document["body"]:
                rows.append((row["from"], row["to"], plain_text(row["content"])))
        else:
            for row in document.get("events", []):
                text = plain_text("".join(part.get("utf8", "") for part in row.get("segs", [])))
                if not text:
                    continue
                start = row["tStartMs"] / 1000
                rows.append((start, start + row["dDurationMs"] / 1000, text))
    elif ext in {"vtt", "srt"}:
        normalized = data.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        if ext == "vtt" and not re.match(r"WEBVTT(?:[ \t\n]|$)", normalized):
            raise ValueError("字幕缺少 WEBVTT 標頭。")
        for block_index, block in enumerate(re.split(r"\n[ \t]*\n", normalized)):
            lines = block.splitlines()
            if not lines:
                continue
            if ext == "vtt" and (
                block_index == 0
                or re.match(r"NOTE(?:[ \t]|$)", lines[0])
                or lines[0] in {"STYLE", "REGION"}
            ):
                continue
            index = 0 if " --> " in lines[0] else 1
            if index >= len(lines) or " --> " not in lines[index]:
                raise ValueError("字幕 cue 格式不正確。")
            start, end = lines[index].split(" --> ", 1)
            text = plain_text("\n".join(lines[index + 1 :]), markup=True)
            if text:
                rows.append((timestamp(start), timestamp(end.split()[0]), text))
    else:
        raise ValueError("字幕格式不支援。")
    segments = [
        Segment(start=milliseconds(start), end=milliseconds(end), text=text)
        for start, end, text in rows
        if text
    ]
    check_segments(segments)
    return segments


def available_tracks(info: dict) -> list[tuple[Track, dict]]:
    result = []
    for key, source in [("subtitles", "manual"), ("automatic_captions", "automatic")]:
        for language, formats in sorted((info.get(key) or {}).items()):
            if language == "danmaku" or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", language):
                continue
            usable = [item for item in formats if item.get("ext") in SUPPORTED]
            if not usable:
                continue
            actual_source = "automatic" if language.startswith("ai-") else source
            track = Track(id=f"{actual_source}:{language}", language=language, source=actual_source)
            chosen = min(
                usable, key=lambda item: ["json3", "json", "vtt", "srt"].index(item["ext"])
            )
            if not any(existing.id == track.id for existing, _ in result):
                result.append((track, chosen))
    return sorted(result, key=lambda pair: (pair[0].source != "manual", pair[0].language))


def fetch_subtitles(info: dict, downloader, selected: str | None) -> dict:
    tracks = available_tracks(info)
    if not tracks:
        present = any(
            language != "danmaku" and formats
            for key in ["subtitles", "automatic_captions"]
            for language, formats in (info.get(key) or {}).items()
        )
        return Transcript(
            status="unsupported" if present else "unavailable", tracks=[]
        ).model_dump()
    choice = (
        next((pair for pair in tracks if pair[0].id == selected), None) if selected else tracks[0]
    )
    if choice is None:
        raise ValueError("字幕語言已不可用，請重新取得字幕。")
    track, metadata = choice
    if "data" in metadata:
        data = metadata["data"]
    else:
        from yt_dlp.networking import Request

        # GuardedDL validates target URLs; its sole urllib transport uses the socket guard.
        with downloader.urlopen(
            Request(metadata["url"], headers=info.get("http_headers") or {})
        ) as response:
            raw = response.read(MAX_SUBTITLE_BYTES + 1)
        if len(raw) > MAX_SUBTITLE_BYTES:
            raise ValueError("字幕超過大小上限。")
        data = raw.decode("utf-8-sig")
    segments = parse_subtitles(data, metadata["ext"])
    return Transcript(
        status="ready" if segments else "unavailable",
        tracks=[item for item, _ in tracks],
        selected=track.id,
        segments=segments,
    ).model_dump()


def format_time(seconds: float, separator: str) -> str:
    total = int((Decimal(str(seconds)) * 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    hours, remaining = divmod(total, 3_600_000)
    minutes, remaining = divmod(remaining, 60_000)
    seconds, millis = divmod(remaining, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}{separator}{millis:03}"


def export_subtitles(payload: ExportRequest) -> str:
    if payload.format == "txt":
        return "\n".join(segment.text for segment in payload.segments) + "\n"
    separator = "," if payload.format == "srt" else "."
    cues = []
    for index, segment in enumerate(payload.segments, 1):
        # Escaping preserves literal <, >, & on parser/player readback; blank lines would end cues.
        text = html.escape(segment.text, quote=False)
        cues.append(
            f"{index}\n{format_time(segment.start, separator)} --> "
            f"{format_time(segment.end, separator)}\n{text}\n"
        )
    return ("WEBVTT\n\n" if payload.format == "vtt" else "") + "\n".join(cues) + "\n"


class SubtitleBodyLimit:
    """在 FastAPI JSON 解碼前限制字幕 API body；不相信 Content-Length。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/subtitles"):
            await self.app(scope, receive, send)
            return
        from starlette.responses import JSONResponse

        chunks = []
        total = 0
        limit = MAX_RESULT_BYTES if scope["path"] == "/api/subtitles/export" else 8192
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            total += len(message.get("body", b""))
            if total > limit:
                await JSONResponse(
                    {"detail": "字幕請求超過大小上限。"},
                    status_code=413,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, send)
                return
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
