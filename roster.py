"""
学生名单批量导入模块
- build_template()   生成学生名单导入模板（Excel）
- parse_students()   解析上传名单（xlsx / csv），校验必填项与重复
- build_accounts()   生成导入后的账号清单（含初始密码，便于分发）
"""
import io
import re

NAME_COLS = ["姓名", "学生姓名", "name", "Name"]
NO_COLS = ["学号", "student_no", "学号/编号"]
CLASS_COLS = ["班级", "class", "class_name", "所在班级"]
GROUP_COLS = ["小组", "组别", "分组", "group", "group_name"]
USER_COLS = ["用户名", "账号", "username", "登录名"]


def build_template() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "学生名单"

    ws.append(["姓名", "学号", "班级", "小组", "用户名"])

    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D5E8F0")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    for _ in range(10):
        ws.append(["", "", "", "", ""])

    for col, width in zip("ABCDE", [14, 18, 16, 14, 18]):
        ws.column_dimensions[col].width = width

    ws2 = wb.create_sheet("填写说明")
    ws2["A1"] = "填写说明"
    ws2["A1"].font = Font(bold=True, size=12)
    ws2["A2"] = "1. 必填项：姓名、学号；班级、小组建议填写，用于分组管理与成绩分析。"
    ws2["A3"] = "2. 用户名选填，留空时系统自动使用「学号」作为登录账号。"
    ws2["A4"] = "3. 初始密码统一在导入页面设置（默认 123456），学生可自行登录使用。"
    ws2["A5"] = "4. 已存在的学号会自动跳过，不会覆盖原账号与评价数据。"
    ws2["A6"] = "5. 建议把「学号」列设为文本格式，避免 Excel 丢失前导零或显示为 20230101.0。"
    ws2["A7"] = "6. 小组可填「第一组」「A组」等，导入后可在「学生管理」中调整。"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _clean_id(text: str) -> str:
    """修正 Excel 把学号/账号读成数值产生的 20230101.0、2.0230101e+07 等形态"""
    t = str(text).strip()
    if re.fullmatch(r"[0-9]+\.0", t):
        return t[:-2]
    if re.fullmatch(r"[0-9.]+e[+-]?[0-9]+", t.lower()):
        try:
            return str(int(float(t)))
        except (ValueError, OverflowError):
            return t
    return t


def parse_students(file_bytes: bytes, filename: str) -> dict:
    """返回 {"rows": [...], "errors": [...]}"""
    import pandas as pd

    try:
        if filename.lower().endswith(".csv"):
            try:
                df = pd.read_csv(io.BytesIO(file_bytes))
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding="gbk")
        else:
            df = pd.read_excel(io.BytesIO(file_bytes))
    except Exception as e:
        return {"rows": [], "errors": [f"文件解析失败：{e}"]}

    df.columns = [str(c).strip() for c in df.columns]
    df = df.fillna("")

    def cell(row, col):
        if not col:
            return ""
        s = str(row.get(col, "")).strip()
        return "" if s in ("", "nan", "None", "NaT") else s

    def pick(cands, fuzzy=None):
        for c in cands:
            if c in df.columns:
                return c
        for col in df.columns:
            low = str(col).lower()
            for kw in (fuzzy or []):
                if kw.lower() in low:
                    return col
        return None

    name_col = pick(NAME_COLS, ["姓名"])
    no_col = pick(NO_COLS, ["学号"])
    class_col = pick(CLASS_COLS, ["班级"])
    group_col = pick(GROUP_COLS, ["小组", "组别", "分组"])
    user_col = pick(USER_COLS, ["用户名", "账号"])

    if name_col is None or no_col is None:
        return {"rows": [], "errors": [
            f"名单缺少「姓名」或「学号」列。当前列：{', '.join(df.columns)}。请使用平台模板导入。"
        ]}

    rows, errors = [], []
    seen_no, seen_user = {}, {}

    for idx, row in df.iterrows():
        name = cell(row, name_col)
        no = _clean_id(cell(row, no_col))
        cls = cell(row, class_col)
        grp = cell(row, group_col)
        user = _clean_id(cell(row, user_col))

        if not name and not no:
            continue
        if not name:
            errors.append(f"第 {idx + 2} 行缺少姓名，已跳过")
            continue
        if not no:
            errors.append(f"第 {idx + 2} 行「{name}」缺少学号，已跳过")
            continue

        if no in seen_no:
            errors.append(f"第 {idx + 2} 行学号「{no}」与第 {seen_no[no] + 2} 行重复，已跳过")
            continue
        if user and user in seen_user:
            errors.append(f"第 {idx + 2} 行用户名「{user}」与第 {seen_user[user] + 2} 行重复，已跳过")
            continue

        seen_no[no] = idx
        if user:
            seen_user[user] = idx

        rows.append({
            "name": name,
            "student_no": no,
            "class_name": cls,
            "group_name": grp,
            "username": user or no,
        })

    return {"rows": rows, "errors": errors}


def build_accounts(rows, password) -> bytes:
    """生成账号清单 Excel，便于下发给学生"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "学生账号"
    ws.append(["姓名", "学号", "班级", "小组", "登录用户名", "初始密码"])

    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D5E8F0")
        cell.alignment = Alignment(horizontal="center")

    for r in rows:
        ws.append([r["name"], r["student_no"], r.get("class_name", ""),
                   r.get("group_name", ""), r["username"], password])

    for col, width in zip("ABCDEF", [14, 18, 16, 14, 18, 14]):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
