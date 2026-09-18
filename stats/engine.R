# engine.R - Statistical analysis engine for the stats GUI app
# Reads a JSON request from stdin, performs the analysis, writes JSON results to stdout.
# Request format: {"analysis": "...", "data": [...], "variables": [...], "options": {...}}
suppressPackageStartupMessages({
  library(jsonlite)
})

`%||%` <- function(a, b) if (is.null(a)) b else a

# ---------- helpers ----------
num <- function(x) as.numeric(as.character(x))

fmt_p <- function(p) {
  if (is.na(p)) return(NA_character_)
  if (p < 0.001) "< 0.001" else sprintf("%.3f", p)
}

# ---------- analysis functions ----------

do_descriptives <- function(df, variables, opts) {
  rows <- list()
  for (v in variables) {
    x <- num(df[[v]])
    x <- x[!is.na(x)]
    n_total <- nrow(df)
    if (length(x) < 1) {
      rows[[length(rows) + 1]] <- list(variable = v, n = 0, missing = n_total)
      next
    }
    q <- quantile(x, c(0.25, 0.75), names = FALSE)
    n <- length(x)
    m <- mean(x); s <- sd(x)
    if (is.na(s) || s == 0 || n < 3) {
      skew <- NA; kurt <- NA
    } else {
      z <- (x - m) / s
      skew <- sum(z^3) * n / ((n - 1) * (n - 2))
      kurt <- sum(z^4) / n - 3
    }
    rows[[length(rows) + 1]] <- list(
      variable = v, n = n, missing = n_total - n,
      mean = round(m, 4), sd = round(s, 4),
      median = round(median(x), 4),
      min = round(min(x), 4), max = round(max(x), 4),
      q1 = round(q[1], 4), q3 = round(q[2], 4),
      iqr = round(q[2] - q[1], 4),
      skewness = round(skew, 4), kurtosis = round(kurt, 4),
      se = if (!is.na(s)) round(s / sqrt(n), 4) else NA
    )
  }
  list(title = "Descriptive Statistics", table = rows)
}


do_ttest <- function(df, variables, opts) {
  type <- opts$type %||% "independent"
  alpha <- 0.05

  shapiro_note <- function(x) {
    x <- x[!is.na(x)]
    if (length(x) < 3 || length(x) > 5000) return(NA_character_)
    sw <- tryCatch(shapiro.test(x), error = function(e) NULL)
    if (is.null(sw)) return(NA_character_)
    if (sw$p.value < alpha) "Normality violated (Shapiro-Wilk p < 0.05)" else "Normality holds (Shapiro-Wilk p >= 0.05)"
  }

  cohens_d <- function(x, y, paired) {
    x <- x[!is.na(x)]; y <- y[!is.na(y)]
    d <- tryCatch({
      if (paired) mean(x - y) / sd(x - y)
      else {
        nx <- length(x); ny <- length(y)
        sp <- sqrt(((nx - 1) * var(x) + (ny - 1) * var(y)) / (nx + ny - 2))
        (mean(x) - mean(y)) / sp
      }
    }, error = function(e) NA)
    round(d, 4)
  }

  if (type == "one-sample") {
    v <- variables[1]
    mu <- as.numeric(opts$mu %||% 0)
    x <- num(df[[v]])
    tt <- tryCatch(t.test(x, mu = mu, alternative = opts$alternative %||% "two.sided"), error = function(e) e)
    if (inherits(tt, "error")) return(list(error = conditionMessage(tt)))
    list(title = sprintf("One-Sample t-test: %s vs mu = %g", v, mu),
      rows = list(list(
        statistic = round(tt$statistic, 4), df = round(tt$parameter, 3),
        p_value = fmt_p(tt$p.value),
        mean_diff = round(tt$estimate - mu, 4),
        ci_lower = round(tt$conf.int[1], 4), ci_upper = round(tt$conf.int[2], 4),
        n = sum(!is.na(x)), effect_size = NA,
        interpretation = if (tt$p.value < alpha) "Significant difference" else "No significant difference"
      )),
      notes = shapiro_note(x))
  } else if (type == "paired") {
    v1 <- variables[1]; v2 <- variables[2]
    x <- num(df[[v1]]); y <- num(df[[v2]])
    ok <- !is.na(x) & !is.na(y)
    tt <- tryCatch(t.test(x[ok], y[ok], paired = TRUE, alternative = opts$alternative %||% "two.sided"), error = function(e) e)
    if (inherits(tt, "error")) return(list(error = conditionMessage(tt)))
    list(title = sprintf("Paired t-test: %s vs %s", v1, v2),
      rows = list(list(
        statistic = round(tt$statistic, 4), df = round(tt$parameter, 3),
        p_value = fmt_p(tt$p.value),
        mean_diff = round(tt$estimate, 4),
        ci_lower = round(tt$conf.int[1], 4), ci_upper = round(tt$conf.int[2], 4),
        n = sum(ok),
        effect_size = cohens_d(x[ok], y[ok], TRUE),
        interpretation = if (tt$p.value < alpha) "Significant difference between paired means" else "No significant difference between paired means"
      )),
      notes = shapiro_note(x[ok] - y[ok]))
  } else {
    dv <- variables[1]; grp <- variables[2]
    x <- num(df[[dv]]); g <- droplevels(factor(df[[grp]]))
    lv <- levels(g)
    if (length(lv) != 2) {
      return(list(error = sprintf("Grouping variable '%s' must have exactly 2 levels (found %d).", grp, length(lv))))
    }
    a <- x[g == lv[1]]; b <- x[g == lv[2]]
    welch <- if (is.null(opts$welch)) TRUE else as.logical(opts$welch)
    tt <- tryCatch(t.test(a, b, var.equal = !welch, alternative = opts$alternative %||% "two.sided"), error = function(e) e)
    if (inherits(tt, "error")) return(list(error = conditionMessage(tt)))
    lev_p <- tryCatch({
      if (requireNamespace("car", quietly = TRUE)) {
        fmt_p(car::leveneTest(x ~ g)$`Pr(>F)`[1])
      } else NA_character_
    }, error = function(e) NA_character_)
    list(title = sprintf("Independent-Samples t-test: %s by %s", dv, grp),
      rows = list(list(
        statistic = round(tt$statistic, 4),

        df = round(tt$parameter, 3),
        p_value = fmt_p(tt$p.value),
        mean_diff = round(tt$estimate[2] - tt$estimate[1], 4),
        ci_lower = round(tt$conf.int[1], 4), ci_upper = round(tt$conf.int[2], 4),
        n = sprintf("%s=%d; %s=%d", lv[1], sum(g == lv[1] & !is.na(x)), lv[2], sum(g == lv[2] & !is.na(x))),
        effect_size = cohens_d(a, b, FALSE),
        interpretation = if (tt$p.value < alpha) "Significant difference between group means" else "No significant difference between group means"
      )),
      notes = paste0("Method: ", if (welch) "Welch (unequal variances)" else "Student (equal variances)",
        ". Levene's test p: ", lev_p,
        ". Group means: ", lv[1], " = ", round(mean(a, na.rm = TRUE), 4),
        "; ", lv[2], " = ", round(mean(b, na.rm = TRUE), 4), "."))
  }
}

do_regression <- function(df, variables, opts) {
  dv <- variables[1]
  ivs <- variables[-1]
  if (length(ivs) == 0) return(list(error = "Select at least one independent variable."))
  f <- stats::as.formula(paste0("`", dv, "` ~ ", paste(sprintf("`%s`", ivs), collapse = " + ")))
  dat <- df[, c(dv, ivs), drop = FALSE]
  dat <- dat[stats::complete.cases(dat), , drop = FALSE]
  if (nrow(dat) < length(ivs) + 2) {
    return(list(error = sprintf("Not enough complete cases (%d) for the model.", nrow(dat))))
  }
  fit <- tryCatch(lm(f, data = dat), error = function(e) e)
  if (inherits(fit, "error")) return(list(error = conditionMessage(fit)))

  co <- summary(fit)$coefficients
  ci <- tryCatch(stats::confint(fit), error = function(e) NULL)
  coef_rows <- lapply(seq_len(nrow(co)), function(i) {
    list(
      term = rownames(co)[i],
      estimate = round(co[i, 1], 4),
      se = round(co[i, 2], 4),
      t = round(co[i, 3], 4),
      p_value = fmt_p(co[i, 4]),
      ci_lower = if (!is.null(ci)) round(ci[i, 1], 4) else NA,
      ci_upper = if (!is.null(ci)) round(ci[i, 2], 4) else NA
    )
  })

  # standardized (beta) coefficients from z-scored data
  std_rows <- tryCatch({
    zs <- as.data.frame(scale(dat))
    fs <- stats::as.formula(paste0("`", dv, "` ~ ", paste(sprintf("`%s`", ivs), collapse = " + ")))
    sc <- summary(lm(fs, data = zs))$coefficients
    setNames(lapply(seq_len(nrow(sc)), function(i) round(sc[i, 1], 4)), rownames(sc))
  }, error = function(e) NULL)

  sw <- tryCatch(shapiro.test(residuals(fit))$p.value, error = function(e) NA)
  bp <- tryCatch(lmtest::bptest(fit)$p.value, error = function(e) NA)
  vifs <- tryCatch({
    if (length(ivs) > 1 && requireNamespace("car", quietly = TRUE)) car::vif(fit) else NULL
  }, error = function(e) NULL)

  sm <- summary(fit)
  list(title = "Linear Regression",
    model = sprintf("%s ~ %s", dv, paste(ivs, collapse = " + ")),
    n = nrow(dat),
    r_squared = round(sm$r.squared, 4),
    adj_r_squared = round(sm$adj.r.squared, 4),
    f_statistic = round(sm$fstatistic[1], 4),
    f_p_value = tryCatch(fmt_p(stats::pf(sm$fstatistic[1], sm$fstatistic[2], sm$fstatistic[3], lower.tail = FALSE)), error = function(e) NA_character_),
    residual_se = round(sm$sigma, 4),
    coefficients = coef_rows,
    standardized = std_rows,
    diagnostics = list(
      normality_shapiro_p = if (!is.na(sw)) fmt_p(sw) else NA,
      heteroscedasticity_breusch_pagan_p = if (!is.na(bp)) fmt_p(bp) else NA,
      vif = if (!is.null(vifs)) as.list(round(vifs, 3)) else NULL
    ))
}

# ---------- main ----------
req <- tryCatch(fromJSON(readLines(con = "stdin", warn = FALSE), simplifyVector = FALSE),
                error = function(e) list(error = paste0("Bad input JSON: ", conditionMessage(e))))
if (!is.null(req$error)) {
  cat(toJSON(list(error = req$error), auto_unbox = TRUE, na = "null"))
  quit(status = 1)
}

analysis <- req$analysis
opts <- req$options %||% list()
variables <- unlist(req$variables %||% character(0))

# rebuild data frame from JSON records (array of objects -> data frame)
df <- tryCatch({
  recs <- req$data
  if (is.null(recs) || length(recs) == 0) NULL
  else {
    cols <- names(recs[[1]])
    out_df <- as.data.frame(lapply(cols, function(nm) {
      v <- lapply(recs, function(r) if (is.null(r[[nm]])) NA else r[[nm]])
      unname(unlist(v))
    }), stringsAsFactors = FALSE, check.names = FALSE)
    names(out_df) <- cols
    out_df
  }
}, error = function(e) NULL)

if (is.null(df) || ncol(df) == 0) {
  cat(toJSON(list(error = "No data received."), auto_unbox = TRUE, na = "null"))
  quit(status = 1)
}

# coerce numeric-looking columns to numeric (keep as factor/text otherwise)
for (nm in names(df)) {
  v <- df[[nm]]
  nums <- suppressWarnings(as.numeric(as.character(v)))
  non_blank <- !is.na(as.character(v)) & trimws(as.character(v)) != ""
  if (sum(non_blank) > 0 && !any(is.na(nums[non_blank]))) df[[nm]] <- nums
}

out <- tryCatch({
  result <- switch(analysis,
    "descriptives" = do_descriptives(df, variables, opts),
    "ttest"        = do_ttest(df, variables, opts),
    "regression"   = do_regression(df, variables, opts),
    list(error = paste0("Unknown analysis type: ", analysis)))
  result
}, error = function(e) list(error = conditionMessage(e)))

cat(toJSON(out, auto_unbox = TRUE, na = "null", digits = 6))
