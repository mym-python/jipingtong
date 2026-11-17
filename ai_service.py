"""
AI 服务模块：封装 DeepSeek API 调用
功能：
  1. generate_criteria()  - 根据技能点描述生成可量化的评价标准
  2. ai_grade_work()      - 根据评价标准对学生作品自动评分并生成评语
"""
import json
import openai
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


def _get_client():
    """获取 OpenAI 兼容客户端（对接 DeepSeek）"""
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "your_deepseek_api_key_here":
        return None
    return openai.OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
    )


def is_ai_available():
    """检查 AI 服务是否可用"""
    return _get_client() is not None


def generate_criteria(skill_name: str, skill_desc: str, task_title: str, task_desc: str = "") -> str:
    """
    根据技能点描述和任务要求，AI 生成具体的、可量化的评价标准
    返回评价标准文本（含职业素养监控要求）
    """
    client = _get_client()
    if client is None:
        return _fallback_criteria(skill_name, skill_desc)

    prompt = f"""你是一位高职教育评价专家。请根据以下技能点和实操任务，生成具体、可量化、可操作的评价标准。
要求：
1. 评价标准必须可观察、可测量，避免主观模糊描述
2. 必须包含职业素养方面的评价要点（如规范意识、安全操作、团队协作、创新思维等）
3. 按要点分条列出，每条说明"达标表现"与"扣分情形"
4. 总分为100分，给出各要点的建议分值占比

技能点名称：{skill_name}
技能点描述：{skill_desc}
实操任务：{task_title}
任务说明：{task_desc}

请直接输出评价标准文本，不要多余解释。"""

    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[AI 生成失败：{str(e)}]\n\n{_fallback_criteria(skill_name, skill_desc)}"


def _fallback_criteria(skill_name: str, skill_desc: str) -> str:
    """AI 不可用时的兜底评价标准模板"""
    return f"""【{skill_name}】评价标准（系统默认模板，请教师根据实际情况调整）

一、技能操作（60分）
1. 操作流程规范性（20分）：操作步骤完整、顺序正确，无违规操作
   - 达标：流程完整规范
   - 扣分：遗漏关键步骤或顺序错误

2. 操作结果正确性（25分）：最终成果符合任务要求，技术指标达标
   - 达标：成果完全符合要求
   - 扣分：存在技术性错误或指标不达标

3. 问题解决能力（15分）：遇到问题能独立分析并解决
   - 达标：能独立解决实操中的问题
   - 扣分：无法解决常见问题

二、职业素养（40分）
1. 规范与安全意识（15分）：遵守操作规程，注重安全
2. 工作态度与责任心（15分）：认真完成任务，不敷衍
3. 创新与改进意识（10分）：对操作方法有思考和改进

技能点说明：{skill_desc}"""


def ai_grade_work(skill_name: str, criteria: str, work_content: str, file_name: str = "") -> dict:
    """
    AI 根据评价标准对学生作品进行自动评分
    返回: {"score": float, "comment": str}
    """
    client = _get_client()
    if client is None:
        return {"score": 0, "comment": "[AI 服务未配置，请教师手动评分]"}

    # 作品内容过长时截断
    content_preview = work_content[:3000] if work_content else ""
    prompt = f"""你是一位严格公正的高职实操评价教师。请根据以下评价标准，对学生的实操作品进行评分。

技能点：{skill_name}
评价标准：
{criteria}

学生作品文件：{file_name}
学生作品内容：
{content_preview}

请严格按照评价标准评分，并输出 JSON 格式结果：
{{"score": 分数(0-100的数字), "comment": "评语，指出优点、不足与改进建议"}}

只输出 JSON，不要其他内容。"""

    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        result_text = resp.choices[0].message.content.strip()
        # 尝试解析 JSON
        try:
            result = json.loads(result_text)
            score = float(result.get("score", 0))
            comment = str(result.get("comment", ""))
        except json.JSONDecodeError:
            # 解析失败，尝试提取
            import re
            score_match = re.search(r'"score"\s*:\s*(\d+\.?\d*)', result_text)
            comment_match = re.search(r'"comment"\s*:\s*"([^"]*)"', result_text)
            score = float(score_match.group(1)) if score_match else 0
            comment = comment_match.group(1) if comment_match else result_text

        score = max(0, min(100, score))
        return {"score": score, "comment": comment}
    except Exception as e:
        return {"score": 0, "comment": f"[AI 评分失败：{str(e)}]"}


def summarize_mastery(skill_scores: list) -> str:
    """
    根据各技能点得分率，AI 判断学生技能掌握程度并给出建议
    skill_scores: [{"skill_name": str, "score": float}, ...]
    """
    client = _get_client()
    if client is None:
        return _fallback_mastery(skill_scores)

    skills_text = "\n".join([f"- {s['skill_name']}: {s['score']}分" for s in skill_scores])
    prompt = f"""以下是学生在本次实操中各技能点的得分情况（满分100）：
{skills_text}

请分析该学生的技能掌握程度：
1. 指出掌握较好的技能点
2. 指出薄弱技能点（得分低于70分）
3. 给出针对性的提升建议

请用简洁的语言输出，分点陈述。"""

    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=600,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[分析失败：{str(e)}]\n\n{_fallback_mastery(skill_scores)}"


def _fallback_mastery(skill_scores: list) -> str:
    if not skill_scores:
        return "暂无评分数据"
    weak = [s for s in skill_scores if s["score"] < 70]
    good = [s for s in skill_scores if s["score"] >= 85]
    lines = []
    if good:
        lines.append(f"掌握较好的技能：{', '.join(s['skill_name'] for s in good)}")
    if weak:
        lines.append(f"薄弱技能点（需加强）：{', '.join(s['skill_name'] for s in weak)}")
        lines.append("建议：针对薄弱技能点增加实操练习次数，教师可进行专项指导。")
    else:
        lines.append("各技能点掌握均衡，继续保持。")
    return "\n".join(lines)
