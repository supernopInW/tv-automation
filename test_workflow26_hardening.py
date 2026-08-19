import json
import os
from pathlib import Path

# Offline tests intentionally use in-memory limiter storage.
os.environ['APP_ENV'] = 'test'
os.environ['RATELIMIT_STORAGE_URI'] = 'memory://'
os.environ['APP_SESSION_SECRET'] = 'test-only-session-secret'

# The application uses the deterministic local rules-based parser; no external
# AI SDK stub is needed for these offline hardening tests.

import app


class FakePage:
    def __init__(self, diagnostics):
        self.url = diagnostics.get("url", "https://tandv.doae.go.th/workflow/workflow_start.php?W=26")
        self.diagnostics = diagnostics

    def wait_for_load_state(self, *args, **kwargs):
        return None

    def wait_for_timeout(self, *args, **kwargs):
        return None

    def evaluate(self, script, *args):
        return self.diagnostics


def test_finalize_unknown_without_success_marker():
    page = FakePage({
        "url": "https://tandv.doae.go.th/workflow/workflow_start.php?W=26",
        "bodyText": "กำลังประมวลผล",
        "loginVisible": False,
    })
    result = app._verify_finalize_result(page, "submit", page.url)
    assert result["confirmed"] is False


def test_finalize_confirmed_by_portal_marker():
    page = FakePage({
        "url": "https://tandv.doae.go.th/workflow/complete.php",
        "bodyText": "บันทึกข้อมูลเรียบร้อยแล้ว",
        "loginVisible": False,
    })
    result = app._verify_finalize_result(page, "draft", "https://tandv.doae.go.th/workflow/workflow_start.php?W=26")
    assert result["confirmed"] is True


class _run_route_test_env:
    """Disable app auth and the shared rate limiter for one offline test.

    The /api/run limit (2 per 10 minutes) would otherwise reject the third
    request in this suite before the code under test is reached.
    """

    def __enter__(self):
        self._old_required = app.APP_AUTH_REQUIRED
        self._old_limiter_enabled = app.limiter.enabled
        app.APP_AUTH_REQUIRED = False
        app.limiter.enabled = False
        return self

    def __exit__(self, exc_type, exc, tb):
        app.APP_AUTH_REQUIRED = self._old_required
        app.limiter.enabled = self._old_limiter_enabled
        return False


class FakeTvSession:
    def __init__(self, running, logged_in):
        self._running = running
        self._logged_in = logged_in

    def status(self):
        return {"running": self._running, "logged_in": self._logged_in, "message": ""}

    def last_status(self):
        return self.status()

    def is_running(self):
        return self._running

    def submit_run(self, job, on_abort):
        return False


def test_run_rejects_missing_credentials_without_starting_browser():
    """/api/run must require T&V credentials from the user's session payload."""
    with _run_route_test_env():
        client = app.app.test_client()
        csrf = client.get("/api/access/status").get_json()["csrf_token"]
        response = client.post(
            "/api/run",
            json={"records": [], "mode": "dry_run"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 400
        payload = response.get_json()
        assert payload["success"] is False
        assert "รหัสผ่าน" in payload["error"]


def test_run_does_not_require_local_headed_when_credentials_present():
    """Headless/Render may run once the officer supplied T&V credentials."""
    old_available = app._local_headed_available
    app._local_headed_available = lambda: False
    try:
        with _run_route_test_env():
            client = app.app.test_client()
            csrf = client.get("/api/access/status").get_json()["csrf_token"]
            response = client.post(
                "/api/run",
                json={"records": [], "mode": "dry_run"},
                headers={"X-CSRF-Token": csrf},
            )
            # Missing credentials still 400 — not a local-only 503.
            assert response.status_code == 400
            assert response.get_json()["error"] != app.TV_BROWSER_LOCAL_ONLY_ERROR
    finally:
        app._local_headed_available = old_available


def test_is_tv_logged_in_heuristics():
    login_form_page = FakePage({
        "urlPath": "/index/login_tv_system.php",
        "loginVisible": True,
        "authMarkers": False,
    })
    assert app.is_tv_logged_in(login_form_page) is False

    login_url_page = FakePage({
        "urlPath": "/index/login_tv_system.php",
        "loginVisible": False,
        "authMarkers": True,
    })
    assert app.is_tv_logged_in(login_url_page) is False

    no_marker_page = FakePage({
        "urlPath": "/index/main_tv_system.php",
        "loginVisible": False,
        "authMarkers": False,
    })
    assert app.is_tv_logged_in(no_marker_page) is False

    authenticated_page = FakePage({
        "urlPath": "/workflow/workflow_start.php",
        "loginVisible": False,
        "authMarkers": True,
    })
    assert app.is_tv_logged_in(authenticated_page) is True

    class BrokenPage:
        def evaluate(self, script, *args):
            raise RuntimeError("page closed")

    assert app.is_tv_logged_in(BrokenPage()) is False


def test_diagnostics_never_include_password():
    page = FakePage({"url": "https://tandv.doae.go.th/index/login_tv_system.php", "bodyText": "login"})
    result = app._page_diagnostics(page)
    assert "password" not in json.dumps(result, ensure_ascii=False).lower()


def test_modal_dynamic_selects_are_reapplied_after_generic_events():
    app_source = Path("app.py").read_text(encoding="utf-8")
    cli_source = Path("automate_submission.py").read_text(encoding="utf-8")
    for source, generic_marker, date_marker in (
        (app_source, "# Trigger events on all inputs", "_set_modal_dates(page, be_date)"),
        (cli_source, "# Trigger input events", "_set_modal_dates(page, rec['date'])"),
    ):
        generic_pos = source.index(generic_marker)
        final_select_pos = source.index("_set_modal_select_value", generic_pos)
        date_pos = source.index(date_marker)
        assert generic_pos < final_select_pos < date_pos
        helper_start = source.index("def _set_modal_select_value")
        helper_end = source.index("def _set_modal_dates", helper_start)
        helper_source = source[helper_start:helper_end]
        assert "new Event('input'" in helper_source
        assert "new Event('change'" not in helper_source


def test_modal_dates_are_set_after_generic_events_in_both_paths():
    app_source = Path("app.py").read_text(encoding="utf-8")
    cli_source = Path("automate_submission.py").read_text(encoding="utf-8")
    assert app_source.index("# Trigger events on all inputs") < app_source.index("_set_modal_dates(page, be_date)")
    assert cli_source.index("# Trigger input events") < cli_source.index("_set_modal_dates(page, rec['date'])")


if __name__ == "__main__":
    tests = [
        test_finalize_unknown_without_success_marker,
        test_finalize_confirmed_by_portal_marker,
        test_run_rejects_missing_credentials_without_starting_browser,
        test_run_does_not_require_local_headed_when_credentials_present,
        test_is_tv_logged_in_heuristics,
        test_diagnostics_never_include_password,
        test_modal_dynamic_selects_are_reapplied_after_generic_events,
        test_modal_dates_are_set_after_generic_events_in_both_paths,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
