"""
技评通 · 职业技能智能评价平台 - MVP 原型（Streamlit）
支持三种评价模式：
  1. 观察法 + 档案袋评定法
  2. 作品分析法 + 档案袋评定法
  3. 综合模式（观察 + 作品分析 + 档案袋）
"""
import os
import sys
import time
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as pgo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ===== Streamlit Cloud Secrets 注入到环境变量 =====
# 云端部署时没有 .env 文件，密钥通过控制台的 Secrets 提供；
# 本地开发时走 .env（load_dotenv），下面这段会被跳过。
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, dict):
            for _kk, _vv in _v.items():
                os.environ.setdefault(_kk, str(_vv))
        else:
            os.environ.setdefault(_k, str(_v))
except Exception:
    pass

import database as db
import dbcompat
import ai_service
import evaluation
import quality
import roster
import ui
from config import (
    UPLOAD_DIR, SCORE_MIN, SCORE_MAX,
    EVAL_MODES, EVAL_MODE_OBS, EVAL_MODE_WORK, EVAL_MODE_COMBINED, DEFAULT_OBS_WEIGHT,
)

# ===================== 页面配置 =====================
st.set_page_config(
    page_title="技评通 · 职业技能智能评价平台",
    page_icon=os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "favicon.png"),
    layout="wide",
)

ui.inject_theme()

# 初始化数据库
db.init_db()

# ===================== 会话状态 =====================
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "login"


# ===================== 辅助函数 =====================
def go(page):
    st.session_state.page = page
    st.rerun()


def logout():
    st.session_state.user = None
    st.session_state.page = "login"
    st.rerun()


def render_sidebar(user):
    """侧边栏导航：品牌 + 用户卡 + 菜单"""
    with st.sidebar:
        st.markdown(f"""
        <div class="sb-brand">
          <div class="logo-row">{ui.logo(30)}<span class="logo">技评通</span></div>
          <div class="sub">Skill Evaluation</div>
        </div>
        """, unsafe_allow_html=True)

        initial = user["name"][0] if user["name"] else "U"
        role_text = "教师" if user["role"] == "teacher" else "学生"
        sub_text = "教学管理端" if user["role"] == "teacher" else f"{user['class_name'] or '未填写班级'}"
        st.markdown(f"""
        <div class="sb-user">
          <div class="sb-avatar">{initial}</div>
          <div><div class="nm">{user['name']}</div><div class="rl">{role_text} · {sub_text}</div></div>
        </div>
        """, unsafe_allow_html=True)

        if user["role"] == "teacher":
            menus = [
                ("teacher_home", "🏠  工作台"),
                ("teacher_skills", "📚  技能库"),
                ("teacher_tasks", "📝  任务管理"),
                ("teacher_eval", "✅  评价中心"),
                ("teacher_quality", "📊  成绩分析"),
                ("teacher_students", "👥  学生名单"),
                ("teacher_archives", "📈  学生档案"),
            ]
        else:
            menus = [
                ("student_home", "🏠  工作台"),
                ("student_tasks", "📝  实操任务"),
                ("student_archive", "📊  成长档案"),
            ]

        current = st.session_state.get("page")
        for page_key, label in menus:
            if st.button(label, key=f"nav_{page_key}", use_container_width=True,
                         type="primary" if current == page_key else "secondary"):
                go(page_key)

        st.divider()
        if st.button("🚪  退出登录", key="nav_logout", use_container_width=True):
            logout()
        st.markdown('<div style="font-size:.68rem;opacity:.45;padding-top:10px;">'
                    'v1.0 MVP · 作品/观察/综合三模式</div>', unsafe_allow_html=True)


# ===================== 登录/注册页 =====================
def render_login():
    ui.hero(
        "技评通 · 职业技能智能评价平台",
        "以职业技能培养为主线，用观察、作品与成长档案三重视角，记录并呈现学生的能力成长路径。",
        ["观察法", "作品分析法", "档案袋评定", "AI 辅助评分"],
        eyebrow="技评通 · VOCATIONAL SKILL EVALUATION PLATFORM",
    )

    left, right = st.columns([1.15, 0.85], gap="large")

    with left:
        ui.section("平台能力", "三种评价模式，一个成长档案")
        c1, c2, c3 = st.columns(3)
        with c1:
            ui.info_card("观察法", "教师线下观察实操过程，按标准现场打分，表格一键导出与导入。")
        with c2:
            ui.info_card("作品分析法", "学生上传实操作品，AI 依据评价标准自动评分并生成评语。")
        with c3:
            ui.info_card("档案袋评定", "每次评价自动汇入技能档案，雷达图可视化掌握程度与薄弱点。")

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        ui.section("使用流程", "五步完成一次完整评价")
        ui.steps([
            "教师建立技能库与实操任务",
            "AI 生成可量化评价标准",
            "学生提交作品 / 教师现场观察",
            "评分汇入档案并生成画像",
            "汇总班级成绩，开展成绩分析",
        ])

    with right:
        tab1, tab2 = st.tabs(["登录", "注册"])
        with tab1:
            with st.form("login_form"):
                st.markdown("**欢迎回来**")
                username = st.text_input("用户名", placeholder="请输入用户名")
                password = st.text_input("密码", type="password", placeholder="请输入密码")
                submitted = st.form_submit_button("登 录", use_container_width=True, type="primary")
                if submitted:
                    user = db.login(username, password)
                    if user:
                        st.session_state.user = user
                        st.session_state.page = "teacher_home" if user["role"] == "teacher" else "student_home"
                        st.rerun()
                    else:
                        st.error("用户名或密码错误")
            st.caption("演示账号：teacher / 123456　·　student / 123456")

        with tab2:
            with st.form("register_form"):
                st.markdown("**创建账号**")
                reg_role = st.selectbox("角色", ["student", "teacher"],
                                        format_func=lambda x: "学生" if x == "student" else "教师")
                reg_name = st.text_input("姓名")
                reg_username = st.text_input("用户名")
                reg_password = st.text_input("密码", type="password")
                c1, c2 = st.columns(2)
                with c1:
                    reg_class = st.text_input("班级（学生填写）")
                with c2:
                    reg_student_no = st.text_input("学号（学生填写）")
                submitted = st.form_submit_button("注 册", use_container_width=True, type="primary")
                if submitted:
                    if not all([reg_name, reg_username, reg_password]):
                        st.error("请填写完整信息")
                    else:
                        uid = db.create_user(reg_username, reg_password, reg_role,
                                             reg_name, reg_class, reg_student_no)
                        if uid:
                            st.success("注册成功，请切换到「登录」页登录")
                        else:
                            st.error("用户名已存在")


# ===================== 教师端：主页 =====================
def render_teacher_home():
    user = st.session_state.user
    ui.page_header(f"教师工作台", f"{user['name']}，欢迎回来 · 从今天开始新的评价任务", "🧑‍🏫")

    tasks = db.get_tasks()
    skills = db.get_skills()
    students = db.get_students()
    sub_count = sum(len(db.get_submissions_by_task(t["id"])) for t in tasks)

    ui.stat_cards([
        {"label": "技能点", "value": len(skills), "hint": "技能库累计", "tone": ""},
        {"label": "实操任务", "value": len(tasks), "hint": "已发布任务", "tone": "blue"},
        {"label": "学生人数", "value": len(students), "hint": "在册学生", "tone": "amber"},
        {"label": "作品/记录", "value": sub_count, "hint": "提交与观察记录", "tone": ""},
    ])

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    ui.section("快捷入口", "常用操作一键直达")
    c1, c2, c3, c4 = st.columns(4)
    quick = [
        (c1, "📚 技能库", "维护职业技能点与分类", "teacher_skills"),
        (c2, "📝 任务管理", "发布任务并关联技能点", "teacher_tasks"),
        (c3, "✅ 评价中心", "观察评分 / AI 评分 / 综合评分", "teacher_eval"),
        (c4, "📈 学生档案", "查看技能雷达图与薄弱点", "teacher_archives"),
    ]
    for col, title, desc, page_key in quick:
        with col:
            ui.info_card(title, desc)
            if st.button("进入 →", key=f"quick_{page_key}", use_container_width=True):
                go(page_key)

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    ui.section("最近任务", f"共 {len(tasks)} 个任务")
    if tasks:
        recent = pd.DataFrame(tasks).head(6)[["title", "eval_mode", "deadline", "created_at"]]
        recent.columns = ["任务名称", "评价模式", "截止日期", "创建时间"]
        st.dataframe(recent, use_container_width=True, hide_index=True)
    else:
        st.info("暂无任务，请到「任务管理」发布实操任务。")



# ===================== 教师端：技能库管理 =====================
def render_teacher_skills():
    ui.page_header("技能库管理", "按课程维护技能库：一门课一套技能点，支撑任务评价与成长档案", "📚")

    flash = st.session_state.pop("skill_flash", None)
    if flash:
        st.success(flash)

    courses = db.get_courses()
    unassigned = db.get_skills(0)

    # ---------- 课程管理 ----------
    with st.expander("📚 课程管理（一门课对应一个技能库）", expanded=not courses):
        c_add, c_list = st.columns([1, 1.4])
        with c_add:
            with st.form("add_course_form"):
                c_name = st.text_input("课程名称", placeholder="如：Python程序设计")
                c_desc = st.text_area("课程说明", height=80)
                if st.form_submit_button("➕ 新建课程", type="primary"):
                    if not c_name.strip():
                        st.error("请填写课程名称")
                    elif db.create_course(c_name, c_desc) is None:
                        st.error("同名课程已存在，请换一个名称")
                    else:
                        st.session_state["skill_flash"] = f"已创建课程：{c_name.strip()}"
                        st.rerun()
        with c_list:
            if courses:
                st.dataframe(pd.DataFrame([
                    {"编号": c["id"], "课程名称": c["name"],
                     "技能点数": c["skill_count"], "课程说明": c["description"] or "—"}
                    for c in courses
                ]), use_container_width=True, hide_index=True, height=180)
            else:
                st.info("还没有课程。请先新建课程，再往课程里添加技能点。")

        if courses:
            st.markdown("**课程信息维护**")
            c_opts = {f"#{c['id']}  {c['name']}": c for c in courses}
            if st.session_state.get("course_mgmt_select") not in c_opts:
                st.session_state.pop("course_mgmt_select", None)
            chosen_c = st.selectbox("选择课程", list(c_opts.keys()), key="course_mgmt_select")
            c = c_opts[chosen_c]
            with st.form("edit_course_form"):
                e1, e2 = st.columns(2)
                nc_name = e1.text_input("课程名称", value=c["name"])
                nc_desc = e2.text_input("课程说明", value=c["description"] or "")
                if st.form_submit_button("💾 保存课程信息"):
                    if not nc_name.strip():
                        st.error("课程名称不能为空")
                    elif not db.update_course(c["id"], nc_name, nc_desc):
                        st.error("课程名称与其他课程重复")
                    else:
                        st.session_state["skill_flash"] = f"已更新课程：{nc_name.strip()}"
                        st.rerun()

            st.markdown("**删除课程**")
            st.caption("课程下仍有技能点时不允许删除，请先把技能点移到其他课程或删除。")
            del_confirm = st.checkbox("我确认删除该课程", key=f"course_del_{c['id']}")
            if st.button("确认删除课程", key=f"course_delete_{c['id']}",
                         disabled=not del_confirm):
                ok, count = db.delete_course(c["id"])
                if ok:
                    st.session_state["skill_flash"] = f"已删除课程「{c['name']}」"
                    st.session_state.pop("course_mgmt_select", None)
                    st.session_state.pop("current_course", None)
                    st.rerun()
                else:
                    st.error(f"无法删除：该课程下还有 {count} 个技能点")

    if not courses:
        if unassigned:
            st.info(f"检测到 {len(unassigned)} 个历史技能点尚未归属课程，创建课程后可一键归入。")
        st.info("请先创建课程，再维护该课程的技能库。")
        return

    # ---------- 筛选 ----------
    st.divider()
    ui.section("筛选技能点", "按课程、分类与关键词定位技能点，支持批量处理")

    course_names = {c["id"]: c["name"] for c in courses}
    total_all = sum(c["skill_count"] for c in courses) + len(unassigned)
    course_filter_opts = {"全部课程": None}
    for c in courses:
        course_filter_opts[c["name"]] = c["id"]
    if unassigned:
        course_filter_opts["未归属课程"] = 0
    if st.session_state.get("skill_filter_course") not in course_filter_opts:
        st.session_state.pop("skill_filter_course", None)

    f1, f2, f3 = st.columns([1.2, 1, 1.2])
    with f1:
        sel_filter = st.selectbox(
            "课程筛选", list(course_filter_opts.keys()), key="skill_filter_course",
            format_func=lambda x: (
                f"{x}（{total_all} 个技能点）" if x == "全部课程"
                else f"{x}（{len(unassigned)} 个技能点）" if x == "未归属课程"
                else f"{x}（{next((c['skill_count'] for c in courses if c['name'] == x), 0)} 个技能点）"
            ),
        )
    scope = course_filter_opts[sel_filter]
    scope_skills = db.get_skills() if scope is None else db.get_skills(scope)

    cats = sorted({(s["category"] or "").strip() for s in scope_skills if (s["category"] or "").strip()})
    cat_opts = ["全部分类"] + cats
    if any(not (s["category"] or "").strip() for s in scope_skills):
        cat_opts.append("未分类")
    if st.session_state.get("skill_filter_cat") not in cat_opts:
        st.session_state.pop("skill_filter_cat", None)
    with f2:
        sel_cat = st.selectbox("分类筛选", cat_opts, key="skill_filter_cat")
    with f3:
        kw = st.text_input("关键词搜索", placeholder="技能名称 / 描述", key="skill_filter_kw")

    keyword = kw.strip().lower()
    filtered = []
    for s in scope_skills:
        cat = (s["category"] or "").strip()
        if sel_cat == "未分类":
            if cat:
                continue
        elif sel_cat != "全部分类" and cat != sel_cat:
            continue
        if keyword and keyword not in (s["name"] + (s["description"] or "")).lower():
            continue
        filtered.append(s)

    ui.stat_cards([
        {"label": "筛选结果", "value": len(filtered), "hint": f"当前范围共 {len(scope_skills)} 个技能点", "tone": ""},
        {"label": "覆盖课程", "value": len({s["course_id"] for s in filtered}), "hint": "结果涉及的课程数", "tone": "blue"},
        {"label": "分类数量", "value": len({(s["category"] or "未分类").strip() or "未分类" for s in filtered}),
         "hint": "结果涉及的分类数", "tone": "amber"},
    ])

    if unassigned:
        st.info(f"检测到 {len(unassigned)} 个技能点尚未归属任何课程。")
        a1, a2 = st.columns([1.2, 1])
        with a1:
            assign_opts = {c["name"]: c["id"] for c in courses}
            target_assign = st.selectbox("归入课程", list(assign_opts.keys()), key="assign_target_course")
        with a2:
            st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
            if st.button(f"一键将未归属技能点归入「{target_assign}」", key="assign_unassigned",
                         use_container_width=True):
                n = db.assign_unassigned_skills(assign_opts[target_assign])
                st.session_state["skill_flash"] = f"已将 {n} 个技能点归入「{target_assign}」"
                st.rerun()

    # ---------- 新增 ----------
    st.divider()
    ui.section("新增技能点", "添加到指定课程的技能库")
    add_opts = {c["name"]: c["id"] for c in courses}
    default_add = sel_filter if sel_filter in add_opts else courses[0]["name"]
    with st.form("add_skill"):
        c1, c2 = st.columns(2)
        with c1:
            s_name = st.text_input("技能名称")
            s_category = st.text_input("分类（如：专业核心技能、职业素养）")
            s_course = st.selectbox("所属课程", list(add_opts.keys()),
                                    index=list(add_opts).index(default_add))
        with c2:
            s_desc = st.text_area("技能描述")
        if st.form_submit_button("添加技能点"):
            if s_name:
                db.create_skill(s_name, s_desc, s_category,
                                st.session_state.user["id"], add_opts[s_course])
                st.session_state["skill_flash"] = f"已添加技能点：{s_name}（{s_course}）"
                st.rerun()
            else:
                st.error("请填写技能名称")

    # ---------- 列表 ----------
    st.divider()
    ui.section(f"技能库 · {sel_filter}", f"筛选结果 {len(filtered)} 个技能点")
    if filtered:
        st.dataframe(pd.DataFrame([
            {"编号": s["id"], "技能名称": s["name"],
             "所属课程": course_names.get(s["course_id"], "未归属课程"),
             "分类": s["category"] or "—", "技能描述": s["description"] or "—"}
            for s in filtered
        ]), use_container_width=True, hide_index=True)
    else:
        st.info("当前筛选条件下没有技能点。")

    # ---------- 批量操作 ----------
    if filtered:
        with st.expander(f"⚡ 批量操作（当前筛选 {len(filtered)} 个技能点）"):
            batch_labels = {
                f"#{s['id']}  {s['name']}（{course_names.get(s['course_id'], '未归属课程')} · "
                f"{s['category'] or '未分类'}）": s
                for s in filtered
            }
            prev = st.session_state.get("skill_batch_select", [])
            valid_prev = [v for v in prev if v in batch_labels]
            if valid_prev != prev:
                st.session_state["skill_batch_select"] = valid_prev
            picked = st.multiselect("选择技能点（可多选）", list(batch_labels.keys()),
                                    key="skill_batch_select")
            sel_skills = [batch_labels[x] for x in picked]
            action = st.radio("批量操作类型", ["移动到课程", "设置分类", "删除技能点"],
                              horizontal=True, key="skill_batch_action")

            if action == "移动到课程":
                move_opts = {c["name"]: c["id"] for c in courses}
                move_opts["未归属课程"] = None
                b1, b2 = st.columns([1.2, 1])
                with b1:
                    target_move = st.selectbox("目标课程", list(move_opts.keys()),
                                               key="skill_batch_move_course")
                with b2:
                    st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
                    if st.button(f"批量移动到「{target_move}」（{len(sel_skills)} 个）",
                                 key="do_batch_move", disabled=not sel_skills, use_container_width=True):
                        n = db.batch_move_skills([s["id"] for s in sel_skills],
                                                 move_opts[target_move])
                        st.session_state["skill_flash"] = f"已将 {n} 个技能点移动到「{target_move}」"
                        st.session_state.pop("skill_batch_select", None)
                        st.session_state.pop("skill_mgmt_select", None)
                        st.rerun()
            elif action == "设置分类":
                b1, b2 = st.columns([1.2, 1])
                with b1:
                    new_cat = st.text_input("新分类名称", placeholder="留空表示设为未分类",
                                            key="skill_batch_category")
                with b2:
                    st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
                    if st.button(f"批量设置分类（{len(sel_skills)} 个）", key="do_batch_category",
                                 disabled=not sel_skills, use_container_width=True):
                        n = db.batch_set_category([s["id"] for s in sel_skills], new_cat)
                        cat_text = new_cat.strip() or "未分类"
                        st.session_state["skill_flash"] = f"已将 {n} 个技能点分类设为「{cat_text}」"
                        st.session_state.pop("skill_batch_select", None)
                        st.rerun()
            else:
                st.caption("批量删除会逐个检查引用：已有评价记录的技能点将跳过，以保护学生成长档案。")
                confirm_batch = st.checkbox("我确认批量删除所选技能点（不可恢复）",
                                            key="skill_batch_del_confirm")
                if st.button("确认批量删除", type="primary", key="do_batch_delete",
                             disabled=not (sel_skills and confirm_batch), use_container_width=True):
                    ok_count, blocked = 0, []
                    for sk in sel_skills:
                        ok, usage = db.delete_skill(sk["id"])
                        if ok:
                            ok_count += 1
                        else:
                            blocked.append(f"{sk['name']}（{usage['evaluations'] + usage['finals']} 条评价）")
                    msg = f"已删除 {ok_count} 个技能点"
                    if blocked:
                        msg += f"；跳过 {len(blocked)} 个已有评价记录：" + "、".join(blocked)
                    st.session_state["skill_flash"] = msg
                    st.session_state.pop("skill_batch_select", None)
                    st.session_state.pop("skill_mgmt_select", None)
                    st.rerun()

    if not filtered:
        return

    # ---------- 修改 / 删除 ----------
    st.divider()
    ui.section("修改 / 删除技能点", "可调整所属课程；已有评价记录的技能点不可删除")
    options = {f"#{s['id']}  {s['name']}（{s['category'] or '未分类'}）": s for s in filtered}
    if st.session_state.get("skill_mgmt_select") not in options:
        st.session_state.pop("skill_mgmt_select", None)
    chosen = st.selectbox("选择技能点", list(options.keys()), key="skill_mgmt_select")
    s = options[chosen]
    usage = db.get_skill_usage(s["id"])
    st.caption(f"引用情况：被 {usage['tasks']} 个任务关联 ｜ "
               f"评价记录 {usage['evaluations'] + usage['finals']} 条")

    course_move_opts = {c["name"]: c["id"] for c in courses}
    course_move_opts["未归属课程"] = None
    cur_course_name = next((c["name"] for c in courses if c["id"] == s.get("course_id")), "未归属课程")
    with st.form("edit_skill_form"):
        e1, e2 = st.columns(2)
        new_name = e1.text_input("技能名称", value=s["name"])
        new_category = e2.text_input("分类", value=s["category"] or "")
        move_labels = list(course_move_opts.keys())
        new_course = st.selectbox(
            "所属课程", move_labels,
            index=move_labels.index(cur_course_name) if cur_course_name in move_labels else 0,
        )
        new_desc = st.text_area("技能描述", value=s["description"] or "")
        if st.form_submit_button("💾 保存修改", type="primary"):
            if not new_name.strip():
                st.error("技能名称不能为空")
            else:
                db.update_skill(s["id"], new_name, new_desc, new_category,
                                course_move_opts[new_course])
                st.session_state["skill_flash"] = f"已更新技能点：{new_name.strip()}（{new_course}）"
                st.rerun()

    with st.expander("🗑 删除该技能点（不可恢复）"):
        st.caption("删除前会检查引用：若已有评价记录，为保护学生成长档案将不允许删除。")
        confirm = st.checkbox("我确认删除该技能点", key=f"skill_del_confirm_{s['id']}")
        if st.button("确认删除", key=f"skill_delete_{s['id']}", disabled=not confirm,
                     use_container_width=True):
            ok, usage = db.delete_skill(s["id"])
            if ok:
                msg = f"已删除技能点「{s['name']}」"
                if usage["tasks"]:
                    msg += f"，并解除 {usage['tasks']} 个任务的关联"
                st.session_state["skill_flash"] = msg
                st.session_state.pop("skill_mgmt_select", None)
                st.rerun()
            else:
                st.error(
                    f"无法删除：该技能点已有 {usage['evaluations'] + usage['finals']} 条评价记录。"
                    "可修改名称/描述或移动到其他课程，以保留历史档案。"
                )


# ===================== 教师端：任务管理 =====================
def task_range_text(task):
    cls = (task.get("target_class") or "").strip()
    grp = (task.get("target_group") or "").strip()
    if not cls and not grp:
        return "全体学生"
    return " · ".join([p for p in (cls, grp) if p])


def task_visible_to(task, user):
    """学生是否属于任务发布范围"""
    cls = (task.get("target_class") or "").strip()
    grp = (task.get("target_group") or "").strip()
    if cls and (user.get("class_name") or "").strip() != cls:
        return False
    if grp and (user.get("group_name") or "").strip() != grp:
        return False
    return True


def student_task_done(task_id, student_id):
    """学生是否已完成任务：已有作品提交、观察记录或综合评分"""
    return bool(
        db.get_submission_by_task_student(task_id, student_id, eval_source="work")
        or db.get_submission_by_task_student(task_id, student_id, eval_source="observation")
        or db.get_final_evaluations(task_id, student_id)
    )


def render_teacher_tasks():
    flash = st.session_state.pop("task_flash", None)
    if flash:
        st.success(flash)
    ui.page_header("任务管理", "发布实操任务并关联技能点，任务决定学生要提交什么、按什么标准评", "📝")

    students_all = db.get_students(include_inactive=False)
    class_opts = ["全部班级"] + sorted({s["class_name"] for s in students_all if s.get("class_name")})
    group_opts = ["全部小组"] + sorted({s.get("group_name") for s in students_all if s.get("group_name")})

    courses = db.get_courses()
    course_opts = {c["name"]: c["id"] for c in courses}

    ui.section("发布新实操任务")
    with st.form("create_task"):
        t_title = st.text_input("任务标题")
        t_desc = st.text_area("任务说明与要求")
        c1, c2 = st.columns(2)
        with c1:
            t_course = st.selectbox("所属课程", list(course_opts.keys()) or ["暂无课程"])
        with c2:
            t_mode = st.selectbox("评价模式", EVAL_MODES)
        r1, r2, r3 = st.columns(3)
        with r1:
            t_deadline = st.date_input("截止日期")
        with r2:
            t_target_cls = st.selectbox("发布班级", class_opts)
        with r3:
            t_target_grp = st.selectbox("发布小组（可选）", group_opts)
        t_obs_weight = st.number_input(
            "观察评价占比（仅综合模式生效）",
            min_value=0.0, max_value=1.0, value=DEFAULT_OBS_WEIGHT, step=0.1,
        )
        if st.form_submit_button("创建任务"):
            if not course_opts:
                st.error("请先在「技能库」创建课程，再发布任务")
            elif not t_title.strip():
                st.error("请填写任务标题")
            else:
                tid = db.create_task(
                    t_title, t_desc, str(t_deadline), t_mode,
                    st.session_state.user["id"], t_obs_weight,
                    "" if t_target_cls == "全部班级" else t_target_cls,
                    "" if t_target_grp == "全部小组" else t_target_grp,
                    course_id=course_opts[t_course],
                )
                st.success(f"任务「{t_title}」已创建，请关联技能点。")
                st.session_state.editing_task_id = tid
                time.sleep(0.5)
                go("teacher_task_detail")

    st.divider()
    tasks = db.get_tasks()
    filter_opts = {"全部课程": None}
    for c in courses:
        filter_opts[c["name"]] = c["id"]
    if any(not t.get("course_name") for t in tasks):
        filter_opts["未归属课程"] = 0
    if st.session_state.get("task_filter_course") not in filter_opts:
        st.session_state.pop("task_filter_course", None)

    lf1, lf2 = st.columns([1, 2.2])
    with lf1:
        sel_task_course = st.selectbox("按课程筛选任务", list(filter_opts.keys()),
                                       key="task_filter_course")
    course_scope = filter_opts[sel_task_course]
    if course_scope is None:
        shown_tasks = tasks
    elif course_scope == 0:
        shown_tasks = [t for t in tasks if not t.get("course_name")]
    else:
        shown_tasks = [t for t in tasks if t.get("course_id") == course_scope]

    with lf2:
        st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        st.caption(f"当前筛选：{len(shown_tasks)} 个任务（全部共 {len(tasks)} 个）")

    ui.section("任务列表", f"共 {len(shown_tasks)} 个任务")
    if shown_tasks:
        for t in shown_tasks:
            total, done = db.get_task_stats(t["id"])
            rate = f"{done / total * 100:.0f}%" if total else "—"
            with st.expander(f"📌 {t['title']}（截止：{t['deadline']}）· 完成 {done}/{total}"):
                st.write(f"**说明**：{t['description']}")
                st.write(f"**所属课程**：{t.get('course_name') or '未归属课程'}")
                st.write(f"**评价模式**：{t['eval_mode']}")
                st.write(f"**发布范围**：{task_range_text(t)}")
                st.write(f"**完成情况**：已完成 {done} 人 / 应完成 {total} 人（{rate}）")
                skills = db.get_task_skills(t["id"])
                if skills:
                    st.write(f"**关联技能点（{len(skills)}个）**：")
                    for s in skills:
                        st.write(f"  - {s['skill_name']}（权重：{s['weight']}）")
                else:
                    st.warning("尚未关联技能点")
                if st.button("作答情况 / 编辑任务", key=f"edit_{t['id']}"):
                    st.session_state.editing_task_id = t["id"]
                    go("teacher_task_detail")
                st.markdown("---")
                st.caption("删除任务会同时清除关联技能点、学生作品/观察记录、评价记录、综合评分与督促记录，且不可恢复。")
                del_ok = st.checkbox("我确认删除该任务及其全部记录", key=f"task_del_{t['id']}")
                if st.button("删除任务", key=f"task_delete_{t['id']}", disabled=not del_ok):
                    db.delete_task(t["id"])
                    st.session_state["task_flash"] = f"已删除任务「{t['title']}」及其全部记录"
                    st.rerun()
    else:
        st.info("当前筛选条件下没有任务")


# ===================== 教师端：任务详情（关联技能点+AI生成评价标准）=====================
def render_teacher_task_detail():
    tid = st.session_state.get("editing_task_id")
    if not tid:
        go("teacher_tasks")
        return
    task = db.get_task(tid)
    if not task:
        go("teacher_tasks")
        return

    ui.page_header("任务详情", task["title"], "📝")

    st.write(f"**任务说明**：{task['description']}")
    st.markdown(f"**截止日期**：{task['deadline']}　　**评价模式**：{ui.mode_chip(task['eval_mode'])}",
                unsafe_allow_html=True)

    courses = db.get_courses()
    task_skills = db.get_task_skills(tid)
    course = next((c for c in courses if c["id"] == task.get("course_id")), None)
    st.write(f"**所属课程**：{course['name'] if course else '未设置'}")

    if not course:
        st.warning("该任务尚未设置所属课程。设置后，任务只能关联该课程的技能点。")
        with st.form("task_course_form"):
            c_opts = {c["name"]: c["id"] for c in courses}
            sel_task_c = st.selectbox("任务所属课程", list(c_opts.keys()) or ["暂无课程"])
            if st.form_submit_button("保存所属课程"):
                if c_opts:
                    db.update_task_course(tid, c_opts[sel_task_c])
                    st.success("已设置任务所属课程")
                    st.rerun()
                else:
                    st.error("请先在「技能库」创建课程")

    if task["eval_mode"] == EVAL_MODE_COMBINED:
        weight = st.number_input(
            "观察评价占比",
            min_value=0.0, max_value=1.0,
            value=float(task.get("obs_weight") or DEFAULT_OBS_WEIGHT), step=0.1,
            key=f"obs_weight_{tid}",
        )
        if st.button("保存权重"):
            db.update_task_obs_weight(tid, weight)
            st.success("权重已保存")
            st.rerun()

    # ---------- 发布范围 ----------
    students_all = db.get_students(include_inactive=False)
    class_opts = ["全部班级"] + sorted({s["class_name"] for s in students_all if s.get("class_name")})
    group_opts = ["全部小组"] + sorted({s.get("group_name") for s in students_all if s.get("group_name")})
    cur_cls = (task.get("target_class") or "").strip()
    cur_grp = (task.get("target_group") or "").strip()

    st.divider()
    ui.section("发布范围", "按班级或小组发布，学生端只显示与自己相关的任务")
    with st.form("task_target_form"):
        c1, c2 = st.columns(2)
        sel_cls = c1.selectbox(
            "发布班级", class_opts,
            index=class_opts.index(cur_cls) if cur_cls in class_opts else 0,
        )
        sel_grp = c2.selectbox(
            "发布小组（可选）", group_opts,
            index=group_opts.index(cur_grp) if cur_grp in group_opts else 0,
        )
        if st.form_submit_button("保存发布范围"):
            db.update_task_target(
                tid,
                "" if sel_cls == "全部班级" else sel_cls,
                "" if sel_grp == "全部小组" else sel_grp,
            )
            st.success("发布范围已保存")
            st.rerun()
    st.caption(f"当前发布范围：{task_range_text(task)}　应完成学生 {len(db.get_task_recipients(tid))} 人")

    # ---------- 作答情况与督促 ----------
    recipients = db.get_task_recipients(tid)
    sub_status = db.get_task_submission_status(tid)
    done_students, undone_students = [], []
    for s in recipients:
        info = sub_status.get(s["id"])
        if info:
            done_students.append((s, info))
        else:
            undone_students.append(s)

    total = len(recipients)
    done_n = len(done_students)
    rate = f"{done_n / total * 100:.0f}%" if total else "—"
    remind_counts = db.get_reminder_counts(tid)

    ui.section("作答情况", "查看已完成 / 未完成学生，并向未完成学生发起督促")
    ui.stat_cards([
        {"label": "应完成", "value": total, "hint": "发布范围内的在册学生", "tone": ""},
        {"label": "已完成", "value": done_n, "hint": "已提交作品或已有观察记录", "tone": ""},
        {"label": "未完成", "value": len(undone_students), "hint": "待提交学生", "tone": "amber"},
        {"label": "完成率", "value": rate, "hint": "已完成 / 应完成", "tone": "amber"},
    ])

    tab_done, tab_undone, tab_remind = st.tabs([
        f"✅ 已完成（{done_n}）",
        f"⏳ 未完成（{len(undone_students)}）",
        "📨 督促记录",
    ])

    with tab_done:
        if done_students:
            df_done = pd.DataFrame([
                {
                    "班级": s.get("class_name") or "—",
                    "小组": s.get("group_name") or "—",
                    "学号": s.get("student_no") or "—",
                    "姓名": s["name"],
                    "最近提交": (info.get("last_time") or "").replace("T", " ")[:16] or "—",
                    "提交次数": info.get("sub_count", 0),
                    "评价状态": "已评分" if info.get("eval_count") else "待评分",
                }
                for s, info in done_students
            ])
            st.dataframe(df_done, use_container_width=True, hide_index=True, height=420)
        else:
            st.info("暂无学生完成该任务。")

    with tab_undone:
        if undone_students:
            df_undone = pd.DataFrame([
                {
                    "班级": s.get("class_name") or "—",
                    "小组": s.get("group_name") or "—",
                    "学号": s.get("student_no") or "—",
                    "姓名": s["name"],
                    "登录账号": s["username"],
                    "已督促次数": remind_counts.get(s["id"], {}).get("count", 0),
                }
                for s in undone_students
            ])
            st.dataframe(df_undone, use_container_width=True, hide_index=True, height=420)
            st.download_button(
                "⬇️ 导出未完成名单（CSV）",
                data=df_undone.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"未完成名单_{task['title']}.csv",
                mime="text/csv",
                key=f"undone_csv_{tid}",
            )
        else:
            st.success("发布范围内的学生均已完成。")

    with tab_remind:
        if not undone_students:
            st.success("暂无未完成学生，无需督促。")
        else:
            default_tpl = ("【任务提醒】{name}同学：你尚未完成「{task}」，截止时间为 {deadline}。"
                           "请尽快登录技评通平台提交作品，如有疑问请联系任课教师。")
            tpl = st.text_area("督促通知模板", value=default_tpl, height=110,
                               key=f"remind_tpl_{tid}")
            st.caption("可用占位符：{name} 姓名、{task} 任务名称、{deadline} 截止日期、"
                       "{class} 班级、{group} 小组")

            options = {}
            for s in undone_students:
                label = (f"{s['name']}（{s.get('class_name') or '未分班'}"
                         f"{'/' + s['group_name'] if s.get('group_name') else ''}）")
                options[label] = s
            chosen = st.multiselect("督促对象", list(options.keys()),
                                    default=list(options.keys()), key=f"remind_sel_{tid}")

            if st.button("📨 生成督促通知并记录", type="primary",
                         key=f"remind_btn_{tid}", disabled=not chosen):
                items, texts = [], []
                for label in chosen:
                    s = options[label]
                    msg = (tpl.replace("{name}", s["name"])
                           .replace("{task}", task["title"])
                           .replace("{deadline}", task["deadline"] or "未设置")
                           .replace("{class}", s.get("class_name") or "")
                           .replace("{group}", s.get("group_name") or ""))
                    items.append((s["id"], msg))
                    texts.append(f"—— {s['name']}（{s.get('student_no') or ''}）——\n{msg}")
                n = db.add_reminders(tid, items)
                st.session_state[f"remind_texts_{tid}"] = "\n\n".join(texts)
                st.success(f"已记录 {n} 条督促通知，可复制下方内容发送到班级群")

            texts = st.session_state.get(f"remind_texts_{tid}")
            if texts:
                st.text_area("督促通知内容（可复制）", value=texts, height=260,
                             key=f"remind_copy_{tid}")
                st.download_button(
                    "⬇️ 下载督促通知（TXT）",
                    data=texts.encode("utf-8-sig"),
                    file_name=f"督促通知_{task['title']}.txt",
                    mime="text/plain",
                    key=f"remind_dl_{tid}",
                )

            history = db.get_task_reminders(tid)
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            ui.section("督促记录", f"共 {len(history)} 条")
            if history:
                st.dataframe(pd.DataFrame([
                    {
                        "时间": (h["created_at"] or "").replace("T", " ")[:16],
                        "学生": h["student_name"],
                        "班级": h["class_name"] or "—",
                        "小组": h["group_name"] or "—",
                        "渠道": h["channel"],
                        "内容": (h["message"][:60] + "…") if len(h["message"]) > 60 else h["message"],
                    }
                    for h in history
                ]), use_container_width=True, hide_index=True, height=260)
            else:
                st.caption("尚未发起督促。")

    st.divider()
    ui.section("关联技能点", "任务->技能点->评价标准，形成可记录的成长链条")

    # 添加技能点：只能从任务所属课程的技能库中选择，且不重复关联
    if not course:
        st.info("请先设置任务所属课程，再关联技能点。")
    else:
        course_skills = db.get_skills(course["id"])
        linked = {ts["skill_id"] for ts in task_skills}
        available = [s for s in course_skills if s["id"] not in linked]
        if available:
            with st.form("add_task_skill"):
                skill_options = {f"{s['name']}（{s['category'] or '未分类'}）": s["id"]
                                 for s in available}
                selected = st.selectbox("选择技能点", list(skill_options.keys()))
                weight = st.number_input("权重", min_value=0.1, max_value=10.0, value=1.0, step=0.1)
                if st.form_submit_button("关联到此任务"):
                    db.add_task_skill(tid, skill_options[selected], "", weight)
                    st.success("已关联技能点")
                    st.rerun()
        elif course_skills:
            st.success(f"「{course['name']}」技能库中的技能点已全部关联")
        else:
            st.warning(f"「{course['name']}」下暂无技能点，请先到「技能库」添加")

    st.divider()
    # 已关联技能点 & AI生成评价标准
    if task_skills:
        ui.section("评价标准设置", "AI 生成后可手动修改")
        ai_status = "🟢 AI已配置" if ai_service.is_ai_available() else "🔴 AI未配置（将使用默认模板）"
        st.caption(ai_status)

        for ts in task_skills:
            with st.expander(f"🎯 {ts['skill_name']}（权重：{ts['weight']}）", expanded=True):
                st.write(f"**技能描述**：{ts['skill_desc']}")
                criteria = st.text_area(
                    "评价标准（可手动编辑或用AI生成）",
                    value=ts["criteria"],
                    height=200,
                    key=f"criteria_{ts['id']}",
                )
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("🤖 AI 生成评价标准", key=f"ai_{ts['id']}"):
                        with st.spinner("AI 正在生成评价标准..."):
                            new_criteria = ai_service.generate_criteria(
                                ts["skill_name"], ts["skill_desc"], task["title"], task["description"]
                            )
                        db.update_task_skill_criteria(ts["id"], new_criteria)
                        st.success("AI 评价标准已生成")
                        st.rerun()
                with c2:
                    if st.button("💾 保存修改", key=f"save_{ts['id']}"):
                        db.update_task_skill_criteria(ts["id"], criteria)
                        st.success("评价标准已保存")
    else:
        st.info("请先关联技能点")


# ===================== 教师端：作品评价 =====================
def render_teacher_eval():
    ui.page_header("评价中心", "按任务模式自动切换：观察评分 / AI 作品评分 / 综合加权", "✅")

    tasks = db.get_tasks()
    if not tasks:
        st.info("暂无任务")
        return

    task_options = {t["title"]: t["id"] for t in tasks}
    selected_title = st.selectbox("选择实操任务", list(task_options.keys()))
    tid = task_options[selected_title]
    task = db.get_task(tid)

    mode = task["eval_mode"]
    st.markdown(f"当前任务评价模式：{ui.mode_chip(mode)}", unsafe_allow_html=True)

    if mode == EVAL_MODE_OBS:
        render_observation_panel(tid, task)
    elif mode == EVAL_MODE_COMBINED:
        tab1, tab2, tab3 = st.tabs(["① 线下观察评价", "② 作品评价", "③ 综合评分"])
        with tab1:
            render_observation_panel(tid, task)
        with tab2:
            render_work_panel(tid, task)
        with tab3:
            render_combined_panel(tid, task)
    else:
        render_work_panel(tid, task)


def render_work_panel(tid, task):
    submissions = db.get_submissions_by_task(tid, eval_source="work")
    ui.section("作品提交情况", f"{len(submissions)} 份作品待评价")

    if submissions:
        # 提交情况总览表
        overview = []
        for s in submissions:
            evals = db.get_evaluations_by_submission(s["id"])
            has_eval = len(evals) > 0
            overall = round(sum(e["score"] for e in evals) / len(evals), 1) if evals else 0
            overview.append({
                "学生": s["student_name"],
                "班级": s["class_name"],
                "学号": s["student_no"],
                "文件": s["file_name"],
                "提交时间": s["submitted_at"][:16],
                "已评价": "✅" if has_eval else "❌",
                "综合分": overall if has_eval else "-",
            })
        st.dataframe(pd.DataFrame(overview), use_container_width=True, hide_index=True)

        st.divider()
        ui.section("逐份评价", "AI 评分后由教师确认")
        for s in submissions:
            with st.expander(f"📄 {s['student_name']} - {s['file_name']}（{s['submitted_at'][:16]}）"):
                # 显示作品内容
                content_text = s.get("content_text", "")
                if s["file_name"]:
                    st.write(f"**提交文件**：{s['file_name']}")
                if content_text:
                    with st.expander("查看作品内容", expanded=False):
                        st.text(content_text[:2000])

                task_skills = db.get_task_skills(tid)

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🤖 AI 自动评分", key=f"ai_grade_{s['id']}"):
                        with st.spinner("AI 正在评分，请稍候..."):
                            results = evaluation.run_ai_grading(s["id"])
                        if results:
                            st.success(f"AI 评分完成，共 {len(results)} 个技能点")
                            st.rerun()
                        else:
                            st.warning("该任务未关联技能点，无法评分")
                with col2:
                    if st.button("🗑️ 清除评价", key=f"clear_{s['id']}"):
                        db.delete_evaluations_by_submission(s["id"])
                        st.rerun()

                # 评分编辑区
                st.markdown("**评分与评语**")
                existing_evals = db.get_evaluations_by_submission(s["id"])
                eval_map = {e["skill_id"]: e for e in existing_evals}

                with st.form(f"grade_form_{s['id']}"):
                    skill_scores = {}
                    skill_comments = {}
                    for ts in task_skills:
                        sid_skill = ts["skill_id"]
                        existing = eval_map.get(sid_skill)
                        default_score = existing["score"] if existing else 0.0
                        default_comment = existing["comment"] if existing else ""
                        evaluator_tag = f"（{existing['evaluator']}评）" if existing else ""

                        st.markdown(f"**{ts['skill_name']}** {evaluator_tag}")
                        if ts["criteria"]:
                            with st.expander("查看评价标准", expanded=False):
                                st.text(ts["criteria"])
                        c1, c2 = st.columns([1, 3])
                        with c1:
                            score = st.slider(
                                "评分", float(SCORE_MIN), float(SCORE_MAX), 
                                float(default_score),
                                key=f"score_{s['id']}_{sid_skill}",
                            )
                            skill_scores[sid_skill] = score
                        with c2:
                            comment = st.text_area(
                                "评语", value=default_comment, height=80,
                                key=f"comment_{s['id']}_{sid_skill}",
                            )
                            skill_comments[sid_skill] = comment

                    if st.form_submit_button("💾 保存教师评分", use_container_width=True):
                        evaluation.save_teacher_grading(s["id"], skill_scores, skill_comments)
                        st.success("教师评分已保存")
                        st.rerun()

                # 综合结果
                if existing_evals:
                    overall = evaluation.get_submission_overall(s["id"])
                    st.info(f"**综合得分：{overall['overall_score']} 分**")
                    with st.expander("AI 掌握度分析", expanded=False):
                        st.write(overall["mastery"])
    else:
        st.info("暂无学生提交作品")


# ===================== 教师端：观察法评价面板 =====================
def render_observation_panel(tid, task):
    ui.section("线下观察评价", "导出评价表 → 现场打分 → 导入回平台")
    task_skills = db.get_task_skills(tid)
    if not task_skills:
        st.warning("该任务尚未关联技能点，请先在任务详情中关联技能点，再导出评价表。")
        return

    st.markdown("流程：**① 导出评价表** → 线下观察实操时逐项打分写评语 → **② 导入评价表**，分数自动写入学生成长档案")

    c1, c2 = st.columns(2)
    with c1:
        try:
            tpl = evaluation.build_observation_template(tid)
            st.download_button(
                "📥 导出观察评价表（Excel）",
                data=tpl,
                file_name=f"观察评价表_{task['title']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"模板生成失败：{e}")
    with c2:
        uploaded = st.file_uploader("导入填写后的评价表", type=["xlsx"], key=f"obs_upload_{tid}")
        if uploaded is not None:
            if st.button("📤 导入评分", key=f"obs_import_{tid}", use_container_width=True):
                result = evaluation.import_observation_scores(tid, uploaded.getvalue())
                if result["errors"]:
                    for err in result["errors"]:
                        st.error(err)
                if result["skipped"]:
                    with st.expander(f"跳过 {len(result['skipped'])} 条记录"):
                        for sk in result["skipped"]:
                            st.write(f"- {sk}")
                st.success(f"导入完成，成功录入 {result['imported']} 名学生")

    st.divider()
    students = db.get_students()
    if not students:
        st.info("暂无学生，请先导入学生名单（注册时填写班级+学号）")
        return

    obs_subs = {s["student_id"]: s for s in db.get_submissions_by_task(tid, eval_source="observation")}
    recorded = sum(
        1 for stu in students
        if obs_subs.get(stu["id"]) and db.get_evaluations_by_submission(obs_subs[stu["id"]]["id"])
    )
    ui.section("观察评分录入与查看", f"已录入 {recorded} / {len(students)} 人")

    for stu in students:
        sub = obs_subs.get(stu["id"])
        evals = db.get_evaluations_by_submission(sub["id"]) if sub else []
        eval_map = {e["skill_id"]: e for e in evals}
        if evals:
            recorded += 1
        overall = round(sum(e["score"] for e in evals) / len(evals), 1) if evals else None
        tag = f"已录入 {overall} 分" if evals else "未录入"
        with st.expander(f"👤 {stu['name']}（{stu['class_name']}-{stu['student_no']}）· {tag}"):
            with st.form(f"obs_form_{tid}_{stu['id']}"):
                scores, comments = {}, {}
                for ts in task_skills:
                    sid_skill = ts["skill_id"]
                    existing = eval_map.get(sid_skill)
                    st.markdown(f"**{ts['skill_name']}**")
                    if ts["criteria"]:
                        with st.expander("查看评价标准", expanded=False):
                            st.text(ts["criteria"])
                    cc1, cc2 = st.columns([1, 3])
                    with cc1:
                        scores[sid_skill] = st.slider(
                            "评分", float(SCORE_MIN), float(SCORE_MAX), 
                            float(existing["score"]) if existing else 0.0,
                            key=f"obs_score_{tid}_{stu['id']}_{sid_skill}",
                        )
                    with cc2:
                        comments[sid_skill] = st.text_area(
                            "评语", value=existing["comment"] if existing else "",
                            height=80, key=f"obs_cmt_{tid}_{stu['id']}_{sid_skill}",
                        )
                if st.form_submit_button("💾 保存该生观察评分", use_container_width=True):
                    obs_id = db.create_observation_record(tid, stu["id"])
                    evaluation.save_teacher_grading(obs_id, scores, comments)
                    st.success(f"已保存 {stu['name']} 的观察评分")
                    st.rerun()

    st.caption(f"已录入观察评分：{recorded} / {len(students)} 人")


# ===================== 教师端：综合模式汇总 =====================
def render_combined_panel(tid, task):
    ui.section("综合评分", "观察评分与作品评分按权重合并，写入最终档案")
    task_skills = db.get_task_skills(tid)
    if not task_skills:
        st.warning("该任务尚未关联技能点")
        return

    weight = st.slider(
        "观察评价占比", 0.0, 1.0,
        float(task.get("obs_weight") or DEFAULT_OBS_WEIGHT), 0.1,
        key=f"comb_w_{tid}",
    )
    st.caption(f"综合得分 = 观察评分 × {weight:.0%} + 作品评分 × {1 - weight:.0%}（缺失一侧时按已有得分计算）")

    students = db.get_students()
    if not students:
        st.info("暂无学生")
        return

    obs_subs = {s["student_id"]: s for s in db.get_submissions_by_task(tid, eval_source="observation")}
    work_subs = {s["student_id"]: s for s in db.get_submissions_by_task(tid, eval_source="work")}

    def _overall(sub):
        if not sub:
            return None
        ev = db.get_evaluations_by_submission(sub["id"])
        return round(sum(e["score"] for e in ev) / len(ev), 1) if ev else None

    rows = []
    for stu in students:
        finals = db.get_final_evaluations(tid, stu["id"])
        final_overall = round(sum(f["score"] for f in finals) / len(finals), 1) if finals else None
        rows.append({
            "student": stu,
            "obs": _overall(obs_subs.get(stu["id"])),
            "work": _overall(work_subs.get(stu["id"])),
            "final": final_overall,
        })

    def _fmt(v):
        return f"{v:.1f}" if v is not None else "—"

    df = pd.DataFrame([{
        "学生": r["student"]["name"],
        "班级": r["student"]["class_name"],
        "观察评分": _fmt(r["obs"]),
        "作品评分": _fmt(r["work"]),
        "综合得分": _fmt(r["final"]),
    } for r in rows])
    st.dataframe(df, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("⚙️ 一键生成全体综合评分", use_container_width=True, key=f"comb_all_{tid}"):
            count = 0
            for stu in students:
                res = evaluation.compute_combined(tid, stu["id"], weight)
                if res["items"]:
                    count += 1
            st.success(f"已生成 {count} 名学生的综合评分")
            st.rerun()
    with c2:
        stu_options = {r["student"]["name"]: r["student"]["id"] for r in rows}
        picked = st.selectbox("单独生成：选择学生", list(stu_options.keys()), key=f"comb_pick_{tid}")
        if st.button("生成所选学生综合评分", use_container_width=True, key=f"comb_one_{tid}"):
            res = evaluation.compute_combined(tid, stu_options[picked], weight)
            if res["items"]:
                st.success(f"{picked} 综合得分：{res['overall']} 分")
            else:
                st.warning("该生暂无观察或作品评分，无法生成")

    # 最新综合结果明细
    st.divider()
    ui.section("综合评分明细")
    any_final = False
    for r in rows:
        finals = db.get_final_evaluations(tid, r["student"]["id"])
        if not finals:
            continue
        any_final = True
        with st.expander(f"📄 {r['student']['name']} · 综合 {r['final']} 分"):
            st.dataframe(pd.DataFrame([{
                "技能点": f["skill_name"], "得分": f["score"], "计算说明": f["comment"]
            } for f in finals]), use_container_width=True, hide_index=True)
            if st.button("清除该生综合评分", key=f"comb_del_{tid}_{r['student']['id']}"):
                db.delete_final_evaluations(tid, r["student"]["id"])
                st.rerun()
    if not any_final:
        st.info("尚未生成综合评分")


# ===================== 教师端：成绩分析 =====================
def render_teacher_quality():
    ui.page_header("成绩分析", "导入成绩 → 区间统计 → 分布直方图 → 教学诊断建议", "📊")

    ui.section("成绩数据来源", "可上传成绩表，也可直接汇总平台内的任务评价结果")
    tab_import, tab_task = st.tabs(["① 导入成绩表", "② 从任务评价汇总"])

    with tab_import:
        c1, c2 = st.columns(2)
        with c1:
            try:
                tpl = quality.build_template()
                st.download_button(
                    "📥 下载成绩导入模板（Excel）",
                    data=tpl,
                    file_name="成绩导入模板.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"模板生成失败：{e}")
        with c2:
            uploaded = st.file_uploader("上传成绩表（xlsx / csv）", type=["xlsx", "xls", "csv"],
                                        key="quality_upload")

        if uploaded is not None:
            parsed = quality.parse_scores(uploaded.getvalue(), uploaded.name)
            for err in parsed["errors"][:5]:
                st.error(err)
            if parsed["rows"]:
                st.success(
                    f"解析成功：{len(parsed['rows'])} 条有效成绩"
                    + (f"，跳过 {parsed['skipped']} 行空白记录" if parsed["skipped"] else "")
                )
                preview = pd.DataFrame(parsed["rows"])
                preview.columns = ["姓名", "学号", "班级", "成绩"]
                st.dataframe(preview, use_container_width=True, hide_index=True)
                default_name = f"成绩表·{uploaded.name.rsplit('.', 1)[0]}"
                ds_name = st.text_input("数据集名称", value=default_name, key="quality_ds_name")
                if st.button("💾 保存并分析", type="primary", use_container_width=True, key="quality_save"):
                    name = (ds_name or "").strip() or "未命名成绩"
                    db.save_quality_scores(name, parsed["rows"])
                    st.session_state["quality_dataset"] = name
                    st.rerun()
            elif not parsed["errors"]:
                st.warning("未解析到有效成绩，请检查表头是否包含「姓名」「成绩」列")

    with tab_task:
        tasks = db.get_tasks()
        if not tasks:
            st.info("暂无任务")
        else:
            task_options = {t["title"]: t["id"] for t in tasks}
            picked = st.selectbox("选择实操任务", list(task_options.keys()), key="quality_task_pick")
            rows = quality.collect_task_scores(task_options[picked])
            if rows:
                st.caption(f"已汇总 {len(rows)} 名学生的成绩（优先综合分，其次作品分，再次观察分）")
                preview = pd.DataFrame(rows)
                preview.columns = ["姓名", "学号", "班级", "成绩"]
                st.dataframe(preview, use_container_width=True, hide_index=True)
                if st.button("📊 汇总并分析该任务成绩", type="primary",
                             use_container_width=True, key="quality_task_save"):
                    name = f"任务成绩·{picked}"
                    db.save_quality_scores(name, rows)
                    st.session_state["quality_dataset"] = name
                    st.rerun()
            else:
                st.info("该任务暂无已评价的成绩，请先在「评价中心」完成评分")

    datasets = db.list_quality_datasets()
    if not datasets:
        st.divider()
        st.info("暂无成绩数据集。请先导入成绩表，或从任务评价中汇总成绩。")
        return

    st.divider()
    names = [d["dataset"] for d in datasets]
    default_idx = names.index(st.session_state["quality_dataset"]) \
        if st.session_state.get("quality_dataset") in names else 0
    selected_ds = st.selectbox("选择要分析的数据集", names, index=default_idx, key="quality_ds_select")

    rows = db.get_quality_scores(selected_ds)
    result = quality.analyze([r["score"] for r in rows])
    if not result:
        st.warning("该数据集无有效成绩")
        return

    ui.section("成绩统计概览", f"数据集「{selected_ds}」· 参考 {result['total']} 人")
    ui.stat_cards([
        {"label": "参考人数", "value": result["total"], "hint": "纳入统计的有效成绩", "tone": ""},
        {"label": "平均分", "value": f"{result['mean']}", "hint": f"中位数 {result['median']}　最高 {result['max']}　最低 {result['min']}", "tone": "blue"},
        {"label": "及格率", "value": f"{result['pass_rate']}%", "hint": "≥60 分占比", "tone": ""},
        {"label": "优秀率", "value": f"{result['excellent_rate']}%", "hint": "≥90 分占比", "tone": "amber"},
    ])

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1.25, 1])

    with c1:
        ui.section("成绩分布直方图")
        fig = pgo.Figure()
        fig.add_trace(pgo.Bar(
            x=[b["range"] for b in result["buckets"]],
            y=[b["count"] for b in result["buckets"]],
            marker_color=[b["color"] for b in result["buckets"]],
            marker_line_width=0,
            text=[f"{b['count']} 人<br>{b['pct']}%" for b in result["buckets"]],
            textposition="outside",
            customdata=[b["label"] for b in result["buckets"]],
            hovertemplate="%{x} 分（%{customdata}）<br>人数 %{y}<extra></extra>",
            width=0.62,
        ))
        fig.update_xaxes(title="分数区间", gridcolor="rgba(0,0,0,0)")
        fig.update_yaxes(title="人数", gridcolor="#E3EAF3", rangemode="tozero")
        fig.update_layout(showlegend=False,
                          title=dict(text=f"成绩分布（平均 {result['mean']} 分，标准差 {result['std']}）",
                                     font=dict(size=14)))
        ui.style_fig(fig, height=400)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        ui.section("成绩区间统计")
        table = pd.DataFrame([{
            "分数区间": b["range"],
            "等级": b["label"],
            "人数": b["count"],
            "占比": f"{b['pct']}%",
        } for b in result["buckets"]])
        st.dataframe(table, use_container_width=True, hide_index=True, height=250)
        fig2 = pgo.Figure()
        fig2.add_trace(pgo.Bar(
            y=[b["label"] for b in result["buckets"]][::-1],
            x=[b["pct"] for b in result["buckets"]][::-1],
            orientation="h",
            marker_color=[b["color"] for b in result["buckets"]][::-1],
            text=[f"{b['pct']}%" for b in result["buckets"]][::-1],
            textposition="outside",
            hovertemplate="%{y}：%{x}%<extra></extra>",
        ))
        fig2.update_xaxes(range=[0, 110], gridcolor="#E3EAF3", title="占比（%）")
        fig2.update_yaxes(title="")
        fig2.update_layout(showlegend=False)
        ui.style_fig(fig2, height=260)
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    ui.section("分析说明与教学建议")
    st.markdown(f"""
    <div class="icard">
      <div class="hd">诊断结论</div>
      <div class="bd" style="white-space:pre-wrap;font-size:.9rem;line-height:1.9;">
        {result['analysis']}
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander(f"查看原始成绩（{len(rows)} 条）"):
        raw = pd.DataFrame(rows)
        raw.columns = ["姓名", "学号", "班级", "成绩"]
        st.dataframe(raw, use_container_width=True, hide_index=True)

    if st.button("🗑 删除该数据集", key="quality_delete"):
        db.delete_quality_dataset(selected_ds)
        st.session_state.pop("quality_dataset", None)
        st.rerun()


# ===================== 教师端：学生名单 =====================
def render_teacher_students():
    ui.page_header("学生名单", "按班级/小组管理 · 账号与学籍信息维护", "👥")

    students = db.get_students()
    active = [s for s in students if s.get("is_active", 1)]
    classes = sorted({s["class_name"] for s in active if s.get("class_name")})
    groups = sorted({s.get("group_name") for s in active if s.get("group_name")})
    ui.stat_cards([
        {"label": "在册学生", "value": len(active), "hint": "可正常登录", "tone": ""},
        {"label": "覆盖班级", "value": len(classes),
         "hint": "、".join(classes[:3]) if classes else "暂无", "tone": "amber"},
        {"label": "小组数", "value": len(groups),
         "hint": "、".join(groups[:3]) if groups else "未分组", "tone": ""},
        {"label": "已停用", "value": len(students) - len(active), "hint": "不可登录", "tone": "amber"},
    ])

    tab_import, tab_list, tab_manage = st.tabs(
        ["① 批量导入名单", "② 按班级 · 小组查看", "③ 学生管理"]
    )

    with tab_import:
        ui.section("导入准备", "下载模板 → 填写名单 → 上传校验 → 确认导入")
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇️ 下载导入模板",
                data=roster.build_template(),
                file_name="学生名单导入模板.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="roster_tpl",
            )
            st.caption("模板含「姓名 / 学号 / 班级 / 小组 / 用户名（选填）」五列，学号即默认登录账号。")
        with c2:
            uploaded = st.file_uploader("上传已填写的名单（xlsx / csv）",
                                        type=["xlsx", "xls", "csv"], key="roster_file")

        if uploaded is not None:
            parsed = roster.parse_students(uploaded.getvalue(), uploaded.name)
            rows, errors = parsed["rows"], parsed["errors"]

            if errors:
                msg = "\n".join(f"- {e}" for e in errors[:8])
                if len(errors) > 8:
                    msg += f"\n- …… 共 {len(errors)} 处问题"
                st.warning("部分行存在问题：\n" + msg)

            if not rows:
                if not errors:
                    st.info("未从文件中解析到学生数据，请检查表格内容。")
            else:
                st.success(f"解析成功 {len(rows)} 人，可确认导入")
                preview = pd.DataFrame([
                    {"姓名": r["name"], "学号": r["student_no"],
                     "班级": r["class_name"] or "—", "小组": r.get("group_name") or "—",
                     "登录用户名": r["username"]}
                    for r in rows
                ])
                st.dataframe(preview, use_container_width=True, hide_index=True,
                             height=min(38 * len(rows) + 40, 320))

                pwd = st.text_input("初始密码（学生首次登录使用）", value="123456", key="roster_pwd")
                if st.button("🚀 确认导入", type="primary", key="roster_import"):
                    if not pwd.strip():
                        st.error("初始密码不能为空")
                    else:
                        inserted, skipped = db.create_students_bulk(rows, pwd.strip())
                        tip = f"成功创建 {inserted} 个学生账号"
                        if skipped:
                            tip += f"，跳过 {skipped} 人（学号或账号已存在）"
                        st.success(tip)
                        st.info("导入即自动生成成长档案，后续任务评分会写入对应学生的档案。")
                        st.session_state["roster_last"] = {"rows": rows, "password": pwd.strip()}

        last = st.session_state.get("roster_last")
        if last:
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            ui.section("账号清单", "最近一次导入的账号，可下载后分发给学生")
            st.download_button(
                "⬇️ 下载账号清单（含初始密码）",
                data=roster.build_accounts(last["rows"], last["password"]),
                file_name="学生账号清单.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="roster_accounts",
            )

    with tab_list:
        if not students:
            st.info("暂无学生账号，请先在「批量导入名单」中导入。")
        else:
            ui.section("筛选与查看", "按班级、小组或状态快速定位学生")
            f1, f2, f3, f4 = st.columns([1, 1, 1, 1.2])
            sel_cls = f1.selectbox("班级", ["全部班级"] + classes, key="filter_class")
            sel_grp = f2.selectbox("小组", ["全部小组"] + groups, key="filter_group")
            sel_status = f3.selectbox("状态", ["全部", "在册", "已停用"], key="filter_status")
            kw = f4.text_input("搜索姓名 / 学号", key="filter_kw")

            filtered = []
            for s in students:
                if sel_cls != "全部班级" and s.get("class_name", "") != sel_cls:
                    continue
                if sel_grp != "全部小组" and s.get("group_name", "") != sel_grp:
                    continue
                if sel_status == "在册" and not s.get("is_active", 1):
                    continue
                if sel_status == "已停用" and s.get("is_active", 1):
                    continue
                if kw.strip() and kw.strip() not in s["name"] and kw.strip() not in (s["student_no"] or ""):
                    continue
                filtered.append(s)

            st.caption(f"筛选结果：{len(filtered)} 人 / 共 {len(students)} 人")
            if filtered:
                df = pd.DataFrame([
                    {"班级": s.get("class_name") or "—", "小组": s.get("group_name") or "—",
                     "学号": s.get("student_no") or "—", "姓名": s["name"],
                     "登录用户名": s["username"],
                     "状态": "在册" if s.get("is_active", 1) else "已停用",
                     "注册时间": (s.get("created_at") or "")[:10]}
                    for s in filtered
                ])
                st.dataframe(df, use_container_width=True, hide_index=True, height=500)
                st.download_button(
                    "⬇️ 导出筛选结果（CSV）",
                    data=df.to_csv(index=False).encode("utf-8-sig"),
                    file_name="学生名单.csv",
                    mime="text/csv",
                    key="roster_export",
                )
            else:
                st.info("没有符合筛选条件的学生。")

    with tab_manage:
        flash = st.session_state.pop("roster_flash", None)
        if flash:
            st.success(flash)

        if not students:
            st.info("暂无学生账号，请先在「批量导入名单」中导入。")
            return

        options = {}
        for s in students:
            tag = "已停用" if not s.get("is_active", 1) else "在册"
            label = (f"{s['name']} · {s.get('class_name') or '未分班'}"
                     f"{'/' + s['group_name'] if s.get('group_name') else ''}"
                     f"（{s.get('student_no') or '无学号'}）· {tag}")
            options[label] = s["id"]

        selected = st.selectbox("选择要管理的学生", list(options.keys()), key="mgmt_student")
        sid = options[selected]
        s = db.get_user(sid)
        if not s:
            st.warning("该学生不存在，请重新选择。")
            return
        records = db.get_student_record_count(sid)
        st.caption(f"登录账号：{s['username']} ｜ 评价记录：{records} 条 ｜ "
                   f"状态：{'在册' if s.get('is_active', 1) else '已停用（无法登录）'}")

        with st.form("edit_student_form"):
            e1, e2, e3 = st.columns(3)
            new_name = e1.text_input("姓名", value=s["name"])
            new_cls = e2.text_input("班级", value=s.get("class_name") or "")
            new_grp = e3.text_input("小组", value=s.get("group_name") or "")
            if st.form_submit_button("💾 保存信息", type="primary"):
                if not new_name.strip():
                    st.error("姓名不能为空")
                else:
                    db.update_student(sid, new_name, new_cls, new_grp)
                    st.success(f"已更新 {new_name.strip()} 的班级/小组信息")

        c_reset, c_status = st.columns(2)
        with c_reset:
            new_pwd = st.text_input("新的初始密码", value="123456", key=f"newpwd_{sid}")
            if st.button("🔑 重置密码", key=f"reset_{sid}", use_container_width=True):
                if not new_pwd.strip():
                    st.error("密码不能为空")
                else:
                    db.reset_student_password(sid, new_pwd.strip())
                    st.success(f"已将 {s['name']} 的密码重置为 {new_pwd.strip()}")

        with c_status:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if s.get("is_active", 1):
                if st.button("⏸ 停用账号", key=f"disable_{sid}", use_container_width=True):
                    db.set_student_active(sid, False)
                    st.session_state["roster_flash"] = f"已停用 {s['name']}，该账号将无法登录"
                    st.rerun()
            else:
                if st.button("▶️ 启用账号", key=f"enable_{sid}", use_container_width=True):
                    db.set_student_active(sid, True)
                    st.session_state["roster_flash"] = f"已启用 {s['name']}，可正常登录"
                    st.rerun()

        with st.expander("🗑 删除学生账号（不可恢复）"):
            st.caption("删除后该生无法登录；若已有评价记录，可选择一并删除，否则建议使用「停用」。")
            confirm = st.checkbox("我确认删除该学生账号", key=f"del_confirm_{sid}")
            del_records = False
            if records:
                del_records = st.checkbox(
                    f"同时删除该生的 {records} 条评价记录（作品/观察/综合评分）",
                    key=f"del_rec_{sid}"
                )
            can_delete = confirm and (records == 0 or del_records)
            if st.button("确认删除", key=f"delete_{sid}", disabled=not can_delete,
                         use_container_width=True):
                ok, n = db.delete_student(sid, with_records=True)
                if ok:
                    st.session_state["roster_flash"] = (
                        f"已删除学生 {s['name']} 及其 {n} 条评价记录"
                        if n else f"已删除学生 {s['name']}"
                    )
                    st.session_state.pop("mgmt_student", None)
                    st.rerun()
                else:
                    st.error(f"删除失败：该生有 {n} 条评价记录，请勾选「同时删除评价记录」")


# ===================== 教师端：学生档案 =====================
def render_teacher_archives():
    ui.page_header("学生成长档案", "技能雷达图 · 掌握趋势 · 薄弱环节预警", "📈")

    students = db.get_students()
    if not students:
        st.info("暂无学生")
        return

    student_options = {f"{s['name']}（{s['class_name']}-{s['student_no']}）": s["id"] for s in students}
    selected = st.selectbox("选择学生", list(student_options.keys()))
    sid = student_options[selected]
    student = db.get_user(sid)

    archive = db.get_student_archive(sid)

    if archive:
        avg = round(sum(a["avg_score"] or 0 for a in archive) / len(archive), 1)
        weak = [a for a in archive if (a["avg_score"] or 0) < 70]
        strong = [a for a in archive if (a["avg_score"] or 0) >= 85]
        ui.stat_cards([
            {"label": "平均掌握度", "value": f"{avg}", "hint": "全部技能点均值", "tone": ""},
            {"label": "已记录技能", "value": len(archive), "hint": "档案覆盖技能点", "tone": "blue"},
            {"label": "优势技能", "value": len(strong), "hint": "≥85 分", "tone": "amber"},
            {"label": "待提升技能", "value": len(weak), "hint": "<70 分", "tone": ""},
        ])
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        c1, c2 = st.columns([1.15, 1])
        with c1:
            ui.section(f"{student['name']} 的技能画像")
            fig = pgo.Figure()
            fig.add_trace(pgo.Scatterpolar(
                r=[a["avg_score"] for a in archive],
                theta=[a["skill_name"] for a in archive],
                fill="toself",
                name="平均得分",
                line=dict(color="#00BFA6", width=2),
                fillcolor="rgba(0,191,166,0.22)",
                marker=dict(size=7, color="#0E7C86"),
            ))
            fig.update_layout(
                polar=dict(
                    bgcolor="rgba(0,0,0,0)",
                    radialaxis=dict(visible=True, range=[0, 100], gridcolor="#E3EAF3",
                                    tickfont=dict(size=11, color="#37507A")),
                    angularaxis=dict(gridcolor="#E3EAF3"),
                ),
                showlegend=False,
                title=dict(text="技能掌握雷达图", font=dict(size=15)),
            )
            ui.style_fig(fig, height=430)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            ui.section("掌握度明细")
            ui.skill_bars(archive)
            if weak:
                st.warning(f"⚠️ 薄弱技能点：{', '.join(a['skill_name'] for a in weak)}")

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        ui.section("档案数据表")
        df = pd.DataFrame(archive)[["course_name", "skill_name", "skill_category", "task_count", "avg_score", "max_score", "min_score"]]
        df.columns = ["课程", "技能点", "分类", "参与任务数", "平均分", "最高分", "最低分"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("该学生暂无评价记录")


# ===================== 学生端：主页 =====================
def render_student_home():
    user = st.session_state.user
    ui.page_header("学生工作台", f"{user['name']} · {user['class_name'] or '未填写班级'} · 学号 {user['student_no']}", "🎓")

    tasks = [t for t in db.get_tasks() if task_visible_to(t, user)]
    pending = [t for t in tasks if not student_task_done(t["id"], user["id"])]
    archive = db.get_student_archive(user["id"])
    avg = round(sum(a["avg_score"] or 0 for a in archive) / len(archive), 1) if archive else 0

    ui.stat_cards([
        {"label": "待完成任务", "value": len(pending), "hint": f"共 {len(tasks)} 个已分配任务", "tone": "blue"},
        {"label": "已评价技能", "value": len(archive), "hint": "进入成长档案", "tone": ""},
        {"label": "平均掌握度", "value": avg, "hint": "技能平均得分", "tone": "amber"},
    ])

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    ui.section("我的入口", "提交作品、查看评分与成长画像")
    c1, c2 = st.columns(2)
    with c1:
        ui.info_card("📝 实操任务", "查看任务要求与评价标准，提交作品或参与线下观察。")
        if st.button("进入任务列表 →", use_container_width=True, key="stu_go_tasks"):
            go("student_tasks")
    with c2:
        ui.info_card("📊 成长档案", "查看技能雷达图、得分趋势与需要加强的技能点。")
        if st.button("查看我的画像 →", use_container_width=True, key="stu_go_archive"):
            go("student_archive")


# ===================== 学生端：任务列表与提交 =====================
def render_student_tasks():
    ui.page_header("实操任务", "查看任务要求与评价标准，按模式提交作品或等待现场观察", "📝")

    user = st.session_state.user
    tasks = [t for t in db.get_tasks() if task_visible_to(t, user)]
    if not tasks:
        st.info("暂无分配给你的实操任务")
        return

    for t in tasks:
        with st.expander(f"📌 {t['title']}（截止：{t['deadline']}）"):
            st.write(f"**任务说明**：{t['description']}")
            st.markdown(f"**评价模式**：{ui.mode_chip(t['eval_mode'])}", unsafe_allow_html=True)
            if (t.get("target_class") or "") or (t.get("target_group") or ""):
                st.caption(f"发布范围：{task_range_text(t)}")

            # 关联技能点
            task_skills = db.get_task_skills(t["id"])
            if task_skills:
                st.write("**评价技能点**：")
                for ts in task_skills:
                    st.write(f"  - {ts['skill_name']}")
                    with st.expander("查看评价标准", expanded=False):
                        st.text(ts["criteria"] or "暂无评价标准")

            st.divider()
            mode = t["eval_mode"]

            # 综合评分结果（综合模式生成后展示）
            finals = db.get_final_evaluations(t["id"], user["id"])
            if finals:
                final_overall = round(sum(f["score"] for f in finals) / len(finals), 1)
                st.success(f"✅ 综合得分：{final_overall} 分（{finals[0]['method']}）")
                st.dataframe(pd.DataFrame([{
                    "技能点": f["skill_name"], "得分": f["score"], "计算说明": f["comment"]
                } for f in finals]), use_container_width=True, hide_index=True)

            # 观察法：无需线上提交
            if mode == EVAL_MODE_OBS:
                st.info("本任务采用「观察法」评价：由教师线下观察你的实操过程并现场打分，无需线上提交作品。")
                obs = db.get_submission_by_task_student(t["id"], user["id"], eval_source="observation")
                evals = db.get_evaluations_by_submission(obs["id"]) if obs else []
                if evals:
                    overall = evaluation.get_submission_overall(obs["id"])
                    st.success(f"✅ 教师观察评分：{overall['overall_score']} 分")
                    for e in evals:
                        with st.expander(f"{e['skill_name']}：{e['score']} 分"):
                            st.write(e["comment"] or "（无评语）")
                    with st.expander("掌握度分析"):
                        st.write(overall["mastery"])
                else:
                    st.warning("⏳ 教师尚未完成观察评价")
                continue

            # 作品分析法 / 综合模式：线上提交作品
            existing = db.get_submission_by_task_student(t["id"], user["id"])
            if existing:
                st.info(f"已提交：{existing['file_name']}（{existing['submitted_at'][:16]}）")
                evals = db.get_evaluations_by_submission(existing["id"])
                if evals:
                    overall = evaluation.get_submission_overall(existing["id"])
                    st.success(f"✅ 作品评分：{overall['overall_score']} 分")
                    for e in evals:
                        with st.expander(f"{e['skill_name']}：{e['score']}分（{e['evaluator']}评）"):
                            st.write(e["comment"])
                    with st.expander("掌握度分析"):
                        st.write(overall["mastery"])
                else:
                    st.warning("⏳ 教师尚未评价")
            elif mode == EVAL_MODE_COMBINED:
                st.caption("综合模式：本任务既包含线下观察评分，也需要线上提交作品。")

            with st.form(f"submit_form_{t['id']}"):
                uploaded = st.file_uploader("上传实操作品", type=["txt", "md", "docx", "xlsx", "pdf", "png", "jpg", "jpeg"], key=f"file_{t['id']}")
                text_input = st.text_area("或直接输入作品内容（可选）", height=100, key=f"text_{t['id']}")
                if st.form_submit_button("📤 提交作品"):
                    file_path = ""
                    file_name = ""
                    file_bytes = None
                    if uploaded is not None:
                        file_bytes = uploaded.getvalue()
                        file_name = uploaded.name
                        # 本地运行时额外留一份磁盘副本；云端部署以数据库为准
                        if not dbcompat.IS_POSTGRES:
                            save_name = f"{user['id']}_{t['id']}_{int(time.time())}_{uploaded.name}"
                            file_path = os.path.join(UPLOAD_DIR, save_name)
                            with open(file_path, "wb") as f:
                                f.write(file_bytes)
                    if uploaded is None and not text_input:
                        st.error("请上传文件或输入作品内容")
                    else:
                        db.create_submission(t["id"], user["id"], file_path, file_name, text_input,
                                             eval_source="work", file_data=file_bytes)
                        st.success("作品提交成功！")
                        st.rerun()


# ===================== 学生端：个人成长档案 =====================
def render_student_archive():
    ui.page_header("我的技能成长档案", "记录每一次实操表现，看见自己的能力变化", "📊")

    user = st.session_state.user
    archive = db.get_student_archive(user["id"])

    if archive:
        avg = round(sum(a["avg_score"] or 0 for a in archive) / len(archive), 1)
        weak = [a for a in archive if (a["avg_score"] or 0) < 70]
        best = max(archive, key=lambda a: a["avg_score"] or 0)

        ui.stat_cards([
            {"label": "平均掌握度", "value": f"{avg}", "hint": "全部技能点均值", "tone": ""},
            {"label": "已记录技能", "value": len(archive), "hint": "档案覆盖技能点", "tone": "blue"},
            {"label": "最擅长", "value": best["skill_name"], "hint": f"{best['avg_score']} 分", "tone": "amber"},
            {"label": "待加强", "value": len(weak), "hint": "<70 分的技能点", "tone": ""},
        ])
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        c1, c2 = st.columns([1.15, 1])
        with c1:
            ui.section("技能雷达图")
            fig = pgo.Figure()
            fig.add_trace(pgo.Scatterpolar(
                r=[a["avg_score"] for a in archive],
                theta=[a["skill_name"] for a in archive],
                fill="toself",
                name="平均得分",
                line=dict(color="#00BFA6", width=2),
                fillcolor="rgba(0,191,166,0.22)",
                marker=dict(size=7, color="#0E7C86"),
            ))
            fig.update_layout(
                polar=dict(
                    bgcolor="rgba(0,0,0,0)",
                    radialaxis=dict(visible=True, range=[0, 100], gridcolor="#E3EAF3",
                                    tickfont=dict(size=11, color="#37507A")),
                    angularaxis=dict(gridcolor="#E3EAF3"),
                ),
                showlegend=False,
            )
            ui.style_fig(fig, height=430)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            ui.section("掌握度明细")
            ui.skill_bars(archive)
            if weak:
                st.warning(f"⚠️ 需加强：{', '.join(a['skill_name'] for a in weak)}")
            else:
                st.success("🎉 各技能点掌握良好，继续保持！")

        ui.section("技能得分趋势")
        # 同名技能可能来自不同课程，重名时在标签中补课程名，避免选错技能点
        name_counts = {}
        for a in archive:
            name_counts[a["skill_name"]] = name_counts.get(a["skill_name"], 0) + 1
        skill_options = {}
        for a in archive:
            label = (a["skill_name"] if name_counts[a["skill_name"]] == 1
                     else f"{a['skill_name']}（{a['course_name']}）")
            skill_options.setdefault(label, a["skill_id"])
        selected_skill = st.selectbox("选择技能点查看趋势", list(skill_options.keys()))
        if selected_skill:
            trend = db.get_student_skill_trend(user["id"], skill_options[selected_skill])
            if trend:
                tdf = pd.DataFrame(trend)
                fig2 = px.line(tdf, x="evaluated_at", y="score", markers=True,
                               labels={"evaluated_at": "评价时间", "score": "得分"})
                fig2.update_traces(line=dict(color="#0E7C86", width=3),
                                   marker=dict(size=9, color="#00BFA6"))
                fig2.update_yaxes(range=[0, 100], gridcolor="#E3EAF3")
                fig2.update_xaxes(gridcolor="#E3EAF3")
                ui.style_fig(fig2, height=340)
                st.plotly_chart(fig2, use_container_width=True)

        ui.section("档案数据表")
        df = pd.DataFrame(archive)[["course_name", "skill_name", "skill_category", "task_count", "avg_score", "max_score", "min_score"]]
        df.columns = ["课程", "技能点", "分类", "参与任务数", "平均分", "最高分", "最低分"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("暂无评价记录，请先完成实操任务。")


# ===================== 路由 =====================
def main():
    page = st.session_state.get("page", "login")
    user = st.session_state.get("user")

    if page == "login" or user is None:
        render_login()
        return

    render_sidebar(user)

    if user["role"] == "teacher":
        renderers = {
            "teacher_home": render_teacher_home,
            "teacher_skills": render_teacher_skills,
            "teacher_tasks": render_teacher_tasks,
            "teacher_task_detail": render_teacher_task_detail,
            "teacher_eval": render_teacher_eval,
            "teacher_quality": render_teacher_quality,
            "teacher_students": render_teacher_students,
            "teacher_archives": render_teacher_archives,
        }
    else:
        renderers = {
            "student_home": render_student_home,
            "student_tasks": render_student_tasks,
            "student_archive": render_student_archive,
        }

    renderers.get(page, renderers.get(list(renderers)[0]))()


if __name__ == "__main__":
    main()
