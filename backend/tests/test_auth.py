import os
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import ABSOLUTE, IDLE, AuthSettings, cleanup_expired, digest, now
from app.database import LoginSession, User, build_engine
from app.main import app

HEADERS = {"Origin": "http://127.0.0.1:3422", "X-Requested-With": "video-notes"}
PASSWORD = "public-test-password-12345"
BODY = {"email": "reader@example.test", "password": PASSWORD}


@pytest.fixture(scope="module")
def engine():
    url = os.environ.get("VIDEO_NOTES_DATABASE_URL")
    if not url or os.environ.get("VIDEO_NOTES_ISOLATED_TEST_DB") != "1":
        pytest.fail("auth tests 必須用 make test-integration 啟動隔離 PostgreSQL。")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    db = build_engine(url)
    yield db
    db.dispose()


@pytest.fixture
def client(engine, tmp_path, monkeypatch):
    with Session(engine) as db, db.begin():
        db.execute(delete(LoginSession))
        db.execute(delete(User))
    monkeypatch.setenv("VIDEO_NOTES_DOWNLOAD_DIR", str(tmp_path / "downloads"))
    with TestClient(app) as session:
        yield session


def register(client):
    response = client.post("/api/auth/register", json=BODY, headers=HEADERS)
    assert response.status_code == 201
    return response


def test_auth_register_reload_logout_and_revocation(client, engine):
    response = register(client)
    assert response.json()["email"] == BODY["email"]
    assert set(response.json()) == {"id", "email"}
    flags = response.headers["set-cookie"].lower()
    assert "httponly" in flags and "samesite=lax" in flags and "domain=" not in flags
    assert response.headers["cache-control"] == "no-store"
    token = client.cookies.get("vn_session")
    with Session(engine) as db:
        user = db.scalar(select(User))
        assert user.password_hash.startswith("$argon2id$")
        assert db.get(LoginSession, digest(token)) is not None
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout", json={}, headers=HEADERS).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set("vn_session", token)
    assert client.get("/api/auth/me").status_code == 401


def test_auth_login_wrong_password_rotation_and_duplicate(client, engine):
    register(client)
    old = client.cookies.get("vn_session")
    assert client.post("/api/auth/register", json=BODY, headers=HEADERS).status_code == 409
    wrong = {**BODY, "password": "wrong-public-password"}
    assert client.post("/api/auth/login", json=wrong, headers=HEADERS).status_code == 401
    assert client.post("/api/auth/login", json=BODY, headers=HEADERS).status_code == 200
    assert client.cookies.get("vn_session") != old
    with Session(engine) as db:
        assert db.get(LoginSession, digest(old)) is None


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "null"},
        {**HEADERS, "Origin": "https://evil.example"},
        {"Origin": HEADERS["Origin"]},
        {**HEADERS, "Content-Type": "text/plain"},
    ],
)
def test_auth_csrf_rejected(client, headers):
    assert client.post("/api/auth/register", json=BODY, headers=headers).status_code == 403


def test_auth_forged_session_rejected(client):
    client.cookies.set("vn_session", "A" * 43)
    assert client.get("/api/auth/me").status_code == 401, "AUTH_GUARD_ASSERTION"


@pytest.mark.parametrize("expiration", ["idle", "absolute"])
def test_auth_expired_session_rejected(client, engine, expiration):
    register(client)
    with Session(engine) as db, db.begin():
        session = db.scalar(select(LoginSession))
        if expiration == "idle":
            session.last_seen_at = now() - IDLE - timedelta(seconds=1)
        else:
            session.absolute_expires_at = now() - timedelta(seconds=1)
    assert client.get("/api/auth/me").status_code == 401


def test_auth_idle_refresh_respects_absolute_and_cookie(client, engine):
    register(client)
    with Session(engine) as db, db.begin():
        session = db.scalar(select(LoginSession))
        session.last_seen_at = now() - timedelta(minutes=20)
        absolute = session.absolute_expires_at
    assert client.get("/api/auth/me").status_code == 200
    with Session(engine) as db:
        session = db.scalar(select(LoginSession))
        assert session.last_seen_at > now() - timedelta(seconds=10)
        assert session.absolute_expires_at == absolute
        assert session.absolute_expires_at - session.created_at == ABSOLUTE


def test_auth_secure_configuration(client):
    assert AuthSettings("https://video.example", True).cookie == "__Host-vn_session"
    app.state.auth_settings = AuthSettings("https://video.example", True)
    response = client.post(
        "/api/auth/register", json=BODY, headers={**HEADERS, "Origin": "https://video.example"}
    )
    assert response.status_code == 201
    flags = response.headers["set-cookie"].lower()
    assert flags.startswith("__host-vn_session=") and "secure" in flags and "httponly" in flags
    assert "domain=" not in flags and "path=/" in flags
    with pytest.raises(RuntimeError):
        AuthSettings("http://video.example", True)


def test_auth_expired_cleanup_preserves_live_session(client, engine):
    register(client)
    clock = now()
    with Session(engine) as db, db.begin():
        user = db.scalar(select(User))
        db.add(
            LoginSession(
                token_hash="a" * 64,
                user_id=user.id,
                created_at=clock - ABSOLUTE,
                last_seen_at=clock,
                absolute_expires_at=clock - timedelta(seconds=1),
            )
        )
        db.add(
            LoginSession(
                token_hash="b" * 64,
                user_id=user.id,
                created_at=clock - IDLE,
                last_seen_at=clock - IDLE - timedelta(seconds=1),
                absolute_expires_at=clock + ABSOLUTE,
            )
        )
    cleanup_expired(engine)
    with Session(engine) as db:
        assert len(db.scalars(select(LoginSession)).all()) == 1
    assert client.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize("password", ["short-secret", "long-secret-" * 20])
def test_auth_validation_does_not_echo_password(client, password):
    response = client.post(
        "/api/auth/register", json={**BODY, "password": password}, headers=HEADERS
    )
    assert response.status_code == 422
    assert password not in response.text, "PASSWORD_REDACTION_ASSERTION"


def test_auth_password_not_stripped_and_rate_limit(client):
    body = {**BODY, "password": " space-password-12345 "}
    assert client.post("/api/auth/register", json=body, headers=HEADERS).status_code == 201
    assert (
        client.post(
            "/api/auth/login", json={**body, "password": body["password"].strip()}, headers=HEADERS
        ).status_code
        == 401
    )
    for _ in range(8):
        client.post("/api/auth/login", json=body, headers=HEADERS)
    assert client.post("/api/auth/login", json=body, headers=HEADERS).status_code == 429
