from pathlib import Path
import sys
import types

# app.py imports Google GenAI, but this test exercises only Playwright helpers.
sys.modules.setdefault("google", types.ModuleType("google"))
sys.modules.setdefault("google.genai", types.ModuleType("google.genai"))
sys.modules["google"].genai = sys.modules["google.genai"]

import app


class FakePage:
    def __init__(self):
        self.calls = []

    def wait_for_function(self, script, *args, **kwargs):
        self.calls.append((script, args, kwargs))


def test_wait_for_portal_ready_accepts_initial_month_placeholder():
    page = FakePage()
    app._wait_for_portal_ready(page, "offline-test")
    assert len(page.calls) == 1
    script, args, kwargs = page.calls[0]
    assert "#PL_YAER" in script
    assert "#PL_MOUNT" in script
    assert "#PL_TAMBONN" in script
    assert "'#PL_MOUNT': 1" in script
    assert "options.length >= minimum" in script
    assert kwargs["timeout"] == app.PLAYWRIGHT_NAVIGATION_TIMEOUT_MS


def test_wait_for_select_options_waits_for_dynamic_month():
    page = FakePage()
    app._wait_for_select_options(page, "select#PL_MOUNT", 2, "after-year")
    assert len(page.calls) == 1
    script, args, kwargs = page.calls[0]
    assert "options.length >= 2" in script
    assert 'querySelector("select#PL_MOUNT")' in script
    assert args == ()
    assert kwargs["timeout"] == app.PLAYWRIGHT_ACTION_TIMEOUT_MS


def test_source_does_not_wait_for_hidden_select_visibility():
    source = Path("app.py").read_text(encoding="utf-8")
    readiness = source[source.index("def _wait_for_portal_ready"):source.index("def _assert_authenticated")]
    assert "wait_for_function" in readiness
    assert "state='visible'" not in readiness


def test_cleanup_is_not_after_context_teardown():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "if browser.is_connected():" in source
    assert "browser = None" in source
    assert "Do not call browser.close() after its event loop is stopped." in source


if __name__ == "__main__":
    tests = [
        test_wait_for_portal_ready_accepts_initial_month_placeholder,
        test_wait_for_select_options_waits_for_dynamic_month,
        test_source_does_not_wait_for_hidden_select_visibility,
        test_cleanup_is_not_after_context_teardown,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
