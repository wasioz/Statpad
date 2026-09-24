"""UI state-machine and workflow tests.

Real Tk windows are created but immediately withdrawn. All dialogs are
replaced with recorders via the `dialogs` fixture.
"""
import csv

import app

SAMPLE_COLS = ["group", "age", "pre", "post", "score"]


def _load_sample(a):
    a.load_sample()
    assert len(a.records) == 18 and a.columns == SAMPLE_COLS


def test_window_boots_with_defaults(tk_app):
    a = tk_app
    assert a.title() == app.APP_TITLE
    assert a.analysis_var.get() == "Descriptive statistics"
    assert a.lbl_data.cget("text") == "No data loaded"
    assert not a.tree["columns"]


def test_load_sample_populates_ui(tk_app):
    a = tk_app
    _load_sample(a)
    assert a.lbl_data.cget("text").startswith("sample_data.csv")
    assert list(a.varlist.get(0, "end")) == SAMPLE_COLS


def test_analysis_switch_updates_options_and_labels(tk_app):
    a = tk_app
    _load_sample(a)
    a.analysis_var.set("t-test"); a.on_analysis_change()
    assert "t-test" in a.varf.cget("text")
    a.analysis_var.set("Linear regression"); a.on_analysis_change()
    assert "Independent variables" in a.varf.cget("text")
    assert hasattr(a, "dv_var")
    a.analysis_var.set("Descriptive statistics"); a.on_analysis_change()
    assert "multi-select" in a.varf.cget("text")


def test_ttype_switching_preserves_selection(tk_app):
    """Regression test for the ttype_var reset bug class."""
    a = tk_app
    _load_sample(a)
    a.analysis_var.set("t-test"); a.on_analysis_change()
    a.ttype_var.set("Paired"); a.on_analysis_change()
    assert a.ttype_var.get() == "Paired"
    assert hasattr(a, "first_var") and hasattr(a, "second_var")
    a.ttype_var.set("One-sample"); a.on_analysis_change()
    assert a.ttype_var.get() == "One-sample"
    assert hasattr(a, "mu_var")
    a.ttype_var.set("Independent samples"); a.on_analysis_change()
    assert hasattr(a, "welch_var") and hasattr(a, "outcome_var")
    a.analysis_var.set("Descriptive statistics"); a.on_analysis_change()
    a.analysis_var.set("t-test"); a.on_analysis_change()
    assert a.ttype_var.get() == "Independent samples"   # last used type sticks


def test_collect_request_all_types(tk_app):
    a = tk_app
    _load_sample(a)
    a.analysis_var.set("t-test"); a.on_analysis_change()
    a.outcome_var.set("score"); a.group_var.set("group")
    assert a.collect_request() == {
        "analysis": "ttest", "variables": ["score", "group"],
        "options": {"type": "independent", "welch": True, "alternative": "two.sided"}}
    a.ttype_var.set("Paired"); a.on_analysis_change()
    a.first_var.set("post"); a.second_var.set("pre")
    assert a.collect_request()["variables"] == ["post", "pre"]
    a.ttype_var.set("One-sample"); a.on_analysis_change()
    a.varone_var.set("score"); a.mu_var.set("50")
    req = a.collect_request()
    assert req["variables"] == ["score"] and req["options"]["mu"] == 50.0
    a.analysis_var.set("Linear regression"); a.on_analysis_change()
    a.dv_var.set("score")
    a.varlist.selection_clear(0, "end")
    a.varlist.selection_set(1); a.varlist.selection_set(2)   # age, pre
    assert a.collect_request()["variables"] == ["score", "age", "pre"]


def test_validation_errors(tk_app, dialogs):
    a = tk_app
    _load_sample(a)
    a.analysis_var.set("Descriptive statistics"); a.on_analysis_change()
    try:
        a.collect_request()
        assert False, "expected ValueError with nothing selected"
    except ValueError:
        pass
    a.run_analysis()
    assert any(c[0] == "warn" for c in dialogs)
    a.analysis_var.set("Linear regression"); a.on_analysis_change()
    a.dv_var.set("")
    a.varlist.selection_set(1)
    try:
        a.collect_request(); assert False, "expected ValueError for missing DV"
    except ValueError:
        pass
    a.dv_var.set("score")
    a.varlist.selection_clear(0, "end"); a.varlist.selection_set(4)
    try:
        a.collect_request(); assert False, "expected ValueError when DV is also an IV"
    except ValueError:
        pass


def test_descriptives_flow_and_ragged_headers(tk_app):
    a = tk_app
    _load_sample(a)
    a.varlist.selection_clear(0, "end")
    a.varlist.selection_set(0); a.varlist.selection_set(4)   # group, score
    a.run_analysis()
    headers = list(a.tree["columns"])
    assert headers[:3] == ["variable", "n", "missing"] and "mean" in headers
    rows = a.tree.get_children()
    assert len(rows) == 2
    i = headers.index("mean")
    vals_group = a.tree.item(rows[0])["values"]              # group row: no numeric stats
    cell = vals_group[i] if i < len(vals_group) else ""
    assert cell in ("", None)
    vals_score = a.tree.item(rows[1])["values"]
    assert abs(float(vals_score[i]) - 58.6111) < 1e-3


def test_ttest_flows_in_one_session(tk_app):
    a = tk_app
    _load_sample(a)
    a.analysis_var.set("t-test"); a.on_analysis_change()
    a.outcome_var.set("score"); a.group_var.set("group")
    a.run_analysis()
    vals = a.tree.item(a.tree.get_children()[0])["values"]
    assert abs(float(vals[0]) + 7.4517) < 1e-3
    assert vals[2] == "< 0.001"
    notes = a.txt_notes.get("1.0", "end")
    assert "Welch" in notes and "Levene" in notes
    a.ttype_var.set("Paired"); a.on_analysis_change()
    a.first_var.set("post"); a.second_var.set("pre")
    a.run_analysis()
    vals = a.tree.item(a.tree.get_children()[0])["values"]
    assert abs(float(vals[0]) - 5.9579) < 1e-3


def test_regression_flow_adds_std_beta(tk_app):
    a = tk_app
    _load_sample(a)
    a.analysis_var.set("Linear regression"); a.on_analysis_change()
    a.dv_var.set("score")
    a.varlist.selection_set(1); a.varlist.selection_set(2)   # age, pre
    a.run_analysis()
    headers = list(a.tree["columns"])
    assert "std_beta" in headers
    assert len(a.tree.get_children()) == 3
    vals = a.tree.item(a.tree.get_children()[0])["values"]
    assert vals[0] == "(Intercept)"
    notes = a.txt_notes.get("1.0", "end")
    assert "Model:" in notes and "R2" in notes and "VIF" in notes


def test_export_writes_displayed_table(tk_app, monkeypatch, tmp_path):
    a = tk_app
    _load_sample(a)
    a.varlist.selection_set(0, "end")
    a.run_analysis()
    out = tmp_path / "results.csv"
    monkeypatch.setattr(app.filedialog, "asksaveasfilename", lambda **k: str(out))
    a.export_results()
    with open(out, newline="", encoding="utf-8") as f:
        table = list(csv.reader(f))
    headers = list(a.tree["columns"])
    assert table[0] == headers
    assert len(table) - 1 == len(a.tree.get_children())
    i_mean = headers.index("mean")
    assert table[1][i_mean] == ""        # group row has empty numeric cells in CSV
    assert table[5][i_mean] != ""


def test_load_missing_file_shows_error(tk_app, dialogs):
    a = tk_app
    _load_sample(a)
    before = a.records
    a.load_path("Z:/definitely/not/here.csv")
    assert any(c[0] == "error" for c in dialogs)
    assert a.records == before           # previous data stays loaded


def test_run_without_data_warns(tk_app, dialogs):
    a = tk_app
    a.run_analysis()
    assert any(c[0] == "warn" for c in dialogs)


