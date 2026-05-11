# 儿童维生素D与骨密度基线数据整理

## 项目目标

本项目按 `codex_R_data_cleaning_prompt.md` 的要求，将 `Data.xlsx` 中的多工作表样本医疗数据整理为可分析的基线数据库：一行代表一个孩子的一条基线记录。基线日期优先定义为首次血清 25(OH)D 检测日期；未检出 25(OH)D 的患儿保留占位记录，并在 `notes` 与日志中标记。

## 输入文件

- `Data.xlsx`：样本数据，含患者基础信息、就诊信息、实验室检查、病历、影像报告、处方/医嘱等工作表。
- `中国药师协会科研课题申报书模板 已盖章(1).pdf`：课题申报书，用于整理规则依据说明。
- `Paper1.pdf`：维生素D与骨密度相关参考文献，本阶段未作为主数据依据。

## 一键运行方式

安装 R 和所需 R 包后，可运行：

```r
source("R/01_clean_baseline_data.R")
source("R/02_generate_qc_tables.R")
```

当前电脑环境未检测到可用 `Rscript`，因此本轮已用等价本地生成流程写出结果文件；R 脚本已按交付要求保留，便于正式 R 环境复现。

## 输出文件说明

- `outputs/baseline_master.csv`、`outputs/baseline_master.xlsx`：脱敏后的主分析表，字段顺序与 Markdown 要求一致。
- `outputs/baseline_data_dictionary.xlsx`：数据字典，含 `variable_dictionary` 与 `coding_rules`。
- `outputs/lab_long_clean.csv`：清洗后的实验室长表，含结构化实验室数据和病历文本抽取的 25(OH)D。
- `outputs/asm_detail.csv`：抗癫痫发作药物明细；本样本仅识别到文本中的 ASM 线索。
- `outputs/bmd_detail.csv`：骨密度明细，儿童骨密度仅使用 Z 值或明确 Z 阈值文本。
- `outputs/qc_missingness.csv`：变量缺失情况。
- `outputs/qc_sample_counts.csv`：样本量流程表。
- `outputs/qc_variable_ranges.csv`：合理范围质控表。
- `outputs/original_column_inventory.csv`：原始工作表和列名清单。
- `outputs/id_mapping_internal_do_not_share.csv`：内部脱敏映射表，含原始患者编号，不应外发。
- `docs/analysis_basis.md`：每一步整理规则与申报书依据。
- `logs/data_cleaning_log.txt`：空表、无法抽取字段、R 环境限制等日志。

## 本次样本运行摘要

清洗完成。

- 进入 `baseline_master` 的患儿数：n = 12
- 癫痫儿童数：n = 3
- 普通儿童数：n = 9
- 有 25(OH)D：n = 2
- 有 BMD Z 值：n = 1
- 同时有 25(OH)D 和 BMD Z 值：n = 1
- 维生素D缺乏人数：n = 0
- 骨密度降低人数：n = 1

## 当前样本数据限制

- 结构化 `实验室检查_行级数据` 中未检出 25(OH)D，本轮 25(OH)D 来自出院记录/诊疗经过文本抽取。
- 多数患者缺少出生日期、身高、体重、癫痫分型、起病年龄、病程、发作频率、生活方式和膳食摄入字段。
- 部分骨密度信息仅为病历文本描述；1 例含 `Z≤-2.0` 阈值表达，正式数据应补充原始 DXA 报告精确 Z 值。
- 抗癫痫发作药物信息在样本中不完整，正式数据需要补充用药开始/结束日期、剂量、疗程和当前用药状态。

## 正式数据到位后重新运行

替换同名 `Data.xlsx` 后重新运行两段 R 命令即可。正式数据中若新增 sheet 或字段，脚本会继续输出列名清单和日志；需要人工复核新增字段是否应并入主表或数据字典。
