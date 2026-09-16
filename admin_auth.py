import hashlib
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import HTTPException, Request, Response

import db

SESSION_COOKIE = "varol_admin_session"
SESSION_TTL_HOURS = int(os.getenv("ADMIN_SESSION_TTL_HOURS", "12"))
MIN_PASSWORD_LENGTH = 20
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 900
LOGIN_BLOCK_SECONDS = 900

_login_attempts: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def _check_login_rate_limit(ip: str) -> None:
    now = time.time()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
    _login_attempts[ip] = attempts
    if len(attempts) >= LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Слишком много попыток входа. Попробуйте позже.",
        )


def _record_failed_login(ip: str) -> None:
    _login_attempts.setdefault(ip, []).append(time.time())


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise RuntimeError(f"ADMIN_PASSWORD must contain at least {MIN_PASSWORD_LENGTH} characters")
    if password.strip() != password:
        raise RuntimeError("ADMIN_PASSWORD must not start or end with whitespace")
    if len(set(password)) < 8:
        raise RuntimeError("ADMIN_PASSWORD is too repetitive")


def ensure_admin_password(password: str, *, force_update: bool = False) -> None:
    if not password:
        raise RuntimeError("ADMIN_PASSWORD is required")
    validate_password_strength(password)
    existing = db.get_admin_password_hash()
    if existing and not force_update and verify_password(password, existing):
        return
    db.set_admin_password_hash(hash_password(password))
    db.delete_all_admin_sessions()


def login(request: Request, response: Response, password: str) -> None:
    ip = _client_ip(request)
    _check_login_rate_limit(ip)

    stored_hash = db.get_admin_password_hash()
    if not stored_hash or not verify_password(password, stored_hash):
        _record_failed_login(ip)
        raise HTTPException(status_code=401, detail="Неверный пароль")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
    db.create_admin_session(
        token_hash=_hash_token(token),
        expires_at=expires_at,
        ip_address=ip,
        user_agent=(request.headers.get("User-Agent") or "")[:512],
    )

    secure = request.url.scheme == "https"
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=SESSION_TTL_HOURS * 3600,
        path="/",
    )
    _login_attempts.pop(ip, None)


def logout(request: Request, response: Response) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.delete_admin_session(_hash_token(token))
    response.delete_cookie(SESSION_COOKIE, path="/")


def verify_admin(request: Request) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    session = db.get_admin_session(_hash_token(token))
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")

    expires_at = session.get("expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc):
        db.delete_admin_session(_hash_token(token))
        raise HTTPException(status_code=401, detail="Session expired")
