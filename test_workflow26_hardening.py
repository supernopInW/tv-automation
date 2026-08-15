import json
import sys
import types
from pathlib import Path

# app.py imports Google GenAI lazily for optional Excel classification. The
# hardening tests do not call Gemini, so provide an offline import stub.
sys.modules.setdefault("google", types.ModuleType("google"))
sys.modules.setdefault("google.genai", types.ModuleType("google.genai"))
sys.modules["google"].genai = sys.modules["google.genai"]

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


def test_run_rejects_missing_credentials_without_starting_browser():
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
        test_diagnostics_never_include_password,
        test_modal_dynamic_selects_are_reapplied_after_generic_events,
        test_modal_dates_are_set_after_generic_events_in_both_paths,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
