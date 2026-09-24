"""Shared helpers for the test suite."""
import os
import subprocess

import app

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# The engine rounds outputs to 4 decimals; allow slack around unrounded truth.
TOL = 6e-5


def engine(payload):
    """Run an analysis through the app's normal run_r path."""
    return app.run_r(payload)


def raw_engine(raw_text):
    """Send raw text to engine.R via stdin (for malformed-JSON tests)."""
    return subprocess.run(
        [app.RSCRIPT, app.ENGINE_PATH],
        input=raw_text,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def load(name):
    """Load a fixture CSV through the app's normal loader path."""
    return app.load_table_r(os.path.join(FIXTURES, name))


def close(actual, expected, tol=TOL, msg=""):
    assert abs(float(actual) - float(expected)) <= tol, (
        f"{msg} expected ~{expected}, got {actual} (tol {tol})")
