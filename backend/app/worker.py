"""隔離影片工作：固定 transport、原生格式與本機 ffmpeg 合併。"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from app.subtitles import fetch_subtitles
from app.url_policy import install_socket_guard, resolve_public, validate_url
from app.video import DEMO_URL, DemoVideoParser, VideoFormat, VideoInfo

MAX_BYTES = int(os.environ.get("VIDEO_NOTES_MAX_DOWNLOAD_BYTES", str(128 * 1024 * 1024)))


def native_formats(info: dict) -> list[VideoFormat]:
    usable = [
        item
        for item in info.get("formats", [])
        if item.get("protocol") in {"http", "https"}
        and item.get("ext") in {"mp4", "webm", "m4a"}
        and not item.get("has_drm")
        and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", str(item.get("format_id", "")))
    ]
    audio = [
        item
        for item in usable
        if item.get("vcodec") == "none" and item.get("acodec") not in {None, "none"}
    ]
    result = []
    for item in sorted(usable, key=lambda item: item.get("height") or 0, reverse=True):
        if item.get("vcodec") in {None, "none"} or item["ext"] not in {"mp4", "webm"}:
            continue
        format_id = item["format_id"]
        has_audio = item.get("acodec") not in {None, "none"}
        if not has_audio:
            compatible = [
                track
                for track in audio
                if track["ext"] in ({"m4a", "mp4"} if item["ext"] == "mp4" else {"webm"})
            ]
            if not compatible:
                continue
            track = max(compatible, key=lambda track: track.get("abr") or 0)
            format_id += "+" + track["format_id"]
        result.append(
            VideoFormat(
                format_id=format_id,
                ext=item["ext"],
                has_audio=True,
                requires_merge=not has_audio,
                label=f"{item.get('height') or '?'}p {item['ext'].upper()} · "
                + ("本機合併音訊" if not has_audio else "影片與音訊"),
            )
        )
    return result[:24]


def project_info(info: dict) -> VideoInfo:
    if info.get("_type") in {"playlist", "multi_video"}:
        raise ValueError("請提供單支影片連結。")
    return VideoInfo(
        id=str(info.get("id") or "video"),
        title=str(info.get("title") or "未命名影片")[:200],
        uploader=str(info.get("uploader") or "未知作者")[:100],
        duration_seconds=max(0, int(info.get("duration") or 0)),
        source=str(info.get("extractor_key") or "video"),
        formats=native_formats(info),
    )


def run(payload: dict) -> dict:
    action, url = payload["action"], payload["url"]
    if url == DEMO_URL:
        video = DemoVideoParser().parse(url)
        if action == "subtitles":
            return fetch_subtitles(
                {
                    "subtitles": {
                        "zh-Hant": [
                            {
                                "ext": "json",
                                "data": json.dumps(
                                    {
                                        "body": [
                                            {
                                                "from": 0,
                                                "to": 2.125,
                                                "content": "先理解問題，再選擇工具。",
                                            },
                                            {
                                                "from": 3.5,
                                                "to": 5,
                                                "content": "先理解問題，再選擇工具。",
                                            },
                                            {
                                                "from": 6,
                                                "to": 8,
                                                "content": "保留脈絡，也保留時間。",
                                            },
                                        ]
                                    },
                                    ensure_ascii=False,
                                ),
                            }
                        ],
                    },
                    "automatic_captions": {
                        "en": [
                            {
                                "ext": "json3",
                                "data": json.dumps(
                                    {
                                        "events": [
                                            {
                                                "tStartMs": 0,
                                                "dDurationMs": 2125,
                                                "segs": [{"utf8": "Understand the problem first."}],
                                            },
                                        ]
                                    }
                                ),
                            }
                        ],
                    },
                },
                None,
                payload.get("track_id"),
            )
        if action == "parse":
            return video.model_dump()
        if payload["format_id"] != "demo-360":
            raise ValueError("請重新選擇可用格式。")
        if action == "direct":
            raise ValueError("範例影片請使用「下載影片」。")
        output = Path(payload["directory"]) / "media.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x47754e:s=640x360:d=1",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=1",
                "-c:v",
                "mpeg4",
                "-c:a",
                "aac",
                "-shortest",
                "-movflags",
                "+faststart",
                str(output),
            ],
            check=True,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if output.stat().st_size > MAX_BYTES:
            raise ValueError("下載超過本機檔案大小上限。")
        return {"path": str(output), "title": video.title, "ext": "mp4"}

    validate_url(url, entry=True)
    os.environ["YTDLP_NO_PLUGINS"] = "1"
    install_socket_guard()
    from yt_dlp import YoutubeDL
    from yt_dlp.networking._urllib import UrllibRH

    class GuardedDL(YoutubeDL):
        def urlopen(self, request):
            target = request if isinstance(request, str) else request.url
            validate_url(target)
            return super().urlopen(request)

    def enforce_size(_progress):
        directory = Path(payload["directory"])
        if sum(path.stat().st_size for path in directory.iterdir() if path.is_file()) > MAX_BYTES:
            raise ValueError("下載超過本機檔案大小上限。")

    options = {
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "noplaylist": True,
        "cachedir": False,
        "proxy": "",
        "socket_timeout": 10,
        "retries": 1,
        "fragment_retries": 0,
        "enable_file_urls": False,
        "remote_components": set(),
        "js_runtimes": {},
        "max_filesize": MAX_BYTES,
        "overwrites": True,
        "writesubtitles": action == "subtitles",
        "writeautomaticsub": action == "subtitles",
    }
    if action == "download":
        options.update(
            {
                "outtmpl": str(Path(payload["directory"]) / "media.%(ext)s"),
                "progress_hooks": [enforce_size],
            }
        )
    with GuardedDL(options) as downloader:
        downloader._request_director = downloader.build_request_director([UrllibRH])
        info = downloader.extract_info(url, download=False)
        if action == "subtitles":
            if info.get("_type") in {"playlist", "multi_video"}:
                raise ValueError("請提供單支影片連結。")
            return fetch_subtitles(info, downloader, payload.get("track_id"))
        video = project_info(info)
        if action == "parse":
            return video.model_dump()
        chosen = next(
            (item for item in video.formats if item.format_id == payload["format_id"]), None
        )
        if chosen is None:
            raise ValueError("格式已不可用，請重新解析影片。")
        if action == "direct":
            if chosen.requires_merge:
                raise ValueError("此格式需要合併音訊，請使用「下載影片」。")
            media = next(item for item in info["formats"] if item["format_id"] == chosen.format_id)
            host, port = validate_url(media["url"])
            resolve_public(host, port)
            return {"url": media["url"]}
        downloader.params["format"] = chosen.format_id
        downloader.format_selector = downloader.build_format_selector(chosen.format_id)
        selected_ids = set(chosen.format_id.split("+"))
        info["formats"] = [item for item in info["formats"] if item["format_id"] in selected_ids]
        # extract_info(download=False) also persists the default merge selection.
        # A later muxed selection must start without those tracks.
        info.pop("requested_formats", None)
        info.pop("requested_downloads", None)
        downloader.process_ie_result(info, download=True)
        output = Path(payload["directory"]) / f"media.{chosen.ext}"
        if not output.is_file():
            raise ValueError("下載或音訊合併未產生檔案。")
        if output.stat().st_size > MAX_BYTES:
            raise ValueError("下載超過本機檔案大小上限。")
        return {"path": str(output), "title": video.title, "ext": chosen.ext}


if __name__ == "__main__":
    try:
        result = run(json.loads(sys.stdin.read()))
        print(json.dumps({"ok": True, "data": result}, ensure_ascii=False))
    except Exception:  # noqa: BLE001 — worker boundary must suppress provider URLs and tracebacks.
        # 不把 yt-dlp 的簽名 URL、供應商內容或 traceback 寫進 API／日誌。
        print(json.dumps({"ok": False, "error": "影片解析或下載失敗，請確認來源與格式後重試。"}))
        sys.exit(1)
