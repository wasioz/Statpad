"""Dataset profile tests: per-column examination, warnings, and the Data tab."""
import os

import app

PROFILE_DATA = [
    {"id": "R1", "grp": "A", "x": 1.0, "x2": 2.0, "const": 5.0, "messy": "1", "bigmiss": 1.0},
    {"id": "R2", "grp": "a ", "x": 2.0, "x2": 4.0, "const": 5.0, "messy": "2", "bigmiss": None},
    {"id": "R3", "grp": "B", "x": 3.0, "x2": 6.0, "const": 5.0, "messy": "3", "bigmiss": None},
    {"id": "R4", "grp": "B", "x": 4.0, "x2": 8.0, "const": 5.0, "messy": "oops", "bigmiss": None},
    {"id": "R5", "grp": "B", "x": 5.0, "x2": 10.0, "const": 5.0, "messy": "5", "bigmiss": None},
    {"id": "R6", "grp": "A", "x": 6.0, "x2": 12.0, "const": 5.0, "messy": "6", "bigmiss": None},
    {"id": "R7", "grp": "A", "x": 7.0, "x2": 14.0, "const": 5.0, "messy": "7", "bigmiss": None},
    {"id": "R8", "grp": "B", "x": 8.0, "x2": 16.0, "const": 5.0, "messy": "8", "bigmiss": None},
    {"id": "R9", "grp": "A", "x": 9.0, "x2": 18.0, "const": 5.0, "messy": "9", "bigmiss": None},
    {"id": "R10", "grp": "B", "x": 100.0, "x2": 200.0, "const": 5.0, "messy": "10", "bigmiss": None},
    {"id": "D1", "grp": "A", "x": 1.0, "x2": 2.0, "const": 5.0, "messy": "1", "bigmiss": 1.0},
    {"id": "D2", "grp": "a ", "x": 2.0, "x2": 4.0, "const": 5.0, "messy": "2", "bigmiss": None},
    {"id": "D3", "grp": "B", "x": 3.0, "x2": 6.0, "const": 5.0, "messy": "3", "bigmiss": None},
    {"id": "D3", "grp": "B", "x": 3.0, "x2": 6.0, "const": 5.0, "messy": "3", "bigmiss": None},
]

def get_profile(data, **opts):
    return app.run_r({"analysis": "profile", "variables": [], "options": opts, "data": data})


def by_column(res, name):
    return {r["column"]: r for r in res["table"]}[name]


def notes_text(res):
    n = res.get("notes") or []
    if isinstance(n, str):
        return n
    return "\n".join(str(x) for x in n)


def test_dims_and_duplicates():
    res = get_profile(PROFILE_DATA)
    assert res["title"].startswith("Dataset Profile - 14 rows x 7 columns")
    assert res["dims"]["rows"] == 14 and res["dims"]["cols"] == 7
    assert res["dims"]["duplicates"] == 1
    assert "1 duplicate row(s)" in notes_text(res)


def test_table_covers_every_column():
    res = get_profile(PROFILE_DATA)
    cols = [r["column"] for r in res["table"]]
    assert cols == ["id", "grp", "x", "x2", "const", "messy", "bigmiss"]
    for r in res["table"]:
        assert {"column", "type", "n", "missing", "missing_pct", "unique"} <= set(r)


def test_numeric_profile_and_outliers():
    res = get_profile(PROFILE_DATA)
    x = by_column(res, "x")
    assert x["type"] == "numeric"
    assert x["n"] == 14 and x["missing"] == 0
    assert x["outliers"] == 1
    assert "(row 10)" in x["outlier_examples"]      # the 100.0 value
    assert "possible outlier(s)" in notes_text(res)


def test_categorical_profile():
    res = get_profile(PROFILE_DATA)
    g = by_column(res, "grp")
    assert g["type"] == "categorical"
    assert g["unique"] == 3                          # A, "a ", B
    assert g["levels"] == 3
    assert "top_value" in g


def test_warnings_fire_for_dirty_columns():
    text = notes_text(get_profile(PROFILE_DATA))
    assert "constant" in text                        # const: zero variance
    assert "looks numeric but contains non-numeric text" in text   # messy
    assert "missing" in text                         # bigmiss: >20% missing
    assert "case/whitespace variants" in text        # "A" vs "a "
    assert "Highly correlated pair" in text          # x vs x2 (r = 1.00)


def test_id_column_warning():
    data = [{"uid": f"row{i}", "y": float(i)} for i in range(1, 9)]
    text = notes_text(get_profile(data))
    assert "'uid' looks like an ID column" in text


def test_clean_dataset_has_no_structural_warnings():
    cols, rows = app.load_table_r(os.path.join(app.SCRIPT_DIR, "sample_data.csv"))
    text = notes_text(get_profile(rows))
    for bad in ("missing - ", "is constant", "ID column", "duplicate row",
                "looks numeric but contains", "case/whitespace"):
        assert bad not in text, f"unexpected warning: {bad}"


def test_missingness_plot_attached_when_needed(sample, tmp_path):
    cols, rows = sample
    res = get_profile(rows, plots=True, plot_dir=str(tmp_path))
    assert res.get("plots") in (None, [])            # sample has no missing data
    res = get_profile(PROFILE_DATA, plots=True, plot_dir=str(tmp_path))
    assert len(res["plots"]) == 1
    with open(res["plots"][0], "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"


# ---------------- Data tab UI ----------------

def test_ui_data_tab_populated_on_load(tk_app):
    a = tk_app
    a.load_sample()
    assert list(a.data_tree["columns"]) == ["group", "age", "pre", "post", "score"]
    kids = a.data_tree.get_children()
    assert len(kids) == 18
    vals = a.data_tree.item(kids[0])["values"]
    assert vals[0] == "Control" and float(vals[3]) == 54.3
    assert a.nb.tab(0, "text") == "Data"
    assert "18 of 18" in a.lbl_data_status.cget("text")


def test_ui_data_tab_paging(tk_app):
    a = tk_app
    big = [{"n": float(i), "sq": float(i * i)} for i in range(1, 1201)]
    a.records, a.columns = big, ["n", "sq"]
    a.fill_data_preview()
    kids = a.data_tree.get_children()
    assert len(kids) == 500
    assert "500 of 1,200" in a.lbl_data_status.cget("text")
    assert str(a.btn_more.cget("state")) != "disabled"
    a.show_more_rows()
    assert len(a.data_tree.get_children()) == 1000
    a.show_more_rows()
    assert len(a.data_tree.get_children()) == 1200
    assert "1,200 of 1,200" in a.lbl_data_status.cget("text")
    assert str(a.btn_more.cget("state")) == "disabled"


def test_ui_data_tab_reload_resets(tk_app):
    a = tk_app
    a.load_sample()
    a.load_sample()          # reload same file -> no duplicates in view
    assert len(a.data_tree.get_children()) == 18


def test_ui_profile_flow(tk_app):
    a = tk_app
    a.load_sample()
    a.analysis_var.set("Dataset profile"); a.on_analysis_change()
    req = a.collect_request()
    assert req == {"analysis": "profile", "variables": [], "options": {}}
    a.run_analysis()
    headers = list(a.tree["columns"])
    assert headers[0] == "column" and "missing_pct" in headers and "outliers" in headers
    assert len(a.tree.get_children()) == 5
    notes = a.txt_notes.get("1.0", "end")
    assert "correlated" in notes.lower()
