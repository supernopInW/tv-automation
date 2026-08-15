import json
import sys
import types

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
    response = client.post("/api/run", json={"records": [], "mode": "dry_run"})
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "รหัสผ่าน" in payload["error"]


def test_diagnostics_never_include_password():
    page = FakePage({"url": "https://tandv.doae.go.th/index/login_tv_system.php", "bodyText": "login"})
    result = app._page_diagnostics(page)
    assert "password" not in json.dumps(result, ensure_ascii=False).lower()


if __name__ == "__main__":
    tests = [
        test_finalize_unknown_without_success_marker,
        test_finalize_confirmed_by_portal_marker,
        test_run_rejects_missing_credentials_without_starting_browser,
        test_diagnostics_never_include_password,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
