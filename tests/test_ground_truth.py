"""Ground-truth tests: synthetic data generated in Python with KNOWN parameters.

Seeds are fixed, so the suite is deterministic. The engine must recover the
simulation parameters within tolerances that comfortably exceed sampling error.
"""
import random
import statistics as st

from helpers import close, engine

TOL = 6e-5


def test_independent_ttest_recovers_known_effect():
    rng = random.Random(2024)
    a = [rng.gauss(100, 15) for _ in range(250)]
    b = [rng.gauss(108, 15) for _ in range(250)]      # true delta = 8, true d = 0.533
    data = [{"y": v, "g": "A"} for v in a] + [{"y": v, "g": "B"} for v in b]
    res = engine({"analysis": "ttest", "variables": ["y", "g"],
                  "options": {"type": "independent", "welch": True, "alternative": "two.sided"},
                  "data": data})
    row = res["rows"][0]
    assert row["p_value"] == "< 0.001"
    assert row["interpretation"].startswith("Significant")
    assert abs(row["mean_diff"] - 8.0) < 2.0          # engine reports mean(B) - mean(A)
    assert -0.75 < row["effect_size"] < -0.30          # Cohen's d uses mean(A) - mean(B)
    assert 460 <= row["df"] <= 498


def test_paired_ttest_recovers_delta():
    rng = random.Random(99)
    pre = [rng.gauss(50, 10) for _ in range(120)]
    post = [p + 1.5 + rng.gauss(0, 2) for p in pre]   # true delta = +1.5
    data = [{"pre": p, "post": q} for p, q in zip(pre, post)]
    res = engine({"analysis": "ttest", "variables": ["pre", "post"],
                  "options": {"type": "paired", "alternative": "two.sided"}, "data": data})
    row = res["rows"][0]
    assert row["p_value"] == "< 0.001"
    assert abs(row["mean_diff"] - (-1.5)) < 0.4       # engine reports mean(pre) - mean(post)
    close(row["df"], 119.0, TOL)


def test_regression_recovers_coefficients():
    rng = random.Random(7)
    n = 300
    x1 = [rng.uniform(-5, 5) for _ in range(n)]
    x2 = [rng.uniform(-5, 5) for _ in range(n)]
    y = [2.0 + 3.0 * p - 1.5 * q + rng.gauss(0, 2) for p, q in zip(x1, x2)]
    data = [{"y": yy, "x1": xx1, "x2": xx2} for yy, xx1, xx2 in zip(y, x1, x2)]
    res = engine({"analysis": "regression", "variables": ["y", "x1", "x2"],
                  "options": {}, "data": data})
    assert res["f_p_value"] == "< 0.001"
    assert res["n"] == n
    coefs = {c["term"]: c for c in res["coefficients"]}
    assert abs(coefs["(Intercept)"]["estimate"] - 2.0) < 1.0
    assert abs(coefs["x1"]["estimate"] - 3.0) < 0.3   # true slope = 3
    assert abs(coefs["x2"]["estimate"] + 1.5) < 0.3   # true slope = -1.5
    b1, b2 = res["standardized"]["x1"], res["standardized"]["x2"]
    assert abs(b1 / b2 - (3.0 / -1.5)) < 0.5          # beta ratio tracks slope ratio
    assert abs(res["residual_se"] - 2.0) < 0.4        # true noise SD = 2


def test_nonnormality_is_flagged():
    rng = random.Random(11)
    x = [rng.expovariate(1.0) for _ in range(200)]    # right-skewed exponential
    data = [{"x": v} for v in x]
    res = engine({"analysis": "ttest", "variables": ["x"],
                  "options": {"type": "one-sample", "mu": 0, "alternative": "two.sided"}, "data": data})
    assert "violated" in res["notes"]
    assert res["rows"][0]["p_value"] == "< 0.001"


def test_descriptives_match_python_reference():
    """Independent cross-check: R's mean/sd/median vs Python's statistics module."""
    rng = random.Random(5)
    vals = [rng.gauss(7.5, 2.3) for _ in range(333)]
    data = [{"v": v} for v in vals]
    row = engine({"analysis": "descriptives", "variables": ["v"],
                  "options": {}, "data": data})["table"][0]
    assert row["n"] == len(vals)
    assert abs(row["mean"] - st.mean(vals)) < 5e-4
    assert abs(row["sd"] - st.stdev(vals)) < 5e-4
    assert abs(row["median"] - st.median(vals)) < 5e-4
