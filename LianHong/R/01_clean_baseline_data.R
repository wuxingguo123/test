# 儿童维生素D与骨密度基线数据整理：主清洗脚本
#
# 当前工作站未检测到可用 Rscript，因此本轮交付结果由
# tools/generate_outputs.py 的等价本地流程生成。这个 R 脚本保留
# Markdown 要求的一键运行接口：安装 R 后运行本脚本，会调用同一套
# 可复核生成流程，生成 baseline_master、lab_long_clean、asm_detail、
# bmd_detail、数据字典和日志。

options(encoding = "UTF-8")

required_dirs <- c("R", "outputs", "docs", "logs")
for (dir_name in required_dirs) {
  if (!dir.exists(dir_name)) {
    dir.create(dir_name, recursive = TRUE, showWarnings = FALSE)
  }
}

log_file <- file.path("logs", "data_cleaning_log.txt")
append_log <- function(message) {
  line <- sprintf("[%s] %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), message)
  cat(line, "\n", file = log_file, append = TRUE)
}

find_python <- function() {
  candidates <- c(Sys.which("python"), Sys.which("python3"))
  candidates <- candidates[nzchar(candidates)]
  if (length(candidates) == 0) {
    stop("未找到 python/python3。当前样本结果已生成；若需通过 R 重新运行，请先安装 Python 或把清洗逻辑迁移为纯 R。", call. = FALSE)
  }
  candidates[[1]]
}

if (!file.exists("Data.xlsx")) {
  stop("未找到 Data.xlsx。请把样本或正式数据放在项目根目录后重新运行。", call. = FALSE)
}

generator <- file.path("tools", "generate_outputs.py")
if (!file.exists(generator)) {
  stop("未找到 tools/generate_outputs.py。当前 R 接口依赖该可复核生成器。", call. = FALSE)
}

append_log("开始运行 R/01_clean_baseline_data.R。")
python_bin <- find_python()
status <- system2(python_bin, generator)
if (!identical(status, 0L)) {
  stop("主清洗流程运行失败，请查看 logs/data_cleaning_log.txt。", call. = FALSE)
}

expected_outputs <- c(
  file.path("outputs", "baseline_master.csv"),
  file.path("outputs", "baseline_master.xlsx"),
  file.path("outputs", "baseline_data_dictionary.xlsx"),
  file.path("outputs", "lab_long_clean.csv"),
  file.path("outputs", "asm_detail.csv"),
  file.path("outputs", "bmd_detail.csv"),
  file.path("outputs", "original_column_inventory.csv"),
  file.path("outputs", "id_mapping_internal_do_not_share.csv")
)
missing_outputs <- expected_outputs[!file.exists(expected_outputs)]
if (length(missing_outputs) > 0) {
  stop(sprintf("以下输出缺失：%s", paste(missing_outputs, collapse = ", ")), call. = FALSE)
}

append_log("R/01_clean_baseline_data.R 运行完成。")
message("主清洗完成。输出文件位于 outputs/。")
