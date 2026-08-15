from pathlib import Path

from scripts.security_check import FAIL, PASS, check_app_auth, check_docker_permissions


AUTH_SOURCE = """
import os
APP_AUTH_REQUIRED = os.environ.get('APP_AUTH_REQUIRED', '1').strip().lower() in {'1', 'true', 'yes'}
APP_AUTH_USERNAME = os.environ.get('APP_AUTH_USERNAME', '').strip()
APP_AUTH_PASSWORD_HASH = os.environ.get('APP_AUTH_PASSWORD_HASH', '').strip()
APP_SESSION_SECRET = os.environ.get('APP_SESSION_SECRET', '').strip()
PROTECTED_API_PATHS = {'/api/run'}
if APP_AUTH_REQUIRED and not _auth_configured():
    pass
if APP_AUTH_REQUIRED and not _app_authenticated():
    pass
@limiter.limit('5 per minute; 20 per hour')
def app_login():
    pass
"""


def _write_repo(tmp_path: Path, app_source: str, dockerfile: str) -> Path:
    (tmp_path / "app.py").write_text(app_source, encoding="utf-8")
    (tmp_path / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    return tmp_path


def _statuses(findings):
    return {finding.check: finding.status for finding in findings}


def test_auth_checker_rejects_non_fail_closed_default(tmp_path):
    source = AUTH_SOURCE.replace("'1'", "'0'", 1)
    repo = _write_repo(tmp_path, source, "FROM scratch\n")
    findings = []

    check_app_auth(repo, findings)

    statuses = _statuses(findings)
    assert statuses["APP_AUTH_REQUIRED.default"] == FAIL
    assert statuses["APP_AUTH_REQUIRED.fail_closed"] == PASS
    assert statuses["APP_AUTH_REQUIRED.api_run_boundary"] == PASS


def test_auth_checker_accepts_fail_closed_contract(tmp_path):
    repo = _write_repo(tmp_path, AUTH_SOURCE, "FROM scratch\n")
    findings = []

    check_app_auth(repo, findings)

    assert all(finding.status != FAIL for finding in findings)
    assert _statuses(findings)["APP_AUTH_REQUIRED.default"] == PASS


def test_docker_checker_rejects_world_writable_root(tmp_path):
    dockerfile = """
FROM python:3.12
WORKDIR /code
COPY . /code
RUN mkdir -p /code/uploads && chmod -R 777 /code
CMD [\"python\", \"app.py\"]
"""
    repo = _write_repo(tmp_path, AUTH_SOURCE, dockerfile)
    findings = []

    check_docker_permissions(repo, findings)

    statuses = _statuses(findings)
    assert statuses["Docker.permissions.world_writable"] == FAIL
    assert statuses["Docker.permissions.non_root"] == FAIL
    assert statuses["Docker.permissions.copy_owner"] == FAIL


def test_docker_checker_accepts_non_root_and_scoped_permissions(tmp_path):
    dockerfile = """
FROM python:3.12
WORKDIR /code
RUN useradd --create-home --uid 1000 appuser \\
    && mkdir -p /code/uploads /tmp/tv-automation-uploads \\
    && chown -R appuser:appuser /code /tmp/tv-automation-uploads
COPY --chown=appuser:appuser . /code
USER appuser
CMD [\"python\", \"app.py\"]
"""
    repo = _write_repo(tmp_path, AUTH_SOURCE, dockerfile)
    findings = []

    check_docker_permissions(repo, findings)

    assert all(finding.status != FAIL for finding in findings)
    assert _statuses(findings)["Docker.permissions.world_writable"] == PASS
    assert _statuses(findings)["Docker.permissions.non_root"] == PASS
    assert _statuses(findings)["Docker.permissions.copy_owner"] == PASS
    assert _statuses(findings)["Docker.permissions.ownership"] == PASS


def test_security_gate_invokes_checker():
    workflow = Path('.github/workflows/security.yml').read_text(encoding='utf-8')
    assert 'python scripts/security_check.py' in workflow
    assert 'python test_security_check.py' in workflow
