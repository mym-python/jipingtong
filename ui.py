"""
UI 主题模块：统一视觉风格（职业能力数字画像风格）
- inject_theme()  注入全局 CSS
- hero()          品牌横幅
- page_header()   页面标题
- stat_cards()    统计卡片
- info_card()     信息卡片
- mode_chip()     评价模式徽标
- steps()         流程步骤
- skill_bars()    技能掌握进度条
- style_fig()     Plotly 图表统一主题
"""
import streamlit as st

INK = "#0B1F3A"
INK_SOFT = "#37507A"
TEAL = "#00BFA6"
TEAL_DEEP = "#009E8A"
AMBER = "#FFB020"
ROSE = "#FF6B6B"
LINE = "#E3EAF3"

CSS = """
<style>
:root{
  --ink:#0B1F3A; --ink-soft:#37507A;
  --teal:#00BFA6; --teal-deep:#009E8A;
  --amber:#FFB020; --rose:#FF6B6B;
  --bg:#F4F7FB; --card:#FFFFFF; --line:#E3EAF3;
}
html, body, .stApp, [class*="css"]{
  font-family:"Microsoft YaHei","PingFang SC","Segoe UI",system-ui,sans-serif;
}
.stApp{
  background:
    radial-gradient(1000px 520px at 8% -12%, #E4F3FF 0%, rgba(228,243,255,0) 62%),
    radial-gradient(900px 480px at 100% 0%, #E7FBF7 0%, rgba(231,251,247,0) 60%),
    var(--bg);
}
.block-container{ padding-top:1.6rem; padding-bottom:3rem; max-width:1280px; }

/* ---------- 侧边栏 ---------- */
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#0B1F3A 0%,#102E52 55%,#0C4650 100%);
  border-right:none;
}
[data-testid="stSidebar"] *{ color:#E9F3FF; }
[data-testid="stSidebar"] hr{ border-color:rgba(255,255,255,.14); }
[data-testid="stSidebar"] .stButton>button{
  background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.13);
  color:#E9F3FF; border-radius:12px; justify-content:flex-start;
  font-weight:500; box-shadow:none;
}
[data-testid="stSidebar"] .stButton>button:hover{
  background:rgba(0,191,166,.22); border-color:#00BFA6; color:#ffffff;
  transform:translateX(2px);
}
.sb-brand{ padding:6px 2px 14px 2px; }
.sb-brand .logo-row{ display:flex; align-items:center; gap:10px; }
.sb-brand .logo{ font-size:1.45rem; font-weight:800; letter-spacing:.02em; }
.sb-brand .sub{ font-size:.72rem; opacity:.6; letter-spacing:.16em; text-transform:uppercase; margin-top:4px; }
.sb-user{
  display:flex; align-items:center; gap:10px;
  background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.12);
  border-radius:14px; padding:10px 12px; margin-bottom:14px;
}
.sb-avatar{
  width:36px; height:36px; border-radius:50%; flex:none;
  background:linear-gradient(135deg,#00BFA6,#0E7C86);
  display:flex; align-items:center; justify-content:center;
  font-weight:700; font-size:.95rem;
}
.sb-user .nm{ font-size:.95rem; font-weight:600; line-height:1.2; }
.sb-user .rl{ font-size:.7rem; opacity:.62; }

/* ---------- 品牌横幅 ---------- */
.hero{
  position:relative; overflow:hidden;
  background:
    repeating-linear-gradient(90deg, rgba(255,255,255,.045) 0 1px, transparent 1px 46px),
    repeating-linear-gradient(0deg, rgba(255,255,255,.035) 0 1px, transparent 1px 46px),
    linear-gradient(135deg,#0B1F3A 0%,#123B6B 52%,#0C6E76 100%);
  border-radius:22px; padding:34px 38px 30px; color:#fff;
  box-shadow:0 18px 44px rgba(11,31,58,.28);
  margin-bottom:22px;
}
.hero:after{
  content:""; position:absolute; right:-70px; top:-90px; width:300px; height:300px;
  background:radial-gradient(circle, rgba(0,191,166,.55) 0%, rgba(0,191,166,0) 68%);
}
.hero .eyebrow{
  font-size:.72rem; letter-spacing:.2em; text-transform:uppercase;
  opacity:.72; display:flex; align-items:center; gap:8px; margin-bottom:12px;
}
.hero .eyebrow .dot{
  width:7px; height:7px; border-radius:50%; background:#00BFA6;
  box-shadow:0 0 0 4px rgba(0,191,166,.18); display:inline-block;
}
.hero h1{ font-size:2.1rem; margin:0 0 8px; font-weight:800; letter-spacing:.01em; color:#fff; }
.hero .hero-head{ display:flex; align-items:center; gap:16px; flex-wrap:wrap; margin-bottom:10px; }
.hero .hero-head h1{ margin:0; }
.hero .hero-head .mark{ filter:drop-shadow(0 8px 20px rgba(0,0,0,.35)); flex:none; }
.hero p{ margin:0; opacity:.82; font-size:.95rem; max-width:640px; }
.chips{ margin-top:18px; display:flex; flex-wrap:wrap; gap:9px; }
.chips span{
  font-size:.78rem; padding:5px 13px; border-radius:999px;
  background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.2);
  backdrop-filter:blur(4px);
}

/* ---------- 页面标题 ---------- */
.pg-head{ margin:2px 0 18px; }
.pg-head .icon{
  display:inline-flex; width:38px; height:38px; border-radius:11px; align-items:center; justify-content:center;
  background:linear-gradient(135deg, rgba(0,191,166,.16), rgba(14,124,134,.1));
  border:1px solid rgba(0,191,166,.28); font-size:1.1rem; margin-right:10px; vertical-align:middle;
}
.pg-head h2{
  display:inline; font-size:1.42rem; font-weight:750; color:var(--ink); margin:0; vertical-align:middle;
}
.pg-head .sub{ margin-top:8px; color:var(--ink-soft); font-size:.88rem; opacity:.85; }

/* ---------- 分区标题 ---------- */
.sec-title{
  display:flex; align-items:center; gap:10px; margin:6px 0 12px;
}
.sec-title:before{
  content:""; width:4px; height:20px; border-radius:3px;
  background:linear-gradient(180deg,#00BFA6,#0E7C86);
}
.sec-title .t{ font-size:1.02rem; font-weight:700; color:var(--ink); }
.sec-title .d{ font-size:.8rem; color:var(--ink-soft); opacity:.75; }

/* ---------- 统计卡片 ---------- */
.stat{
  background:#fff; border:1px solid var(--line); border-radius:16px;
  padding:16px 18px; position:relative; overflow:hidden;
  box-shadow:0 8px 22px rgba(16,42,67,.06);
}
.stat:before{
  content:""; position:absolute; left:0; top:0; bottom:0; width:4px;
  background:linear-gradient(180deg,#00BFA6,#0E7C86);
}
.stat.amber:before{ background:linear-gradient(180deg,#FFB020,#F08C00); }
.stat.blue:before{ background:linear-gradient(180deg,#4C8DFF,#2251C8); }
.stat .lb{ font-size:.78rem; color:var(--ink-soft); letter-spacing:.04em; }
.stat .vl{ font-size:1.85rem; font-weight:800; color:var(--ink); line-height:1.25; }
.stat .hi{ font-size:.74rem; color:var(--ink-soft); opacity:.7; }

/* ---------- 信息卡片 ---------- */
.icard{
  background:#fff; border:1px solid var(--line); border-radius:16px;
  padding:16px 18px; box-shadow:0 6px 18px rgba(16,42,67,.05); height:100%;
}
.icard .hd{ font-weight:700; color:var(--ink); margin-bottom:6px; font-size:.95rem; }
.icard .bd{ color:var(--ink-soft); font-size:.85rem; line-height:1.65; }

/* ---------- 模式徽标 ---------- */
.mchip{
  display:inline-block; font-size:.76rem; padding:3px 11px; border-radius:999px;
  font-weight:600; border:1px solid transparent;
}
.mchip.obs{ background:rgba(76,141,255,.12); color:#2251C8; border-color:rgba(76,141,255,.3); }
.mchip.work{ background:rgba(0,191,166,.12); color:#00806E; border-color:rgba(0,191,166,.32); }
.mchip.comb{ background:rgba(255,176,32,.15); color:#9A6400; border-color:rgba(255,176,32,.38); }

/* ---------- 步骤 ---------- */
.steps{ display:flex; gap:10px; flex-wrap:wrap; margin:4px 0 6px; }
.steps .st{
  flex:1 1 150px; background:#fff; border:1px solid var(--line); border-radius:14px;
  padding:12px 14px; box-shadow:0 4px 14px rgba(16,42,67,.05);
}
.steps .st .no{
  width:22px; height:22px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center;
  background:linear-gradient(135deg,#00BFA6,#0E7C86); color:#fff; font-size:.72rem; font-weight:700; margin-bottom:7px;
}
.steps .st .tx{ font-size:.82rem; color:var(--ink); font-weight:600; line-height:1.45; }

/* ---------- 技能进度条 ---------- */
.sbar{ margin:9px 0 13px; }
.sbar .top{ display:flex; justify-content:space-between; font-size:.84rem; color:var(--ink); margin-bottom:5px; }
.sbar .top .sc{ font-weight:700; }
.sbar .track{ height:9px; border-radius:999px; background:#EAF0F7; overflow:hidden; }
.sbar .fill{ height:100%; border-radius:999px; background:linear-gradient(90deg,#0E7C86,#00BFA6); }
.sbar .fill.warn{ background:linear-gradient(90deg,#F08C00,#FFB020); }
.sbar .fill.bad{ background:linear-gradient(90deg,#D93B4B,#FF6B6B); }
.sbar .cat{ font-size:.72rem; color:var(--ink-soft); opacity:.7; }

/* ---------- 控件美化 ---------- */
.stButton>button{
  border-radius:12px; border:1px solid var(--line); background:#fff; color:var(--ink);
  font-weight:600; padding:.48rem 1rem; transition:all .18s ease;
  box-shadow:0 1px 2px rgba(16,42,67,.05);
}
.stButton>button:hover{
  transform:translateY(-1px); border-color:#00BFA6; color:#009E8A;
  box-shadow:0 10px 22px rgba(0,191,166,.18);
}
.stButton>button[kind="primary"]{
  background:linear-gradient(135deg,#0E7C86,#00BFA6); color:#fff; border:none;
  box-shadow:0 8px 20px rgba(0,191,166,.3);
}
[data-testid="stForm"]{
  background:#fff; border:1px solid var(--line); border-radius:16px; padding:18px 20px;
  box-shadow:0 8px 22px rgba(16,42,67,.05);
}
details[data-testid="stExpander"]{
  background:#fff; border:1px solid var(--line) !important; border-radius:14px;
  box-shadow:0 4px 14px rgba(16,42,67,.04); margin-bottom:10px;
}
[data-testid="stMetric"]{
  background:#fff; border:1px solid var(--line); border-radius:16px; padding:14px 18px;
  box-shadow:0 8px 22px rgba(16,42,67,.06);
}
[data-testid="stMetricValue"]{ color:var(--ink); font-weight:800; }
button[data-baseweb="tab"]{
  border-radius:10px !important; padding:7px 18px !important;
  background:#fff; border:1px solid var(--line) !important; margin-right:6px;
  font-weight:600;
}
button[data-baseweb="tab"][aria-selected="true"]{
  background:linear-gradient(135deg,#0E7C86,#00BFA6) !important;
  color:#fff !important; border-color:transparent !important;
}
button[data-baseweb="tab"][aria-selected="true"] *{ color:#fff !important; }
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"]{ background:transparent !important; }
[data-testid="stDataFrame"]{ border-radius:12px; overflow:hidden; }
h1,h2,h3,h4{ color:var(--ink); }
hr{ border-color:var(--line); }
</style>
"""


LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" role="img" aria-label="技评通">
<defs>
  <linearGradient id="jg" x1="4" y1="2" x2="60" y2="62" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="#0B1F3A"/>
    <stop offset="0.55" stop-color="#0E7C86"/>
    <stop offset="1" stop-color="#00BFA6"/>
  </linearGradient>
</defs>
<rect x="2" y="2" width="60" height="60" rx="16" fill="url(#jg)"/>
<circle cx="45" cy="19" r="13" fill="#FFFFFF" opacity="0.10"/>
<circle cx="45" cy="19" r="7.5" fill="#FFFFFF" opacity="0.14"/>
<path d="M17 38 L28.5 46.5 L49.5 21" fill="none" stroke="#FFFFFF" stroke-width="4.2"
      stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="49.5" cy="21" r="3.4" fill="#FFB020"/>
</svg>"""


def logo(size=32):
    """返回指定尺寸的 Logo 内联 SVG"""
    return LOGO_SVG.replace('width="64" height="64"', f'width="{size}" height="{size}"', 1)


def inject_theme():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title, subtitle, chips=None, eyebrow="职业能力数字画像 · Vocational Skill Intelligence"):
    chip_html = "".join(f"<span>{c}</span>" for c in (chips or []))
    st.markdown(f"""
    <div class="hero">
      <div class="eyebrow"><span class="dot"></span>{eyebrow}</div>
      <div class="hero-head"><span class="mark">{logo(58)}</span><h1>{title}</h1></div>
      <p>{subtitle}</p>
      <div class="chips">{chip_html}</div>
    </div>
    """, unsafe_allow_html=True)


def page_header(title, subtitle="", icon="◆"):
    st.markdown(f"""
    <div class="pg-head">
      <span class="icon">{icon}</span><h2>{title}</h2>
      {f'<div class="sub">{subtitle}</div>' if subtitle else ''}
    </div>
    """, unsafe_allow_html=True)


def section(title, desc=""):
    d = f'<span class="d">{desc}</span>' if desc else ""
    st.markdown(f'<div class="sec-title"><span class="t">{title}</span>{d}</div>', unsafe_allow_html=True)


def stat_cards(items):
    """items: [{"label","value","hint","tone"(teal/amber/blue)}]"""
    cols = st.columns(len(items))
    for col, it in zip(cols, items):
        tone = it.get("tone", "")
        hint = it.get("hint", "")
        with col:
            st.markdown(f"""
            <div class="stat {tone}">
              <div class="lb">{it['label']}</div>
              <div class="vl">{it['value']}</div>
              <div class="hi">{hint}</div>
            </div>
            """, unsafe_allow_html=True)


def info_card(title, body):
    st.markdown(f"""
    <div class="icard"><div class="hd">{title}</div><div class="bd">{body}</div></div>
    """, unsafe_allow_html=True)


def mode_chip(mode):
    cls = "work"
    if "观察法" in mode and "综合" not in mode:
        cls = "obs"
    elif "综合" in mode:
        cls = "comb"
    return f'<span class="mchip {cls}">{mode}</span>'


def steps(items):
    html = "".join(
        f'<div class="st"><div class="no">{i + 1}</div><div class="tx">{t}</div></div>'
        for i, t in enumerate(items)
    )
    st.markdown(f'<div class="steps">{html}</div>', unsafe_allow_html=True)


def skill_bars(rows):
    """rows: [{"skill_name","avg_score","skill_category"}]"""
    html = []
    for r in rows:
        score = r.get("avg_score") or 0
        score = float(score)
        cls = "" if score >= 85 else ("warn" if score >= 70 else "bad")
        cat = r.get("skill_category") or "技能"
        html.append(f"""
        <div class="sbar">
          <div class="top"><span>{r['skill_name']}<span class="cat"> · {cat}</span></span>
          <span class="sc">{score:.1f}</span></div>
          <div class="track"><div class="fill {cls}" style="width:{max(2, min(100, score)):.0f}%"></div></div>
        </div>
        """)
    st.markdown("".join(html), unsafe_allow_html=True)


def style_fig(fig, height=420):
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Microsoft YaHei, PingFang SC, Segoe UI", size=13, color=INK),
        colorway=[TEAL, "#4C8DFF", AMBER, ROSE, "#7C5CFF"],
        margin=dict(l=40, r=24, t=48, b=40),
        hoverlabel=dict(bgcolor="#0B1F3A", font_color="#fff"),
    )
    return fig
