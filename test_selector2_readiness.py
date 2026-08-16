import os
from pathlib import Path

# Offline tests intentionally use in-memory limiter storage.
os.environ['APP_ENV'] = 'test'
os.environ['RATELIMIT_STORAGE_URI'] = 'memory://'
os.environ['APP_SESSION_SECRET'] = 'test-only-session-secret'

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
    """The session worker must close its persistent context inside sync_playwright."""
    source = Path("app.py").read_text(encoding="utf-8")
    worker_start = source.index("def _worker(self):")
    worker_end = source.index("_tv_session = TvBrowserSession", worker_start)
    worker_source = source[worker_start:worker_end]
    # launch and close both happen inside the `with sync_playwright()` block,
    # so no Playwright call can outlive its event loop.
    launch_pos = worker_source.index("launch_persistent_context")
    close_pos = worker_source.index("context.close()")
    with_pos = worker_source.index("with sync_playwright() as p:")
    assert with_pos < launch_pos < close_pos
    assert "browser.close()" not in worker_source


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
