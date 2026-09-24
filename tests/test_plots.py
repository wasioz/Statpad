"""Plot feature tests: exploration plots, result-attached plots, and the
Plots-tab UI. A plot "passes" if the engine returns an existing, non-trivial
PNG file; image content itself is covered by manual visual QA.
"""
import os

import app

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _assert_png(path):
    assert isinstance(path, str) and os.path.isfile(path), f"not a file: {path}"
    with open(path, "rb") as f:
        head = f.read(8)
    assert head == PNG_MAGIC, f"not a PNG: {path}"
    assert os.path.getsize(path) > 500, f"suspiciously small PNG: {path}"


def _plot_request(cols, rows, variables, ptype, tmp_path, **extra_opts):
    opts = {"plot_type": ptype, "plot_dir": str(tmp_path)}
    opts.update(extra_opts)
    return app.run_r({"analysis": "plot", "variables": variables,
                      "options": opts, "data": rows})


# ---------------- exploration plots ----------------

def test_explore_histogram(sample, tmp_path):
    cols, rows = sample
    res = _plot_request(cols, rows, ["score", "post", "pre"], "histogram", tmp_path)
    assert res.get("error") is None
    plots = res["plots"]
    assert len(plots) == 3
    for p in plots:
        _assert_png(p)
    assert res["title"] == "Histograms"


def test_explore_boxplot_grouped_and_ungrouped(sample, tmp_path):
    cols, rows = sample
    res = _plot_request(cols, rows, ["score"], "boxplot", tmp_path, group="group")
    assert res.get("error") is None and len(res["plots"]) == 1
    _assert_png(res["plots"][0])
    res2 = _plot_request(cols, rows, ["score"], "boxplot", tmp_path)
    assert res2.get("error") is None and len(res2["plots"]) == 1   # "All" fallback


def test_explore_scatter_qq_bar(sample, tmp_path):
    cols, rows = sample
    r1 = _plot_request(cols, rows, ["pre", "post"], "scatter", tmp_path)
    r2 = _plot_request(cols, rows, ["score"], "qq", tmp_path)
    r3 = _plot_request(cols, rows, ["group"], "bar", tmp_path)
    for res in (r1, r2, r3):
        assert res.get("error") is None
        assert len(res["plots"]) == 1
        _assert_png(res["plots"][0])


def test_explore_plot_errors(sample, tmp_path):
    cols, rows = sample
    res = _plot_request(cols, rows, ["score"], "scatter", tmp_path)
    assert "two numeric variables" in res["error"]
    res = _plot_request(cols, rows, ["group"], "histogram", tmp_path)
    assert "numeric" in res["error"]
    res = _plot_request(cols, rows, ["score"], "pie3d", tmp_path)
    assert "Unknown plot type" in res["error"]
    res = _plot_request(cols, rows, [], "histogram", tmp_path)
    assert "at least one variable" in res["error"]


def test_plot_with_degenerate_data_degrades_gracefully(tmp_path):
    data = [{"y": 5.0} for _ in range(10)]
    res = app.run_r({"analysis": "plot", "variables": ["y"],
                     "options": {"plot_type": "histogram", "plot_dir": str(tmp_path)},
                     "data": data})
    assert res.get("error") is None and len(res["plots"]) == 1
    _assert_png(res["plots"][0])
    res = app.run_r({"analysis": "plot", "variables": ["y"],
                     "options": {"plot_type": "qq", "plot_dir": str(tmp_path)},
                     "data": [{"y": 1.0}, {"y": 2.0}]})
    assert "error" in res


def test_plot_hostile_column_name(sample, tmp_path):
    cols, rows = sample
    data = [{"my var": float(r["score"]), "y": float(r["post"])} for r in rows]
    res = app.run_r({"analysis": "plot", "variables": ["my var", "y"],
                     "options": {"plot_type": "scatter", "plot_dir": str(tmp_path)},
                     "data": data})
    assert res.get("error") is None
    _assert_png(res["plots"][0])


# ---------------- result-attached plots ----------------

def test_result_plots_off_by_default(sample, tmp_path):
    cols, rows = sample
    res = app.run_r({"analysis": "ttest", "variables": ["score", "group"],
                     "options": {"type": "independent", "welch": True,
                                 "alternative": "two.sided", "plot_dir": str(tmp_path)},
                     "data": rows})
    assert "plots" not in res


def test_result_plots_ttest_all_types(sample, tmp_path):
    cols, rows = sample
    cases = [
        ({"type": "independent", "welch": True, "alternative": "two.sided"},
         ["score", "group"], "res_group_box"),
        ({"type": "paired"}, ["post", "pre"], "res_slope"),
        ({"type": "one-sample", "mu": 50, "alternative": "two.sided"},
         ["score"], "res_hist_mu"),
    ]
    for opts, variables, fname in cases:
        opts = {**opts, "plots": True, "plot_dir": str(tmp_path)}
        res = app.run_r({"analysis": "ttest", "variables": variables,
                         "options": opts, "data": rows})
        assert res.get("error") is None
        assert any(os.path.basename(p) == fname + ".png" for p in res["plots"])
        for p in res["plots"]:
            _assert_png(p)


def test_result_plots_descriptives_and_regression(sample, tmp_path):
    cols, rows = sample
    res = app.run_r({"analysis": "descriptives", "variables": ["score", "post"],
                     "options": {"plots": True, "plot_dir": str(tmp_path)}, "data": rows})
    assert len(res["plots"]) == 2
    res = app.run_r({"analysis": "regression", "variables": ["score", "age", "pre"],
                     "options": {"plots": True, "plot_dir": str(tmp_path)}, "data": rows})
    names = {os.path.basename(p) for p in res["plots"]}
    assert "res_forest.png" in names and "res_diagnostics.png" in names
    for p in res["plots"]:
        _assert_png(p)


def test_result_plots_do_not_break_analysis_payload(sample, tmp_path):
    """Numbers in the response must be identical with and without plots."""
    cols, rows = sample
    base = {"analysis": "regression", "variables": ["score", "age", "pre"], "data": rows}
    plain = app.run_r({**base, "options": {}})
    plotted = app.run_r({**base, "options": {"plots": True, "plot_dir": str(tmp_path)}})
    for key in ("r_squared", "adj_r_squared", "f_statistic", "residual_se", "coefficients"):
        assert plain[key] == plotted[key], f"{key} changed when plots were enabled"


# ---------------- Plots tab UI ----------------

def test_ui_explore_plots_flow(tk_app, dialogs):
    a = tk_app
    a.load_sample()
    a.analysis_var.set("Explore data (plots)"); a.on_analysis_change()
    assert hasattr(a, "plot_type_var")

    a.plot_type_var.set("Histogram"); a.on_analysis_change()
    a.pv_var.set("score")
    a.run_analysis()
    assert len(a._plots) == 1 and os.path.isfile(a._plots[0])
    assert a.lbl_image.cget("image") is not None
    assert "score" in a.lbl_plot_name.cget("text")

    a.plot_type_var.set("Boxplot"); a.on_analysis_change()
    a.bx_var.set("score"); a.bg_var.set("group")
    a.run_analysis()
    assert len(a._plots) == 1
    a.plot_type_var.set("Scatterplot"); a.on_analysis_change()
    a.sx_var.set("pre"); a.sy_var.set("post")
    a.run_analysis()
    assert len(a._plots) == 1
    a.plot_type_var.set("Bar chart"); a.on_analysis_change()
    a.bar_var.set("group")
    a.run_analysis()
    assert len(a._plots) == 1


def test_ui_plot_validation_and_nav(tk_app, dialogs):
    a = tk_app
    a.load_sample()
    a.analysis_var.set("Explore data (plots)"); a.on_analysis_change()
    # no variable picked -> warning, not crash
    a.run_analysis()
    assert any(c[0] == "warn" for c in dialogs)
    # scatter with same variable -> warning
    a.plot_type_var.set("Scatterplot"); a.on_analysis_change()
    a.sx_var.set("pre"); a.sy_var.set("pre")
    try:
        a._collect_plot_request()
        assert False, "expected ValueError for same X and Y"
    except ValueError:
        pass
    # multi-plot histogram navigates
    a.analysis_var.set("Explore data (plots)")
    a.plot_type_var.set("Histogram"); a.on_analysis_change()
    a.pv_var.set("post")
    a.run_analysis()
    assert len(a._plots) == 1
    a.show_plot(5)          # out of range clamps
    a.show_plot(0)
    assert a._plot_idx == 0


def test_ui_result_plots_appear_in_tab(tk_app):
    a = tk_app
    a.load_sample()
    assert a.plots_var.get() is True
    a.analysis_var.set("t-test"); a.on_analysis_change()
    a.outcome_var.set("score"); a.group_var.set("group")
    a.run_analysis()
    assert len(a._plots) == 1 and os.path.isfile(a._plots[0])
    # results table still populated
    assert a.tree.item(a.tree.get_children()[0])["values"][2] == "< 0.001"


def test_ui_plots_disabled_when_checkbox_off(tk_app):
    a = tk_app
    a.load_sample()
    a.plots_var.set(False)
    a.analysis_var.set("t-test"); a.on_analysis_change()
    a.outcome_var.set("score"); a.group_var.set("group")
    a.run_analysis()
    assert a._plots == []


def test_ui_save_plot_as(tk_app, monkeypatch, tmp_path):
    a = tk_app
    a.load_sample()
    a.analysis_var.set("Explore data (plots)"); a.on_analysis_change()
    a.plot_type_var.set("Histogram"); a.on_analysis_change()
    a.pv_var.set("score")
    a.run_analysis()
    out = tmp_path / "saved.png"
    monkeypatch.setattr(app.filedialog, "asksaveasfilename", lambda **k: str(out))
    a.save_plot_as()
    assert out.is_file()
    with open(out, "rb") as f:
        assert f.read(8) == PNG_MAGIC
