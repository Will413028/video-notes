import hashlib
import math
import re
import secrets
import threading
import time
from collections import OrderedDict, deque
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import LoginSession, User

router = APIRouter(prefix="/api/auth")
hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID)
DUMMY_HASH = hasher.hash("dummy-public-fixture-password")
IDLE = timedelta(minutes=30)
ABSOLUTE = timedelta(hours=12)


def now():
    return datetime.now(UTC)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthSettings:
    def __init__(self, origin="http://127.0.0.1:3422", secure=False):
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError("Auth origin 必須是完整且無路徑的 HTTP(S) origin。")
        if secure and parsed.scheme != "https":
            raise RuntimeError("Secure cookie 必須搭配 HTTPS origin。")
        if not secure and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise RuntimeError("非本機 origin 必須使用 Secure cookie。")
        self.origin, self.secure = origin, secure
        self.cookie = "__Host-vn_session" if secure else "vn_session"


class Attempts:
    def __init__(self):
        self.lock = threading.Lock()
        self.entries = OrderedDict()

    def check(self, key: str, limit: int):
        clock = time.monotonic()
        with self.lock:
            entries = self.entries.setdefault(key, deque())
            self.entries.move_to_end(key)
            while entries and entries[0] < clock - 60:
                entries.popleft()
            if len(entries) >= limit:
                raise HTTPException(
                    429, "嘗試次數過多，請稍後再試。", headers={"Retry-After": "60"}
                )
            entries.append(clock)
            while len(self.entries) > 2048:
                self.entries.popitem(last=False)


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=15, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if (
            not re.fullmatch(
                r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}",
                value,
            )
            or ".." in value
        ):
            raise ValueError("請輸入有效 email。")
        return value


def database(request: Request):
    engine = request.app.state.database
    if engine is None:
        raise HTTPException(503, "請先啟動本機資料庫與 migration。")
    with Session(engine) as db, db.begin():
        yield db


def csrf(request: Request):
    settings = request.app.state.auth_settings
    if (
        request.headers.get("origin") != settings.origin
        or request.headers.get("x-requested-with") != "video-notes"
        or request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(403, "請從本站重新操作。")


def cookie(
    response: Response, settings: AuthSettings, token: str, expires: datetime, clock: datetime
):
    response.set_cookie(
        settings.cookie,
        token,
        max_age=max(0, math.ceil((expires - clock).total_seconds())),
        httponly=True,
        secure=settings.secure,
        samesite="lax",
        path="/",
    )


def user_json(user: User):
    return {"id": str(user.id), "email": user.email}


def new_session(request: Request, response: Response, db: Session, user: User):
    settings = request.app.state.auth_settings
    old = request.cookies.get(settings.cookie)
    if old:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(old)))
    clock, token = now(), secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=digest(token),
            user_id=user.id,
            created_at=clock,
            last_seen_at=clock,
            absolute_expires_at=clock + ABSOLUTE,
        )
    )
    cookie(response, settings, token, clock + IDLE, clock)
    return user_json(user)


Database = Annotated[Session, Depends(database, scope="function")]


def current_user(request: Request, response: Response, db: Database):
    settings = request.app.state.auth_settings
    token = request.cookies.get(settings.cookie, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise HTTPException(401, "請先登入。")
    session = db.scalar(
        select(LoginSession).where(LoginSession.token_hash == digest(token)).with_for_update()
    )
    clock = now()
    if (
        session is None
        or session.absolute_expires_at <= clock
        or session.last_seen_at + IDLE <= clock
    ):
        raise HTTPException(401, "請重新登入。")
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(401, "請重新登入。")
    session.last_seen_at = clock
    cookie(response, settings, token, min(clock + IDLE, session.absolute_expires_at), clock)
    return user


def cleanup_expired(engine):
    clock = now()
    with Session(engine) as db, db.begin():
        db.execute(delete(LoginSession).where(LoginSession.absolute_expires_at <= clock))
        db.execute(delete(LoginSession).where(LoginSession.last_seen_at <= clock - IDLE))


def limit(request: Request, email: str):
    attempts = request.app.state.auth_attempts
    attempts.check("peer:" + (request.client.host if request.client else "unknown"), 60)
    attempts.check("email:" + digest(email), 10)


@router.post("/register", dependencies=[Depends(csrf)], status_code=201)
def register(payload: Credentials, request: Request, response: Response, db: Database):
    limit(request, payload.email)
    user = User(email=payload.email, password_hash=hasher.hash(payload.password), created_at=now())
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        raise HTTPException(409, "此 email 已註冊。") from None
    return new_session(request, response, db, user)


@router.post("/login", dependencies=[Depends(csrf)])
def login(payload: Credentials, request: Request, response: Response, db: Database):
    limit(request, payload.email)
    user = db.scalar(select(User).where(User.email == payload.email))
    try:
        hasher.verify(user.password_hash if user else DUMMY_HASH, payload.password)
    except (VerificationError, InvalidHashError):
        raise HTTPException(401, "Email 或密碼不正確。") from None
    if user is None:
        raise HTTPException(401, "Email 或密碼不正確。")
    return new_session(request, response, db, user)


@router.get("/me")
def me(user: Annotated[User, Depends(current_user)]):
    return user_json(user)


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


@router.post("/logout", dependencies=[Depends(csrf)])
def logout(payload: EmptyRequest, request: Request, response: Response, db: Database):
    settings = request.app.state.auth_settings
    token = request.cookies.get(settings.cookie)
    if token:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(token)))
    response.delete_cookie(
        settings.cookie, path="/", secure=settings.secure, httponly=True, samesite="lax"
    )
    return {"status": "ok"}
