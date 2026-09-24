"""Contract tests: the JSON boundary between app.py and engine.R.

These pin the response schemas, p-value formatting, stdout purity, and
determinism. If they fail after refactoring, something about the app<->R
protocol changed and both sides need review.
"""
import json
import re

from helpers import engine, raw_engine

P_RE = re.compile(r"^(< 0\.001|\d\.\d{3})$")


def test_descriptives_schema(sample):
    cols, rows = sample
    res = engine({"analysis": "descriptives", "variables": ["score"], "options": {}, "data": rows})
    assert {"title", "table"} <= set(res)
    allowed = {"variable", "n", "missing", "mean", "sd", "median", "min", "max",
               "q1", "q3", "iqr", "skewness", "kurtosis", "se"}
    for row in res["table"]:
        assert {"variable", "n", "missing"} <= set(row)
        assert set(row) <= allowed
        assert isinstance(row["n"], int)


def test_ttest_schema(sample):
    cols, rows = sample
    res = engine({"analysis": "ttest", "variables": ["score", "group"],
                  "options": {"type": "independent", "welch": True, "alternative": "two.sided"},
                  "data": rows})
    assert {"title", "rows", "notes"} <= set(res)
    required = {"statistic", "df", "p_value", "mean_diff", "ci_lower", "ci_upper",
                "n", "effect_size", "interpretation"}
    assert set(res["rows"][0]) == required
    assert P_RE.match(res["rows"][0]["p_value"])


def test_regression_schema(sample):
    cols, rows = sample
    res = engine({"analysis": "regression", "variables": ["score", "age", "pre"],
                  "options": {}, "data": rows})
    top = {"title", "model", "n", "r_squared", "adj_r_squared", "f_statistic",
           "f_p_value", "residual_se", "coefficients", "standardized", "diagnostics"}
    assert top <= set(res)
    for c in res["coefficients"]:
        assert {"term", "estimate", "se", "t", "p_value", "ci_lower", "ci_upper"} == set(c)
        assert P_RE.match(c["p_value"])
    d = res["diagnostics"]
    assert {"normality_shapiro_p", "heteroscedasticity_breusch_pagan_p", "vif"} <= set(d)


def test_warnings_stay_on_stderr():
    """R warnings must never leak into the stdout JSON stream."""
    data = [{"y": v} for v in ["1", "2", "abc", "4"]]   # "abc" forces a coercion warning
    p = raw_engine(json.dumps({"analysis": "ttest", "variables": ["y"],
                               "options": {"type": "one-sample", "mu": 0, "alternative": "two.sided"},
                               "data": data}))
    assert p.returncode == 0
    resp = json.loads(p.stdout.strip().splitlines()[-1])
    assert resp.get("error") is None
    assert resp["rows"][0]["n"] == 3                    # "abc" became NA and was dropped
    assert "Warning" in (p.stderr or "")


def test_error_responses_have_only_error_key(sample):
    cols, rows = sample
    for payload in (
        {"analysis": "anova", "variables": ["score"], "options": {}, "data": rows},
        {"analysis": "ttest", "variables": ["score", "age"],
         "options": {"type": "independent", "welch": True, "alternative": "two.sided"}, "data": rows},
    ):
        res = engine(payload)
        assert set(res) == {"error"}


def test_determinism(sample):
    cols, rows = sample
    payload = {"analysis": "descriptives", "variables": ["score", "post"], "options": {}, "data": rows}
    assert engine(payload) == engine(payload)


def test_variable_order_is_respected(sample):
    cols, rows = sample
    r1 = engine({"analysis": "descriptives", "variables": ["post", "score"], "options": {}, "data": rows})
    r2 = engine({"analysis": "descriptives", "variables": ["score", "post"], "options": {}, "data": rows})
    assert [r["variable"] for r in r1["table"]] == ["post", "score"]
    by_name_1 = {r["variable"]: r for r in r1["table"]}
    by_name_2 = {r["variable"]: r for r in r2["table"]}
    assert by_name_1["score"] == by_name_2["score"]
