"""Redis-backed application users and one-time invites.

Design:
- Shared office ACL still comes from server env (role/office/tambons/approvers).
- Bootstrap admin is synced from APP_AUTH_USERNAME / APP_AUTH_PASSWORD_HASH.
- Invite tokens are stored hashed; the raw token is returned only at creation.
- Storage URI defaults to APP_USER_REDIS_URI, then RATELIMIT_STORAGE_URI.
- memory:// uses an in-process dict (tests/local only; not shared across workers).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import time
from typing import Any
from urllib.parse import urlparse

from werkzeug.security import check_password_hash, generate_password_hash

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
INVITE_TTL_SECONDS = int(os.environ.get("APP_INVITE_TTL_SECONDS", str(7 * 24 * 3600)))
MIN_PASSWORD_LENGTH = 10
KEY_PREFIX = os.environ.get("APP_USER_REDIS_PREFIX", "tvauth").strip() or "tvauth"

_LOCK = threading.Lock()
_CLIENT: Any = None
_MEMORY: dict[str, str] | None = None
_REDIS_URL: str | None = None


class _MemoryRedis:
    """Minimal Redis-like store for memory:// and offline tests."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: str) -> bool:
        with self._lock:
            self._data[key] = value
            return True

    def delete(self, *keys: str) -> int:
        with self._lock:
            removed = 0
            for key in keys:
                if key in self._data:
                    del self._data[key]
                    removed += 1
            return removed

    def sadd(self, key: str, *members: str) -> int:
        with self._lock:
            current = set(json.loads(self._data.get(key, "[]")))
            before = len(current)
            current.update(members)
            self._data[key] = json.dumps(sorted(current), ensure_ascii=False)
            return len(current) - before

    def srem(self, key: str, *members: str) -> int:
        with self._lock:
            current = set(json.loads(self._data.get(key, "[]")))
            before = len(current)
            current.difference_update(members)
            self._data[key] = json.dumps(sorted(current), ensure_ascii=False)
            return before - len(current)

    def smembers(self, key: str) -> set[str]:
        with self._lock:
            return set(json.loads(self._data.get(key, "[]")))

    def ping(self) -> bool:
        return True


def default_redis_url() -> str:
    configured = os.environ.get("APP_USER_REDIS_URI", "").strip()
    if configured:
        return configured
    rate_limit = os.environ.get("RATELIMIT_STORAGE_URI", "memory://").strip()
    return rate_limit or "memory://"


def configure(redis_url: str | None = None) -> str:
    """Connect to Redis (or memory://). Safe to call repeatedly."""
    global _CLIENT, _MEMORY, _REDIS_URL
    url = (redis_url or default_redis_url()).strip() or "memory://"
    with _LOCK:
        if _CLIENT is not None and _REDIS_URL == url:
            return url
        _REDIS_URL = url
        if url.startswith("memory://"):
            _MEMORY = {}
            _CLIENT = _MemoryRedis()
            return url
        import redis

        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        _CLIENT = client
        _MEMORY = None
        return url


def reset_for_tests() -> None:
    """Drop in-process store state (tests only)."""
    global _CLIENT, _MEMORY, _REDIS_URL
    with _LOCK:
        _CLIENT = None
        _MEMORY = None
        _REDIS_URL = None


def _client() -> Any:
    if _CLIENT is None:
        configure()
    assert _CLIENT is not None
    return _CLIENT


def _user_key(username: str) -> str:
    return f"{KEY_PREFIX}:user:{username.casefold()}"


def _users_set_key() -> str:
    return f"{KEY_PREFIX}:users"


def _invite_key(token_hash: str) -> str:
    return f"{KEY_PREFIX}:invite:{token_hash}"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _loads(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def validate_username(username: str) -> str | None:
    value = str(username or "").strip()
    if not USERNAME_RE.fullmatch(value):
        return None
    return value


def validate_password(password: str) -> bool:
    return isinstance(password, str) and len(password) >= MIN_PASSWORD_LENGTH


def bootstrap_admin(username: str, password_hash: str) -> None:
    """Ensure the env bootstrap admin exists and matches the current hash."""
    name = validate_username(username)
    hash_value = str(password_hash or "").strip()
    if not name or not hash_value:
        return
    now = int(time.time())
    client = _client()
    key = _user_key(name)
    existing = _loads(client.get(key))
    payload = {
        "username": name if existing is None else existing.get("username") or name,
        "password_hash": hash_value,
        "is_admin": True,
        "is_active": True,
        "created_at": int(existing["created_at"]) if existing and existing.get("created_at") else now,
        "updated_at": now,
    }
    client.set(key, _dumps(payload))
    client.sadd(_users_set_key(), payload["username"])


def authenticate(username: str, password: str) -> dict | None:
    name = validate_username(username)
    if not name or not isinstance(password, str) or not password:
        return None
    row = _loads(_client().get(_user_key(name)))
    if row is None or not row.get("is_active"):
        return None
    if not check_password_hash(str(row.get("password_hash") or ""), password):
        return None
    return {
        "username": str(row.get("username") or name),
        "is_admin": bool(row.get("is_admin")),
    }


def get_user(username: str) -> dict | None:
    name = validate_username(username)
    if not name:
        return None
    row = _loads(_client().get(_user_key(name)))
    if row is None:
        return None
    return {
        "username": str(row.get("username") or name),
        "is_admin": bool(row.get("is_admin")),
        "is_active": bool(row.get("is_active")),
        "created_at": int(row.get("created_at") or 0),
    }


def list_users() -> list[dict]:
    client = _client()
    names = sorted(client.smembers(_users_set_key()), key=lambda item: item.casefold())
    users: list[dict] = []
    for name in names:
        row = get_user(name)
        if row is not None:
            users.append(row)
    users.sort(key=lambda item: (not item["is_admin"], item["username"].casefold()))
    return users


def create_invite(created_by: str) -> dict:
    creator = validate_username(created_by) or str(created_by or "").strip()
    if not creator:
        raise ValueError("created_by is required")
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    now = int(time.time())
    expires_at = now + max(3600, INVITE_TTL_SECONDS)
    payload = {
        "created_by": creator,
        "expires_at": expires_at,
        "used_at": None,
        "used_by": None,
        "created_at": now,
    }
    _client().set(_invite_key(token_hash), _dumps(payload))
    return {
        "token": raw_token,
        "expires_at": expires_at,
        "created_by": creator,
    }


def peek_invite(token: str) -> dict | None:
    token_hash = _hash_token(str(token or "").strip())
    now = int(time.time())
    row = _loads(_client().get(_invite_key(token_hash)))
    if row is None:
        return None
    if row.get("used_at") is not None:
        return {"valid": False, "reason": "used"}
    if int(row.get("expires_at") or 0) < now:
        return {"valid": False, "reason": "expired"}
    return {"valid": True, "expires_at": int(row["expires_at"])}


def accept_invite(token: str, username: str, password: str) -> dict:
    name = validate_username(username)
    if not name:
        raise ValueError("invalid_username")
    if not validate_password(password):
        raise ValueError("weak_password")
    token_hash = _hash_token(str(token or "").strip())
    invite_key = _invite_key(token_hash)
    user_key = _user_key(name)
    now = int(time.time())
    password_hash = generate_password_hash(password)
    client = _client()

    # Memory backend: simple lock; Redis: optimistic WATCH transaction.
    if isinstance(client, _MemoryRedis):
        with _LOCK:
            invite = _loads(client.get(invite_key))
            if invite is None:
                raise ValueError("invalid_invite")
            if invite.get("used_at") is not None:
                raise ValueError("used")
            if int(invite.get("expires_at") or 0) < now:
                raise ValueError("expired")
            if client.get(user_key):
                raise ValueError("username_taken")
            user_payload = {
                "username": name,
                "password_hash": password_hash,
                "is_admin": False,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            invite["used_at"] = now
            invite["used_by"] = name
            client.set(user_key, _dumps(user_payload))
            client.sadd(_users_set_key(), name)
            client.set(invite_key, _dumps(invite))
        return {"username": name, "is_admin": False}

    # redis-py WatchError path
    import redis as redis_mod

    with client.pipeline() as pipe:
        while True:
            try:
                pipe.watch(invite_key, user_key)
                invite = _loads(pipe.get(invite_key))
                if invite is None:
                    pipe.unwatch()
                    raise ValueError("invalid_invite")
                if invite.get("used_at") is not None:
                    pipe.unwatch()
                    raise ValueError("used")
                if int(invite.get("expires_at") or 0) < now:
                    pipe.unwatch()
                    raise ValueError("expired")
                if pipe.get(user_key):
                    pipe.unwatch()
                    raise ValueError("username_taken")
                user_payload = {
                    "username": name,
                    "password_hash": password_hash,
                    "is_admin": False,
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                }
                invite["used_at"] = now
                invite["used_by"] = name
                pipe.multi()
                pipe.set(user_key, _dumps(user_payload))
                pipe.sadd(_users_set_key(), name)
                pipe.set(invite_key, _dumps(invite))
                pipe.execute()
                break
            except redis_mod.WatchError:
                continue
    return {"username": name, "is_admin": False}


def set_user_active(username: str, active: bool) -> bool:
    name = validate_username(username)
    if not name:
        return False
    client = _client()
    key = _user_key(name)
    row = _loads(client.get(key))
    if row is None or row.get("is_admin"):
        return False
    row["is_active"] = bool(active)
    row["updated_at"] = int(time.time())
    client.set(key, _dumps(row))
    return True


def storage_backend_label() -> str:
    url = _REDIS_URL or default_redis_url()
    if url.startswith("memory://"):
        return "memory"
    parsed = urlparse(url)
    return parsed.scheme or "redis"
