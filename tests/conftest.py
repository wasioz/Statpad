"""Pytest fixtures shared across the test suite."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (ROOT, TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app  # noqa: E402


@pytest.fixture(scope="session")
def sample():
    """The app's demo dataset as (columns, records)."""
    cols, rows = app.load_table_r(os.path.join(ROOT, "sample_data.csv"))
    return cols, rows


@pytest.fixture
def tk_app():
    """A real App instance, window hidden, destroyed on teardown.

    Windows Store Python occasionally fails to locate tk.tcl inside the
    ACL-restricted WindowsApps folder; retry a few times before giving up.
    """
    import time
    last_err = None
    a = None
    for _ in range(5):
        try:
            a = app.App()
            break
        except app.tk.TclError as e:
            last_err = e
            time.sleep(0.3)
    if a is None:
        pytest.fail(f"Tk failed to initialize after retries: {last_err}")
    a.withdraw()
    yield a
    a.destroy()


@pytest.fixture
def dialogs(monkeypatch):
    """Replace message boxes with recorders; returns the list of calls."""
    calls = []

    def _rec(kind):
        def fn(*args, **kwargs):
            calls.append((kind,) + args)
        return fn

    monkeypatch.setattr(app.messagebox, "showerror", _rec("error"))
    monkeypatch.setattr(app.messagebox, "showwarning", _rec("warn"))
    monkeypatch.setattr(app.messagebox, "showinfo", _rec("info"))
    return calls
