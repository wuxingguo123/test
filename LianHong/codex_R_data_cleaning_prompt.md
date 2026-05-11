# 可直接复制到 Codex 的提示词：儿童维生素D与骨密度基线数据整理（R语言）

你现在是一个资深医学统计数据工程师和 R 语言开发者。请基于当前项目目录中的 `Data.xlsx` 样本数据，以及课题申报书 PDF，完成“儿童维生素D与骨密度基线数据库整理”的第一阶段工作。核心目标是把原始多工作表医疗数据整理成可分析的标准格式：**一行 = 一个孩子的一条基线记录**。如果同一孩子存在多次维生素D检测，当前阶段只保留第一次符合条件的血清 25(OH)D 检测作为基线时间点。

请以 R 语言为主完成，要求代码清晰、可复现、可扩展，能够在样本数据只有几行的情况下正常运行，也能适配后续正式大样本数据。

---

## 0. 输入文件与项目结构要求

### 0.1 输入文件
请自动识别或按以下路径读取：

- `Data.xlsx`：样本数据，包含多个工作表，可能包括但不限于：
  - `患者基本信息`
  - `就诊信息`
  - `门诊诊病历`
  - `病案基本信息`
  - `病案诊断_行级`
  - `药物治疗`
  - `住院非用医医嘱`
  - `门诊处方`
  - `实验室检查_行级数据`
  - `X射线报告`
  - `CT报告`
  - `磁共振报告`
  - `入院记录`
  - `出院记录`
- `中国药师协会科研课题申报书模板 已盖章(1)(1).pdf` 或项目目录中唯一的申报书 PDF。

如果文件名不同，请写自动查找逻辑：

- Excel：优先查找 `Data.xlsx`，否则查找目录下第一个 `.xlsx` 文件。
- PDF：优先查找文件名含“申报书”的 `.pdf` 文件。

### 0.2 输出目录
请自动创建以下目录：

```text
R/
outputs/
docs/
logs/
```

### 0.3 必须生成的文件
请至少生成以下文件：

```text
R/01_clean_baseline_data.R
R/02_generate_qc_tables.R
outputs/baseline_master.csv
outputs/baseline_master.xlsx
outputs/baseline_data_dictionary.xlsx
outputs/qc_missingness.csv
outputs/qc_sample_counts.csv
outputs/qc_variable_ranges.csv
outputs/lab_long_clean.csv
outputs/asm_detail.csv
outputs/bmd_detail.csv
docs/analysis_basis.md
logs/data_cleaning_log.txt
README.md
```

如某些字段在样本数据中无法提取，不要报错终止，应输出该字段为 `NA`，并在 `logs/data_cleaning_log.txt` 和 `docs/analysis_basis.md` 中记录“当前样本数据暂未提供/暂未识别”。

---

## 1. 总体原则

### 1.1 数据整理目标
把原始 Excel 多表整理为主分析表：

```text
outputs/baseline_master.csv
outputs/baseline_master.xlsx
```

主表必须满足：

```text
一行 = 一个孩子的一条基线记录
```

基线定义：

```text
baseline_date = 第一次符合条件的血清 25(OH)D 检测日期
```

如果某个孩子没有 25(OH)D 检测，则：

- 不能进入以维生素 D 为核心的基线主分析；
- 但可以在 QC 表中统计为“无 25(OH)D 检测记录”；
- 不要把无 25(OH)D 的孩子强行纳入 `baseline_master`，除非在代码开头设置 `include_no_vitd <- TRUE`。

### 1.2 脱敏原则
不得直接使用姓名、住院号、身份证号、健康卡号等作为分析 ID。

请根据原始 `患者编号` 生成脱敏编号：

```text
study_id = S000001, S000002, S000003 ...
```

同时保留内部映射文件：

```text
outputs/id_mapping_internal_do_not_share.csv
```

并在 README 中提醒：此映射文件含潜在可回溯信息，仅限本地质控使用，不得对外共享。

---

## 2. R 包要求

请优先使用以下 R 包：

```r
library(tidyverse)
library(readxl)
library(writexl)
library(janitor)
library(lubridate)
library(stringr)
library(digest)
library(glue)
library(openxlsx)
```

如果某个包未安装，请在脚本开头提供自动安装逻辑，但不要强制覆盖用户环境。

---

## 3. 原始数据读取与标准化

### 3.1 读取所有工作表
请读取 Excel 中所有 sheet，并建立命名列表：

```r
raw_sheets <- readxl::excel_sheets(path) |> set_names() |> map(~ readxl::read_excel(path, sheet = .x))
```

### 3.2 列名清理
保留原始中文列名，同时建立一个列名映射表：

```text
outputs/original_column_inventory.csv
```

字段包括：

- sheet_name
- original_colname
- cleaned_colname
- inferred_meaning

不要直接把所有列名改成难以识别的英文，关键表内部可以先保留中文列名，后续输出主表使用标准英文变量名。

### 3.3 安全取表函数
写一个函数：

```r
get_sheet <- function(raw_sheets, sheet_name) { ... }
```

如果 sheet 不存在，返回空 tibble 并写入日志。

---

## 4. 主表字段：必须输出的标准变量

请在 `baseline_master` 中输出以下字段。即使样本数据没有对应字段，也必须创建该列并填 `NA`。

### 4.1 基础信息字段

| 输出字段 | 含义 | 主要来源建议 |
|---|---|---|
| study_id | 脱敏编号 | 由患者编号生成 |
| source_patient_id_hash | 患者编号哈希 | digest，不输出原始编号 |
| group | 分组：普通儿童/癫痫儿童 | 诊断、病历、药物综合判断 |
| sex | 男/女 | 患者基本信息 |
| birth_date | 出生日期 | 病案基本信息，必要时从年龄反推则标记 |
| visit_date | 基线就诊日期 | 与 baseline_date 最近的就诊日期，或 baseline_date |
| baseline_date | 基线日期 | 第一次 25(OH)D 检测日期 |
| age_year | 基线年龄，单位岁 | `(baseline_date - birth_date)/365.25`；或年龄换算天数/365.25 |
| age_group | 年龄分组 | `<1岁`, `1–3岁`, `4–6岁`, `7–12岁`, `13–18岁` |
| height | 身高 cm | 门诊病历/入院记录/结构化字段/文本抽取 |
| weight | 体重 kg | 门诊病历/入院记录/结构化字段/文本抽取 |
| BMI | BMI kg/m2 | `weight/(height/100)^2` |
| season | 检测季节 | 根据 baseline_date 月份生成 |

年龄分组规则：

```r
case_when(
  age_year < 1 ~ "<1岁",
  age_year >= 1 & age_year < 4 ~ "1–3岁",
  age_year >= 4 & age_year < 7 ~ "4–6岁",
  age_year >= 7 & age_year < 13 ~ "7–12岁",
  age_year >= 13 & age_year <= 18 ~ "13–18岁",
  TRUE ~ NA_character_
)
```

季节规则：

```r
case_when(
  month %in% c(3, 4, 5) ~ "春",
  month %in% c(6, 7, 8) ~ "夏",
  month %in% c(9, 10, 11) ~ "秋",
  month %in% c(12, 1, 2) ~ "冬",
  TRUE ~ NA_character_
)
```

### 4.2 实验室指标字段

| 输出字段 | 含义 | 主要来源建议 |
|---|---|---|
| vitd_25oh | 血清 25(OH)D，统一 ng/mL | 实验室检查_行级数据 |
| vitd_original_value | 原始维生素D结果 | 实验室检查_行级数据 |
| vitd_original_unit | 原始单位 | 实验室检查_行级数据 |
| vitd_unit | 统一后单位，固定为 ng/mL | 转换后 |
| calcium | 血钙 | 实验室检查_行级数据，取基线附近最近值 |
| phosphorus | 血磷 | 实验室检查_行级数据，取基线附近最近值 |
| ALP | 碱性磷酸酶 | 实验室检查_行级数据，取基线附近最近值 |
| PTH | 甲状旁腺激素 | 实验室检查_行级数据，取基线附近最近值 |
| test_date | 实验室检测日期 | 25(OH)D 检测日期 |
| lab_window_days | 骨代谢指标与 baseline_date 的时间差 | 绝对天数 |

维生素 D 单位统一：

```text
1 ng/mL = 2.5 nmol/L
如果原始单位是 nmol/L，则 ng/mL = nmol/L / 2.5
如果原始单位是 ng/mL，则保持原值
如果单位无法识别，保留原值到 vitd_original_value，vitd_25oh 设为 NA，并写入日志
```

实验室项目识别关键词：

```r
vitd_patterns <- c("25.*OH.*D", "25.*羟.*维生素.*D", "25羟维生素D", "25-羟基维生素D", "维生素D")
calcium_patterns <- c("血钙", "钙", "Ca")
phosphorus_patterns <- c("血磷", "磷", "P$", "Phos")
alp_patterns <- c("碱性磷酸酶", "ALP")
pth_patterns <- c("甲状旁腺激素", "PTH")
```

注意：`钙` 和 `磷` 的匹配要避免误匹配到“尿钙”“尿磷”等非血清项目。优先要求样本名称为“血清/静脉血/血液”，若样本类型无法判断，则保留但写入日志。

骨代谢指标选取规则：

```text
以 baseline_date 为中心，优先选择同一天检测值；
如果同一天没有，则选择距离 baseline_date 最近的结果；
默认允许窗口为 ±30 天；
如果没有 ±30 天结果，则保留 NA；
窗口参数写在脚本开头：lab_window_max_days <- 30
```

### 4.3 维生素 D 分组字段

必须生成：

| 输出字段 | 规则 |
|---|---|
| severe_vitd_deficiency | `vitd_25oh < 12` |
| vitd_deficiency | `vitd_25oh < 20` |
| vitd_insufficiency | `vitd_25oh >= 20 & vitd_25oh < 30` |
| vitd_sufficient | `vitd_25oh >= 30` |
| vitd_status3 | 缺乏/不足/充足 |
| vitd_status4 | 严重缺乏/缺乏/不足/充足 |

分组标准：

```r
vitd_status3 = case_when(
  vitd_25oh < 20 ~ "缺乏",
  vitd_25oh >= 20 & vitd_25oh < 30 ~ "不足",
  vitd_25oh >= 30 ~ "充足",
  TRUE ~ NA_character_
)

vitd_status4 = case_when(
  vitd_25oh < 12 ~ "严重缺乏",
  vitd_25oh >= 12 & vitd_25oh < 20 ~ "缺乏",
  vitd_25oh >= 20 & vitd_25oh < 30 ~ "不足",
  vitd_25oh >= 30 ~ "充足",
  TRUE ~ NA_character_
)
```

### 4.4 骨密度字段

| 输出字段 | 含义 | 主要来源建议 |
|---|---|---|
| bmd_date | 骨密度检测日期 | X射线报告/影像报告/骨密度相关报告 |
| bmd_site | 检测部位：腰椎/全身/股骨等 | 报告名称、检查部位、检查所见、检查结论 |
| bmd_value | 原始 BMD 值 | 文本抽取或结构化字段 |
| bmd_z | 骨密度 Z 值 | 文本抽取或结构化字段 |
| bmd_machine | 检测设备 | 若报告中有 DXA/双能X线信息则提取 |
| bmd_window_days | bmd_date 与 baseline_date 的时间差 | 绝对天数 |
| low_bmd | 是否低骨密度 | `bmd_z <= -2.0` |

骨密度检测筛选关键词：

```r
bmd_report_patterns <- c("骨密度", "BMD", "DXA", "DEXA", "双能", "腰椎", "全身", "股骨")
```

Z 值抽取建议正则：

```r
z_regex <- "(?i)(Z\\s*[-_ ]?(score|值)?\\s*[:：=]?\\s*)([-+]?\\d+(\\.\\d+)?)"
```

也要兼容中文写法：

```r
z_regex_cn <- "Z值\\s*[:：=]?\\s*([-+]?\\d+(\\.\\d+)?)"
```

骨密度基线匹配规则：

```text
优先选择 bmd_date 与 baseline_date 相差 ≤30 天的检查；
如果没有，可在 bmd_window_fallback_days <- 90 下选择最近一次，并标记 bmd_window_flag = "fallback_90d"；
如果仍没有，则骨密度相关字段为 NA。
```

骨密度分组：

```r
low_bmd = case_when(
  !is.na(bmd_z) & bmd_z <= -2.0 ~ 1L,
  !is.na(bmd_z) & bmd_z > -2.0 ~ 0L,
  TRUE ~ NA_integer_
)

bmd_status = case_when(
  low_bmd == 1L ~ "骨密度降低",
  low_bmd == 0L ~ "正常",
  TRUE ~ NA_character_
)
```

儿童骨密度只使用 Z 值作为核心判定；如果报告只有 T 值，不得用 T 值替代 Z 值，应记录为“无可用 Z 值”。

### 4.5 癫痫儿童专属字段

这部分普通儿童允许为 NA，但字段必须存在。

| 输出字段 | 含义 | 来源建议 |
|---|---|---|
| epilepsy_type | 癫痫类型 | 病案诊断、入院记录、出院记录、门诊病历文本抽取 |
| seizure_type | 发作类型 | 病历文本抽取 |
| onset_age | 起病年龄 | 病历文本抽取，无法识别则 NA |
| disease_duration | 病程 | 病历文本抽取或 baseline_age - onset_age |
| seizure_frequency | 发作频率 | 病历文本抽取 |
| ASM_name | 当前抗癫痫药物名称，合并字符串 | 药物治疗、门诊处方、出院用药 |
| ASM_number | 当前 ASM 种数 | 去重计数 |
| monotherapy | 单药/多药 | `ASM_number == 1` 为单药，`>=2` 为多药 |
| enzyme_inducing_ASM | 是否酶诱导型药物 | 药物名称字典匹配 |
| valproate | 是否使用丙戊酸 | 药物名称字典匹配 |
| topiramate | 是否使用托吡酯 | 药物名称字典匹配 |
| ASM_duration | 用药时间，月 | 最早 ASM 开始日期至 baseline_date |
| intellectual_disability | 是否智力障碍 | 诊断/病历文本关键词 |
| motor_disability | 是否运动障碍或躯体残疾 | 诊断/病历文本关键词 |
| activity_limited | 是否活动受限 | 病历文本关键词 |

癫痫分组判断：

```text
group = "癫痫儿童"，如果满足任一条件：
1. 诊断名称/诊断描述/入院诊断/出院诊断/门诊诊断含“癫痫”；
2. 病历文本含明确癫痫诊断；
3. 当前或既往药物中含明确抗癫痫发作药物，且诊断或病历中有癫痫相关信息。
否则 group = "普通儿童"。
```

抗癫痫药物字典至少包括：

```r
asm_dictionary <- tribble(
  ~drug_keyword, ~drug_class, ~enzyme_inducing, ~is_valproate, ~is_topiramate,
  "卡马西平", "ASM", TRUE, FALSE, FALSE,
  "苯妥英", "ASM", TRUE, FALSE, FALSE,
  "苯巴比妥", "ASM", TRUE, FALSE, FALSE,
  "扑米酮", "ASM", TRUE, FALSE, FALSE,
  "奥卡西平", "ASM", FALSE, FALSE, FALSE,
  "丙戊酸", "ASM", FALSE, TRUE, FALSE,
  "德巴金", "ASM", FALSE, TRUE, FALSE,
  "左乙拉西坦", "ASM", FALSE, FALSE, FALSE,
  "开浦兰", "ASM", FALSE, FALSE, FALSE,
  "拉莫三嗪", "ASM", FALSE, FALSE, FALSE,
  "托吡酯", "ASM", FALSE, FALSE, TRUE,
  "妥泰", "ASM", FALSE, FALSE, TRUE,
  "氯硝西泮", "ASM", FALSE, FALSE, FALSE,
  "地西泮", "ASM", FALSE, FALSE, FALSE,
  "咪达唑仑", "ASM", FALSE, FALSE, FALSE,
  "拉考沙胺", "ASM", FALSE, FALSE, FALSE,
  "吡仑帕奈", "ASM", FALSE, FALSE, FALSE,
  "唑尼沙胺", "ASM", FALSE, FALSE, FALSE,
  "加巴喷丁", "ASM", FALSE, FALSE, FALSE,
  "普瑞巴林", "ASM", FALSE, FALSE, FALSE,
  "氨己烯酸", "ASM", FALSE, FALSE, FALSE,
  "卢非酰胺", "ASM", FALSE, FALSE, FALSE,
  "乙琥胺", "ASM", FALSE, FALSE, FALSE
)
```

如果医生希望把奥卡西平或高剂量托吡酯按酶诱导相关处理，请把字典设计成可配置，并在文档中说明当前默认规则。

当前 ASM 判断规则：

```text
从 药物治疗 和 门诊处方 中抽取药物；
若医嘱开始时间 ≤ baseline_date 且 医嘱结束时间为空或 ≥ baseline_date，则认为是当前用药；
若处方没有结束日期，则以开方时间距 baseline_date 最近且不晚于 baseline_date 的处方作为当前用药候选；
如果样本缺少用药时间，则保守提取“曾用 ASM”，并在 asm_current_flag 中标记 uncertain。
```

输出 `outputs/asm_detail.csv`，一行 = 一个孩子一种 ASM，字段至少包括：

```text
study_id, drug_name_raw, drug_keyword, drug_class, drug_start_date, drug_end_date,
ASM_duration_month, enzyme_inducing, is_valproate, is_topiramate, current_at_baseline, source_sheet
```

---

## 5. 派生变量和质控变量

### 5.1 必须生成的质控变量

在 `baseline_master` 中增加：

```text
has_vitd
has_bmd_z
has_calcium
has_phosphorus
has_ALP
has_PTH
has_height_weight
is_age_eligible
baseline_source
lab_source_sheet
bmd_source_sheet
asm_source_sheet
```

### 5.2 异常值检查
生成 `outputs/qc_variable_ranges.csv`，至少检查：

| 变量 | 合理范围建议 |
|---|---|
| age_year | 0 到 18 |
| vitd_25oh | 0 到 150 ng/mL，超出标记 |
| height | 30 到 220 cm |
| weight | 1 到 200 kg |
| BMI | 8 到 60 |
| bmd_z | -6 到 6 |
| calcium | 根据单位先不强制删除，仅标记极端值 |
| phosphorus | 根据单位先不强制删除，仅标记极端值 |
| ALP | 儿童年龄差异大，只标记明显非数字或极端大值 |
| PTH | 标记非数字或极端大值 |

不要自动删除异常值，只在 QC 中标记。

### 5.3 缺失值表
生成 `outputs/qc_missingness.csv`：

```text
variable, n_missing, pct_missing
```

### 5.4 样本量流程表
生成 `outputs/qc_sample_counts.csv`，至少包括：

```text
原始患者数
有 25(OH)D 检测患者数
进入 baseline_master 患者数
癫痫儿童数
普通儿童数
有 BMD Z 值患者数
同时有 25(OH)D 和 BMD Z 值患者数
有完整基础信息患者数
有 ASM 信息癫痫儿童数
```

---

## 6. 数据字典

生成 `outputs/baseline_data_dictionary.xlsx`，至少包含两个 sheet：

### 6.1 `variable_dictionary`
字段：

```text
variable_name
variable_label
variable_type
unit
allowed_values
derivation_rule
source_sheet
source_column
analysis_role
basis_in_protocol
notes
```

### 6.2 `coding_rules`
记录所有分类变量编码：

```text
variable_name
code
meaning
rule
```

必须包含：

- sex
- group
- age_group
- season
- vitd_status3
- vitd_status4
- low_bmd
- bmd_status
- monotherapy
- enzyme_inducing_ASM
- valproate
- topiramate
- intellectual_disability
- motor_disability
- activity_limited

---

## 7. docs/analysis_basis.md 必须写清楚“每一步依据”

请生成 `docs/analysis_basis.md`，这是非常重要的交付物。它不是普通 README，而是记录每一步数据整理为什么这样做、对应开题报告/申报书哪一部分依据。

该文件必须使用中文撰写，结构如下：

```markdown
# 儿童维生素D与骨密度基线数据整理依据说明

## 1. 本阶段数据整理目标
说明本阶段目标是建立基线数据库，而不是进行最终干预效果分析。

## 2. 一行一个孩子一条基线记录的依据
说明申报书总体框架包括“基线评估-风险分层-分层监测-分层干预-长期随访-效果评价”，当前处于基线评估和横断面调查/模型开发阶段，因此主表采用一行一个患儿的基线记录。

## 3. 基线日期定义依据
说明以第一次符合条件的血清 25(OH)D 检测日期作为 baseline_date 的原因：申报书把血清 25(OH)D 作为通用初步监测和核心结局指标。

## 4. 基础信息字段依据
逐项说明 age, sex, height, weight, BMI, season 等字段的依据。

## 5. 实验室指标字段依据
逐项说明 25(OH)D、钙、磷、碱性磷酸酶、甲状旁腺激素的依据。

## 6. 骨密度字段依据
说明 DXA、腰椎/全身 BMD、儿科软件、Z 值，以及儿童不能用 T 值替代 Z 值。

## 7. 维生素D分组依据
说明 <20 ng/mL 定义为缺乏，20–<30 ng/mL 定义为不足，≥30 ng/mL 定义为充足；<12 ng/mL 作为严重缺乏扩展分层。

## 8. 骨密度分组依据
说明 BMD Z 值 ≤ -2.0 定义为骨密度降低/骨量减少。

## 9. 癫痫专属字段依据
说明癫痫类型、起病年龄、病程、发作频率、ASM 种类/数量/疗程、共病状态的依据。

## 10. 抗癫痫药物分组依据
说明酶诱导型 ASM、非酶诱导型 ASM、丙戊酸、托吡酯、单药、多药联合的依据。

## 11. 低/中/高风险初步分层依据
说明低风险、中风险、高风险字段如何构造，以及与申报书分层监测表的对应关系。

## 12. 数据质量控制依据
说明统一培训、双人录入、定期核查、逻辑校验等申报书数据质量要求如何转化为当前 QC 表。

## 13. 当前样本数据限制
逐条列出样本数据中缺少的字段、无法可靠抽取的字段、需要正式数据补充的字段。

## 14. 输出文件说明
列出每个输出文件的用途。
```

### 7.1 analysis_basis.md 必须覆盖的申报书依据
请在文档中引用或标注以下依据，使用“申报书第 X 页”形式：

1. 研究摘要中提出通过定期血清 25(OH)D、骨代谢指标及骨密度测定，评估维生素 D、骨密度、骨折、癫痫发作控制和生活质量等结局。
2. 立题依据中说明癫痫儿童是 VitD 缺乏和骨代谢紊乱高危人群，并且风险与长期 ASM、智力障碍、活动受限、日照不足等因素相关。
3. 立题依据中说明酶诱导型 ASM、丙戊酸、托吡酯、多药联合治疗与 VitD 或骨健康风险相关。
4. 研究目标中说明要整合人口学、癫痫类型、病程、发作频率、药物种类、数量、疗程、智力/躯体残疾，建立风险预测模型。
5. 研究内容中说明纳入标准为 1 月龄至 18 岁癫痫儿童，并列出排除标准。
6. 研究内容中说明总体框架为“基线评估-风险分层-分层监测-分层干预-长期随访-效果评价”。
7. 研究内容中说明基线横断面调查需要建立多维数据库，含人口学与生活方式、癫痫疾病特征、治疗因素、共病状态、核心结局指标。
8. 研究内容中说明核心结局指标包括血清 25(OH)D、钙、磷、碱性磷酸酶、甲状旁腺激素、腰椎及全身骨密度，并且 BMD 以 Z 值表示。
9. 研究方法中说明基线数据收集包括年龄、性别、身高、体重、BMI、日照时间、户外活动、膳食钙和维生素D摄入、癫痫类型、起病年龄、病程、发作频率、发作类型、ASM 种类/剂量/疗程/单药多药/既往用药史、共病、实验室检测、影像学评估。
10. 研究方法中说明多因素 Logistic 回归识别维生素 D 缺乏 `25(OH)D <20 ng/mL` 和骨密度降低 `Z 值 ≤ -2.0` 的独立危险因素。
11. 研究方法中说明风险分层：低风险无明确危险因素；中风险 1–2 个危险因素；高风险 ≥3 个危险因素，或酶诱导型 ASMs、多药联合、智力/躯体残疾。
12. 研究计划中说明 2026.06–2026.09 为准备与基线评估阶段，需要完成基线横断面调查、数据录入、初步分析和风险预测模型初版。
13. 可行性/风险控制中说明数据质量需要统一培训、双人录入、定期核查、逻辑校验。

不要写“根据常识”来替代申报书依据；每个关键规则都要能在申报书依据中找到出处。若某条规则来自本项目数据处理约定，而非申报书原文，请明确写为“项目数据处理约定”。

---

## 8. 初步风险分层变量

请在 `baseline_master` 中生成初步风险变量，供后续使用：

```text
risk_factor_count
risk_level_initial
```

可计入的危险因素：

```text
1. vitd_deficiency == 1
2. low_bmd == 1
3. enzyme_inducing_ASM == 1
4. valproate == 1
5. topiramate == 1
6. monotherapy == "多药"
7. disease_duration 较长；如果无明确阈值，暂不计入，记录为待定
8. intellectual_disability == 1
9. motor_disability == 1
10. activity_limited == 1
```

初步风险分层规则：

```r
risk_level_initial = case_when(
  group != "癫痫儿童" ~ NA_character_,
  enzyme_inducing_ASM == 1 | monotherapy == "多药" | intellectual_disability == 1 | motor_disability == 1 | risk_factor_count >= 3 ~ "高风险",
  risk_factor_count >= 1 & risk_factor_count <= 2 ~ "中风险",
  risk_factor_count == 0 ~ "低风险",
  TRUE ~ NA_character_
)
```

注意：正式模型前，这只是“规则型初步分层”，不是最终预测模型。请在文档中明确。

---

## 9. R 脚本实现要求

### 9.1 `R/01_clean_baseline_data.R`
此脚本完成：

1. 初始化目录与日志；
2. 读取 Excel；
3. 导出 sheet 与列名清单；
4. 建立脱敏 ID；
5. 清洗患者基础信息；
6. 清洗就诊信息；
7. 清洗实验室长表；
8. 识别 25(OH)D 并确定 baseline_date；
9. 提取 baseline 附近钙、磷、ALP、PTH；
10. 提取或构造身高、体重、BMI；
11. 识别癫痫诊断与癫痫相关字段；
12. 提取 ASM 用药明细并生成 `asm_detail.csv`；
13. 提取骨密度报告并生成 `bmd_detail.csv`；
14. 合并生成 `baseline_master`；
15. 生成维生素 D 分组、低骨密度、风险分层等派生变量；
16. 导出 CSV/XLSX。

### 9.2 `R/02_generate_qc_tables.R`
此脚本完成：

1. 读取 `baseline_master.csv`；
2. 生成缺失值表；
3. 生成样本量流程表；
4. 生成变量范围异常检查表；
5. 更新日志。

### 9.3 README.md
README 必须说明：

```text
1. 项目目标
2. 输入文件
3. 一键运行方式
4. 输出文件说明
5. 当前样本数据限制
6. 正式数据到位后如何重新运行
```

建议提供运行命令：

```r
source("R/01_clean_baseline_data.R")
source("R/02_generate_qc_tables.R")
```

---

## 10. 代码鲁棒性要求

请特别注意：

1. 样本数据只有几行，也必须能跑通。
2. 某 sheet 缺失时不能报错中断。
3. 某列缺失时不能报错中断。
4. 某字段无法抽取时输出 NA，并记录日志。
5. 所有日期解析必须兼容 Excel 日期、字符日期、POSIXct。
6. 所有数值解析必须兼容字符型数值，如 `"223.0000"`。
7. 中文列名和中文文本要保持 UTF-8 编码。
8. 维生素 D 单位必须统一为 ng/mL。
9. 儿童骨密度只使用 Z 值；不能用 T 值替代。
10. 不得删除异常值，只做 QC 标记。
11. 不得把同一孩子多次检测当成多个孩子。
12. 不得把姓名、住院号、健康卡号输出到主分析表。
13. 所有输出字段顺序要固定，便于后续统计分析。

---

## 11. `baseline_master` 推荐字段顺序

请按以下顺序输出：

```text
study_id
source_patient_id_hash
group
sex
birth_date
visit_date
baseline_date
test_date
age_year
age_group
height
weight
BMI
season
vitd_25oh
vitd_original_value
vitd_original_unit
vitd_unit
vitd_status3
vitd_status4
severe_vitd_deficiency
vitd_deficiency
vitd_insufficiency
vitd_sufficient
calcium
phosphorus
ALP
PTH
lab_window_days
bmd_date
bmd_site
bmd_value
bmd_z
bmd_machine
bmd_window_days
bmd_window_flag
low_bmd
bmd_status
epilepsy_type
seizure_type
onset_age
disease_duration
seizure_frequency
ASM_name
ASM_number
monotherapy
enzyme_inducing_ASM
valproate
topiramate
ASM_duration
intellectual_disability
motor_disability
activity_limited
risk_factor_count
risk_level_initial
has_vitd
has_bmd_z
has_calcium
has_phosphorus
has_ALP
has_PTH
has_height_weight
is_age_eligible
baseline_source
lab_source_sheet
bmd_source_sheet
asm_source_sheet
notes
```

---

## 12. 运行后请输出简短总结

完成后，请在终端或 README 中输出：

```text
清洗完成。
进入 baseline_master 的患儿数：n = X
癫痫儿童数：n = X
普通儿童数：n = X
有 25(OH)D：n = X
有 BMD Z 值：n = X
同时有 25(OH)D 和 BMD Z 值：n = X
维生素D缺乏人数：n = X
骨密度降低人数：n = X
输出文件位于 outputs/ 和 docs/。
```

---

## 13. 最终交付标准

请确保项目完成后：

1. `R/01_clean_baseline_data.R` 可以独立运行；
2. `R/02_generate_qc_tables.R` 可以在第一个脚本运行后独立运行；
3. `baseline_master.csv` 含所有指定字段；
4. `baseline_data_dictionary.xlsx` 记录所有变量含义、来源、编码和依据；
5. `analysis_basis.md` 逐条记录每一步整理规则与申报书依据；
6. `logs/data_cleaning_log.txt` 记录缺失 sheet、缺失字段、无法识别单位、无法提取骨密度 Z 值等问题；
7. 所有代码中关键处理步骤都有中文注释；
8. 不要进行正式统计建模，本阶段只做数据标准化、派生变量、质控表和依据文档。
