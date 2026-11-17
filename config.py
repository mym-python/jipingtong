"""
配置模块：读取环境变量，管理 DeepSeek API 配置与平台基础配置
"""
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# ===== DeepSeek API 配置 =====
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# ===== 平台配置 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "platform.db")

# 确保目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 评价模式
EVAL_MODE_WORK = "作品分析法+档案袋评定法"
EVAL_MODE_OBS = "观察法+档案袋评定法"
EVAL_MODE_COMBINED = "综合模式（观察+作品+档案袋）"

EVAL_MODES = [EVAL_MODE_OBS, EVAL_MODE_WORK, EVAL_MODE_COMBINED]

# 综合模式默认权重：观察评价占比
DEFAULT_OBS_WEIGHT = 0.4

# 评分范围
SCORE_MIN = 0
SCORE_MAX = 100
