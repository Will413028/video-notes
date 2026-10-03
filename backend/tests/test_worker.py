import copy
import io
import json
import subprocess

import pytest
from yt_dlp import YoutubeDL
from yt_dlp.networking.common import Response

from app import worker


@pytest.fixture
def native_media(tmp_path, monkeypatch):
    video, audio = tmp_path / "video.mp4", tmp_path / "audio.m4a"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=s=160x90:d=0.2",
            "-c:v",
            "mpeg4",
            str(video),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=0.2",
            "-c:a",
            "aac",
            str(audio),
        ],
        check=True,
    )
    info = {
        "id": "fixture",
        "title": "同名影片",
        "extractor": "youtube",
        "extractor_key": "Youtube",
        "webpage_url": "https://youtube.com/watch?v=fixture",
        "formats": [
            {
                "format_id": "v",
                "url": "https://cdn.example/video",
                "ext": "mp4",
                "protocol": "https",
                "vcodec": "mpeg4",
                "acodec": "none",
                "height": 90,
            },
            {
                "format_id": "a",
                "url": "https://cdn.example/audio",
                "ext": "m4a",
                "protocol": "https",
                "vcodec": "none",
                "acodec": "aac",
                "abr": 128,
            },
        ],
    }
    monkeypatch.setattr(worker, "install_socket_guard", lambda: None)
    monkeypatch.setattr(
        YoutubeDL,
        "extract_info",
        lambda self, *args, **kwargs: self.process_video_result(
            copy.deepcopy(info), download=False
        ),
    )

    def local_response(self, request):
        data = (video if request.url.endswith("video") else audio).read_bytes()
        return Response(io.BytesIO(data), request.url, {"Content-Length": str(len(data))})

    monkeypatch.setattr(YoutubeDL, "urlopen", local_response)
    return info


def test_real_ytdlp_native_download_and_ffmpeg_merge_without_network(
    native_media, tmp_path, capsys
):
    directory = tmp_path / "job"
    directory.mkdir()
    result = worker.run(
        {
            "action": "download",
            "url": "https://youtube.com/watch?v=fixture",
            "format_id": "v+a",
            "directory": str(directory),
        }
    )
    assert result["path"] == str(directory / "media.mp4")
    assert capsys.readouterr().out == "", "worker stdout 必須只留給 JSON 結果"
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            result["path"],
        ],
        check=True,
        capture_output=True,
    )
    assert {stream["codec_type"] for stream in json.loads(probe.stdout)["streams"]} == {
        "video",
        "audio",
    }


def test_size_limit_and_unlisted_selector_fail(native_media, tmp_path, monkeypatch):
    directory = tmp_path / "job"
    directory.mkdir()
    payload = {
        "action": "download",
        "url": "https://youtube.com/watch?v=fixture",
        "format_id": "best/bestvideo",
        "directory": str(directory),
    }
    with pytest.raises(ValueError, match="格式已不可用"):
        worker.run(payload)
    assert not list(directory.iterdir())
    payload["format_id"] = "v+a"
    monkeypatch.setattr(worker, "MAX_BYTES", 1024)
    with pytest.raises(ValueError):
        worker.run(payload)


def test_direct_rejects_merge_format(native_media):
    with pytest.raises(ValueError, match="合併音訊"):
        worker.run(
            {"action": "direct", "url": "https://youtube.com/watch?v=fixture", "format_id": "v+a"}
        )


def test_direct_returns_validated_muxed_url(native_media, monkeypatch):
    native_media["formats"][0]["acodec"] = "aac"
    checked = []
    monkeypatch.setattr(worker, "resolve_public", lambda host, port: checked.append((host, port)))
    assert worker.run(
        {"action": "direct", "url": "https://youtube.com/watch?v=fixture", "format_id": "v"}
    ) == {"url": "https://cdn.example/video"}
    assert checked == [("cdn.example", 443)]


def test_selected_format_overrides_ytdlp_default(native_media, tmp_path, monkeypatch):
    native_media["formats"] = [
        {
            "format_id": "low",
            "url": "https://cdn.example/video",
            "ext": "mp4",
            "protocol": "https",
            "vcodec": "mpeg4",
            "acodec": "aac",
            "height": 90,
        },
        {
            "format_id": "high",
            "url": "https://cdn.example/audio",
            "ext": "mp4",
            "protocol": "https",
            "vcodec": "mpeg4",
            "acodec": "aac",
            "height": 720,
        },
    ]
    directory = tmp_path / "selected"
    directory.mkdir()
    result = worker.run(
        {
            "action": "download",
            "url": "https://youtube.com/watch?v=fixture",
            "format_id": "low",
            "directory": str(directory),
        }
    )
    from pathlib import Path

    assert Path(result["path"]).read_bytes() == (tmp_path / "video.mp4").read_bytes(), (
        "SELECTED_FORMAT_ASSERTION"
    )


def test_muxed_selection_discards_preprocessed_merge_tracks(native_media, tmp_path):
    native_media["formats"].insert(
        0,
        {
            "format_id": "muxed",
            "url": "https://cdn.example/video",
            "ext": "mp4",
            "protocol": "https",
            "vcodec": "mpeg4",
            "acodec": "aac",
            "height": 40,
        },
    )
    directory = tmp_path / "muxed"
    directory.mkdir()
    worker.run(
        {
            "action": "download",
            "url": "https://youtube.com/watch?v=fixture",
            "format_id": "muxed",
            "directory": str(directory),
        }
    )
    assert (directory / "media.mp4").read_bytes() == (tmp_path / "video.mp4").read_bytes(), (
        "STALE_MERGE_ASSERTION"
    )
