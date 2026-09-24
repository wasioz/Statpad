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

# Round for display, but keep +/-Inf visible as strings (jsonlite would
# otherwise turn Inf into null with na="null").
fin <- function(x) {
  if (length(x) == 0 || is.na(x)) return(NA)
  if (is.finite(x)) return(round(x, 4))
  paste0(if (x < 0) "-" else "", "Inf")
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
      mean = round(m, 4), sd = fin(s),
      median = round(median(x), 4),
      min = round(min(x), 4), max = round(max(x), 4),
      q1 = round(q[1], 4), q3 = round(q[2], 4),
      iqr = round(q[2] - q[1], 4),
      skewness = round(skew, 4), kurtosis = round(kurt, 4),
      se = fin(s / sqrt(n))
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
        ci_lower = fin(tt$conf.int[1]), ci_upper = fin(tt$conf.int[2]),
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
        ci_lower = fin(tt$conf.int[1]), ci_upper = fin(tt$conf.int[2]),
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
        ci_lower = fin(tt$conf.int[1]), ci_upper = fin(tt$conf.int[2]),
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
  # map original (possibly non-syntactic) names to safe syntactic placeholders
  allv <- c(dv, ivs)
  safe <- make.names(allv, unique = TRUE)
  mapping <- setNames(as.list(safe), allv)
  f <- stats::as.formula(paste(mapping[[dv]], "~",
                               paste(unlist(mapping[ivs]), collapse = " + ")))
  dat <- df[, allv, drop = FALSE]
  names(dat) <- safe
  dat <- dat[stats::complete.cases(dat), , drop = FALSE]
  if (nrow(dat) < length(ivs) + 2) {
    return(list(error = sprintf("Not enough complete cases (%d) for the model.", nrow(dat))))
  }
  fit <- tryCatch(lm(f, data = dat), error = function(e) e)
  if (inherits(fit, "error")) return(list(error = conditionMessage(fit)))

  co <- summary(fit)$coefficients
  ci <- tryCatch(stats::confint(fit), error = function(e) NULL)
  # map safe term names back to the original variable names
  # (factor predictors expand to terms like <safe><Level>, so prefix-match)
  label_term <- function(tm) {
    for (orig in allv) {
      safe_nm <- mapping[[orig]]
      if (tm == safe_nm || startsWith(tm, safe_nm)) return(orig)
    }
    tm
  }
  coef_rows <- lapply(seq_len(nrow(co)), function(i) {
    list(
      term = label_term(rownames(co)[i]),
      estimate = round(co[i, 1], 4),
      se = round(co[i, 2], 4),
      t = round(co[i, 3], 4),
      p_value = fmt_p(co[i, 4]),
      ci_lower = if (!is.null(ci)) fin(ci[i, 1]) else NA,
      ci_upper = if (!is.null(ci)) fin(ci[i, 2]) else NA
    )
  })

  # standardized (beta) coefficients from z-scored data
  std_rows <- tryCatch({
    zs <- as.data.frame(scale(dat))
    sc <- summary(lm(f, data = zs))$coefficients
    vals <- lapply(seq_len(nrow(sc)), function(i) round(sc[i, 1], 4))
    setNames(vals, vapply(rownames(sc), label_term, character(1)))
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

# ---------- plots ----------
# Plots are generated only when the request sets options$plots = TRUE (or for
# the "plot" analysis type). PNGs are written with ragg so they always have a
# white background and consistent sizing.

HAVE_PLOT_PKGS <- requireNamespace("ggplot2", quietly = TRUE) &&
  requireNamespace("ragg", quietly = TRUE)

resolve_plot_dir <- function(opts) {
  d <- opts$plot_dir
  if (is.null(d) || !nzchar(d)) d <- tempdir()
  dir.create(d, recursive = TRUE, showWarnings = FALSE)
  d
}

theme_sp <- function() {
  ggplot2::theme_minimal(base_size = 14) +
    ggplot2::theme(plot.title = ggplot2::element_text(face = "bold"),
                   panel.grid.minor = ggplot2::element_blank())
}

save_ggplot <- function(p, dir, name, w = 1400, h = 1000) {
  f <- file.path(dir, paste0(name, ".png"))
  ok <- tryCatch({
    ragg::agg_png(f, width = w, height = h, units = "px", res = 150, background = "white")
    print(p)
    grDevices::dev.off()
    TRUE
  }, error = function(e) { try(grDevices::dev.off(), silent = TRUE); FALSE })
  if (ok && file.exists(f) && file.info(f)$size > 100) f else NULL
}

save_baseplot <- function(fun, dir, name, w = 1400, h = 1000) {
  f <- file.path(dir, paste0(name, ".png"))
  ok <- tryCatch({
    ragg::agg_png(f, width = w, height = h, units = "px", res = 150, background = "white")
    fun()
    grDevices::dev.off()
    TRUE
  }, error = function(e) { try(grDevices::dev.off(), silent = TRUE); FALSE })
  if (ok && file.exists(f) && file.info(f)$size > 100) f else NULL
}

plot_histogram <- function(df, v, xline = NULL, name_prefix = "hist") {
  x <- num(df[[v]])
  ok <- !is.na(x)
  if (sum(ok) < 3) return(NULL)
  d <- data.frame(x = x[ok])
  spread <- length(unique(d$x)) > 2 && (length(d$x) < 2 || sd(d$x) > 0)
  p <- ggplot2::ggplot(d, ggplot2::aes(x = x)) +
    ggplot2::geom_histogram(ggplot2::aes(y = ggplot2::after_stat(density)),
                            bins = 30, fill = "#4C72B0", color = "white") +
    ggplot2::labs(title = paste("Distribution of", v), x = v, y = "Density") +
    theme_sp()
  if (spread) {
    p <- p + ggplot2::geom_density(ggplot2::aes(y = ggplot2::after_stat(density)),
                                   color = "#C44E52", linewidth = 1)
  }
  if (!is.null(xline) && is.finite(xline)) {
    p <- p + ggplot2::geom_vline(xintercept = xline, color = "#55A868",
                                 linewidth = 1, linetype = "dashed")
  }
  p
}

plot_box_by_group <- function(df, dv, grp) {
  x <- num(df[[dv]]); g <- droplevels(factor(df[[grp]]))
  ok <- !is.na(x) & !is.na(g)
  if (sum(ok) < 3 || nlevels(g) < 1) return(NULL)
  d <- data.frame(y = x[ok], g = g[ok])
  ggplot2::ggplot(d, ggplot2::aes(x = g, y = y, fill = g)) +
    ggplot2::geom_boxplot(alpha = 0.8, outlier.shape = NA) +
    ggplot2::geom_jitter(width = 0.15, alpha = 0.45, size = 1.6) +
    ggplot2::labs(title = paste(dv, "by", grp), x = grp, y = dv) +
    theme_sp() +
    ggplot2::theme(legend.position = "none")
}

plot_slopegraph <- function(df, v1, v2) {
  a <- num(df[[v1]]); b <- num(df[[v2]])
  ok <- !is.na(a) & !is.na(b)
  if (sum(ok) < 2) return(NULL)
  idx <- which(ok)
  if (length(idx) > 60) idx <- idx[1:60]   # keep the spaghetti readable
  d <- data.frame(id = idx,
                  time = factor(rep(c(v1, v2), each = length(idx)),
                                levels = c(v1, v2)),
                  value = c(a[idx], b[idx]))
  ggplot2::ggplot(d, ggplot2::aes(x = time, y = value, group = id)) +
    ggplot2::geom_line(color = "#4C72B0", alpha = 0.55) +
    ggplot2::geom_point(color = "#4C72B0", size = 1.8) +
    ggplot2::labs(title = "Paired change (first measure -> second measure)",
                  x = NULL, y = "Value") +
    theme_sp()
}

plot_scatter <- function(df, vx, vy) {
  x <- num(df[[vx]]); y <- num(df[[vy]])
  ok <- !is.na(x) & !is.na(y)
  if (sum(ok) < 3) return(NULL)
  d <- data.frame(x = x[ok], y = y[ok])
  ggplot2::ggplot(d, ggplot2::aes(x = x, y = y)) +
    ggplot2::geom_point(color = "#4C72B0", alpha = 0.65, size = 2) +
    ggplot2::geom_smooth(method = "lm", color = "#C44E52") +
    ggplot2::labs(title = paste(vy, "vs", vx), x = vx, y = vy) +
    theme_sp()
}

plot_qq <- function(df, v) {
  x <- num(df[[v]]); x <- x[!is.na(x)]
  if (length(x) < 4) return(NULL)
  d <- data.frame(x = x)
  ggplot2::ggplot(d, ggplot2::aes(sample = x)) +
    ggplot2::stat_qq(color = "#4C72B0", alpha = 0.7) +
    ggplot2::stat_qq_line(color = "#C44E52") +
    ggplot2::labs(title = paste("Normal Q-Q plot:", v), x = "Theoretical quantiles", y = "Sample quantiles") +
    theme_sp()
}

plot_bar <- function(df, v) {
  x <- as.character(df[[v]])
  x <- x[!is.na(x) & nzchar(x)]
  if (length(x) < 1) return(NULL)
  d <- data.frame(x = x)
  ggplot2::ggplot(d, ggplot2::aes(x = x)) +
    ggplot2::geom_bar(fill = "#4C72B0", color = "white") +
    ggplot2::labs(title = paste("Counts of", v), x = v, y = "Count") +
    theme_sp() +
    ggplot2::theme(axis.text.x = ggplot2::element_text(angle = 30, hjust = 1))
}

# ---------- plot dispatcher + result plots ----------

do_plot_analysis <- function(df, variables, opts) {
  dir <- resolve_plot_dir(opts)
  ptype <- opts$plot_type %||% "histogram"
  plots <- list()
  title <- switch(ptype,
    "histogram" = "Histograms",
    "boxplot"   = "Boxplot",
    "scatter"   = "Scatterplot",
    "qq"        = "Normal Q-Q plot",
    "bar"       = "Bar chart",
    NULL)
  if (is.null(title)) return(list(error = sprintf("Unknown plot type: %s", ptype)))
  if (length(variables) < 1) return(list(error = "Select at least one variable for the plot."))

  if (ptype == "histogram") {
    num_vars <- variables[vapply(variables, function(v) is.numeric(df[[v]]), logical(1))]
    if (length(num_vars) == 0) return(list(error = "Histogram needs at least one numeric variable."))
    for (v in utils::head(num_vars, 6)) {
      p <- plot_histogram(df, v)
      f <- if (!is.null(p)) save_ggplot(p, dir, paste0("hist_", v)) else NULL
      if (!is.null(f)) plots[[length(plots) + 1]] <- f
    }
    if (length(plots) == 0) return(list(error = "Could not create histograms (not enough data)."))
  } else if (ptype == "boxplot") {
    v <- variables[1]
    if (!is.numeric(df[[v]])) return(list(error = sprintf("Boxplot needs a numeric variable ('%s' is not numeric).", v)))
    grp <- opts$group
    p <- if (!is.null(grp) && nzchar(grp) && grp %in% names(df) && !is.numeric(df[[grp]])) {
      plot_box_by_group(df, v, grp)
    } else {
      d2 <- df; d2$.all <- factor("All")
      p2 <- plot_box_by_group(d2, v, ".all")
      if (!is.null(p2)) p2 <- p2 + ggplot2::labs(x = NULL)
      p2
    }
    f <- if (!is.null(p)) save_ggplot(p, dir, paste0("box_", v)) else NULL
    if (!is.null(f)) plots[[length(plots) + 1]] <- f
    if (length(plots) == 0) return(list(error = "Could not create boxplot (not enough data)."))
  } else if (ptype == "scatter") {
    if (length(variables) < 2) return(list(error = "Scatterplot needs two numeric variables."))
    p <- plot_scatter(df, variables[1], variables[2])
    f <- if (!is.null(p)) save_ggplot(p, dir, "scatter") else NULL
    if (!is.null(f)) plots[[length(plots) + 1]] <- f
    if (length(plots) == 0) return(list(error = "Could not create scatterplot (not enough data)."))
  } else if (ptype == "qq") {
    p <- plot_qq(df, variables[1])
    f <- if (!is.null(p)) save_ggplot(p, dir, paste0("qq_", variables[1])) else NULL
    if (!is.null(f)) plots[[length(plots) + 1]] <- f
    if (length(plots) == 0) return(list(error = "Could not create Q-Q plot (not enough data)."))
  } else if (ptype == "bar") {
    p <- plot_bar(df, variables[1])
    f <- if (!is.null(p)) save_ggplot(p, dir, paste0("bar_", variables[1])) else NULL
    if (!is.null(f)) plots[[length(plots) + 1]] <- f
    if (length(plots) == 0) return(list(error = "Could not create bar chart (no data)."))
  }

  list(title = title, plots = plots, notes = sprintf("%d plot(s) created.", length(plots)))
}

attach_result_plots <- function(res, df, variables, opts, analysis) {
  if (!isTRUE(opts$plots)) return(res)
  if (!HAVE_PLOT_PKGS) {
    res$notes <- c(res$notes, "Plotting skipped: the ggplot2/ragg packages are not installed.")
    return(res)
  }
  dir <- resolve_plot_dir(opts)
  plots <- list()
  try({
    if (analysis == "descriptives") {
      num_vars <- variables[vapply(variables, function(v) is.numeric(df[[v]]), logical(1))]
      for (v in utils::head(num_vars, 6)) {
        p <- plot_histogram(df, v)
        f <- if (!is.null(p)) save_ggplot(p, dir, paste0("res_hist_", v)) else NULL
        if (!is.null(f)) plots[[length(plots) + 1]] <- f
      }
    } else if (analysis == "profile") {
      miss_pct <- vapply(names(df), function(nm) {
        v <- df[[nm]]
        if (is.character(v)) 100 * mean(is.na(v) | (!is.na(v) & trimws(v) == "")) else 100 * mean(is.na(v))
      }, numeric(1))
      if (any(miss_pct > 0)) {
        d <- data.frame(column = names(miss_pct), pct = as.numeric(miss_pct),
                        stringsAsFactors = FALSE)
        d <- d[d$pct > 0, , drop = FALSE]
        d$column <- factor(d$column, levels = d$column[order(-d$pct)])
        p <- ggplot2::ggplot(d, ggplot2::aes(x = column, y = pct)) +
          ggplot2::geom_col(fill = "#4C72B0") +
          ggplot2::coord_flip() +
          ggplot2::labs(title = "Missing data by column", x = NULL, y = "% missing") +
          theme_sp()
        f <- save_ggplot(p, dir, "res_missing")
        if (!is.null(f)) plots[[length(plots) + 1]] <- f
      }
    } else if (analysis == "ttest") {
      type <- opts$type %||% "independent"
      p <- NULL; f <- NULL
      if (type == "independent" && length(variables) >= 2) {
        p <- plot_box_by_group(df, variables[1], variables[2])
        if (!is.null(p)) f <- save_ggplot(p, dir, "res_group_box")
      } else if (type == "paired" && length(variables) >= 2) {
        p <- plot_slopegraph(df, variables[1], variables[2])
        if (!is.null(p)) f <- save_ggplot(p, dir, "res_slope")
      } else if (type == "one-sample" && length(variables) >= 1) {
        mu <- as.numeric(opts$mu %||% 0)
        p <- plot_histogram(df, variables[1], xline = mu)
        if (!is.null(p)) f <- save_ggplot(p, dir, "res_hist_mu")
      }
      if (!is.null(f)) plots[[length(plots) + 1]] <- f
    } else if (analysis == "regression") {
      co <- res$coefficients
      if (length(co) >= 1) {
        fdf <- data.frame(
          term = vapply(co, function(r) as.character(r$term), character(1)),
          est  = vapply(co, function(r) as.numeric(r$estimate), numeric(1)),
          lo   = suppressWarnings(vapply(co, function(r) as.numeric(r$ci_lower), numeric(1))),
          hi   = suppressWarnings(vapply(co, function(r) as.numeric(r$ci_upper), numeric(1))),
          stringsAsFactors = FALSE)
        fdf <- fdf[is.finite(fdf$est) & is.finite(fdf$lo) & is.finite(fdf$hi), , drop = FALSE]
        if (nrow(fdf) >= 1) {
          fdf$term <- factor(fdf$term, levels = rev(unique(fdf$term)))
          p <- ggplot2::ggplot(fdf, ggplot2::aes(x = est, y = term)) +
            ggplot2::geom_vline(xintercept = 0, linetype = "dashed", color = "grey55") +
            ggplot2::geom_pointrange(ggplot2::aes(xmin = lo, xmax = hi), color = "#4C72B0") +
            ggplot2::labs(title = "Coefficients with 95% CI", x = "Estimate", y = NULL) +
            theme_sp()
          f <- save_ggplot(p, dir, "res_forest")
          if (!is.null(f)) plots[[length(plots) + 1]] <- f
        }
      }
      # refit for diagnostics using the same safe-name mapping as do_regression
      dv <- variables[1]; ivs <- variables[-1]
      allv <- c(dv, ivs)
      safe <- make.names(allv, unique = TRUE)
      fit_dat <- df[, allv, drop = FALSE]
      names(fit_dat) <- safe
      fit <- tryCatch(lm(stats::as.formula(paste(safe[1], "~",
                                                 paste(safe[-1], collapse = " + "))),
                         data = fit_dat[stats::complete.cases(fit_dat), , drop = FALSE]),
                      error = function(e) NULL)
      if (!is.null(fit)) {
        f <- save_baseplot(function() {
          op <- graphics::par(mfrow = c(2, 2), mar = c(4, 4, 3, 1.5))
          on.exit(graphics::par(op), add = TRUE)
          graphics::plot(fit, which = c(1, 2, 3, 4), ask = FALSE, id.n = 0)
        }, dir, "res_diagnostics")
        if (!is.null(f)) plots[[length(plots) + 1]] <- f
      }
    }
  }, silent = TRUE)
  if (length(plots) > 0) res$plots <- plots
  res
}

# ---------- dataset profile ----------
do_profile <- function(df, variables, opts) {
  n_rows <- nrow(df)
  n_cols <- ncol(df)
  rows <- list()
  warn <- character(0)

  dup <- sum(duplicated(df))
  if (dup > 0) {
    warn <- c(warn, sprintf("Dataset contains %d duplicate row(s) (identical to earlier rows).", dup))
  }

  num_cols <- names(df)[vapply(df, is.numeric, logical(1))]
  cor_pairs <- 0
  if (length(num_cols) >= 2 && n_rows >= 3) {
    cm <- suppressWarnings(stats::cor(df[, num_cols, drop = FALSE], use = "pairwise.complete.obs"))
    for (i in seq_along(num_cols)) {
      if (i >= length(num_cols)) break
      for (j in (i + 1):length(num_cols)) {
        r <- cm[i, j]
        if (is.finite(r) && abs(r) >= 0.9) {
          cor_pairs <- cor_pairs + 1
          if (cor_pairs <= 3) {
            warn <- c(warn, sprintf("Highly correlated pair: '%s' and '%s' (r = %.2f) - watch for multicollinearity in regression.", num_cols[i], num_cols[j], r))
          }
        }
      }
    }
    if (cor_pairs > 3) {
      warn <- c(warn, sprintf("... and %d more highly correlated numeric pair(s).", cor_pairs - 3))
    }
  }

  for (nm in names(df)) {
    v <- df[[nm]]
    miss_idx <- if (is.character(v)) is.na(v) | trimws(v) == "" else is.na(v)
    miss <- sum(miss_idx)
    valid <- v[!miss_idx]
    n_uniq <- length(unique(valid))
    miss_pct <- round(100 * miss / n_rows, 1)
    is_num <- is.numeric(v)

    row <- list(column = nm,
                type = if (is_num) "numeric" else "categorical",
                n = n_rows, missing = miss, missing_pct = miss_pct,
                unique = n_uniq)

    if (miss / n_rows > 0.2) {
      warn <- c(warn, sprintf("'%s' is %g%% missing - results using it may be unreliable.", nm, miss_pct))
    }

    if (is_num) {
      x <- num(v); x <- x[!is.na(x)]
      n <- length(x)
      if (n >= 1) {
        q <- stats::quantile(x, c(0.25, 0.75), names = FALSE)
        iqr <- q[2] - q[1]
        lo <- q[1] - 1.5 * iqr; hi <- q[2] + 1.5 * iqr
        xv <- num(v)
        out_idx <- which(!is.na(xv) & (xv < lo | xv > hi))
        m <- mean(x); s <- if (n >= 2) stats::sd(x) else NA
        sk <- NA
        if (n >= 3 && !is.na(s) && s > 0) {
          z <- (x - m) / s
          sk <- sum(z^3) * n / ((n - 1) * (n - 2))
        }
        row$mean <- round(m, 4)
        row$sd <- fin(s)
        row$min <- round(min(x), 4)
        row$q1 <- round(q[1], 4)
        row$median <- round(stats::median(x), 4)
        row$q3 <- round(q[2], 4)
        row$max <- round(max(x), 4)
        row$iqr <- round(iqr, 4)
        row$skewness <- round(sk, 4)
        row$outliers <- length(out_idx)
        if (length(out_idx) > 0) {
          ex <- utils::head(out_idx, 3)
          row$outlier_examples <- paste(sprintf("%.6g (row %d)", xv[ex], ex), collapse = "; ")
          warn <- c(warn, sprintf("'%s' has %d possible outlier(s) (IQR rule), e.g. %.6g at row %d.", nm, length(out_idx), xv[ex[1]], ex[1]))
        }
        if (!is.na(s) && s == 0) {
          warn <- c(warn, sprintf("'%s' is constant (zero variance) - it cannot be used in analyses.", nm))
        }
        if (!is.na(sk) && abs(sk) > 2) {
          warn <- c(warn, sprintf("'%s' is heavily skewed (skewness = %.2f) - consider a transformation or non-parametric tests.", nm, sk))
        }
        id_like <- FALSE
        if (n_uniq == sum(!miss_idx) && sum(!miss_idx) >= 5) {
          if (!is_num) {
            id_like <- TRUE
          } else {
            if (length(x) > 0 && all(x == floor(x)) && all(x == seq_len(n_rows))) id_like <- TRUE
            if (grepl("(^|_)id$|^id_|(^|_)key$|(^|_)index$", tolower(nm))) id_like <- TRUE
          }
        }
        if (id_like) {
          warn <- c(warn, sprintf("'%s' looks like an ID column (all values unique) - exclude it from analyses.", nm))
        }
      }
    } else {
      lv <- unique(valid)
      row$levels <- length(lv)
      if (length(lv) >= 1) {
        tab <- table(valid)
        top <- names(sort(tab, decreasing = TRUE))[1]
        row$top_value <- sprintf("%s (%d)", top, tab[[top]])
        if (length(lv) == length(valid) && length(valid) >= 5) {
          warn <- c(warn, sprintf("'%s' looks like an ID column (all values unique) - exclude it from analyses.", nm))
        }
        rare <- sum(tab < 5)
        if (length(lv) >= 3 && rare >= 2) {
          warn <- c(warn, sprintf("'%s' has %d rare level(s) with fewer than 5 observations each.", nm, rare))
        }
        norm <- trimws(tolower(as.character(lv)))
        if (length(unique(norm)) < length(lv)) {
          warn <- c(warn, sprintf("'%s' has case/whitespace variants of the same level - consider cleaning.", nm))
        }
        nums <- suppressWarnings(as.numeric(valid))
        frac_num <- if (length(valid) > 0) mean(!is.na(nums)) else 0
        if (frac_num >= 0.5 && frac_num < 1) {
          warn <- c(warn, sprintf("'%s' looks numeric but contains non-numeric text - it will be treated as categorical.", nm))
        }
      }
    }
    rows[[length(rows) + 1]] <- row
  }

  list(title = sprintf("Dataset Profile - %d rows x %d columns", n_rows, n_cols),
       dims = list(rows = n_rows, cols = n_cols, duplicates = dup),
       table = rows,
       notes = warn)
}

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
    "plot"         = do_plot_analysis(df, variables, opts),
    "profile"      = do_profile(df, variables, opts),
    list(error = paste0("Unknown analysis type: ", analysis)))
  if (!is.null(result) && is.null(result$error)) {
    result <- attach_result_plots(result, df, variables, opts, analysis)
  }
  result
}, error = function(e) list(error = conditionMessage(e)))

cat(toJSON(out, auto_unbox = TRUE, na = "null", digits = 6))
