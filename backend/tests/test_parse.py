import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_NOTES_DOWNLOAD_DIR", str(tmp_path / "downloads"))
    with TestClient(app) as session:
        yield session


def test_parse_demo(client):
    response = client.post("/api/parse", json={"url": "fixture://learning-demo"})
    assert response.status_code == 200
    assert response.json() == {
        "id": "learning-demo",
        "title": "用 AI 建立你的學習工作流",
        "uploader": "video-notes",
        "duration_seconds": 754,
        "source": "demo",
        "formats": [
            {
                "format_id": "demo-360",
                "label": "360p MP4 · 影片與音訊",
                "ext": "mp4",
                "has_audio": True,
                "requires_merge": False,
            }
        ],
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"url": "https://example.com/video"},
        {"url": ""},
        {"url": " "},
        {"url": "x" * 2049},
        {"url": "fixture://learning-demo", "admin": True},
    ],
)
def test_reject_unavailable_or_invalid_source(payload, client):
    assert client.post("/api/parse", json=payload).status_code == 422


def test_trim_url(client):
    response = client.post("/api/parse", json={"url": " fixture://learning-demo "})
    assert response.status_code == 200
    assert response.json()["id"] == "learning-demo"


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
