"""
评价引擎模块：
  - 解析学生上传的作品文件（docx/txt/md 等文本类文件）
  - 执行 AI 评分流程
  - 更新学生成长档案
"""
import os
import io
import database as db
import ai_service
from config import UPLOAD_DIR


def parse_work_file(file_data, file_name: str) -> str:
    """
    解析学生作品文件，提取文本内容用于 AI 评分
    支持: .txt, .md, .docx, .xlsx
    file_data 可以是字节内容（云端）或本地文件路径（兼容旧数据）
    其他类型返回文件名作为提示
    """
    ext = os.path.splitext(file_name)[1].lower()
    is_bytes = isinstance(file_data, (bytes, bytearray))
    try:
        if ext in (".txt", ".md"):
            if is_bytes:
                return bytes(file_data).decode("utf-8", errors="ignore")
            with open(file_data, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        elif ext == ".docx":
            from docx import Document
            doc = Document(io.BytesIO(file_data) if is_bytes else file_data)
            texts = []
            for p in doc.paragraphs:
                if p.text.strip():
                    texts.append(p.text)
            # 提取表格文本
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text.strip():
                            texts.append(cell.text)
            return "\n".join(texts)
        elif ext in (".xlsx", ".xls"):
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(file_data) if is_bytes else file_data, data_only=True)
            texts = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    texts.append(" | ".join(str(c) for c in row if c is not None))
            return "\n".join(texts)
        else:
            return f"[文件类型 {ext} 暂不支持文本解析，请教师查看原文件进行评价]"
    except Exception as e:
        return f"[文件解析失败：{str(e)}]"


def run_ai_grading(submission_id: int) -> list:
    """
    对指定提交执行 AI 自动评分
    遍历该任务关联的所有技能点，逐一调用 AI 评分
    返回评价结果列表
    """
    submission = db.get_submission(submission_id)
    if not submission:
        return []

    task_id = submission["task_id"]
    task_skills = db.get_task_skills(task_id)
    if not task_skills:
        return []

    # 解析作品内容：优先取数据库中的原始文件，兼容早期的本地文件路径
    work_content = ""
    file_bytes = db.get_submission_file(submission_id)
    if file_bytes:
        work_content = parse_work_file(file_bytes, submission["file_name"])
    elif submission["file_path"] and os.path.exists(submission["file_path"]):
        work_content = parse_work_file(submission["file_path"], submission["file_name"])
    if submission["content_text"]:
        work_content = (work_content + "\n" + submission["content_text"]).strip()

    # 清除已有 AI 评价（保留教师评价）
    conn = db.get_conn()
    conn.execute("DELETE FROM evaluations WHERE submission_id=? AND evaluator='ai'", (submission_id,))
    conn.commit()
    conn.close()

    results = []
    for ts in task_skills:
        skill_id = ts["skill_id"]
        skill_name = ts["skill_name"]
        criteria = ts["criteria"] or f"【{skill_name}】默认评价标准"

        ai_result = ai_service.ai_grade_work(
            skill_name=skill_name,
            criteria=criteria,
            work_content=work_content,
            file_name=submission["file_name"],
        )
        db.create_evaluation(
            submission_id=submission_id,
            skill_id=skill_id,
            evaluator="ai",
            score=ai_result["score"],
            comment=ai_result["comment"],
        )
        results.append({
            "skill_name": skill_name,
            "score": ai_result["score"],
            "comment": ai_result["comment"],
        })

    return results


def save_teacher_grading(submission_id: int, skill_scores: dict, skill_comments: dict):
    """
    保存教师评分（覆盖 AI 评分或手动评分）
    skill_scores: {skill_id: score}
    skill_comments: {skill_id: comment}
    """
    # 清除该提交的所有评价，重新写入教师评价
    db.delete_evaluations_by_submission(submission_id)
    for skill_id, score in skill_scores.items():
        comment = skill_comments.get(skill_id, "")
        db.create_evaluation(
            submission_id=submission_id,
            skill_id=skill_id,
            evaluator="teacher",
            score=float(score),
            comment=comment,
        )


def get_submission_overall(submission_id: int) -> dict:
    """
    获取某次提交的综合评价结果
    返回各技能点评分、综合得分、掌握度分析
    """
    evaluations = db.get_evaluations_by_submission(submission_id)
    if not evaluations:
        return {"skills": [], "overall_score": 0, "mastery": "暂无评价"}

    skill_scores = [{"skill_name": e["skill_name"], "score": e["score"]} for e in evaluations]
    overall = sum(e["score"] for e in evaluations) / len(evaluations) if evaluations else 0
    mastery = ai_service.summarize_mastery(skill_scores)

    return {
        "skills": evaluations,
        "overall_score": round(overall, 1),
        "mastery": mastery,
    }


# ===================== 观察法：评价表格导出 / 导入 =====================
def build_observation_template(task_id: int) -> bytes:
    """
    导出线下观察用评价表格（Excel）
    列结构：班级 | 学号 | 姓名 | {技能点}-评分 | {技能点}-评语 ...
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    task = db.get_task(task_id)
    skills = db.get_task_skills(task_id)
    students = db.get_students()

    wb = Workbook()
    ws = wb.active
    ws.title = "观察评价表"

    # 表头说明行
    ws.append([f"实操任务：{task['title']}（按100分制评分，分数自动汇总到学生成长档案）"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=3 + 2 * len(skills))
    ws["A1"].font = Font(bold=True, size=12)
    ws["A1"].alignment = Alignment(horizontal="left")

    header = ["班级", "学号", "姓名"]
    for s in skills:
        header.append(f"{s['skill_name']}-评分")
        header.append(f"{s['skill_name']}-评语")
    ws.append(header)

    # 表头样式
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for cell in ws[2]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D5E8F0")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border

    for st in students:
        row = [st["class_name"], st["student_no"], st["name"]]
        for _ in skills:
            row += ["", ""]
        ws.append(row)

    # 列宽
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 10
    for i in range(4, 4 + 2 * len(skills)):
        ws.column_dimensions[ws.cell(row=2, column=i).column_letter].width = 20
    ws.freeze_panes = "D3"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def import_observation_scores(task_id: int, file_bytes: bytes) -> dict:
    """
    导入填写后的观察评价表：按学号匹配学生，生成观察记录与教师评分
    返回 {"imported": n, "skipped": [原因...], "errors": [...]}
    """
    import pandas as pd

    task_skills = db.get_task_skills(task_id)
    skills = db.get_students()
    students_by_no = {s["student_no"]: s for s in skills if s["student_no"]}
    students_by_name = {s["name"]: s for s in skills}

    # 第1行为说明，第2行为表头
    df = pd.read_excel(io.BytesIO(file_bytes), header=1, dtype=str)
    df = df.fillna("")

    col_map = {}
    for ts in task_skills:
        score_col = f"{ts['skill_name']}-评分"
        comment_col = f"{ts['skill_name']}-评语"
        if score_col in df.columns:
            col_map[ts["skill_id"]] = (score_col, comment_col)

    result = {"imported": 0, "skipped": [], "errors": []}
    if not col_map:
        result["errors"].append("表格中未找到与任务技能点匹配的评分列，请使用平台导出的模板填写。")
        return result

    for idx, row in df.iterrows():
        name = str(row.get("姓名", "")).strip()
        student_no = str(row.get("学号", "")).strip()
        if not name and not student_no:
            continue

        student = students_by_no.get(student_no) or students_by_name.get(name)
        if not student:
            result["skipped"].append(f"第{idx + 3}行：未匹配到学生（{name}/{student_no}）")
            continue

        scores, comments = {}, {}
        has_value = False
        for skill_id, (score_col, comment_col) in col_map.items():
            raw = str(row.get(score_col, "")).strip()
            if raw:
                try:
                    val = float(raw)
                    val = max(0, min(100, val))
                    scores[skill_id] = val
                    has_value = True
                except ValueError:
                    result["errors"].append(f"{name} - 技能点{skill_id} 评分「{raw}」不是数字，已跳过")
                    continue
            comment = str(row.get(comment_col, "")).strip() if comment_col in df.columns else ""
            comments[skill_id] = comment

        if not has_value:
            result["skipped"].append(f"{name}：未填写任何评分")
            continue

        obs_id = db.create_observation_record(task_id, student["id"])
        db.delete_evaluations_by_submission(obs_id)
        for skill_id, score in scores.items():
            db.create_evaluation(obs_id, skill_id, "teacher", score, comments.get(skill_id, ""))
        result["imported"] += 1

    return result


# ===================== 综合模式：观察 + 作品加权 =====================
def compute_combined(task_id: int, student_id: int, obs_weight: float) -> dict:
    """
    将观察评分与作品评分按权重合并，写入 final_evaluations
    obs_weight: 观察评价占比（0~1）
    """
    obs_sub = db.get_submission_by_task_student(task_id, student_id, eval_source="observation")
    work_sub = db.get_submission_by_task_student(task_id, student_id, eval_source="work")

    obs_scores = {e["skill_id"]: e for e in db.get_evaluations_by_submission(obs_sub["id"])} if obs_sub else {}
    work_scores = {e["skill_id"]: e for e in db.get_evaluations_by_submission(work_sub["id"])} if work_sub else {}

    items = []
    for ts in db.get_task_skills(task_id):
        sid = ts["skill_id"]
        o = obs_scores.get(sid)
        w = work_scores.get(sid)

        if o and w:
            score = o["score"] * obs_weight + w["score"] * (1 - obs_weight)
            comment = f"观察{o['score']:.0f}分 × {obs_weight:.0%} + 作品{w['score']:.0f}分 × {1 - obs_weight:.0%}"
        elif o:
            score = o["score"]
            comment = "仅观察评分"
        elif w:
            score = w["score"]
            comment = "仅作品评分"
        else:
            continue

        items.append({"skill_id": sid, "score": round(score, 1), "comment": comment})

    if items:
        db.save_final_evaluations(
            task_id, student_id, items,
            method=f"观察{obs_weight:.0%}+作品{1 - obs_weight:.0%}"
        )
    return {"items": items, "overall": round(sum(i["score"] for i in items) / len(items), 1) if items else 0}
