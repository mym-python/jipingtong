"""
数据库模块：SQLite 表结构定义与 CRUD 操作
表结构：
  - users         用户（教师/学生）
  - skills        技能库
  - tasks         实操任务
  - task_skills   任务-技能点关联（含评价标准）
  - submissions   学生作品提交
  - evaluations   评价记录（AI/教师评分+评语）
"""
import os
import hashlib
from datetime import datetime
from config import DB_PATH
import dbcompat


def get_conn():
    """获取数据库连接：云端为 PostgreSQL，本地为 SQLite"""
    return dbcompat.connect()


def init_db():
    """初始化数据库表结构"""
    conn = get_conn()
    c = conn.cursor()

    # 用户表
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('teacher','student')),
            name TEXT NOT NULL,
            class_name TEXT DEFAULT '',
            group_name TEXT DEFAULT '',
            student_no TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    # 技能库
    c.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            category TEXT DEFAULT '',
            created_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    # 实操任务（course_id 表示任务属于哪门课程，技能点只能来自该课程技能库）
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            deadline TEXT DEFAULT '',
            eval_mode TEXT DEFAULT '',
            target_class TEXT DEFAULT '',
            target_group TEXT DEFAULT '',
            created_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    # 任务-技能点关联（含 AI 生成的评价标准）
    c.execute("""
        CREATE TABLE IF NOT EXISTS task_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            skill_id INTEGER NOT NULL,
            criteria TEXT DEFAULT '',
            weight REAL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (skill_id) REFERENCES skills(id)
        )
    """)

    # 学生作品提交 / 线下观察记录
    # eval_source: work=线上作品提交, observation=教师线下观察记录
    c.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            file_path TEXT DEFAULT '',
            file_name TEXT DEFAULT '',
            content_text TEXT DEFAULT '',
            submitted_at TEXT NOT NULL,
            status TEXT DEFAULT 'submitted',
            eval_source TEXT DEFAULT 'work',
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES users(id)
        )
    """)

    # 作品原文件（独立表存放，避免列表查询把大文件读进内存；
    # 云端部署时磁盘是临时的，文件必须随数据一起持久化）
    c.execute("""
        CREATE TABLE IF NOT EXISTS submission_files (
            submission_id INTEGER PRIMARY KEY,
            file_name TEXT DEFAULT '',
            data BLOB,
            updated_at TEXT,
            FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE
        )
    """)

    # 评价记录
    c.execute("""
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            skill_id INTEGER NOT NULL,
            evaluator TEXT NOT NULL CHECK(evaluator IN ('ai','teacher')),
            score REAL NOT NULL,
            comment TEXT DEFAULT '',
            evaluated_at TEXT NOT NULL,
            FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE,
            FOREIGN KEY (skill_id) REFERENCES skills(id)
        )
    """)

    # 综合模式最终评分（观察+作品加权后写入，档案以它为准）
    c.execute("""
        CREATE TABLE IF NOT EXISTS final_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            skill_id INTEGER NOT NULL,
            score REAL NOT NULL,
            comment TEXT DEFAULT '',
            method TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES users(id),
            FOREIGN KEY (skill_id) REFERENCES skills(id)
        )
    """)

    # 课程：一门课对应一个技能库
    c.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)

    # 成绩分析：导入的成绩数据集
    c.execute("""
        CREATE TABLE IF NOT EXISTS quality_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset TEXT NOT NULL,
            student_name TEXT DEFAULT '',
            student_no TEXT DEFAULT '',
            class_name TEXT DEFAULT '',
            score REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # 未完成督促记录
    c.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            message TEXT DEFAULT '',
            channel TEXT DEFAULT '平台通知',
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    conn.commit()

    # 兼容旧库：补列
    _ensure_column(conn, "submissions", "eval_source", "TEXT DEFAULT 'work'")
    _ensure_column(conn, "tasks", "obs_weight", "REAL DEFAULT 0.4")
    _ensure_column(conn, "tasks", "target_class", "TEXT DEFAULT ''")
    _ensure_column(conn, "tasks", "target_group", "TEXT DEFAULT ''")
    _ensure_column(conn, "users", "group_name", "TEXT DEFAULT ''")
    _ensure_column(conn, "users", "is_active", "INTEGER DEFAULT 1")
    _ensure_column(conn, "skills", "course_id", "INTEGER")
    _ensure_column(conn, "tasks", "course_id", "INTEGER")

    # ---------- 数据一致性修复（可重复执行） ----------
    # 1) 同一任务重复关联同一技能点会重复评分、重复计入档案：保留最早一条
    conn.execute("""
        DELETE FROM task_skills WHERE id NOT IN (
            SELECT MIN(id) FROM task_skills GROUP BY task_id, skill_id
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_task_skills "
                 "ON task_skills(task_id, skill_id)")

    # 2) 综合评分按 任务+学生+技能点 唯一，重复记录只保留最新一条
    conn.execute("""
        DELETE FROM final_evaluations WHERE id NOT IN (
            SELECT MAX(id) FROM final_evaluations GROUP BY task_id, student_id, skill_id
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_final_evaluations "
                 "ON final_evaluations(task_id, student_id, skill_id)")

    # 3) 历史任务回填所属课程：取已关联技能点所属课程
    conn.execute("""
        UPDATE tasks SET course_id = (
            SELECT MIN(s.course_id) FROM task_skills ts
            JOIN skills s ON ts.skill_id = s.id
            WHERE ts.task_id = tasks.id AND s.course_id IS NOT NULL
        )
        WHERE course_id IS NULL
    """)

    conn.commit()
    conn.close()


def _ensure_column(conn, table, column, declaration):
    """旧数据库缺失列时自动补列"""
    cols = dbcompat.table_columns(conn, table)
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


# ===================== 用户相关 =====================
def create_user(username, password, role, name, class_name="", student_no=""):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO users(username,password,role,name,class_name,student_no,created_at) VALUES(?,?,?,?,?,?,?)",
            (username, hash_password(password), role, name, class_name, student_no, datetime.now().isoformat())
        )
        conn.commit()
        return cur.lastrowid
    except dbcompat.IntegrityError:
        return None
    finally:
        conn.close()


def create_students_bulk(rows, password="123456"):
    """
    批量创建学生账号
    rows: [{"name","student_no","class_name","username"}]
    用户名缺省使用学号；已存在的用户名/学号跳过。
    返回 (成功数, 跳过数)
    """
    conn = get_conn()
    inserted, skipped = 0, 0
    now = datetime.now().isoformat()
    pwd = hash_password(password)
    try:
        for r in rows:
            username = (r.get("username") or r.get("student_no") or "").strip()
            if not username or not r.get("name"):
                skipped += 1
                continue
            exists = conn.execute(
                "SELECT 1 FROM users WHERE username=? "
                "OR (role='student' AND student_no=? AND student_no<>'')",
                (username, r.get("student_no", ""))
            ).fetchone()
            if exists:
                skipped += 1
                continue
            conn.execute(
                "INSERT INTO users(username,password,role,name,class_name,group_name,student_no,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (username, pwd, "student", r["name"],
                 r.get("class_name", ""), r.get("group_name", ""),
                 r.get("student_no", ""), now)
            )
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted, skipped


def login(username, password):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE username=? AND password=? AND is_active=1",
        (username, hash_password(password))
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user(uid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_students(include_inactive=True):
    conn = get_conn()
    sql = "SELECT * FROM users WHERE role='student'"
    if not include_inactive:
        sql += " AND is_active=1"
    sql += " ORDER BY class_name, group_name, student_no"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_student(uid, name, class_name, group_name):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET name=?, class_name=?, group_name=? WHERE id=? AND role='student'",
        (name.strip(), class_name.strip(), group_name.strip(), uid)
    )
    conn.commit()
    conn.close()


def set_student_active(uid, active: bool):
    conn = get_conn()
    conn.execute("UPDATE users SET is_active=? WHERE id=? AND role='student'",
                 (1 if active else 0, uid))
    conn.commit()
    conn.close()


def reset_student_password(uid, new_password="123456"):
    conn = get_conn()
    conn.execute("UPDATE users SET password=? WHERE id=?",
                 (hash_password(new_password), uid))
    conn.commit()
    conn.close()


def get_student_record_count(uid):
    """学生已有评价记录数（作品提交 + 观察记录 + 综合评分）"""
    conn = get_conn()
    subs = conn.execute("SELECT COUNT(*) FROM submissions WHERE student_id=?", (uid,)).fetchone()[0]
    finals = conn.execute("SELECT COUNT(*) FROM final_evaluations WHERE student_id=?", (uid,)).fetchone()[0]
    conn.close()
    return subs + finals


def delete_student(uid, with_records=False):
    """
    删除学生账号。
    有评价记录时需 with_records=True 才会连同记录一并删除；否则返回 (False, 记录数)。
    返回 (是否删除, 关联记录数)
    """
    conn = get_conn()
    try:
        subs = [r["id"] for r in conn.execute(
            "SELECT id, file_path FROM submissions WHERE student_id=?", (uid,)).fetchall()]
        finals = conn.execute(
            "SELECT COUNT(*) FROM final_evaluations WHERE student_id=?", (uid,)).fetchone()[0]
        records = len(subs) + finals
        if records and not with_records:
            return False, records

        for sid in subs:
            conn.execute("DELETE FROM evaluations WHERE submission_id=?", (sid,))
        conn.execute("DELETE FROM submissions WHERE student_id=?", (uid,))
        conn.execute("DELETE FROM final_evaluations WHERE student_id=?", (uid,))
        conn.execute("DELETE FROM users WHERE id=? AND role='student'", (uid,))
        conn.commit()
        return True, records
    finally:
        conn.close()


# ===================== 技能库相关 =====================
def create_skill(name, description="", category="", created_by=None, course_id=None):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO skills(course_id,name,description,category,created_by,created_at) VALUES(?,?,?,?,?,?)",
        (course_id, name, description, category, created_by, datetime.now().isoformat())
    )
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return sid


def get_skills(course_id=None):
    """course_id=None 返回全部；course_id=0 返回未归属课程的技能"""
    conn = get_conn()
    if course_id == 0:
        rows = conn.execute(
            "SELECT * FROM skills WHERE course_id IS NULL ORDER BY category, name"
        ).fetchall()
    elif course_id:
        rows = conn.execute(
            "SELECT * FROM skills WHERE course_id=? ORDER BY category, name", (course_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM skills ORDER BY category, name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_skill(sid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM skills WHERE id=?", (sid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_skill(sid, name, description="", category="", course_id=None):
    conn = get_conn()
    conn.execute(
        "UPDATE skills SET name=?, description=?, category=?, course_id=? WHERE id=?",
        (name.strip(), description.strip(), category.strip(), course_id, sid)
    )
    conn.commit()
    conn.close()


# ===================== 课程管理 =====================
def get_courses():
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.*, (SELECT COUNT(*) FROM skills s WHERE s.course_id = c.id) AS skill_count
        FROM courses c ORDER BY c.id
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_course(name, description=""):
    """返回课程 id；同名课程已存在则返回 None"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO courses(name,description,created_at) VALUES(?,?,?)",
            (name.strip(), description.strip(), datetime.now().isoformat())
        )
        conn.commit()
        return cur.lastrowid
    except dbcompat.IntegrityError:
        return None
    finally:
        conn.close()


def update_course(cid, name, description=""):
    """返回 True/False；名称与其他课程重复时返回 False"""
    conn = get_conn()
    try:
        conn.execute("UPDATE courses SET name=?, description=? WHERE id=?",
                     (name.strip(), description.strip(), cid))
        conn.commit()
        return True
    except dbcompat.IntegrityError:
        return False
    finally:
        conn.close()


def delete_course(cid):
    """课程下还有技能点时禁止删除，返回 (是否删除, 技能数)"""
    conn = get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM skills WHERE course_id=?", (cid,)).fetchone()[0]
        if count:
            return False, count
        conn.execute("DELETE FROM courses WHERE id=?", (cid,))
        conn.commit()
        return True, 0
    finally:
        conn.close()


def assign_unassigned_skills(course_id):
    """把未归属课程的技能点批量归入指定课程"""
    conn = get_conn()
    cur = conn.execute("UPDATE skills SET course_id=? WHERE course_id IS NULL", (course_id,))
    conn.commit()
    conn.close()
    return cur.rowcount


def batch_move_skills(skill_ids, course_id=None):
    """批量调整技能点所属课程（course_id=None 表示设为未归属），返回更新数量"""
    ids = [int(i) for i in skill_ids]
    if not ids:
        return 0
    conn = get_conn()
    placeholders = ",".join("?" for _ in ids)
    cur = conn.execute(
        f"UPDATE skills SET course_id=? WHERE id IN ({placeholders})",
        (course_id, *ids)
    )
    conn.commit()
    conn.close()
    return cur.rowcount


def batch_set_category(skill_ids, category=""):
    """批量设置技能分类（传空字符串表示未分类），返回更新数量"""
    ids = [int(i) for i in skill_ids]
    if not ids:
        return 0
    conn = get_conn()
    placeholders = ",".join("?" for _ in ids)
    cur = conn.execute(
        f"UPDATE skills SET category=? WHERE id IN ({placeholders})",
        (category.strip(), *ids)
    )
    conn.commit()
    conn.close()
    return cur.rowcount


def get_skill_usage(sid):
    """技能点被引用情况：任务关联数、评价记录数（作品评价 + 综合评分）"""
    conn = get_conn()
    task_count = conn.execute(
        "SELECT COUNT(*) FROM task_skills WHERE skill_id=?", (sid,)).fetchone()[0]
    eval_count = conn.execute(
        "SELECT COUNT(*) FROM evaluations WHERE skill_id=?", (sid,)).fetchone()[0]
    final_count = conn.execute(
        "SELECT COUNT(*) FROM final_evaluations WHERE skill_id=?", (sid,)).fetchone()[0]
    conn.close()
    return {"tasks": task_count, "evaluations": eval_count, "finals": final_count}


def delete_skill(sid):
    """
    删除技能点：
    - 已有评价记录时禁止删除（保护历史档案），返回 (False, usage)
    - 仅被任务关联时，同步解除任务关联后删除，返回 (True, usage)
    """
    usage = get_skill_usage(sid)
    if usage["evaluations"] or usage["finals"]:
        return False, usage
    conn = get_conn()
    try:
        conn.execute("DELETE FROM task_skills WHERE skill_id=?", (sid,))
        conn.execute("DELETE FROM skills WHERE id=?", (sid,))
        conn.commit()
    finally:
        conn.close()
    return True, usage


# ===================== 任务相关 =====================
def create_task(title, description="", deadline="", eval_mode="", created_by=None,
                obs_weight=0.4, target_class="", target_group="", course_id=None):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO tasks(course_id,title,description,deadline,eval_mode,created_by,created_at,"
        "obs_weight,target_class,target_group) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (course_id, title, description, deadline, eval_mode, created_by,
         datetime.now().isoformat(), obs_weight, target_class, target_group)
    )
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return tid


def update_task_course(tid, course_id):
    """设置任务所属课程；课程改动后任务只能关联该课程的技能点"""
    conn = get_conn()
    conn.execute("UPDATE tasks SET course_id=? WHERE id=?", (course_id, tid))
    conn.commit()
    conn.close()


def update_task_obs_weight(task_id, obs_weight):
    conn = get_conn()
    conn.execute("UPDATE tasks SET obs_weight=? WHERE id=?", (float(obs_weight), task_id))
    conn.commit()
    conn.close()


def get_tasks(course_id=None):
    """course_id=None 返回全部（含课程名）；传课程 id 只返回该课程任务"""
    conn = get_conn()
    base = ("SELECT t.*, c.name AS course_name FROM tasks t "
            "LEFT JOIN courses c ON t.course_id = c.id")
    if course_id:
        rows = conn.execute(base + " WHERE t.course_id=? ORDER BY t.created_at DESC",
                            (course_id,)).fetchall()
    else:
        rows = conn.execute(base + " ORDER BY t.created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_task(tid):
    """删除任务：依赖外键级联清理关联技能点、提交、评价、综合评分与督促记录"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
        conn.commit()
    finally:
        conn.close()


def get_task(tid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_task_target(tid, target_class="", target_group=""):
    conn = get_conn()
    conn.execute("UPDATE tasks SET target_class=?, target_group=? WHERE id=?",
                 (target_class.strip(), target_group.strip(), tid))
    conn.commit()
    conn.close()


def get_task_recipients(task_id):
    """任务的应完成学生：按发布班级/小组筛选在册学生；均为空表示全体"""
    task = get_task(task_id)
    if not task:
        return []
    cls = (task.get("target_class") or "").strip()
    grp = (task.get("target_group") or "").strip()
    result = []
    for s in get_students(include_inactive=False):
        if cls and (s.get("class_name") or "").strip() != cls:
            continue
        if grp and (s.get("group_name") or "").strip() != grp:
            continue
        result.append(s)
    return result


def get_task_submission_status(task_id):
    """返回 {student_id: {"last_time","sub_count","eval_count"}}"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT s.student_id,
               MAX(s.submitted_at) AS last_time,
               COUNT(DISTINCT s.id) AS sub_count,
               SUM((SELECT COUNT(*) FROM evaluations e WHERE e.submission_id = s.id)) AS eval_count
        FROM submissions s
        WHERE s.task_id=?
        GROUP BY s.student_id
    """, (task_id,)).fetchall()
    conn.close()
    return {
        r["student_id"]: {
            "last_time": r["last_time"],
            "sub_count": r["sub_count"],
            "eval_count": r["eval_count"] or 0,
        }
        for r in rows
    }


def get_task_stats(task_id):
    """(应完成人数, 已完成人数)"""
    recipients = get_task_recipients(task_id)
    ids = {s["id"] for s in recipients}
    status = get_task_submission_status(task_id)
    done = len([sid for sid in status if sid in ids])
    return len(recipients), done


# ===================== 未完成督促 =====================
def add_reminders(task_id, items, channel="平台通知"):
    """items: [(student_id, message)]"""
    conn = get_conn()
    now = datetime.now().isoformat()
    for sid, msg in items:
        conn.execute(
            "INSERT INTO reminders(task_id,student_id,message,channel,created_at) "
            "VALUES(?,?,?,?,?)", (task_id, sid, msg, channel, now)
        )
    conn.commit()
    conn.close()
    return len(items)


def get_task_reminders(task_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT r.*, u.name AS student_name, u.class_name, u.group_name
        FROM reminders r JOIN users u ON r.student_id = u.id
        WHERE r.task_id=? ORDER BY r.created_at DESC, r.id DESC
    """, (task_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_reminder_counts(task_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT student_id, COUNT(*) AS c, MAX(created_at) AS last "
        "FROM reminders WHERE task_id=? GROUP BY student_id", (task_id,)
    ).fetchall()
    conn.close()
    return {r["student_id"]: {"count": r["c"], "last": r["last"]} for r in rows}


# ===================== 任务-技能点关联 =====================
def add_task_skill(task_id, skill_id, criteria="", weight=1.0):
    """关联技能点；同一任务重复关联同一技能点时更新标准与权重，不新增重复记录"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO task_skills(task_id,skill_id,criteria,weight,created_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(task_id,skill_id) DO UPDATE SET "
        "criteria=excluded.criteria, weight=excluded.weight",
        (task_id, skill_id, criteria, weight, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def update_task_skill_criteria(ts_id, criteria):
    conn = get_conn()
    conn.execute("UPDATE task_skills SET criteria=? WHERE id=?", (criteria, ts_id))
    conn.commit()
    conn.close()


def get_task_skills(task_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT ts.*, s.name AS skill_name, s.description AS skill_desc, s.category AS skill_category
        FROM task_skills ts JOIN skills s ON ts.skill_id = s.id
        WHERE ts.task_id=? ORDER BY ts.id
    """, (task_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===================== 提交作品相关 =====================
def create_submission(task_id, student_id, file_path="", file_name="", content_text="",
                      eval_source="work", file_data=None):
    """
    作品提交：一次任务每个学生只保留一份作品，重复提交覆盖旧记录。
    覆盖时清空旧评价与综合评分，避免旧分数与新作品错配、档案重复计分。
    file_data 为作品原始字节，存入 submission_files 表随数据库持久化。
    """
    if eval_source == "work":
        existing = get_submission_by_task_student(task_id, student_id, eval_source="work")
        if existing:
            old_path = (existing.get("file_path") or "").strip()
            if old_path and old_path != file_path and os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass
            conn = get_conn()
            conn.execute(
                "UPDATE submissions SET file_path=?, file_name=?, content_text=?, "
                "submitted_at=?, status='submitted' WHERE id=?",
                (file_path, file_name, content_text, datetime.now().isoformat(), existing["id"])
            )
            conn.execute("DELETE FROM evaluations WHERE submission_id=?", (existing["id"],))
            conn.execute("DELETE FROM final_evaluations WHERE task_id=? AND student_id=?",
                         (task_id, student_id))
            _save_submission_file(conn, existing["id"], file_name, file_data)
            conn.commit()
            conn.close()
            return existing["id"]

    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO submissions(task_id,student_id,file_path,file_name,content_text,submitted_at,status,eval_source) VALUES(?,?,?,?,?,?,?,?)",
        (task_id, student_id, file_path, file_name, content_text,
         datetime.now().isoformat(), "submitted", eval_source)
    )
    conn.commit()
    sid = cur.lastrowid
    _save_submission_file(conn, sid, file_name, file_data)
    conn.commit()
    conn.close()
    return sid


def _save_submission_file(conn, submission_id, file_name, file_data):
    """作品文件落库（覆盖式写入）"""
    if file_data is None:
        return
    conn.execute("DELETE FROM submission_files WHERE submission_id=?", (submission_id,))
    conn.execute(
        "INSERT INTO submission_files(submission_id,file_name,data,updated_at) VALUES(?,?,?,?)",
        (submission_id, file_name, file_data, datetime.now().isoformat())
    )


def get_submission_file(submission_id):
    """取作品原始文件，返回 bytes 或 None"""
    conn = get_conn()
    row = conn.execute(
        "SELECT data FROM submission_files WHERE submission_id=?", (submission_id,)
    ).fetchone()
    conn.close()
    if not row or row["data"] is None:
        return None
    return bytes(row["data"])


def create_observation_record(task_id, student_id, note=""):
    """创建/更新线下观察记录（不依赖学生上传）"""
    existing = get_submission_by_task_student(task_id, student_id, eval_source="observation")
    if existing:
        return existing["id"]
    return create_submission(
        task_id, student_id, file_path="", file_name="（线下观察记录）",
        content_text=note, eval_source="observation"
    )


def get_submissions_by_task(task_id, eval_source=None):
    conn = get_conn()
    if eval_source:
        rows = conn.execute("""
            SELECT sub.*, u.name AS student_name, u.class_name, u.student_no
            FROM submissions sub JOIN users u ON sub.student_id = u.id
            WHERE sub.task_id=? AND sub.eval_source=? ORDER BY sub.submitted_at
        """, (task_id, eval_source)).fetchall()
    else:
        rows = conn.execute("""
            SELECT sub.*, u.name AS student_name, u.class_name, u.student_no
            FROM submissions sub JOIN users u ON sub.student_id = u.id
            WHERE sub.task_id=? ORDER BY sub.submitted_at
        """, (task_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_submission(sid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_submission_by_task_student(task_id, student_id, eval_source="work"):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM submissions WHERE task_id=? AND student_id=? AND eval_source=? ORDER BY submitted_at DESC LIMIT 1",
        (task_id, student_id, eval_source)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ===================== 评价记录相关 =====================
def create_evaluation(submission_id, skill_id, evaluator, score, comment=""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO evaluations(submission_id,skill_id,evaluator,score,comment,evaluated_at) VALUES(?,?,?,?,?,?)",
        (submission_id, skill_id, evaluator, score, comment, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def delete_evaluations_by_submission(submission_id):
    conn = get_conn()
    conn.execute("DELETE FROM evaluations WHERE submission_id=?", (submission_id,))
    conn.commit()
    conn.close()


def get_evaluations_by_submission(submission_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT e.*, s.name AS skill_name
        FROM evaluations e JOIN skills s ON e.skill_id = s.id
        WHERE e.submission_id=? ORDER BY e.id
    """, (submission_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===================== 综合评分（观察+作品） =====================
def save_final_evaluations(task_id, student_id, items, method=""):
    """
    保存综合模式最终评分
    items: [{"skill_id": int, "score": float, "comment": str}, ...]
    """
    conn = get_conn()
    conn.execute("DELETE FROM final_evaluations WHERE task_id=? AND student_id=?", (task_id, student_id))
    now = datetime.now().isoformat()
    for it in items:
        conn.execute(
            "INSERT INTO final_evaluations(task_id,student_id,skill_id,score,comment,method,created_at) VALUES(?,?,?,?,?,?,?)",
            (task_id, student_id, it["skill_id"], float(it["score"]), it.get("comment", ""), method, now)
        )
    conn.commit()
    conn.close()


def get_final_evaluations(task_id, student_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT fe.*, s.name AS skill_name
        FROM final_evaluations fe JOIN skills s ON fe.skill_id = s.id
        WHERE fe.task_id=? AND fe.student_id=? ORDER BY fe.id
    """, (task_id, student_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_final_evaluations(task_id, student_id):
    conn = get_conn()
    conn.execute("DELETE FROM final_evaluations WHERE task_id=? AND student_id=?", (task_id, student_id))
    conn.commit()
    conn.close()


# ===================== 学生成长档案 =====================
def get_student_archive(student_id):
    """
    获取学生技能成长档案：
    按技能点聚合所有任务的评分，计算平均得分率，反映掌握路径。
    综合模式任务若已生成最终评分，则以最终评分为准（避免观察/作品重复计数）。
    """
    conn = get_conn()
    raw = conn.execute("""
        SELECT e.score, e.skill_id, e.submission_id, sub.task_id
        FROM evaluations e
        JOIN submissions sub ON e.submission_id = sub.id
        WHERE sub.student_id = ?
    """, (student_id,)).fetchall()
    finals = conn.execute("""
        SELECT fe.score, fe.skill_id, fe.task_id
        FROM final_evaluations fe WHERE fe.student_id = ?
    """, (student_id,)).fetchall()
    skills = {s["id"]: s for s in (dict(r) for r in conn.execute(
        "SELECT s.*, c.name AS course_name FROM skills s "
        "LEFT JOIN courses c ON s.course_id = c.id"
    ).fetchall())}
    conn.close()

    tasks_with_final = {f["task_id"] for f in finals}
    records = [{"score": f["score"], "skill_id": f["skill_id"], "task_key": f"final_{f['task_id']}"}
               for f in finals]
    records += [{"score": r["score"], "skill_id": r["skill_id"], "task_key": f"sub_{r['submission_id']}"}
                for r in raw if r["task_id"] not in tasks_with_final]

    agg = {}
    for rec in records:
        sk = skills.get(rec["skill_id"])
        if not sk:
            continue
        a = agg.setdefault(rec["skill_id"], {
            "skill_id": rec["skill_id"], "skill_name": sk["name"],
            "skill_category": sk["category"],
            "course_name": sk.get("course_name") or "未归属课程",
            "scores": [], "tasks": set(),
        })
        a["scores"].append(rec["score"])
        a["tasks"].add(rec["task_key"])

    result = []
    for a in agg.values():
        sc = a["scores"]
        result.append({
            "skill_id": a["skill_id"],
            "skill_name": a["skill_name"],
            "skill_category": a["skill_category"],
            "course_name": a["course_name"],
            "task_count": len(a["tasks"]),
            "avg_score": round(sum(sc) / len(sc), 1),
            "max_score": max(sc),
            "min_score": min(sc),
        })
    result.sort(key=lambda x: (x["course_name"] or "", x["skill_category"] or "", x["skill_name"]))
    return result


def get_student_skill_trend(student_id, skill_id):
    """
    某学生某技能点的得分趋势（按时间）。
    与档案口径一致：已生成综合评分的任务用综合分，其余任务用评价记录分。
    """
    conn = get_conn()
    finals = conn.execute("""
        SELECT fe.task_id, fe.score, fe.created_at AS evaluated_at, t.title AS task_title
        FROM final_evaluations fe JOIN tasks t ON fe.task_id = t.id
        WHERE fe.student_id=? AND fe.skill_id=?
    """, (student_id, skill_id)).fetchall()
    final_task_ids = {f["task_id"] for f in finals}
    rows = conn.execute("""
        SELECT e.score, e.evaluated_at, t.title AS task_title, sub.task_id
        FROM evaluations e
        JOIN submissions sub ON e.submission_id = sub.id
        JOIN tasks t ON sub.task_id = t.id
        WHERE sub.student_id=? AND e.skill_id=?
        ORDER BY e.evaluated_at
    """, (student_id, skill_id)).fetchall()
    conn.close()

    merged = [{"score": f["score"], "evaluated_at": f["evaluated_at"],
               "task_title": f["task_title"]} for f in finals]
    merged += [{"score": r["score"], "evaluated_at": r["evaluated_at"],
                "task_title": r["task_title"]}
               for r in rows if r["task_id"] not in final_task_ids]
    merged.sort(key=lambda x: x["evaluated_at"] or "")
    return merged


# ===================== 成绩分析：成绩数据集 =====================
def save_quality_scores(dataset, rows):
    """
    保存一份成绩数据集（同名数据集会被覆盖）
    rows: [{"name","student_no","class_name","score"}]
    """
    conn = get_conn()
    conn.execute("DELETE FROM quality_scores WHERE dataset=?", (dataset,))
    now = datetime.now().isoformat()
    for r in rows:
        conn.execute(
            "INSERT INTO quality_scores(dataset,student_name,student_no,class_name,score,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (dataset, r.get("name", ""), r.get("student_no", ""),
             r.get("class_name", ""), float(r["score"]), now)
        )
    conn.commit()
    conn.close()


def list_quality_datasets():
    conn = get_conn()
    rows = conn.execute("""
        SELECT dataset, COUNT(*) AS total, MIN(created_at) AS created_at
        FROM quality_scores GROUP BY dataset ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_quality_scores(dataset):
    conn = get_conn()
    rows = conn.execute("""
        SELECT student_name AS name, student_no, class_name, score
        FROM quality_scores WHERE dataset=? ORDER BY score DESC
    """, (dataset,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_quality_dataset(dataset):
    conn = get_conn()
    conn.execute("DELETE FROM quality_scores WHERE dataset=?", (dataset,))
    conn.commit()
    conn.close()
