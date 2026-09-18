# app.py - Point-and-click statistics app powered by R (no R coding required)
# Front-end: Python/Tkinter. Back-end: Rscript engine.R (JSON over stdin/stdout).
import csv
import glob
import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "StatPad - Point & Click Statistics (R engine)"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_PATH = os.path.join(SCRIPT_DIR, "engine.R")


def find_rscript():
    """Locate Rscript.exe: PATH first, then standard R install locations."""
    p = shutil.which("Rscript")
    if p:
        return p
    for pattern in (r"C:\Program Files\R\R-*\bin\Rscript.exe",
                    r"C:\Program Files\R\R-*\bin\x64\Rscript.exe",
                    os.path.expanduser(r"~\AppData\Local\Programs\R\R-*\bin\Rscript.exe")):
        hits = sorted(glob.glob(pattern), reverse=True)
        if hits:
            return hits[0]
    return None


RSCRIPT = find_rscript()


def run_r(payload):
    """Send a JSON request to engine.R, return parsed JSON response. Retries once on transient R crashes."""
    if RSCRIPT is None:
        raise RuntimeError("R was not found. Install R from https://cran.r-project.org or add Rscript.exe to PATH.")
    if not os.path.exists(ENGINE_PATH):
        raise RuntimeError(f"engine.R not found next to app.py: {ENGINE_PATH}")
    body = json.dumps(payload)
    last_err = None
    for attempt in (1, 2):
        proc = subprocess.run(
            [RSCRIPT, ENGINE_PATH],
            input=body,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        out = (proc.stdout or "").strip()
        if out:
            try:
                return json.loads(out.splitlines()[-1])
            except json.JSONDecodeError:
                last_err = RuntimeError(f"Could not parse R output:\n{out[:800]}")
        else:
            detail = (proc.stderr or "").strip() or "no output from R"
            last_err = RuntimeError(f"R engine failed:\n{detail}")
    raise last_err


def load_table_r(path):
    """Load a CSV/XLS(X) file through R (loader.R); returns (columns, records)."""
    proc = subprocess.run(
        [RSCRIPT, os.path.join(SCRIPT_DIR, "loader.R"), path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Could not read file in R:\n{(proc.stderr or '').strip()}")
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        raise RuntimeError(f"Could not parse loader output:\n{proc.stdout[:800]}")
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(data["error"])
    if not isinstance(data, list):
        raise RuntimeError("R returned no data for this file.")
    cols = list(data[0].keys()) if data else []
    return cols, data

# ---CHUNK-END---

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1000x680")
        self.minsize(860, 560)
        self.records = []          # loaded data rows
        self.columns = []          # column names

        self._build_menu()
        self._build_layout()
        if RSCRIPT is None:
            self.after(300, lambda: messagebox.showerror(
                "R not found", "Rscript.exe was not found.\nInstall R (https://cran.r-project.org) and restart the app."))

    # ---------- UI construction ----------
    def _build_menu(self):
        m = tk.Menu(self)
        fm = tk.Menu(m, tearoff=0)
        fm.add_command(label="Open data file (CSV / Excel)...", command=self.open_file)
        fm.add_command(label="Load sample data", command=self.load_sample)
        fm.add_separator()
        fm.add_command(label="Export results as CSV...", command=self.export_results)
        fm.add_separator()
        fm.add_command(label="Exit", command=self.destroy)
        m.add_cascade(label="File", menu=fm)
        hm = tk.Menu(m, tearoff=0)
        hm.add_command(label="About", command=lambda: messagebox.showinfo(
            "About", APP_TITLE + "\n\nDescriptives, t-tests and linear regression via R.\nNo R coding required."))
        m.add_cascade(label="Help", menu=hm)
        self.config(menu=m)

    def _build_layout(self):
        panes = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(panes, padding=10)
        panes.add(left, weight=0)

        # data status
        dataf = ttk.LabelFrame(left, text=" Data ", padding=8)
        dataf.pack(fill=tk.X)
        self.lbl_data = ttk.Label(dataf, text="No data loaded", foreground="#777")
        self.lbl_data.pack(anchor="w")
        ttk.Button(dataf, text="Open CSV / Excel", command=self.open_file).pack(fill=tk.X, pady=(6, 2))
        ttk.Button(dataf, text="Load sample data", command=self.load_sample).pack(fill=tk.X)

        # analysis type
        anf = ttk.LabelFrame(left, text=" Analysis ", padding=8)
        anf.pack(fill=tk.X, pady=(10, 0))
        self.analysis_var = tk.StringVar(value="Descriptive statistics")
        for label in ("Descriptive statistics", "t-test", "Linear regression"):
            ttk.Radiobutton(anf, text=label, value=label, variable=self.analysis_var,
                            command=self.on_analysis_change).pack(anchor="w")

        # options frame (rebuilt per analysis type)
        self.optf = ttk.LabelFrame(left, text=" Options ", padding=8)
        self.optf.pack(fill=tk.X, pady=(10, 0))

        # variables
        self.varf = ttk.LabelFrame(left, text=" Variables (multi-select) ", padding=8)
        self.varf.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.varlist = tk.Listbox(self.varf, selectmode=tk.EXTENDED, exportselection=False, height=8)
        self.varlist.pack(fill=tk.BOTH, expand=True)
        ttk.Button(self.varf, text="Run analysis", command=self.run_analysis).pack(fill=tk.X, pady=(8, 0))

        # right pane: results
        right = ttk.Frame(panes, padding=10)
        panes.add(right, weight=1)
        self.lbl_result_title = ttk.Label(right, text="Results", font=("Segoe UI", 11, "bold"))
        self.lbl_result_title.pack(anchor="w")
        self.txt_notes = tk.Text(right, height=4, wrap="word", relief="flat", background="#f5f5f5")
        self.txt_notes.pack(fill=tk.X, pady=(4, 6))
        wrap = ttk.Frame(right)
        wrap.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(wrap, show="headings")
        ys = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self._last_table = None  # (headers, rows) for export
        self.on_analysis_change()

    # ---------- data handling ----------
    def open_file(self):
        path = filedialog.askopenfilename(
            title="Open data file",
            filetypes=[("Data files", "*.csv *.xlsx *.xls"), ("CSV", "*.csv"), ("Excel", "*.xlsx *.xls"), ("All files", "*.*")])
        if not path:
            return
        self.load_path(path)

    def load_path(self, path):
        try:
            cols, recs = load_table_r(path)
        except Exception as e:
            messagebox.showerror("Load error", str(e))
            return
        self.records, self.columns = recs, cols
        self.set_data_label(f"{os.path.basename(path)}  ({len(recs):,} rows x {len(cols)} cols)")
        self.refresh_varlist()

    def load_sample(self):
        self.load_path(os.path.join(SCRIPT_DIR, "sample_data.csv"))

    def set_data_label(self, text):
        self.lbl_data.config(text=text, foreground="#000")

    def refresh_varlist(self):
        self.varlist.delete(0, tk.END)
        for c in self.columns:
            self.varlist.insert(tk.END, c)

    def selected_vars(self):
        return [self.varlist.get(i) for i in self.varlist.curselection()]

    # ---------- options UI ----------
    def _role_combo(self, parent, label, var, extra_cols=14):
        row = ttk.Frame(parent); row.pack(fill=tk.X, pady=(3, 0))
        ttk.Label(row, text=label).pack(side=tk.LEFT)
        cb = ttk.Combobox(row, textvariable=var, state="readonly",
                          values=self.columns, width=extra_cols)
        cb.pack(side=tk.LEFT, padx=4)
        return cb

    def on_analysis_change(self):
        for w in self.optf.winfo_children():
            w.destroy()
        a = self.analysis_var.get()
        if a == "Descriptive statistics":
            ttk.Label(self.optf, text="Analyze every selected variable (below).").pack(anchor="w")
            self.varlist.config(state=tk.NORMAL)
        elif a == "t-test":
            if not hasattr(self, "ttype_var"):
                self.ttype_var = tk.StringVar(value="Independent samples")
            row = ttk.Frame(self.optf); row.pack(fill=tk.X)
            ttk.Label(row, text="Type:").pack(side=tk.LEFT)
            cb = ttk.Combobox(row, textvariable=self.ttype_var, state="readonly", width=20,
                              values=["Independent samples", "Paired", "One-sample"])
            cb.pack(side=tk.LEFT, padx=4)
            cb.bind("<<ComboboxSelected>>", lambda e: self.on_analysis_change())
            t = self.ttype_var.get()
            if t == "Independent samples":
                self.outcome_var = tk.StringVar()
                self.group_var = tk.StringVar()
                self._role_combo(self.optf, "Outcome (numeric):", self.outcome_var)
                self._role_combo(self.optf, "Group (2 levels):", self.group_var)
            elif t == "Paired":
                self.first_var = tk.StringVar()
                self.second_var = tk.StringVar()
                self._role_combo(self.optf, "First measure:", self.first_var)
                self._role_combo(self.optf, "Second measure:", self.second_var)
            else:
                self.varone_var = tk.StringVar()
                self._role_combo(self.optf, "Variable (numeric):", self.varone_var)
                row2 = ttk.Frame(self.optf); row2.pack(fill=tk.X, pady=(4, 0))
                ttk.Label(row2, text="Hypothesized mean:").pack(side=tk.LEFT)
                self.mu_var = tk.StringVar(value="0")
                ttk.Entry(row2, textvariable=self.mu_var, width=8).pack(side=tk.LEFT, padx=4)
            self.alt_var = tk.StringVar(value="two.sided")
            row3 = ttk.Frame(self.optf); row3.pack(fill=tk.X, pady=(4, 0))
            ttk.Label(row3, text="Alternative hypothesis:").pack(side=tk.LEFT)
            ttk.Combobox(row3, textvariable=self.alt_var, state="readonly", width=12,
                         values=["two.sided", "greater", "less"]).pack(side=tk.LEFT, padx=4)
            if t == "Independent samples":
                self.welch_var = tk.BooleanVar(value=True)
                ttk.Checkbutton(self.optf, text="Welch (unequal variances)", variable=self.welch_var).pack(anchor="w")
        else:  # regression
            self.dv_var = tk.StringVar()
            self._role_combo(self.optf, "Dependent (numeric):", self.dv_var)
            ttk.Label(self.optf, text="Independent variables: select below.").pack(anchor="w", pady=(4, 0))
        # update the variable-list label contextually
        if a == "Descriptive statistics":
            self.varf.config(text=" Variables (multi-select) ")
        elif a == "Linear regression":
            self.varf.config(text=" Independent variables (multi-select) ")
        else:
            self.varf.config(text=" (not used for t-test - use dropdowns above) ")

    # ---------- request building ----------
    def collect_request(self):
        a = self.analysis_var.get()
        if a == "Descriptive statistics":
            vs = self.selected_vars()
            if not vs:
                raise ValueError("Select at least one variable for descriptives.")
            return {"analysis": "descriptives", "variables": vs, "options": {}}
        if a == "t-test":
            t = self.ttype_var.get()
            if t == "Independent samples":
                dv, grp = self.outcome_var.get(), self.group_var.get()
                if not dv or not grp:
                    raise ValueError("Pick an outcome variable and a grouping variable.")
                if dv == grp:
                    raise ValueError("Outcome and grouping variables must differ.")
                opts = {"type": "independent", "welch": bool(self.welch_var.get()),
                        "alternative": self.alt_var.get()}
                vs = [dv, grp]
            elif t == "Paired":
                v1, v2 = self.first_var.get(), self.second_var.get()
                if not v1 or not v2:
                    raise ValueError("Pick both variables for the paired t-test.")
                if v1 == v2:
                    raise ValueError("Pick two different variables.")
                opts = {"type": "paired", "alternative": self.alt_var.get()}
                vs = [v1, v2]
            else:
                v = self.varone_var.get()
                if not v:
                    raise ValueError("Pick a variable for the one-sample t-test.")
                try:
                    mu = float(self.mu_var.get())
                except ValueError:
                    raise ValueError("Hypothesized mean must be a number.")
                opts = {"type": "one-sample", "mu": mu, "alternative": self.alt_var.get()}
                vs = [v]
            return {"analysis": "ttest", "variables": vs, "options": opts}
        # regression
        dv = self.dv_var.get()
        ivs = self.selected_vars()
        if not dv:
            raise ValueError("Pick a dependent variable.")
        if len(ivs) < 1:
            raise ValueError("Select at least one independent variable (below).")
        if dv in ivs:
            raise ValueError("The dependent variable cannot also be an independent variable.")
        return {"analysis": "regression", "variables": [dv] + ivs, "options": {}}

    # ---------- run + render ----------
    def run_analysis(self):
        if not self.records:
            messagebox.showwarning("No data", "Load a CSV/Excel file or the sample data first.")
            return
        try:
            req = self.collect_request()
        except ValueError as e:
            messagebox.showwarning("Selection problem", str(e))
            return
        req["data"] = self.records
        self.config(cursor="watch"); self.update_idletasks()
        try:
            res = run_r(req)
        except Exception as e:
            self.config(cursor="")
            messagebox.showerror("Analysis error", str(e))
            return
        finally:
            self.config(cursor="")
        if res.get("error"):
            messagebox.showerror("Analysis error", res["error"])
            return
        self.render(res)

    def render(self, res):
        title = res.get("title", "Results")
        headers, rows, notes = [], [], []

        def headers_union(rs):
            hs = []
            for r in rs:
                for k in r.keys():
                    if k not in hs:
                        hs.append(k)
            return hs

        if "table" in res:                       # descriptives
            rows = res["table"]
            headers = headers_union(rows)
        elif "rows" in res:                      # t-test
            rows = res["rows"]
            headers = headers_union(rows)
            if res.get("notes"):
                notes.append(str(res["notes"]))
        elif "coefficients" in res:              # regression
            notes.append(f"Model: {res.get('model','')}")
            notes.append(f"n = {res.get('n')},  R2 = {res.get('r_squared')},  adj. R2 = {res.get('adj_r_squared')}")
            notes.append(f"F = {res.get('f_statistic')} (p {res.get('f_p_value')}),  residual SE = {res.get('residual_se')}")
            d = res.get("diagnostics") or {}
            notes.append(f"Diagnostics: Shapiro-Wilk p {d.get('normality_shapiro_p')}; Breusch-Pagan p {d.get('heteroscedasticity_breusch_pagan_p')}")
            vif = d.get("vif")
            if vif:
                notes.append("VIF: " + ", ".join(f"{k}={v}" for k, v in vif.items()))
            std = res.get("standardized") or {}
            rows = res["coefficients"]
            if std:
                rows = [{**r, "std_beta": std.get(r["term"], "")} for r in rows]
            headers = headers_union(rows)
        else:
            notes.append(json.dumps(res, indent=2)[:400])

        self.lbl_result_title.config(text=title)
        self.txt_notes.config(state=tk.NORMAL)
        self.txt_notes.delete("1.0", tk.END)
        self.txt_notes.insert("1.0", "\n".join(n for n in notes if n))
        self.txt_notes.config(state=tk.DISABLED)

        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = headers
        for h in headers:
            self.tree.heading(h, text=h)
            self.tree.column(h, width=110, anchor="w", stretch=True)
        for r in rows:
            vals = []
            for h in headers:
                v = r.get(h, "")
                if v is None:
                    v = ""
                vals.append(v if isinstance(v, str) else (f"{v:g}" if isinstance(v, float) else str(v)))
            self.tree.insert("", tk.END, values=vals)
        self._last_table = (headers, [[r.get(h, "") for h in headers] for r in rows])

    def export_results(self):
        if not self._last_table:
            messagebox.showinfo("Nothing to export", "Run an analysis first.")
            return
        headers, rows = self._last_table
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")], title="Export results")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(headers)
            w.writerows(rows)
        messagebox.showinfo("Exported", f"Results saved to:\n{path}")


def main():
    if sys.platform != "win32" and RSCRIPT is None:
        pass  # still show the GUI; the error dialog explains what to install
    App().mainloop()


if __name__ == "__main__":
    main()
