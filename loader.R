# loader.R - reads a CSV/Excel file (path from command-line arg), outputs JSON to stdout
args <- commandArgs(trailingOnly = TRUE)
path <- args[1]
if (is.na(path) || !file.exists(path)) {
  cat(toJSON(list(error = paste0("File not found: ", path)), auto_unbox = TRUE))
  quit(status = 1)
}
suppressPackageStartupMessages({
  library(jsonlite)
})
ext <- tolower(tools::file_ext(path))
if (ext %in% c("xlsx", "xls")) {
  suppressPackageStartupMessages(library(readxl))
  d <- tryCatch(readxl::read_excel(path), error = function(e) e)
} else {
  suppressPackageStartupMessages(library(readr))
  d <- tryCatch(readr::read_csv(path, show_col_types = FALSE, guess_max = 100000), error = function(e) e)
}
if (inherits(d, "error")) {
  cat(toJSON(list(error = conditionMessage(d)), auto_unbox = TRUE))
  quit(status = 1)
}
d[] <- lapply(d, function(x) { attr(x, "label") <- NULL; x })
cols <- names(d)
# as.list on a data frame row yields list-of-lists in jsonlite; flatten properly
records <- lapply(seq_len(nrow(d)), function(i) {
  row <- lapply(d[i, ], function(v) if (length(v) == 0) NA else unname(v))
  lapply(row, function(v) if (length(v) == 1) v[[1]] else v)
})
cat(toJSON(list(columns = cols, rows = records), auto_unbox = TRUE, na = "null", digits = NA))