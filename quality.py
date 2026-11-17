"""
成绩分析模块
- build_template()      生成成绩导入模板（Excel）
- parse_scores()        解析上传的成绩表（xlsx / csv）
- analyze()             成绩区间统计 + 教学诊断说明
- collect_task_scores() 从任务评价结果汇总成绩
"""
import io
import math
import statistics

import database as db

INTERVALS = [
    {"label": "优秀", "lo": 90, "hi": 100, "range": "90-100", "color": "#00BFA6"},
    {"label": "良好", "lo": 80, "hi": 90, "range": "80-89", "color": "#4C8DFF"},
    {"label": "中等", "lo": 70, "hi": 80, "range": "70-79", "color": "#FFB020"},
    {"label": "及格", "lo": 60, "hi": 70, "range": "60-69", "color": "#8AA0BF"},
    {"label": "不及格", "lo": 0, "hi": 60, "range": "0-59", "color": "#FF6B6B"},
]

NAME_COLS = ["姓名", "学生姓名", "name", "Name"]
NO_COLS = ["学号", "student_no", "学号/编号"]
CLASS_COLS = ["班级", "class", "class_name", "所在班级"]
SCORE_COLS = ["成绩", "分数", "得分", "score", "Score", "总分"]


# ===================== 导入模板 =====================
def build_template() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "成绩表"

    header = ["姓名", "学号", "班级", "成绩"]
    ws.append(header)

    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D5E8F0")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    for _ in range(10):
        ws.append(["", "", "", ""])

    for col, width in zip("ABCD", [14, 16, 16, 12]):
        ws.column_dimensions[col].width = width

    ws2 = wb.create_sheet("填写说明")
    ws2["A1"] = "填写说明"
    ws2["A1"].font = Font(bold=True, size=12)
    ws2["A2"] = "1. 请在「成绩表」中填写：姓名、学号、班级、成绩（0-100 分）。"
    ws2["A3"] = "2. 姓名与成绩为必填项，学号、班级可留空。"
    ws2["A4"] = "3. 不要修改表头文字，填写完成后上传本文件即可自动统计。"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ===================== 解析上传文件 =====================
def parse_scores(file_bytes: bytes, filename: str) -> dict:
    """返回 {"rows": [...], "errors": [...], "skipped": int}"""
    import pandas as pd

    errors, rows, skipped = [], [], 0

    try:
        if filename.lower().endswith(".csv"):
            try:
                df = pd.read_csv(io.BytesIO(file_bytes))
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding="gbk")
        else:
            df = pd.read_excel(io.BytesIO(file_bytes))
    except Exception as e:
        return {"rows": [], "errors": [f"文件解析失败：{e}"], "skipped": 0}

    df.columns = [str(c).strip() for c in df.columns]
    df = df.fillna("")

    def cell(row, col):
        """读取单元格并归一化为字符串（空值统一为空串）"""
        if not col:
            return ""
        v = row.get(col, "")
        s = str(v).strip()
        return "" if s in ("", "nan", "None", "NaT") else s

    def pick(cands):
        for c in cands:
            if c in df.columns:
                return c
        return None

    name_col = pick(NAME_COLS)
    no_col = pick(NO_COLS)
    class_col = pick(CLASS_COLS)
    score_col = pick(SCORE_COLS)

    if score_col is None:
        return {"rows": [], "errors": [
            f"未找到成绩列。当前列：{', '.join(df.columns)}。请包含「成绩」列，或使用平台模板导入。"
        ], "skipped": 0}

    for idx, row in df.iterrows():
        name = cell(row, name_col)
        raw = cell(row, score_col)

        if not name and not raw:
            continue
        if not name or not raw:
            skipped += 1
            continue

        try:
            score = float(raw)
        except ValueError:
            errors.append(f"第 {idx + 2} 行「{name}」成绩「{raw}」不是数字，已跳过")
            continue

        if math.isnan(score) or score < 0 or score > 100:
            errors.append(f"第 {idx + 2} 行「{name}」成绩「{raw}」超出 0-100，已跳过")
            continue

        rows.append({
            "name": name,
            "student_no": cell(row, no_col),
            "class_name": cell(row, class_col),
            "score": score,
        })

    return {"rows": rows, "errors": errors, "skipped": skipped}


# ===================== 区间统计与分析 =====================
def _bucket_label(score):
    for iv in INTERVALS:
        if iv["lo"] <= score < iv["hi"] or (iv["hi"] == 100 and score >= 90):
            return iv["label"]
    return "不及格"


def analyze(scores):
    scores = [float(s) for s in scores]
    if not scores:
        return None

    n = len(scores)
    mean = round(sum(scores) / n, 1)
    median = round(statistics.median(scores), 1)
    std = round(math.sqrt(sum((s - mean) ** 2 for s in scores) / n), 1)
    vmax, vmin = round(max(scores), 1), round(min(scores), 1)

    counts = {iv["label"]: 0 for iv in INTERVALS}
    for s in scores:
        counts[_bucket_label(s)] += 1

    buckets = []
    for iv in INTERVALS:
        cnt = counts[iv["label"]]
        buckets.append({
            "label": iv["label"],
            "range": iv["range"],
            "color": iv["color"],
            "count": cnt,
            "pct": round(cnt / n * 100, 1),
        })

    pass_rate = round(sum(1 for s in scores if s >= 60) / n * 100, 1)
    excellent_rate = round(counts["优秀"] / n * 100, 1)
    fail_rate = round(counts["不及格"] / n * 100, 1)

    analysis = _build_analysis(
        n, mean, median, std, vmax, vmin, buckets, pass_rate, excellent_rate, fail_rate
    )

    return {
        "total": n, "mean": mean, "median": median, "std": std,
        "max": vmax, "min": vmin,
        "pass_rate": pass_rate, "excellent_rate": excellent_rate, "fail_rate": fail_rate,
        "buckets": buckets, "analysis": analysis,
    }


def _build_analysis(n, mean, median, std, vmax, vmin, buckets, pass_rate, excellent_rate, fail_rate):
    """基于统计指标生成教学诊断说明（规则化，稳定可解释）"""
    top = max(buckets, key=lambda b: b["count"])
    lines = []

    if mean >= 85:
        level = "整体水平优秀，绝大多数学生已达到较高掌握程度"
    elif mean >= 75:
        level = "整体水平良好，多数学生达到课程标准要求"
    elif mean >= 60:
        level = "整体水平基本达标，但部分学生仍存在明显短板"
    else:
        level = "整体水平偏低，教学效果需要重点关注"

    lines.append(
        f"本次共统计 {n} 名学生，平均分 {mean} 分，中位数 {median} 分，"
        f"最高 {vmax} 分、最低 {vmin} 分，{level}。"
    )
    lines.append(
        f"成绩最集中的区间为「{top['label']}」（{top['range']} 分），"
        f"共 {top['count']} 人，占比 {top['pct']}%，说明该分数段是本次考核的主体水平。"
    )
    lines.append(f"及格率 {pass_rate}%，优秀率 {excellent_rate}%，不及格率 {fail_rate}%。")

    if std >= 15:
        lines.append(f"标准差为 {std}，班级内部分化明显，学生之间的能力差距较大。")
    elif std >= 10:
        lines.append(f"标准差为 {std}，学生水平存在一定差异，但总体可控。")
    else:
        lines.append(f"标准差为 {std}，成绩分布较为集中，班级整体水平较均衡。")

    tips = []
    if fail_rate >= 10:
        tips.append(f"不及格占比达 {fail_rate}%，建议对不及格学生开展针对性补练与一对一辅导，优先补足基础操作规范")
    if excellent_rate >= 30:
        tips.append(f"优秀率达 {excellent_rate}%，可适当增加综合性、开放性的挑战任务，避免高水平学生“吃不饱”")
    elif excellent_rate < 10:
        tips.append("优秀率偏低，建议在任务设计中增加示范案例与分层目标，明确高分达成路径")
    if std >= 15:
        tips.append("针对分化明显的情况，建议采用分层任务与同伴互助，缩小两极差距")
    if top["label"] == "不及格":
        tips.append("主体成绩落在不及格区间，建议复盘评价标准与教学进度，并优先安排基础技能补练")
    elif top["label"] == "及格":
        tips.append("主体成绩集中在及格线附近，建议提高课堂练习的达成标准，帮助学生向上突破")
    if not tips:
        tips.append("本次成绩分布合理，可保持当前教学节奏，并持续跟踪个别波动学生")

    lines.append("教学建议：" + "；".join(tips) + "。")
    return "\n\n".join(lines)


# ===================== 从任务评价汇总成绩 =====================
def collect_task_scores(task_id):
    """优先综合评分，其次作品评分，再次观察评分；返回可直接分析的成绩行"""
    rows = []
    work_subs = {s["student_id"]: s for s in db.get_submissions_by_task(task_id, eval_source="work")}
    obs_subs = {s["student_id"]: s for s in db.get_submissions_by_task(task_id, eval_source="observation")}

    for stu in db.get_students():
        finals = db.get_final_evaluations(task_id, stu["id"])
        score = None
        if finals:
            score = sum(f["score"] for f in finals) / len(finals)
        else:
            for subs in (work_subs, obs_subs):
                sub = subs.get(stu["id"])
                if sub:
                    ev = db.get_evaluations_by_submission(sub["id"])
                    if ev:
                        score = sum(e["score"] for e in ev) / len(ev)
                        break
        if score is None:
            continue
        rows.append({
            "name": stu["name"],
            "student_no": stu["student_no"] or "",
            "class_name": stu["class_name"] or "",
            "score": round(float(score), 1),
        })
    return rows
