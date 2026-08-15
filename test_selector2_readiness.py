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

    def wait_for_function(self, script, timeout=None):
        self.calls.append((script, timeout))


def test_wait_for_portal_ready_uses_populated_options():
    page = FakePage()
    app._wait_for_portal_ready(page, "offline-test")
    assert len(page.calls) == 1
    script, timeout = page.calls[0]
    assert "#PL_YAER" in script
    assert "#PL_MOUNT" in script
    assert "#PL_TAMBONN" in script
    assert "options.length > 1" in script
    assert timeout == app.PLAYWRIGHT_NAVIGATION_TIMEOUT_MS


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
        test_wait_for_portal_ready_uses_populated_options,
        test_source_does_not_wait_for_hidden_select_visibility,
        test_cleanup_is_not_after_context_teardown,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
