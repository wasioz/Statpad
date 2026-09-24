"""Golden-value tests (descriptives + t-tests): engine output pinned to
verified R results.

Every expected value below was computed directly in R 4.5.2 against the
built-in datasets sleep and PlantGrowth (e.g. t.test(a, b) on sleep
groups). The engine rounds to 4 decimals, so close() allows 6e-5 slack
around the unrounded truth. If one of these tests fails after an engine
change, a statistic really changed.
"""
from helpers import close, engine, load

TOL = 6e-5


# ---------------- descriptive statistics ----------------

def test_sleep_descriptives():
    cols, rows = load("sleep.csv")
    res = engine({"analysis": "descriptives", "variables": ["extra"], "options": {}, "data": rows})
    assert res["title"] == "Descriptive Statistics"
    row = res["table"][0]
    assert row["n"] == 20 and row["missing"] == 0
    close(row["mean"], 1.540000, TOL)
    close(row["sd"], 2.017920, TOL)
    close(row["median"], 0.950000, TOL)
    close(row["min"], -1.600000, TOL)
    close(row["max"], 5.500000, TOL)
    close(row["q1"], -0.025000, TOL)
    close(row["q3"], 3.400000, TOL)
    close(row["iqr"], 3.425000, TOL)
    close(row["skewness"], 0.451857, TOL)
    close(row["kurtosis"], -1.086590, TOL)
    close(row["se"], 0.451221, TOL)


def test_plant_descriptives():
    cols, rows = load("plant.csv")
    res = engine({"analysis": "descriptives", "variables": ["weight"], "options": {}, "data": rows})
    row = res["table"][0]
    assert row["n"] == 30 and row["missing"] == 0
    close(row["mean"], 5.073000, TOL)
    close(row["sd"], 0.701192, TOL)
    close(row["median"], 5.155000, TOL)
    close(row["q1"], 4.550000, TOL)
    close(row["q3"], 5.530000, TOL)
    close(row["iqr"], 0.980000, TOL)
    close(row["skewness"], -0.161600, TOL)
    close(row["kurtosis"], -0.812409, TOL)
    close(row["se"], 0.128020, TOL)


# ---------------- t-tests: sleep ----------------

def _sleep_independent(welch):
    cols, rows = load("sleep.csv")
    return engine({"analysis": "ttest", "variables": ["extra", "group"],
                   "options": {"type": "independent", "welch": welch,
                               "alternative": "two.sided"}, "data": rows})


def test_sleep_independent_welch():
    res = _sleep_independent(True)
    assert res["title"] == "Independent-Samples t-test: extra by group"
    row = res["rows"][0]
    close(row["statistic"], -1.860813, TOL)
    close(row["df"], 17.776474, 5.1e-4)   # engine rounds df to 3 decimals
    assert row["p_value"] == "0.079"
    close(row["mean_diff"], 1.580000, TOL)            # mean(group 2) - mean(group 1)
    close(row["ci_lower"], -3.365483, TOL)
    close(row["ci_upper"], 0.205483, TOL)
    close(row["effect_size"], -0.832181, TOL)         # Cohen's d, group 1 - group 2
    assert row["n"] == "1=10; 2=10"
    assert "Welch" in res["notes"] and "Levene" in res["notes"]


def test_sleep_independent_student():
    res = _sleep_independent(False)
    row = res["rows"][0]
    close(row["statistic"], -1.860813, TOL)
    close(row["df"], 18.000000, TOL)
    assert row["p_value"] == "0.079"
    assert "Student" in res["notes"]


def test_sleep_paired():
    cols, rows = load("sleep_wide.csv")
    res = engine({"analysis": "ttest", "variables": ["extra1", "extra2"],
                  "options": {"type": "paired", "alternative": "two.sided"}, "data": rows})
    row = res["rows"][0]
    close(row["statistic"], -4.062128, TOL)
    close(row["df"], 9.000000, TOL)
    assert row["p_value"] == "0.003"
    close(row["mean_diff"], -1.580000, TOL)
    close(row["ci_lower"], -2.459886, TOL)
    close(row["ci_upper"], -0.700114, TOL)
    close(row["effect_size"], -1.284558, TOL)         # d_z = t / sqrt(n)
    assert row["n"] == 10


def test_sleep_one_sample():
    cols, rows = load("sleep.csv")
    res = engine({"analysis": "ttest", "variables": ["extra"],
                  "options": {"type": "one-sample", "mu": 0, "alternative": "two.sided"}, "data": rows})
    row = res["rows"][0]
    close(row["statistic"], 3.412965, TOL)
    close(row["df"], 19.000000, TOL)
    assert row["p_value"] == "0.003"
    close(row["mean_diff"], 1.540000, TOL)
    close(row["ci_lower"], 0.595584, TOL)
    close(row["ci_upper"], 2.484416, TOL)
    assert row["effect_size"] is None                 # not defined for one-sample


def test_plant_independent_ctrl_vs_trt1():
    cols, rows = load("plant2.csv")
    res = engine({"analysis": "ttest", "variables": ["weight", "group"],
                  "options": {"type": "independent", "welch": True, "alternative": "two.sided"}, "data": rows})
    row = res["rows"][0]
    close(row["statistic"], 1.191260, TOL)
    close(row["df"], 16.523585, 5.1e-4)   # engine rounds df to 3 decimals
    assert row["p_value"] == "0.250"
    close(row["mean_diff"], -0.371000, TOL)           # mean(trt1) - mean(ctrl)
