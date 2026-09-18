# StatPad — Point & Click Statistics (powered by R)

A Windows desktop app for basic statistical analyses with **no R coding required**.
You load a data file, pick variables from dropdowns, and click **Run analysis** —
the app generates and runs the R code for you and shows clean, formatted results.

## What it can do

| Analysis | Options | Output |
|---|---|---|
| **Descriptive statistics** | any number of numeric variables | n, missing, mean, SD, median, min, max, Q1, Q3, IQR, skewness, kurtosis, SE |
| **t-tests** | independent samples (Welch or Student), paired, one-sample | t, df, p, mean difference, 95% CI, Cohen's d, group means, Levene's test, Shapiro-Wilk normality note |
| **Linear regression** | 1 dependent + any independent variables | coefficients with 95% CI, standardized betas, R², adjusted R², F-test, residual SE, Shapiro-Wilk & Breusch-Pagan diagnostics, VIF |

Results can be exported to CSV (`File > Export results as CSV`).

## Running the app

Double-click **`run_app.bat`** — or from a terminal:

```
python app.py
```

### Requirements

- **Windows**
- **Python 3** (standard install; no extra Python packages needed)
- **R** with the `jsonlite` package (installed automatically with R? No — if missing,
  open R and run `install.packages("jsonlite")`. Optional but recommended:
  `readr`, `readxl`, `car`, `lmtest` for CSV/Excel loading and extra diagnostics.)

The app finds `Rscript.exe` automatically (PATH or `C:\Program Files\R\R-*\bin`).

## Using the app

1. **Load data** — click `Open CSV / Excel` or `Load sample data` (a demo dataset is included).
2. **Pick an analysis** — Descriptive statistics, t-test, or Linear regression.
3. **Pick variables** —
   - *Descriptives*: multi-select any variables in the list.
   - *t-test*: choose the type, then pick variables in the dropdowns.
   - *Regression*: pick the dependent variable in the dropdown, then select the independent variables in the list.
4. **Run analysis** — results appear on the right. Export via `File > Export results as CSV`.

## How it works

```
app.py (Tkinter GUI)  --JSON-->  Rscript engine.R  --JSON results-->  tables in the GUI
```

- `app.py` — the window, dropdowns, and results table. Sends your choices as JSON to R.
- `engine.R` — runs the requested analysis in R (`t.test`, `lm`, `shapiro.test`, ...)
  and returns tidy results as JSON.
- `loader.R` — reads CSV/Excel files (`readr`/`readxl`) and returns JSON.

No R code ever needs to be written, read, or modified to use the app.

## Files

| File | Purpose |
|---|---|
| `app.py` | Tkinter GUI front-end |
| `engine.R` | R analysis engine (descriptives, t-tests, regression) |
| `loader.R` | R data loader for CSV/Excel |
| `run_app.bat` | Double-click launcher |
| `sample_data.csv` | Demo dataset (group, age, pre, post, score) |

## Troubleshooting

- **"R was not found"** — install R from https://cran.r-project.org, or edit `find_rscript()` in `app.py`.
- **"package 'jsonlite' not found"** — in R console: `install.packages("jsonlite")`.
- **Excel files fail to load** — in R console: `install.packages("readxl")`.
- **A t-test says a variable "must have exactly 2 levels"** — the grouping variable in your
  data must contain exactly two distinct values (e.g., Control / Treatment).
