"""Offline tests for Redis/memory-backed app users and invites."""

from __future__ import annotations

import os
import sys
import types

from werkzeug.security import generate_password_hash

sys.modules.setdefault("google", types.ModuleType("google"))
sys.modules.setdefault("google.genai", types.ModuleType("google.genai"))
sys.modules["google"].genai = sys.modules["google.genai"]

os.environ["APP_ENV"] = "test"
os.environ["RATELIMIT_STORAGE_URI"] = "memory://"
os.environ["APP_USER_REDIS_URI"] = "memory://"
os.environ["APP_SESSION_SECRET"] = "test-session-secret-value-32chars!!"
os.environ["APP_AUTH_REQUIRED"] = "1"
os.environ["APP_AUTH_USERNAME"] = "admin.user"
os.environ["APP_AUTH_PASSWORD_HASH"] = generate_password_hash("admin-password-ok")
os.environ["APP_AUTH_ROLE"] = "officer"
os.environ["APP_AUTH_OFFICE_NAME"] = "สำนักงานทดสอบ"
os.environ["APP_AUTH_ALLOWED_TAMBONS"] = "หนองตาดใหญ่"
os.environ["APP_AUTH_ALLOWED_APPROVERS"] = "ผู้อนุมัติทดสอบ"
os.environ["APP_AUTH_CAN_SUBMIT"] = "0"

import user_auth
import app as app_module


def _reset_store():
    user_auth.reset_for_tests()
    user_auth.configure("memory://")
    app_module.app._user_store_ready = False
    app_module.APP_AUTH_REQUIRED = True
    app_module.APP_AUTH_USERNAME = "admin.user"
    app_module.APP_AUTH_PASSWORD_HASH = generate_password_hash("admin-password-ok")
    app_module.APP_SESSION_SECRET = "test-session-secret-value-32chars!!"
    user_auth.bootstrap_admin(app_module.APP_AUTH_USERNAME, app_module.APP_AUTH_PASSWORD_HASH)


def _csrf(client):
    response = client.get("/api/access/status")
    return response.get_json()["csrf_token"]


def test_bootstrap_admin_can_login_and_create_invite():
    _reset_store()
    client = app_module.app.test_client()
    csrf = _csrf(client)
    login = client.post(
        "/api/auth/login",
        json={"username": "admin.user", "password": "admin-password-ok"},
        headers={"X-CSRF-Token": csrf},
    )
    assert login.status_code == 200
    payload = login.get_json()
    assert payload["is_admin"] is True
    invite = client.post(
        "/api/auth/invites",
        json={},
        headers={"X-CSRF-Token": payload["csrf_token"]},
    )
    assert invite.status_code == 200
    invite_body = invite.get_json()
    assert invite_body["invite_url"]
    assert invite_body["token"]


def test_accept_invite_creates_non_admin_user():
    _reset_store()
    client = app_module.app.test_client()
    csrf = _csrf(client)
    login = client.post(
        "/api/auth/login",
        json={"username": "admin.user", "password": "admin-password-ok"},
        headers={"X-CSRF-Token": csrf},
    )
    admin_csrf = login.get_json()["csrf_token"]
    invite = client.post("/api/auth/invites", json={}, headers={"X-CSRF-Token": admin_csrf}).get_json()

    guest = app_module.app.test_client()
    guest_csrf = _csrf(guest)
    accepted = guest.post(
        "/api/auth/accept-invite",
        json={
            "token": invite["token"],
            "username": "officer.one",
            "password": "officer-pass-123",
        },
        headers={"X-CSRF-Token": guest_csrf},
    )
    assert accepted.status_code == 200
    body = accepted.get_json()
    assert body["username"] == "officer.one"
    assert body["is_admin"] is False

    reused = guest.post(
        "/api/auth/accept-invite",
        json={
            "token": invite["token"],
            "username": "officer.two",
            "password": "officer-pass-456",
        },
        headers={"X-CSRF-Token": body["csrf_token"]},
    )
    assert reused.status_code == 400


def test_non_admin_cannot_create_invite():
    _reset_store()
    admin = app_module.app.test_client()
    csrf = _csrf(admin)
    login = admin.post(
        "/api/auth/login",
        json={"username": "admin.user", "password": "admin-password-ok"},
        headers={"X-CSRF-Token": csrf},
    )
    admin_csrf = login.get_json()["csrf_token"]
    invite = admin.post("/api/auth/invites", json={}, headers={"X-CSRF-Token": admin_csrf}).get_json()

    guest = app_module.app.test_client()
    guest_csrf = _csrf(guest)
    accepted = guest.post(
        "/api/auth/accept-invite",
        json={
            "token": invite["token"],
            "username": "field.user",
            "password": "field-user-pass",
        },
        headers={"X-CSRF-Token": guest_csrf},
    )
    assert accepted.status_code == 200
    create = guest.post(
        "/api/auth/invites",
        json={},
        headers={"X-CSRF-Token": accepted.get_json()["csrf_token"]},
    )
    assert create.status_code == 403


def test_invite_token_not_stored_plaintext():
    _reset_store()
    invite = user_auth.create_invite("admin.user")
    raw = invite["token"]
    client = user_auth._client()
    assert isinstance(client, user_auth._MemoryRedis)
    token_hash = user_auth._hash_token(raw)
    # Raw token must not appear in keys or values; only the hash is used as key suffix.
    stored = " ".join(list(client._data.keys()) + list(client._data.values()))
    assert raw not in stored
    assert client.get(user_auth._invite_key(token_hash))
    assert token_hash in user_auth._invite_key(token_hash)


if __name__ == "__main__":
    for test in (
        test_bootstrap_admin_can_login_and_create_invite,
        test_accept_invite_creates_non_admin_user,
        test_non_admin_cannot_create_invite,
        test_invite_token_not_stored_plaintext,
    ):
        test()
        print(f"PASS {test.__name__}")
