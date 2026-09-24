"""Edge cases and error paths for the R engine: hostile-but-legal input
must degrade gracefully (an {"error": ...} response), never hang,
traceback, or produce invalid JSON."""
import json

from helpers import engine, load, raw_engine


def test_bad_json_is_reported_not_crash():
    p = raw_engine("{not json")
    assert p.returncode == 1
    resp = json.loads(p.stdout.strip())
    assert "Bad input JSON" in resp["error"]


def test_unknown_analysis_type(sample):
    cols, rows = sample
    res = engine({"analysis": "anova", "variables": ["score"], "options": {}, "data": rows})
    assert "Unknown analysis type" in res["error"]


def test_empty_data():
    res = engine({"analysis": "descriptives", "variables": ["x"], "options": {}, "data": []})
    assert res["error"] == "No data received."


def test_no_variables_selected(sample):
    cols, rows = sample
    res = engine({"analysis": "descriptives", "variables": [], "options": {}, "data": rows})
    assert res["title"] == "Descriptive Statistics"
    assert res["table"] == []


def test_all_missing_column():
    data = [{"x": None, "y": 1.0}, {"x": None, "y": 2.0}, {"x": None, "y": 3.0}]
    res = engine({"analysis": "descriptives", "variables": ["x", "y"], "options": {}, "data": data})
    table = {r["variable"]: r for r in res["table"]}
    assert table["x"]["n"] == 0 and table["x"]["missing"] == 3
    assert table["y"]["n"] == 3


def test_constant_variable():
    data = [{"y": 5.0} for _ in range(5)]
    row = engine({"analysis": "descriptives", "variables": ["y"],
                  "options": {}, "data": data})["table"][0]
    assert row["n"] == 5
    assert row["sd"] == 0 and row["se"] == 0 and row["iqr"] == 0
    assert row["mean"] == 5 and row["min"] == 5 and row["max"] == 5
    assert row["skewness"] is None and row["kurtosis"] is None


def test_single_row():
    data = [{"y": 3.5}]
    row = engine({"analysis": "descriptives", "variables": ["y"],
                  "options": {}, "data": data})["table"][0]
    assert row["n"] == 1
    assert row["sd"] is None and row["se"] is None and row["skewness"] is None


def test_extreme_values_do_not_crash():
    data = [{"y": v} for v in (1e300, -1e300, 5.0, -5.0)]
    res = engine({"analysis": "descriptives", "variables": ["y"], "options": {}, "data": data})
    assert res.get("error") is None
    assert res["table"][0]["sd"] == "Inf"   # variance overflows; jsonlite string, still valid JSON


def test_three_level_group_rejected():
    cols, rows = load("plant.csv")
    res = engine({"analysis": "ttest", "variables": ["weight", "group"],
                  "options": {"type": "independent", "welch": True, "alternative": "two.sided"},
                  "data": rows})
    assert "exactly 2 levels" in res["error"] and "3" in res["error"]


def test_continuous_group_rejected(sample):
    cols, rows = sample
    res = engine({"analysis": "ttest", "variables": ["score", "age"],
                  "options": {"type": "independent", "welch": True, "alternative": "two.sided"},
                  "data": rows})
    assert "exactly 2 levels" in res["error"]


def test_single_level_group_rejected():
    data = [{"y": 1.0, "g": "A"}, {"y": 2.0, "g": "A"}]
    res = engine({"analysis": "ttest", "variables": ["y", "g"],
                  "options": {"type": "independent", "welch": True, "alternative": "two.sided"},
                  "data": data})
    assert "exactly 2 levels" in res["error"]


def test_paired_no_overlap_is_graceful():
    data = [{"v1": 1.0, "v2": None}, {"v1": 2.0, "v2": None}, {"v1": None, "v2": 4.0}]
    res = engine({"analysis": "ttest", "variables": ["v1", "v2"],
                  "options": {"type": "paired", "alternative": "two.sided"}, "data": data})
    assert "error" in res


def test_one_sample_all_missing_is_graceful():
    data = [{"x": None}, {"x": None}]
    res = engine({"analysis": "ttest", "variables": ["x"],
                  "options": {"type": "one-sample", "mu": 0, "alternative": "two.sided"}, "data": data})
    assert "error" in res


def test_regression_with_text_predictor():
    data = [{"y": x + (2.0 if g == "B" else 0.0), "x": x, "grp": g}
            for x, g in zip([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], ["A", "B", "A", "B", "A", "B"])]
    res = engine({"analysis": "regression", "variables": ["y", "x", "grp"], "options": {}, "data": data})
    assert res.get("error") is None
    terms = [c["term"] for c in res["coefficients"]]
    assert "(Intercept)" in terms and any(t.startswith("grp") for t in terms)
    assert res["n"] == 6


def test_regression_insufficient_cases():
    data = [{"y": 1.0, "x1": 1.0, "x2": 2.0}, {"y": 2.0, "x1": 2.0, "x2": 1.0}]
    res = engine({"analysis": "regression", "variables": ["y", "x1", "x2"], "options": {}, "data": data})
    assert "Not enough complete cases" in res["error"]


def test_regression_skips_incomplete_rows():
    data = [{"y": float(i), "x": float(i) * 2} for i in range(1, 11)]
    data[3]["y"] = None
    data[7]["x"] = None
    res = engine({"analysis": "regression", "variables": ["y", "x"], "options": {}, "data": data})
    assert res["n"] == 8
    est = {c["term"]: c for c in res["coefficients"]}["x"]["estimate"]
    assert abs(est - 0.5) < 1e-6     # perfect line y = x/2 survives row removal


def test_column_names_with_spaces_and_backticks():
    data = [{"my var": float(i), "wei`rd": w, "out come": float(i) + 1.0}
            for i, w in zip(range(1, 11), [-1, 2, -3, 4, -5, 6, -7, 8, -9, 10])]
    res = engine({"analysis": "descriptives", "variables": ["my var", "wei`rd", "out come"],
                  "options": {}, "data": data})
    assert res.get("error") is None and len(res["table"]) == 3
    res = engine({"analysis": "regression", "variables": ["out come", "my var", "wei`rd"],
                  "options": {}, "data": data})
    assert res.get("error") is None
    assert res["model"] == "out come ~ my var + wei`rd"
    # R keeps backticks around non-syntactic names in coefficient terms; strip them
    terms = [c["term"].strip("`") for c in res["coefficients"]]
    assert "my var" in terms and "wei`rd" in terms


def test_unicode_column_name():
    data = [{"précis ✓": float(i), "y": float(i) * 2} for i in range(1, 9)]
    res = engine({"analysis": "regression", "variables": ["y", "précis ✓"], "options": {}, "data": data})
    assert res.get("error") is None
    # R wraps non-syntactic names in backticks in coefficient terms
    assert "précis ✓" in [c["term"].strip("`") for c in res["coefficients"]]


def test_one_sided_alternatives():
    data = [{"x": float(v)} for v in range(1, 11)]
    greater = engine({"analysis": "ttest", "variables": ["x"],
                      "options": {"type": "one-sample", "mu": 0, "alternative": "greater"}, "data": data})
    less = engine({"analysis": "ttest", "variables": ["x"],
                   "options": {"type": "one-sample", "mu": 0, "alternative": "less"}, "data": data})
    assert greater["rows"][0]["ci_upper"] == "Inf"   # documented jsonlite encoding
    assert less["rows"][0]["ci_lower"] == "-Inf"
    assert greater["rows"][0]["p_value"] == "< 0.001"
    assert less["rows"][0]["p_value"] == "1.000"

