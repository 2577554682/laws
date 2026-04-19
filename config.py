"""项目运行配置集中管理。"""

APP_TITLE = "⚖️ 刑法辅助分析系统"
APP_PAGE_TITLE = "刑法辅助分析系统"
APP_CAPTION = "基于本地案例库与刑法原文 | 辅助分析，不替代司法判断"

CASES_PATH = "resources/cases.json"
INDEX_PATH = "resources/case_index.faiss"
CRIME_PATTERNS_PATH = "resources/crime_patterns.json"
LAWS_PATH = "resources/laws.json"

FACT_FIELD = "基本案情"

MODEL_NAME = "deepseek-chat"
OPENAI_BASE_URL = "https://api.deepseek.com"
OPENAI_API_KEY_ENV = "DEEPSEEK_API_KEY"

TOP_K = 8
SIM_THRESHOLD_MIN = 0.30
SIM_THRESHOLD_MAX = 0.90
SIM_THRESHOLD_DEFAULT = 0.45
SIM_THRESHOLD_STEP = 0.01

LAW_REF_MAX_ITEMS = 6
CASE_REF_MAX_ITEMS = 3

