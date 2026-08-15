#!/usr/bin/env python3
"""Static security checks for application authentication and Docker permissions.

This checker is intentionally read-only: it reads repository files, prints findings,
and exits non-zero when a production safety requirement is not met. It never reads
or prints application secrets, contacts production, builds an image, or mutates the
working tree.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    check: str
    status: str
    message: str
    remediation: str = ""


PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"อ่านไฟล์ไม่ได้: {path}: {exc}") from exc


def _add(findings: list[Finding], check: str, status: str, message: str, remediation: str = "") -> None:
    findings.append(Finding(check, status, message, remediation))


def check_app_auth(repo_root: Path, findings: list[Finding]) -> None:
    app_path = repo_root / "app.py"
    if not app_path.is_file():
        _add(findings, "APP_AUTH_REQUIRED", FAIL, "ไม่พบ app.py", "ตรวจว่าเรียกสคริปต์จาก repository ที่ถูกต้อง")
        return

    source = _read_text(app_path)
    assignment = re.search(
        r"APP_AUTH_REQUIRED\s*=\s*os\.environ\.get\(\s*['\"]APP_AUTH_REQUIRED['\"]\s*,\s*['\"]([^'\"]+)['\"]",
        source,
    )
    if not assignment:
        _add(
            findings,
            "APP_AUTH_REQUIRED.default",
            FAIL,
            "ไม่พบการกำหนดค่า APP_AUTH_REQUIRED แบบตรวจสอบได้",
            "กำหนดค่า default ให้ fail-closed และอ่านจาก environment เท่านั้น",
        )
    else:
        default_value = assignment.group(1).strip().lower()
        if default_value in {"1", "true", "yes"}:
            _add(findings, "APP_AUTH_REQUIRED.default", PASS, "default บังคับ application authentication")
        else:
            _add(
                findings,
                "APP_AUTH_REQUIRED.default",
                FAIL,
                f"default ของ APP_AUTH_REQUIRED เป็น {default_value!r} จึงไม่ fail-closed",
                "เปลี่ยน default เป็น '1' หรือกำหนด APP_AUTH_REQUIRED=1 ใน production ก่อนเปิด Public Internet",
            )

    required_envs = ("APP_AUTH_USERNAME", "APP_AUTH_PASSWORD_HASH", "APP_SESSION_SECRET")
    missing_in_source = [name for name in required_envs if name not in source]
    if missing_in_source:
        _add(
            findings,
            "APP_AUTH_REQUIRED.environment",
            FAIL,
            "ไม่พบชื่อ environment ที่จำเป็นครบถ้วนใน app.py: " + ", ".join(missing_in_source),
            "ต้องมี username, password hash และ session secret จาก environment โดยห้าม hardcode secret",
        )
    else:
        _add(findings, "APP_AUTH_REQUIRED.environment", PASS, "พบ production authentication environment contract")

    profile_envs = (
        "APP_AUTH_ROLE",
        "APP_AUTH_OFFICE_NAME",
        "APP_AUTH_ALLOWED_TAMBONS",
        "APP_AUTH_ALLOWED_APPROVERS",
        "APP_AUTH_CAN_SUBMIT",
    )
    missing_profile_envs = [name for name in profile_envs if name not in source]
    has_profile_guard = "def _auth_profile_configured()" in source and "_validate_run_authorization" in source
    if not missing_profile_envs and has_profile_guard:
        _add(findings, "APP_AUTH_REQUIRED.authorization_profile", PASS, "พบ server-side authorization profile และ validation helper")
    else:
        detail = ", ".join(missing_profile_envs) if missing_profile_envs else "authorization validation helper"
        _add(
            findings,
            "APP_AUTH_REQUIRED.authorization_profile",
            FAIL,
            "ไม่พบ contract ของ " + detail,
            "derive role/office/tambon/approver/can_submit จาก authenticated identity และ validate ก่อนเริ่ม automation",
        )

    has_config_guard = "if APP_AUTH_REQUIRED and not _auth_configured()" in source
    has_session_guard = "if APP_AUTH_REQUIRED and not _app_authenticated()" in source
    has_startup_auth_guard = (
        "if APP_ENV in {'production', 'prod'} and APP_AUTH_REQUIRED:" in source
        and "Production application authentication secrets are not configured" in source
        and "Production authorization profile is not configured" in source
    )
    if has_startup_auth_guard:
        _add(findings, "APP_AUTH_REQUIRED.startup_guard", PASS, "production startup จะ fail closed เมื่อ auth secret/profile ไม่ครบ")
    else:
        _add(
            findings,
            "APP_AUTH_REQUIRED.startup_guard",
            FAIL,
            "ไม่พบ production startup guard สำหรับ auth secret/profile",
            "ให้ production container หยุดทำงานเมื่อ authentication หรือ authorization profile ไม่ครบ",
        )
    if has_config_guard and has_session_guard:
        _add(findings, "APP_AUTH_REQUIRED.fail_closed", PASS, "พบ config guard และ unauthenticated-session guard")
    else:
        missing = []
        if not has_config_guard:
            missing.append("config guard")
        if not has_session_guard:
            missing.append("session guard")
        _add(
            findings,
            "APP_AUTH_REQUIRED.fail_closed",
            FAIL,
            "ไม่พบ " + " และ ".join(missing),
            "protected API ต้องตอบปฏิเสธเมื่อ config ไม่ครบหรือยังไม่มี authenticated session",
        )

    has_run_route = "'/api/run'" in source or '"/api/run"' in source
    protected_match = re.search(r"PROTECTED_API_PATHS\s*=\s*\{(?P<body>.*?)\}", source, re.DOTALL)
    run_is_protected = bool(protected_match and "/api/run" in protected_match.group("body"))
    if has_run_route and run_is_protected:
        _add(findings, "APP_AUTH_REQUIRED.api_run_boundary", PASS, "/api/run อยู่ใน protected API set")
    else:
        _add(
            findings,
            "APP_AUTH_REQUIRED.api_run_boundary",
            FAIL,
            "/api/run ไม่ได้ถูกยืนยันว่าอยู่ใน protected API set",
            "เพิ่ม /api/run ใน protected API boundary และทดสอบ unauthenticated access",
        )

    production_rate_limit_guard = (
        "APP_ENV in {'production', 'prod'}" in source
        and "RATE_LIMIT_STORAGE_URI.startswith('memory://')" in source
    )
    if production_rate_limit_guard:
        _add(findings, "APP_AUTH_REQUIRED.rate_limit_storage", PASS, "production memory:// rate limit ถูก fail-closed")
    else:
        _add(
            findings,
            "APP_AUTH_REQUIRED.rate_limit_storage",
            FAIL,
            "ไม่พบ guard ที่ห้ามใช้ memory:// ใน production",
            "ตั้ง RATELIMIT_STORAGE_URI เป็น shared Redis และให้ production startup ปฏิเสธ memory://",
        )

    login_limit = re.search(r"@limiter\.limit\(\s*['\"]5 per minute; 20 per hour['\"]", source)
    if login_limit:
        _add(findings, "APP_AUTH_REQUIRED.login_rate_limit", PASS, "login endpoint มี rate limit")
    else:
        _add(
            findings,
            "APP_AUTH_REQUIRED.login_rate_limit",
            WARN,
            "ไม่พบ login rate limit ตามค่าที่คาดหวัง",
            "กำหนด rate limit และทดสอบ brute-force protection",
        )


def check_docker_permissions(repo_root: Path, findings: list[Finding]) -> None:
    dockerfile = repo_root / "Dockerfile"
    if not dockerfile.is_file():
        _add(findings, "Docker.permissions", FAIL, "ไม่พบ Dockerfile", "ตรวจว่าเรียกสคริปต์จาก repository ที่ถูกต้อง")
        return

    source = _read_text(dockerfile)
    normalized = re.sub(r"\s+", " ", source)

    broad_world_write = re.search(r"chmod\s+(?:-[^\n]*\s+)?(?:-R\s+)?777\s+(?:/code|\.)", normalized, re.IGNORECASE)
    if broad_world_write:
        _add(
            findings,
            "Docker.permissions.world_writable",
            FAIL,
            "พบ chmod 777 แบบ recursive/กว้างกับ source tree",
            "ลบ chmod -R 777 และให้เขียนได้เฉพาะ upload/temp directories ที่จำเป็น",
        )
    else:
        _add(findings, "Docker.permissions.world_writable", PASS, "ไม่พบ chmod 777 กับ source tree")

    user_match = re.search(r"^\s*USER\s+(\S+)\s*$", source, re.MULTILINE)
    if not user_match:
        _add(
            findings,
            "Docker.permissions.non_root",
            FAIL,
            "ไม่พบ USER instruction สำหรับ non-root runtime",
            "สร้าง appuser และใช้ USER appuser ก่อน CMD",
        )
    elif user_match.group(1).lower() == "root":
        _add(
            findings,
            "Docker.permissions.non_root",
            FAIL,
            "Docker runtime ถูกกำหนดเป็น root",
            "เปลี่ยนเป็น non-root user ที่มีสิทธิ์เท่าที่จำเป็น",
        )
    else:
        _add(findings, "Docker.permissions.non_root", PASS, f"runtime user เป็น {user_match.group(1)} ไม่ใช่ root")

    if re.search(r"COPY\s+--chown=[^\s]+\s+\.\s+/code", normalized):
        _add(findings, "Docker.permissions.copy_owner", PASS, "COPY source tree มี owner ที่กำหนดชัดเจน")
    else:
        _add(
            findings,
            "Docker.permissions.copy_owner",
            FAIL,
            "ไม่พบ COPY --chown สำหรับ source tree",
            "ใช้ COPY --chown=appuser:appuser . /code หรือกำหนด ownership อย่างชัดเจนก่อน USER appuser",
        )

    if re.search(r"chown\s+-R\s+[^\s]+\s+/code", normalized) or re.search(r"COPY\s+--chown=[^\s]+\s+\.\s+/code", normalized):
        _add(findings, "Docker.permissions.ownership", PASS, "มีการกำหนด ownership ของ /code อย่างชัดเจน")
    else:
        _add(
            findings,
            "Docker.permissions.ownership",
            WARN,
            "ไม่พบ chown ของ /code แบบ explicit",
            "ตรวจให้ source tree อ่านได้ และ write permission จำกัดอยู่ใน runtime directories",
        )

    compose = repo_root / "docker-compose.yml"
    if compose.is_file():
        compose_source = _read_text(compose)
        if re.search(r"^\s*user\s*:\s*root\s*$", compose_source, re.MULTILINE | re.IGNORECASE):
            _add(
                findings,
                "Docker.permissions.compose_user",
                FAIL,
                "docker-compose กำหนด user เป็น root",
                "ลบ user: root และใช้ non-root user เดียวกับ Dockerfile",
            )
        elif re.search(r"^\s*user\s*:", compose_source, re.MULTILINE):
            _add(findings, "Docker.permissions.compose_user", PASS, "docker-compose มีการกำหนด user")
        else:
            _add(
                findings,
                "Docker.permissions.compose_user",
                WARN,
                "docker-compose ไม่ได้กำหนด user โดยตรง",
                "กำหนด non-root user ให้สอดคล้องกับ Dockerfile หาก compose ใช้ใน production",
            )

        public_port = re.search(r"['\"](?:0\.0\.0\.0:)?7860:7860['\"]", compose_source)
        local_port = re.search(r"['\"]127\.0\.0\.1:7860:7860['\"]", compose_source)
        if public_port and not local_port:
            _add(
                findings,
                "Docker.permissions.compose_port",
                FAIL,
                "docker-compose publish port 7860 ออกทุก interface",
                "bind เป็น 127.0.0.1:7860:7860 หรือไม่ publish port และใช้ reverse proxy/private network",
            )
        else:
            _add(findings, "Docker.permissions.compose_port", PASS, "ไม่มีการ publish port 7860 ออกสู่ public interface")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit one valid JSON object per finding without exposing secrets",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo.resolve()
    findings: list[Finding] = []
    check_app_auth(repo_root, findings)
    check_docker_permissions(repo_root, findings)

    failures = 0
    warnings = 0
    for finding in findings:
        if finding.status == FAIL:
            failures += 1
        elif finding.status == WARN:
            warnings += 1
        if args.json:
            print(json.dumps({
                "check": finding.check,
                "status": finding.status,
                "message": finding.message,
            }, ensure_ascii=False))
        else:
            print(f"[{finding.status}] {finding.check}: {finding.message}")
            if finding.remediation:
                print(f"        remediation: {finding.remediation}")

    print(f"SUMMARY: failures={failures} warnings={warnings} checks={len(findings)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
