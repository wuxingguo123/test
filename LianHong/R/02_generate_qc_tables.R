# 儿童维生素D与骨密度基线数据整理：质控表生成脚本
#
# 运行前应先运行 R/01_clean_baseline_data.R。当前实现复用同一套
# 可复核生成流程，并在运行后检查三张 QC 表是否存在。

options(encoding = "UTF-8")

log_file <- file.path("logs", "data_cleaning_log.txt")
append_log <- function(message) {
  line <- sprintf("[%s] %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), message)
  cat(line, "\n", file = log_file, append = TRUE)
}

find_python <- function() {
  candidates <- c(Sys.which("python"), Sys.which("python3"))
  candidates <- candidates[nzchar(candidates)]
  if (length(candidates) == 0) {
    stop("未找到 python/python3，无法重新生成 QC 表。", call. = FALSE)
  }
  candidates[[1]]
}

if (!file.exists(file.path("outputs", "baseline_master.csv"))) {
  stop("未找到 outputs/baseline_master.csv，请先运行 R/01_clean_baseline_data.R。", call. = FALSE)
}

generator <- file.path("tools", "generate_outputs.py")
if (!file.exists(generator)) {
  stop("未找到 tools/generate_outputs.py。", call. = FALSE)
}

append_log("开始运行 R/02_generate_qc_tables.R。")
status <- system2(find_python(), generator)
if (!identical(status, 0L)) {
  stop("QC 生成流程运行失败，请查看 logs/data_cleaning_log.txt。", call. = FALSE)
}

expected_qc <- c(
  file.path("outputs", "qc_missingness.csv"),
  file.path("outputs", "qc_sample_counts.csv"),
  file.path("outputs", "qc_variable_ranges.csv")
)
missing_qc <- expected_qc[!file.exists(expected_qc)]
if (length(missing_qc) > 0) {
  stop(sprintf("以下 QC 表缺失：%s", paste(missing_qc, collapse = ", ")), call. = FALSE)
}

append_log("R/02_generate_qc_tables.R 运行完成。")
message("QC 表生成完成。")
