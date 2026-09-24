"""Golden-value tests (linear regression): engine output pinned to results
verified directly in R 4.5.2 on the built-in mtcars dataset."""
from helpers import close, engine, load

TOL = 6e-5


def _mtcars_regress(variables):
    cols, rows = load("mtcars.csv")
    return engine({"analysis": "regression", "variables": variables, "options": {}, "data": rows})


def test_mtcars_regression_two_predictors():
    res = _mtcars_regress(["mpg", "wt", "hp"])
    assert res["title"] == "Linear Regression"
    assert res["model"] == "mpg ~ wt + hp"
    assert res["n"] == 32
    close(res["r_squared"], 0.826785, TOL)
    close(res["adj_r_squared"], 0.814840, TOL)
    close(res["f_statistic"], 69.211213, TOL)
    assert res["f_p_value"] == "< 0.001"
    close(res["residual_se"], 2.593412, TOL)

    coefs = {c["term"]: c for c in res["coefficients"]}
    assert set(coefs) == {"(Intercept)", "wt", "hp"}
    ic, wc, hc = coefs["(Intercept)"], coefs["wt"], coefs["hp"]
    close(ic["estimate"], 37.227270, TOL); close(ic["se"], 1.598788, TOL)
    close(ic["t"], 23.284689, TOL); assert ic["p_value"] == "< 0.001"
    close(ic["ci_lower"], 33.957382, TOL); close(ic["ci_upper"], 40.497158, TOL)
    close(wc["estimate"], -3.877831, TOL); close(wc["se"], 0.632733, TOL)
    close(wc["t"], -6.128695, TOL); assert wc["p_value"] == "< 0.001"
    close(wc["ci_lower"], -5.171916, TOL); close(wc["ci_upper"], -2.583745, TOL)
    close(hc["estimate"], -0.031773, TOL); close(hc["se"], 0.009030, TOL)
    close(hc["t"], -3.518712, TOL); assert hc["p_value"] == "0.001"
    close(hc["ci_lower"], -0.050241, TOL); close(hc["ci_upper"], -0.013305, TOL)

    std = res["standardized"]
    close(std["wt"], -0.629555, TOL); close(std["hp"], -0.361451, TOL)

    d = res["diagnostics"]
    assert d["normality_shapiro_p"] == "0.034"
    assert d["heteroscedasticity_breusch_pagan_p"] == "0.644"
    close(d["vif"]["wt"], 1.766625, 5.1e-4)           # engine rounds VIF to 3 dp
    close(d["vif"]["hp"], 1.766625, 5.1e-4)


def test_mtcars_regression_single_predictor():
    res = _mtcars_regress(["mpg", "wt"])
    close(res["r_squared"], 0.752833, TOL)
    coefs = {c["term"]: c for c in res["coefficients"]}
    close(coefs["(Intercept)"]["estimate"], 37.285126, TOL)
    close(coefs["wt"]["estimate"], -5.344472, TOL)
