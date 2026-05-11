from __future__ import annotations

import hashlib
import math
import re
import subprocess
from datetime import date, datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "Data.xlsx"
OUT = ROOT / "outputs"
DOCS = ROOT / "docs"
LOGS = ROOT / "logs"
for path in (OUT, DOCS, LOGS, ROOT / "R"):
    path.mkdir(exist_ok=True)

log_lines: list[str] = []


def log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_lines.append(f"[{stamp}] {message}")


def norm_id(value) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    try:
        num = float(text)
        if num.is_integer():
            return str(int(num))
    except Exception:
        pass
    return re.sub(r"\.0$", "", text)


def parse_date(value):
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.to_datetime(value).normalize()
    if isinstance(value, date):
        return pd.Timestamp(value).normalize()
    if isinstance(value, (int, float)) and 20000 < float(value) < 60000:
        return pd.to_datetime("1899-12-30") + pd.to_timedelta(float(value), unit="D")
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return pd.NaT
    text = text.replace("年", "-").replace("月", "-").replace("日", "")
    text = text.replace("/", "-").replace(".", "-")
    return pd.to_datetime(text, errors="coerce").normalize()


def date_str(value):
    if pd.isna(value):
        return pd.NA
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def num(value):
    if pd.isna(value):
        return math.nan
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    text = text.replace("≤", "").replace("≥", "").replace("<", "").replace(">", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else math.nan


def present(value) -> bool:
    if value is None or pd.isna(value):
        return False
    return str(value).strip() != ""


def first_present(*values):
    for value in values:
        if present(value):
            return value
    return pd.NA


def sex_value(value):
    if not present(value):
        return pd.NA
    text = str(value)
    if "男" in text:
        return "男"
    if "女" in text:
        return "女"
    return pd.NA


def patient_hash(pid: str) -> str:
    return hashlib.sha256(pid.encode("utf-8")).hexdigest()[:32]


def age_band(age):
    if not present(age):
        return pd.NA
    age = float(age)
    if age < 1:
        return "<1岁"
    if age < 4:
        return "1-3岁"
    if age < 7:
        return "4-6岁"
    if age < 13:
        return "7-12岁"
    if age <= 18:
        return "13-18岁"
    return pd.NA


def season(value):
    if pd.isna(value):
        return pd.NA
    month = pd.Timestamp(value).month
    if month in (3, 4, 5):
        return "春"
    if month in (6, 7, 8):
        return "夏"
    if month in (9, 10, 11):
        return "秋"
    return "冬"


def status3(value):
    if not present(value):
        return pd.NA
    value = float(value)
    if value < 20:
        return "缺乏"
    if value < 30:
        return "不足"
    return "充足"


def status4(value):
    if not present(value):
        return pd.NA
    value = float(value)
    if value < 12:
        return "严重缺乏"
    if value < 20:
        return "缺乏"
    if value < 30:
        return "不足"
    return "充足"


def unit_text(value):
    if not present(value):
        return pd.NA
    return str(value).strip()


xl = pd.ExcelFile(DATA)
sheets = {name: pd.read_excel(DATA, sheet_name=name, dtype=object) for name in xl.sheet_names}
log(f"读取 {DATA.name}：{len(sheets)} 个工作表。")
for name, frame in sheets.items():
    if frame.empty:
        log(f"工作表为空：{name}")

inventory = []
meaning_rules = [
    ("患者编号", "患者源编号"),
    ("就诊编号", "就诊源编号"),
    ("性别", "性别"),
    ("出生", "出生日期"),
    ("日期", "日期/时间"),
    ("时间", "日期/时间"),
    ("体重", "体重"),
    ("身高", "身高"),
    ("检验项目", "实验室项目"),
    ("定量结果", "实验室数值"),
    ("单位", "单位"),
    ("诊断", "诊断文本"),
    ("药品", "药物"),
    ("处方", "处方/医嘱"),
    ("报告", "检查/检验报告"),
]
for sheet_name, frame in sheets.items():
    for column in frame.columns:
        meaning = ""
        for key, label in meaning_rules:
            if key in str(column):
                meaning = label
                break
        inventory.append(
            {
                "sheet_name": sheet_name,
                "original_colname": str(column),
                "cleaned_colname": re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", str(column)).strip("_").lower(),
                "inferred_meaning": meaning,
            }
        )
pd.DataFrame(inventory).to_csv(OUT / "original_column_inventory.csv", index=False, encoding="utf-8-sig")

patient_ids: set[str] = set()
for frame in sheets.values():
    if "患者编号" in frame.columns:
        patient_ids.update(pid for pid in frame["患者编号"].map(norm_id).dropna())
patients = sorted(patient_ids, key=lambda x: int(x) if x.isdigit() else x)
id_map = pd.DataFrame(
    {
        "source_patient_id": patients,
        "study_id": [f"S{i:06d}" for i in range(1, len(patients) + 1)],
        "source_patient_id_hash": [patient_hash(pid) for pid in patients],
    }
)
id_map.to_csv(OUT / "id_mapping_internal_do_not_share.csv", index=False, encoding="utf-8-sig")
study_id = dict(zip(id_map.source_patient_id, id_map.study_id))
hash_id = dict(zip(id_map.source_patient_id, id_map.source_patient_id_hash))
log(f"发现原始患者数：{len(patients)}。")

texts = []
date_candidates = {pid: [] for pid in patients}
sex_by_pid = {}
birth_by_pid = {}
age_days_by_pid = {}
height_by_pid = {}
weight_by_pid = {}
height_source = {}
weight_source = {}

for sheet_name, frame in sheets.items():
    if "患者编号" not in frame.columns:
        continue
    for idx, row in frame.iterrows():
        pid = norm_id(row.get("患者编号"))
        if not pid:
            continue
        sex_by_pid[pid] = first_present(sex_by_pid.get(pid), sex_value(row.get("性别")), sex_value(row.get("性别名称")))
        if not present(birth_by_pid.get(pid)):
            bd = parse_date(row.get("出生日期")) if "出生日期" in row.index else pd.NaT
            if not pd.isna(bd):
                birth_by_pid[pid] = bd
        for col in ("年龄换算（天）", "就诊时年龄（天）"):
            if col in row.index and not present(age_days_by_pid.get(pid)):
                value = num(row.get(col))
                if not math.isnan(value):
                    age_days_by_pid[pid] = value
        for col in row.index:
            if "日期" in str(col) or "时间" in str(col):
                dt = parse_date(row.get(col))
                if not pd.isna(dt):
                    date_candidates[pid].append((dt, sheet_name, str(col)))
        for col in ("入院记录身高", "身高"):
            if col in row.index and not present(height_by_pid.get(pid)):
                value = num(row.get(col))
                if not math.isnan(value):
                    height_by_pid[pid] = value
                    height_source[pid] = f"{sheet_name}.{col}"
        for col in ("入院记录体重", "体重"):
            if col in row.index and not present(weight_by_pid.get(pid)):
                value = num(row.get(col))
                if not math.isnan(value):
                    weight_by_pid[pid] = value
                    weight_source[pid] = f"{sheet_name}.{col}"
        row_date = pd.NaT
        for col in row.index:
            if "日期" in str(col) or "时间" in str(col):
                dt = parse_date(row.get(col))
                if not pd.isna(dt):
                    row_date = dt
                    break
        for col, value in row.items():
            if isinstance(value, str) and value.strip():
                texts.append(
                    {
                        "pid": pid,
                        "sheet": sheet_name,
                        "column": str(col),
                        "row_number": idx + 2,
                        "row_date": row_date,
                        "text": value,
                    }
                )

for record in texts:
    pid = record["pid"]
    text = record["text"]
    if not present(sex_by_pid.get(pid)):
        if re.search(r"患儿[，,]?男|男性", text):
            sex_by_pid[pid] = "男"
        elif re.search(r"患儿[，,]?女|女性", text):
            sex_by_pid[pid] = "女"
    if not present(height_by_pid.get(pid)):
        match = re.search(r"(?:身高|身长)[:：]?\s*(\d+(?:\.\d+)?)\s*cm", text, re.I)
        if match:
            height_by_pid[pid] = float(match.group(1))
            height_source[pid] = f"{record['sheet']}.{record['column']}文本"
    if not present(weight_by_pid.get(pid)):
        match = re.search(r"体重[:：]?\s*(\d+(?:\.\d+)?)\s*kg", text, re.I)
        if match:
            weight_by_pid[pid] = float(match.group(1))
            weight_source[pid] = f"{record['sheet']}.{record['column']}文本"

lab_rows = []
lab = sheets.get("实验室检查_行级数据", pd.DataFrame())
if not lab.empty and "患者编号" in lab.columns:
    for _, row in lab.iterrows():
        pid = norm_id(row.get("患者编号"))
        if not pid:
            continue
        item = str(row.get("检验项目名称", "") or "")
        report = str(row.get("报告名称", "") or "")
        sample = str(row.get("样本名称", "") or "")
        value = num(row.get("检验定量结果"))
        unit = unit_text(row.get("检验定量结果单位"))
        dt = parse_date(row.get("检验时间"))
        combined = item + " " + report
        kind = pd.NA
        if re.search(r"25.*OH.*D|25.*羟.*维生素.*D|25羟维生素D|25-羟基维生素D|维生素\s*D", combined, re.I):
            kind = "vitd_25oh"
        elif re.search(r"^(血钙|总钙|钙离子|钙|Ca)$", item, re.I) and "尿" not in item:
            kind = "calcium"
        elif re.search(r"^(血磷|磷|P|Phos)$", item, re.I) and "尿" not in item:
            kind = "phosphorus"
        elif re.search(r"碱性磷酸酶|ALP", item, re.I):
            kind = "ALP"
        elif re.search(r"甲状旁腺激素|PTH", item, re.I):
            kind = "PTH"
        lab_rows.append(
            {
                "pid": pid,
                "study_id": study_id[pid],
                "source_patient_id_hash": hash_id[pid],
                "source_sheet": "实验室检查_行级数据",
                "source_column": "检验项目名称/检验定量结果",
                "test_date": dt,
                "sample_name": sample,
                "report_name": report,
                "item_name": item,
                "original_value": row.get("检验定量结果"),
                "numeric_value": value if not math.isnan(value) else pd.NA,
                "original_unit": unit,
                "standardized_kind": kind,
                "standardized_value": pd.NA,
                "standardized_unit": pd.NA,
                "raw_text_excerpt": pd.NA,
            }
        )

vitd_re = re.compile(
    r"((?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2})[^。；;\n]{0,120}?"
    r"(?:25\s*\(?OH\)?\s*D|维生素\s*D)[^0-9<>≤≥]{0,20}"
    r"([<>≤≥]?\s*\d+(?:\.\d+)?)\s*\(?\s*(ng\s*/?\s*ml|ng\s*/?\s*mL|nmol\s*/?\s*L)?",
    re.I,
)
text_vitd = []
for record in texts:
    for match in vitd_re.finditer(record["text"]):
        value = num(match.group(2))
        unit = (match.group(3) or "ng/mL").replace(" ", "")
        if re.search(r"nmol/?L", unit, re.I):
            std = value / 2.5
        elif re.search(r"ng/?m[lL]", unit, re.I):
            std = value
        else:
            std = math.nan
            log(f"无法识别维生素D单位：患者 {record['pid']}，单位 {unit}。")
        text_vitd.append(
            {
                "pid": record["pid"],
                "study_id": study_id[record["pid"]],
                "source_patient_id_hash": hash_id[record["pid"]],
                "source_sheet": record["sheet"],
                "source_column": record["column"],
                "test_date": parse_date(match.group(1)),
                "sample_name": pd.NA,
                "report_name": "文本抽取",
                "item_name": "维生素D",
                "original_value": match.group(2).replace(" ", ""),
                "numeric_value": value,
                "original_unit": unit,
                "standardized_kind": "vitd_25oh",
                "standardized_value": std if not math.isnan(std) else pd.NA,
                "standardized_unit": "ng/mL" if not math.isnan(std) else pd.NA,
                "raw_text_excerpt": record["text"][max(0, match.start() - 40) : min(len(record["text"]), match.end() + 60)].replace("\n", " "),
            }
        )


def segment_for_date(text: str, dt):
    if pd.isna(dt):
        return ""
    ds = pd.Timestamp(dt).strftime("%Y-%m-%d")
    start = text.find(ds)
    if start < 0:
        return ""
    next_date = re.search(r"(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}", text[start + 10 :])
    end = start + 10 + next_date.start() if next_date else min(len(text), start + 500)
    return text[start:end]


def segments_for_date(text: str, dt):
    if pd.isna(dt):
        return []
    ds = pd.Timestamp(dt).strftime("%Y-%m-%d")
    segments = []
    for hit in re.finditer(re.escape(ds), text):
        start = hit.start()
        next_date = re.search(r"(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}", text[start + 10 :])
        end = start + 10 + next_date.start() if next_date else min(len(text), start + 500)
        segments.append(text[start:end])
    return segments


for vitd in text_vitd:
    for record in texts:
        if record["pid"] != vitd["pid"]:
            continue
        same_day_segments = segments_for_date(record["text"], vitd["test_date"])
        if not same_day_segments:
            continue
        patterns = {
            "calcium": r"(?:总钙|血钙|钙离子|(?<!尿)钙)[:：]?\s*([<>≤≥]?\s*\d+(?:\.\d+)?)\s*\(?\s*([A-Za-zμu/]+)?",
            "phosphorus": r"(?:血磷|(?<!尿)磷)[:：]?\s*([<>≤≥]?\s*\d+(?:\.\d+)?)\s*\(?\s*([A-Za-zμu/]+)?",
            "ALP": r"(?:碱性磷酸酶|ALP)[:：]?\s*([<>≤≥]?\s*\d+(?:\.\d+)?)\s*\(?\s*([A-Za-zμu/]+)?",
            "PTH": r"(?:甲状旁腺激素|PTH)[:：]?\s*([<>≤≥]?\s*\d+(?:\.\d+)?)\s*\(?\s*([A-Za-zμu/]+)?",
        }
        for seg in same_day_segments:
            for kind, pattern in patterns.items():
                match = re.search(pattern, seg, re.I)
                if match:
                    lab_rows.append(
                        {
                            "pid": vitd["pid"],
                            "study_id": study_id[vitd["pid"]],
                            "source_patient_id_hash": hash_id[vitd["pid"]],
                            "source_sheet": record["sheet"],
                            "source_column": record["column"],
                            "test_date": vitd["test_date"],
                            "sample_name": pd.NA,
                            "report_name": "文本抽取",
                            "item_name": kind,
                            "original_value": match.group(1).replace(" ", ""),
                            "numeric_value": num(match.group(1)),
                            "original_unit": unit_text(match.group(2)),
                            "standardized_kind": kind,
                            "standardized_value": num(match.group(1)),
                            "standardized_unit": unit_text(match.group(2)),
                            "raw_text_excerpt": seg[:300].replace("\n", " "),
                        }
                    )

lab_long = pd.DataFrame(lab_rows + text_vitd)
if lab_long.empty:
    lab_long = pd.DataFrame(
        columns=[
            "pid",
            "study_id",
            "source_patient_id_hash",
            "source_sheet",
            "source_column",
            "test_date",
            "sample_name",
            "report_name",
            "item_name",
            "original_value",
            "numeric_value",
            "original_unit",
            "standardized_kind",
            "standardized_value",
            "standardized_unit",
            "raw_text_excerpt",
        ]
    )
for idx, row in lab_long.iterrows():
    if str(row.get("standardized_kind")) == "vitd_25oh" and not present(row.get("standardized_value")):
        value = num(row.get("numeric_value"))
        unit = str(row.get("original_unit") or "")
        if not math.isnan(value):
            if re.search(r"nmol/?L", unit, re.I):
                lab_long.at[idx, "standardized_value"] = value / 2.5
                lab_long.at[idx, "standardized_unit"] = "ng/mL"
            elif re.search(r"ng/?m[lL]", unit, re.I):
                lab_long.at[idx, "standardized_value"] = value
                lab_long.at[idx, "standardized_unit"] = "ng/mL"
lab_long = lab_long.drop_duplicates(
    subset=["pid", "test_date", "standardized_kind", "standardized_value", "original_value", "original_unit"]
)
lab_export = lab_long.drop(columns=["pid"], errors="ignore").copy()
lab_export["test_date"] = lab_export["test_date"].map(date_str)
lab_export.to_csv(OUT / "lab_long_clean.csv", index=False, encoding="utf-8-sig")

vitd_candidates = lab_long[lab_long["standardized_kind"].eq("vitd_25oh") & lab_long["standardized_value"].notna()].copy()
first_vitd = (
    vitd_candidates.sort_values(["pid", "test_date"]).drop_duplicates(subset=["pid"], keep="first")
    if not vitd_candidates.empty
    else pd.DataFrame(columns=lab_long.columns)
)
log(f"识别到有 25(OH)D 的患者数：{first_vitd['pid'].nunique() if not first_vitd.empty else 0}。")
if not lab.empty:
    structured_vitd = lab.apply(lambda row: bool(re.search(r"25.*OH|25.*羟|维生素\s*D", " ".join(map(str, row.values)), re.I)), axis=1)
    if not structured_vitd.any():
        log("结构化实验室长表未检出25(OH)D；样本中的维生素D来自出院/病程文本抽取。")

bmd_rows = []
for record in texts:
    text = record["text"]
    if not re.search(r"骨密度|BMD|双能", text, re.I):
        continue
    for match in re.finditer(r"((?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2})[^。；;\n]{0,220}?(?:骨密度|BMD|双能)[^。；;\n]{0,220}", text, re.I):
        seg = match.group(0)
        z = pd.NA
        low = pd.NA
        note = "无可用Z值"
        zmatch = re.search(r"Z\s*(?:值|score|评分)?\s*(?:≤|<=|=|:|：)?\s*(-?\d+(?:\.\d+)?)", seg, re.I)
        if zmatch:
            z = float(zmatch.group(1))
            low = 1 if z <= -2.0 or re.search(r"Z\s*(?:值)?\s*(?:≤|<=)", seg) else 0
            note = "文本抽取Z值；若原文为阈值表达，正式数据需补充精确值"
        site = "未说明"
        for keyword in ("腰椎", "全身", "股骨"):
            if keyword in seg:
                site = keyword
                break
        if present(low) and int(low) == 1:
            bmd_status_value = "骨密度降低"
        elif present(low) and int(low) == 0:
            bmd_status_value = "正常"
        else:
            bmd_status_value = pd.NA
        bmd_rows.append(
            {
                "pid": record["pid"],
                "study_id": study_id[record["pid"]],
                "source_patient_id_hash": hash_id[record["pid"]],
                "bmd_date": parse_date(match.group(1)),
                "bmd_site": site,
                "bmd_value": pd.NA,
                "bmd_z": z,
                "bmd_machine": "DXA/双能X线" if re.search(r"双能|DXA|DEXA", seg, re.I) else pd.NA,
                "low_bmd": low,
                "bmd_status": bmd_status_value,
                "source_sheet": record["sheet"],
                "source_column": record["column"],
                "raw_text_excerpt": seg.replace("\n", " ")[:500],
                "extraction_note": note,
            }
        )
    for term in re.finditer(r"骨密度|BMD", text, re.I):
        window_start = max(0, term.start() - 500)
        window_end = min(len(text), term.end() + 260)
        seg = text[window_start:window_end]
        prior_dates = list(re.finditer(r"(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}", seg[: term.start() - window_start]))
        if prior_dates:
            bmd_dt = parse_date(prior_dates[-1].group(0))
        else:
            bmd_dt = record["row_date"]
        z = pd.NA
        low = pd.NA
        note = "无可用Z值"
        zmatch = re.search(r"Z\s*(?:值|score|评分)?\s*(?:≤|<=|=|:|：)?\s*(-?\d+(?:\.\d+)?)", seg, re.I)
        if zmatch:
            z = float(zmatch.group(1))
            low = 1 if z <= -2.0 or re.search(r"Z\s*(?:值)?\s*(?:≤|<=)", seg) else 0
            note = "根据骨密度附近文本抽取Z值；若原文为阈值表达，正式数据需补充精确值"
        site = "未说明"
        for keyword in ("腰椎", "全身", "股骨"):
            if keyword in seg:
                site = keyword
                break
        if present(low) and int(low) == 1:
            bmd_status_value = "骨密度降低"
        elif present(low) and int(low) == 0:
            bmd_status_value = "正常"
        else:
            bmd_status_value = pd.NA
        bmd_rows.append(
            {
                "pid": record["pid"],
                "study_id": study_id[record["pid"]],
                "source_patient_id_hash": hash_id[record["pid"]],
                "bmd_date": bmd_dt,
                "bmd_site": site,
                "bmd_value": pd.NA,
                "bmd_z": z,
                "bmd_machine": "DXA/双能X线" if re.search(r"双能|DXA|DEXA", seg, re.I) else pd.NA,
                "low_bmd": low,
                "bmd_status": bmd_status_value,
                "source_sheet": record["sheet"],
                "source_column": record["column"],
                "raw_text_excerpt": seg.replace("\n", " ")[:500],
                "extraction_note": note,
            }
        )
bmd_detail = pd.DataFrame(bmd_rows)
if bmd_detail.empty:
    bmd_detail = pd.DataFrame(
        columns=[
            "pid",
            "study_id",
            "source_patient_id_hash",
            "bmd_date",
            "bmd_site",
            "bmd_value",
            "bmd_z",
            "bmd_machine",
            "low_bmd",
            "bmd_status",
            "source_sheet",
            "source_column",
            "raw_text_excerpt",
            "extraction_note",
        ]
    )
bmd_detail = bmd_detail.sort_values(["pid", "bmd_date", "bmd_z"], na_position="last")
bmd_detail = bmd_detail.drop_duplicates(subset=["pid", "bmd_date", "bmd_z", "low_bmd"], keep="first")
bmd_export = bmd_detail.drop(columns=["pid"], errors="ignore").copy()
bmd_export["bmd_date"] = bmd_export["bmd_date"].map(date_str)
bmd_export.to_csv(OUT / "bmd_detail.csv", index=False, encoding="utf-8-sig")

asm_dictionary = [
    ("卡马西平", True, False, False),
    ("苯妥英", True, False, False),
    ("苯巴比妥", True, False, False),
    ("扑米酮", True, False, False),
    ("奥卡西平", False, False, False),
    ("丙戊酸", False, True, False),
    ("德巴金", False, True, False),
    ("左乙拉西坦", False, False, False),
    ("开浦兰", False, False, False),
    ("拉莫三嗪", False, False, False),
    ("托吡酯", False, False, True),
    ("妥泰", False, False, True),
    ("氯硝西泮", False, False, False),
    ("地西泮", False, False, False),
    ("咪达唑仑", False, False, False),
    ("拉考沙胺", False, False, False),
    ("吡仑帕奈", False, False, False),
    ("唑尼沙胺", False, False, False),
    ("加巴喷丁", False, False, False),
    ("普瑞巴林", False, False, False),
    ("氨己烯酸", False, False, False),
    ("卢非酰胺", False, False, False),
    ("乙琥胺", False, False, False),
]
asm_rows = []
for sheet_name, name_cols, start_col, end_col in [
    ("药物治疗", ["药品名称（归一化）", "药品名称"], "医嘱开始时间", "医嘱结束时间"),
    ("门诊处方", ["处方名称"], "开方时间", None),
]:
    frame = sheets.get(sheet_name, pd.DataFrame())
    if frame.empty or "患者编号" not in frame.columns:
        continue
    for _, row in frame.iterrows():
        pid = norm_id(row.get("患者编号"))
        if not pid:
            continue
        raw_name = " ".join(str(row.get(col, "")) for col in name_cols if present(row.get(col)))
        for keyword, enzyme, valproate, topiramate in asm_dictionary:
            if keyword in raw_name:
                asm_rows.append(
                    {
                        "pid": pid,
                        "study_id": study_id[pid],
                        "drug_name_raw": raw_name,
                        "drug_keyword": keyword,
                        "drug_class": "ASM",
                        "drug_start_date": parse_date(row.get(start_col)) if start_col else pd.NaT,
                        "drug_end_date": parse_date(row.get(end_col)) if end_col else pd.NaT,
                        "ASM_duration_month": pd.NA,
                        "enzyme_inducing": int(enzyme),
                        "is_valproate": int(valproate),
                        "is_topiramate": int(topiramate),
                        "current_at_baseline": "uncertain",
                        "source_sheet": sheet_name,
                    }
                )
for record in texts:
    for keyword, enzyme, valproate, topiramate in asm_dictionary:
        if keyword in record["text"]:
            asm_rows.append(
                {
                    "pid": record["pid"],
                    "study_id": study_id[record["pid"]],
                    "drug_name_raw": keyword,
                    "drug_keyword": keyword,
                    "drug_class": "ASM",
                    "drug_start_date": pd.NaT,
                    "drug_end_date": pd.NaT,
                    "ASM_duration_month": pd.NA,
                    "enzyme_inducing": int(enzyme),
                    "is_valproate": int(valproate),
                    "is_topiramate": int(topiramate),
                    "current_at_baseline": "uncertain",
                    "source_sheet": f"{record['sheet']}.{record['column']}文本",
                }
            )
asm_detail = pd.DataFrame(asm_rows)
asm_cols = [
    "study_id",
    "drug_name_raw",
    "drug_keyword",
    "drug_class",
    "drug_start_date",
    "drug_end_date",
    "ASM_duration_month",
    "enzyme_inducing",
    "is_valproate",
    "is_topiramate",
    "current_at_baseline",
    "source_sheet",
]
if asm_detail.empty:
    asm_detail = pd.DataFrame(columns=["pid"] + asm_cols)
    log("未识别到抗癫痫发作药物字典项；asm_detail.csv 保留表头。")
else:
    asm_detail = asm_detail.drop_duplicates(subset=["pid", "drug_keyword", "source_sheet"])
    asm_detail["drug_start_date"] = asm_detail["drug_start_date"].map(date_str)
    asm_detail["drug_end_date"] = asm_detail["drug_end_date"].map(date_str)
asm_detail.drop(columns=["pid"], errors="ignore")[asm_cols].to_csv(OUT / "asm_detail.csv", index=False, encoding="utf-8-sig")

epilepsy_pids = set()
intellectual = {pid: 0 for pid in patients}
motor = {pid: 0 for pid in patients}
activity = {pid: 0 for pid in patients}
for record in texts:
    pid = record["pid"]
    text = record["text"]
    if "癫痫" in text:
        epilepsy_pids.add(pid)
    if re.search(r"智力发育落后|智力障碍|智力低下|精神发育迟滞", text):
        intellectual[pid] = 1
    if re.search(r"运动障碍|躯体残疾|肢体残疾|脑瘫|瘫痪", text):
        motor[pid] = 1
    if re.search(r"活动受限|卧床|不能行走|行走困难", text):
        activity[pid] = 1
if "pid" in asm_detail:
    epilepsy_pids.update(pid for pid in asm_detail["pid"].dropna())


def nearest_visit(pid, baseline):
    candidates = [(dt, sh, col) for dt, sh, col in date_candidates.get(pid, []) if "出生" not in col]
    if not candidates:
        return pd.NaT, pd.NA
    if not pd.isna(baseline):
        candidates.sort(key=lambda item: abs((pd.Timestamp(item[0]) - pd.Timestamp(baseline)).days))
    else:
        candidates.sort(key=lambda item: pd.Timestamp(item[0]))
    dt, sh, col = candidates[0]
    return dt, f"{sh}.{col}"


field_order = """
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
""".strip().splitlines()

master_rows = []
for pid in patients:
    fv = first_vitd[first_vitd["pid"].eq(pid)] if not first_vitd.empty else pd.DataFrame()
    has_vitd = 0 if fv.empty else 1
    baseline = pd.NaT if fv.empty else fv.iloc[0]["test_date"]
    vitd_value = pd.NA if fv.empty else float(fv.iloc[0]["standardized_value"])
    visit_dt, _ = nearest_visit(pid, baseline)
    birth = birth_by_pid.get(pid, pd.NaT)
    if not pd.isna(baseline) and not pd.isna(birth):
        age = round((pd.Timestamp(baseline) - pd.Timestamp(birth)).days / 365.25, 2)
    elif present(age_days_by_pid.get(pid)):
        age = round(float(age_days_by_pid[pid]) / 365.25, 2)
    else:
        age = pd.NA
    height = height_by_pid.get(pid, pd.NA)
    weight = weight_by_pid.get(pid, pd.NA)
    bmi = pd.NA
    if present(height) and present(weight) and float(height) > 0:
        bmi = round(float(weight) / ((float(height) / 100) ** 2), 2)

    labs = {}
    lab_window = pd.NA
    for kind in ("calcium", "phosphorus", "ALP", "PTH"):
        subset = lab_long[lab_long["pid"].eq(pid) & lab_long["standardized_kind"].eq(kind)].copy()
        if subset.empty or pd.isna(baseline):
            labs[kind] = pd.NA
            continue
        subset["window"] = subset["test_date"].apply(lambda dt: abs((pd.Timestamp(dt) - pd.Timestamp(baseline)).days) if not pd.isna(dt) else 999999)
        subset = subset[subset["window"] <= 30].sort_values("window")
        if subset.empty:
            labs[kind] = pd.NA
        else:
            labs[kind] = subset.iloc[0]["standardized_value"]
            lab_window = int(subset.iloc[0]["window"]) if pd.isna(lab_window) else max(int(lab_window), int(subset.iloc[0]["window"]))

    bmd_vals = {
        "bmd_date": pd.NaT,
        "bmd_site": pd.NA,
        "bmd_value": pd.NA,
        "bmd_z": pd.NA,
        "bmd_machine": pd.NA,
        "bmd_window_days": pd.NA,
        "bmd_window_flag": pd.NA,
        "low_bmd": pd.NA,
        "bmd_status": pd.NA,
        "bmd_source": pd.NA,
    }
    bmd_subset = bmd_detail[bmd_detail["pid"].eq(pid)].copy()
    if not bmd_subset.empty and not pd.isna(baseline):
        bmd_subset["window"] = bmd_subset["bmd_date"].apply(lambda dt: abs((pd.Timestamp(dt) - pd.Timestamp(baseline)).days) if not pd.isna(dt) else 999999)
        bmd_subset = bmd_subset.sort_values("window")
        use = bmd_subset[bmd_subset["window"] <= 30]
        flag = "within_30d"
        if use.empty:
            use = bmd_subset[bmd_subset["window"] <= 90]
            flag = "fallback_90d"
        if not use.empty:
            row = use.iloc[0]
            bmd_vals.update(
                {
                    "bmd_date": row["bmd_date"],
                    "bmd_site": row["bmd_site"],
                    "bmd_value": row["bmd_value"],
                    "bmd_z": row["bmd_z"],
                    "bmd_machine": row["bmd_machine"],
                    "bmd_window_days": int(row["window"]),
                    "bmd_window_flag": flag,
                    "low_bmd": row["low_bmd"],
                    "bmd_status": row["bmd_status"],
                    "bmd_source": row["source_sheet"],
                }
            )

    asm_subset = asm_detail[asm_detail["pid"].eq(pid)].copy() if "pid" in asm_detail else pd.DataFrame()
    if asm_subset.empty:
        asm_name = pd.NA
        asm_number = 0
        monotherapy = pd.NA
        enzyme = valproate = topiramate = 0
        asm_source = pd.NA
    else:
        asm_name = "; ".join(sorted(asm_subset["drug_keyword"].dropna().unique()))
        asm_number = len(set(asm_subset["drug_keyword"].dropna()))
        monotherapy = "单药" if asm_number == 1 else ("多药" if asm_number >= 2 else pd.NA)
        enzyme = int(asm_subset["enzyme_inducing"].fillna(0).astype(int).max())
        valproate = int(asm_subset["is_valproate"].fillna(0).astype(int).max())
        topiramate = int(asm_subset["is_topiramate"].fillna(0).astype(int).max())
        asm_source = "; ".join(sorted(asm_subset["source_sheet"].dropna().unique()))

    group = "癫痫儿童" if pid in epilepsy_pids else "普通儿童"
    severe = 1 if has_vitd and vitd_value < 12 else (0 if has_vitd else pd.NA)
    vitd_def = 1 if has_vitd and vitd_value < 20 else (0 if has_vitd else pd.NA)
    vitd_ins = 1 if has_vitd and 20 <= vitd_value < 30 else (0 if has_vitd else pd.NA)
    vitd_suf = 1 if has_vitd and vitd_value >= 30 else (0 if has_vitd else pd.NA)
    is_polytherapy = present(monotherapy) and monotherapy == "多药"
    factors = [
        vitd_def,
        bmd_vals["low_bmd"],
        enzyme,
        valproate,
        topiramate,
        1 if is_polytherapy else 0,
        intellectual[pid],
        motor[pid],
        activity[pid],
    ]
    risk_count = sum(1 for factor in factors if present(factor) and int(factor) == 1)
    if group != "癫痫儿童":
        risk_level = pd.NA
    elif enzyme == 1 or is_polytherapy or intellectual[pid] == 1 or motor[pid] == 1 or risk_count >= 3:
        risk_level = "高风险"
    elif risk_count >= 1:
        risk_level = "中风险"
    else:
        risk_level = "低风险"

    notes = []
    if not has_vitd:
        notes.append("未检出25(OH)D，baseline_date保留为空")
    if pd.isna(birth):
        notes.append("缺少出生日期")
    if group == "癫痫儿童" and asm_number == 0:
        notes.append("有癫痫相关文本但未识别到ASM用药")
    if pid in set(bmd_detail.loc[bmd_detail["bmd_z"].isna(), "pid"]) and pd.isna(bmd_vals["bmd_z"]):
        notes.append("骨密度文本缺少可用Z值")

    master_rows.append(
        {
            "study_id": study_id[pid],
            "source_patient_id_hash": hash_id[pid],
            "group": group,
            "sex": sex_by_pid.get(pid, pd.NA),
            "birth_date": date_str(birth),
            "visit_date": date_str(visit_dt),
            "baseline_date": date_str(baseline),
            "test_date": date_str(baseline),
            "age_year": age,
            "age_group": age_band(age),
            "height": height,
            "weight": weight,
            "BMI": bmi,
            "season": season(baseline),
            "vitd_25oh": round(vitd_value, 3) if present(vitd_value) else pd.NA,
            "vitd_original_value": pd.NA if fv.empty else fv.iloc[0]["original_value"],
            "vitd_original_unit": pd.NA if fv.empty else fv.iloc[0]["original_unit"],
            "vitd_unit": "ng/mL" if has_vitd else pd.NA,
            "vitd_status3": status3(vitd_value),
            "vitd_status4": status4(vitd_value),
            "severe_vitd_deficiency": severe,
            "vitd_deficiency": vitd_def,
            "vitd_insufficiency": vitd_ins,
            "vitd_sufficient": vitd_suf,
            "calcium": labs["calcium"],
            "phosphorus": labs["phosphorus"],
            "ALP": labs["ALP"],
            "PTH": labs["PTH"],
            "lab_window_days": lab_window,
            "bmd_date": date_str(bmd_vals["bmd_date"]),
            "bmd_site": bmd_vals["bmd_site"],
            "bmd_value": bmd_vals["bmd_value"],
            "bmd_z": bmd_vals["bmd_z"],
            "bmd_machine": bmd_vals["bmd_machine"],
            "bmd_window_days": bmd_vals["bmd_window_days"],
            "bmd_window_flag": bmd_vals["bmd_window_flag"],
            "low_bmd": bmd_vals["low_bmd"],
            "bmd_status": bmd_vals["bmd_status"],
            "epilepsy_type": "未分型" if group == "癫痫儿童" else pd.NA,
            "seizure_type": pd.NA,
            "onset_age": pd.NA,
            "disease_duration": pd.NA,
            "seizure_frequency": pd.NA,
            "ASM_name": asm_name,
            "ASM_number": asm_number,
            "monotherapy": monotherapy,
            "enzyme_inducing_ASM": enzyme,
            "valproate": valproate,
            "topiramate": topiramate,
            "ASM_duration": pd.NA,
            "intellectual_disability": intellectual[pid] if group == "癫痫儿童" else pd.NA,
            "motor_disability": motor[pid] if group == "癫痫儿童" else pd.NA,
            "activity_limited": activity[pid] if group == "癫痫儿童" else pd.NA,
            "risk_factor_count": risk_count if group == "癫痫儿童" else pd.NA,
            "risk_level_initial": risk_level,
            "has_vitd": has_vitd,
            "has_bmd_z": 0 if pd.isna(bmd_vals["bmd_z"]) else 1,
            "has_calcium": 0 if pd.isna(labs["calcium"]) else 1,
            "has_phosphorus": 0 if pd.isna(labs["phosphorus"]) else 1,
            "has_ALP": 0 if pd.isna(labs["ALP"]) else 1,
            "has_PTH": 0 if pd.isna(labs["PTH"]) else 1,
            "has_height_weight": 1 if present(height) and present(weight) else 0,
            "is_age_eligible": 1 if present(age) and 1 / 12 <= float(age) <= 18 else (0 if present(age) else pd.NA),
            "baseline_source": "未检出25(OH)D；纳入占位记录"
            if not has_vitd
            else f"首次25(OH)D：{fv.iloc[0]['source_sheet']}.{fv.iloc[0]['source_column']}",
            "lab_source_sheet": pd.NA if fv.empty else fv.iloc[0]["source_sheet"],
            "bmd_source_sheet": bmd_vals["bmd_source"],
            "asm_source_sheet": asm_source,
            "notes": "; ".join(notes) if notes else pd.NA,
        }
    )

baseline = pd.DataFrame(master_rows)[field_order]
baseline.to_csv(OUT / "baseline_master.csv", index=False, encoding="utf-8-sig")
with pd.ExcelWriter(OUT / "baseline_master.xlsx", engine="openpyxl") as writer:
    baseline.to_excel(writer, index=False, sheet_name="baseline_master")

missing = pd.DataFrame({"variable": baseline.columns, "n_missing": [int(baseline[col].isna().sum()) for col in baseline.columns]})
missing["pct_missing"] = (missing["n_missing"] / len(baseline) * 100).round(1)
missing.to_csv(OUT / "qc_missingness.csv", index=False, encoding="utf-8-sig")

counts = pd.DataFrame(
    [
        ("原始患者数", len(patients)),
        ("有 25(OH)D 检测患者数", int(baseline["has_vitd"].sum())),
        ("进入 baseline_master 患儿数", len(baseline)),
        ("癫痫儿童数", int((baseline["group"] == "癫痫儿童").sum())),
        ("普通儿童数", int((baseline["group"] == "普通儿童").sum())),
        ("有 BMD Z 值患者数", int(baseline["has_bmd_z"].sum())),
        ("同时有 25(OH)D 和 BMD Z 值患者数", int(((baseline["has_vitd"] == 1) & (baseline["has_bmd_z"] == 1)).sum())),
        ("有完整基础信息患者数", int(baseline[["sex", "age_year", "height", "weight"]].notna().all(axis=1).sum())),
        ("有 ASM 信息癫痫儿童数", int(((baseline["group"] == "癫痫儿童") & (baseline["ASM_number"].fillna(0).astype(int) > 0)).sum())),
    ],
    columns=["step", "n"],
)
counts.to_csv(OUT / "qc_sample_counts.csv", index=False, encoding="utf-8-sig")

range_rules = {
    "age_year": (0, 18, "0 到 18 岁"),
    "vitd_25oh": (0, 150, "0 到 150 ng/mL"),
    "height": (30, 220, "30 到 220 cm"),
    "weight": (1, 200, "1 到 200 kg"),
    "BMI": (8, 60, "8 到 60"),
    "bmd_z": (-6, 6, "-6 到 6"),
    "calcium": (0, 5, "仅标记极端值：0 到 5"),
    "phosphorus": (0, 5, "仅标记极端值：0 到 5"),
    "ALP": (0, 5000, "仅标记极端值：0 到 5000"),
    "PTH": (0, 5000, "仅标记极端值：0 到 5000"),
}
range_rows = []
for variable, (low, high, rule) in range_rules.items():
    values = pd.to_numeric(baseline[variable], errors="coerce")
    mask = values.notna() & ((values < low) | (values > high))
    range_rows.append(
        {
            "variable": variable,
            "reasonable_range": rule,
            "n_nonmissing": int(values.notna().sum()),
            "n_out_of_range": int(mask.sum()),
            "out_of_range_study_ids": ";".join(baseline.loc[mask, "study_id"].astype(str).tolist()),
            "min_value": values.min(skipna=True) if values.notna().any() else pd.NA,
            "max_value": values.max(skipna=True) if values.notna().any() else pd.NA,
            "action": "不删除，仅标记复核" if mask.any() else "未发现超范围值",
        }
    )
pd.DataFrame(range_rows).to_csv(OUT / "qc_variable_ranges.csv", index=False, encoding="utf-8-sig")

dictionary_rows = []
label_map = {
    "study_id": ("脱敏编号", "character", "", "S000001格式", "源患者编号生成", "患者编号", "identifier", "项目数据处理约定"),
    "source_patient_id_hash": ("患者编号哈希", "character", "", "", "SHA-256前32位", "患者编号", "identifier", "项目数据处理约定"),
    "group": ("儿童分组", "categorical", "", "普通儿童;癫痫儿童", "诊断/病历/ASM综合判断", "多文本字段", "group", "申报书第5-7页、第10页"),
    "sex": ("性别", "categorical", "", "男;女", "结构化字段优先", "性别/性别名称", "covariate", "申报书第15页"),
    "birth_date": ("出生日期", "date", "", "", "病案基本信息优先", "出生日期", "covariate", "申报书第15页"),
    "baseline_date": ("基线日期", "date", "", "", "首次25(OH)D检测日期", "检验时间/文本日期", "index", "项目数据处理约定"),
    "age_year": ("基线年龄", "numeric", "岁", "", "出生日期计算或年龄天数/365.25", "出生日期/年龄换算（天）", "covariate", "申报书第15页"),
    "vitd_25oh": ("血清25(OH)D", "numeric", "ng/mL", "", "统一为ng/mL", "检验结果/文本", "outcome", "申报书第4页、第10页、第15页"),
    "calcium": ("血钙/总钙", "numeric", "原始单位", "", "baseline_date±30天最近值", "实验室/文本", "outcome", "申报书第10页、第15页"),
    "phosphorus": ("血磷", "numeric", "原始单位", "", "baseline_date±30天最近值", "实验室/文本", "outcome", "申报书第10页、第15页"),
    "ALP": ("碱性磷酸酶", "numeric", "原始单位", "", "baseline_date±30天最近值", "实验室/文本", "outcome", "申报书第10页、第15页"),
    "PTH": ("甲状旁腺激素", "numeric", "原始单位", "", "baseline_date±30天最近值", "实验室/文本", "outcome", "申报书第10页、第15页"),
    "bmd_z": ("骨密度Z值", "numeric", "", "", "只使用Z值或明确Z阈值文本", "骨密度文本", "outcome", "申报书第10页、第15页"),
    "low_bmd": ("是否骨密度降低", "binary", "", "0;1", "bmd_z <= -2.0", "bmd_z", "outcome", "申报书第15页"),
    "risk_factor_count": ("规则型风险因素计数", "integer", "", "", "规则型危险因素求和", "多字段", "derived", "申报书第11页、第15页"),
    "risk_level_initial": ("初步风险分层", "categorical", "", "低风险;中风险;高风险", "按规则型风险分层", "risk_factor_count等", "derived", "申报书第11页"),
}
for variable in field_order:
    label, dtype, unit, allowed, rule, source_col, role, basis = label_map.get(
        variable, (variable, "character", "", "", "见清洗脚本", "", "analysis", "项目数据处理约定")
    )
    dictionary_rows.append(
        {
            "variable_name": variable,
            "variable_label": label,
            "variable_type": dtype,
            "unit": unit,
            "allowed_values": allowed,
            "derivation_rule": rule,
            "source_sheet": "派生/多来源",
            "source_column": source_col,
            "analysis_role": role,
            "basis_in_protocol": basis,
            "notes": "",
        }
    )
var_dict = pd.DataFrame(dictionary_rows)

codes = []


def add_codes(variable, items, rule):
    for code, meaning in items:
        codes.append({"variable_name": variable, "code": code, "meaning": meaning, "rule": rule})


add_codes("sex", [("男", "男"), ("女", "女")], "结构化字段标准化")
add_codes("group", [("普通儿童", "未满足癫痫判断"), ("癫痫儿童", "诊断/文本/ASM提示癫痫")], "综合诊断与病历文本")
add_codes("age_group", [("<1岁", "<1岁"), ("1-3岁", "1到<4岁"), ("4-6岁", "4到<7岁"), ("7-12岁", "7到<13岁"), ("13-18岁", "13到18岁")], "按age_year分组")
add_codes("season", [("春", "3-5月"), ("夏", "6-8月"), ("秋", "9-11月"), ("冬", "12/1/2月")], "按baseline_date月份")
add_codes("vitd_status3", [("缺乏", "<20 ng/mL"), ("不足", "20到<30 ng/mL"), ("充足", ">=30 ng/mL")], "25(OH)D三分类")
add_codes("vitd_status4", [("严重缺乏", "<12 ng/mL"), ("缺乏", "12到<20 ng/mL"), ("不足", "20到<30 ng/mL"), ("充足", ">=30 ng/mL")], "25(OH)D四分类")
for var in ["low_bmd", "enzyme_inducing_ASM", "valproate", "topiramate", "intellectual_disability", "motor_disability", "activity_limited"]:
    add_codes(var, [(0, "否"), (1, "是")], "二分类指示变量")
add_codes("bmd_status", [("骨密度降低", "bmd_z <= -2.0"), ("正常", "bmd_z > -2.0")], "儿童骨密度只用Z值")
add_codes("monotherapy", [("单药", "ASM_number == 1"), ("多药", "ASM_number >= 2")], "按ASM种数")
add_codes("risk_level_initial", [("低风险", "0个危险因素"), ("中风险", "1-2个危险因素"), ("高风险", ">=3个或指定高危因素")], "规则型初步分层")

with pd.ExcelWriter(OUT / "baseline_data_dictionary.xlsx", engine="openpyxl") as writer:
    var_dict.to_excel(writer, index=False, sheet_name="variable_dictionary")
    pd.DataFrame(codes).to_excel(writer, index=False, sheet_name="coding_rules")

summary = [
    "清洗完成。",
    f"进入 baseline_master 的患儿数：n = {len(baseline)}",
    f"癫痫儿童数：n = {int((baseline['group'] == '癫痫儿童').sum())}",
    f"普通儿童数：n = {int((baseline['group'] == '普通儿童').sum())}",
    f"有 25(OH)D：n = {int(baseline['has_vitd'].sum())}",
    f"有 BMD Z 值：n = {int(baseline['has_bmd_z'].sum())}",
    f"同时有 25(OH)D 和 BMD Z 值：n = {int(((baseline['has_vitd'] == 1) & (baseline['has_bmd_z'] == 1)).sum())}",
    f"维生素D缺乏人数：n = {int((baseline['vitd_deficiency'] == 1).sum())}",
    f"骨密度降低人数：n = {int((baseline['low_bmd'] == 1).sum())}",
    "输出文件位于 outputs/ 和 docs/。",
]
try:
    subprocess.run(["Rscript", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
except Exception:
    log("当前环境 PATH 中未找到可用 Rscript；本轮使用 Python 等价流程生成数据结果，仍交付 R 脚本供安装 R 后复现。")
log("\n".join(summary))
(LOGS / "data_cleaning_log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
print("\n".join(summary))
