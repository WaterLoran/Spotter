import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

DATA_DIR = Path(os.getenv("DATA_DIR", str(PROJECT_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

MAIN_DB_NAME = os.getenv("MAIN_DB_NAME", "logs.db")
MAIN_DB_PATH = DATA_DIR / MAIN_DB_NAME

SQLEYE_DB_NAME = os.getenv("SQLEYE_DB_NAME", "sqleye.db")
SQLEYE_DB_PATH = Path(os.getenv("SQLEYE_DB_PATH", str(BASE_DIR / SQLEYE_DB_NAME)))

APIEYE_DB_NAME = os.getenv("APIEYE_DB_NAME", "apieye.db")
APIEYE_DB_PATH = Path(os.getenv("APIEYE_DB_PATH", str(BASE_DIR / APIEYE_DB_NAME)))

REDIS_DB_NAME = os.getenv("REDIS_DB_NAME", "redis_eye.db")
REDIS_DB_PATH = Path(os.getenv("REDIS_DB_PATH", str(BASE_DIR / REDIS_DB_NAME)))

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
APP_LOG_PATH = LOG_DIR / "app.log"

SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
SCHEDULER_INTERVAL_SECONDS = int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "5"))
# 多搜索配置使用全量 cat，与主配置增量分开轮询，避免每轮长时间占锁拖死主路径 tail 采集
SCHEDULER_SEARCH_CONFIG_INTERVAL_SECONDS = int(os.getenv("SCHEDULER_SEARCH_CONFIG_INTERVAL_SECONDS", "60"))

DEFAULT_CONFIG = {
    "server_host": os.getenv("DEFAULT_SERVER_HOST", "127.0.0.1"),
    "server_username": os.getenv("DEFAULT_SERVER_USERNAME", "root"),
    "server_password": os.getenv("DEFAULT_SERVER_PASSWORD", ""),
    "server_port": os.getenv("DEFAULT_SERVER_PORT", "22"),
    "log_directory": os.getenv("DEFAULT_LOG_DIRECTORY", "/var/log"),
    "search_text": os.getenv("DEFAULT_SEARCH_TEXT", "error"),
    "init_time_range_minutes": os.getenv("DEFAULT_INIT_TIME_RANGE_MINUTES", "120"),
    "context_lines_before": os.getenv("DEFAULT_CONTEXT_LINES_BEFORE", "0"),
    "context_lines_after": os.getenv("DEFAULT_CONTEXT_LINES_AFTER", "0"),
    "append_search_text": os.getenv("DEFAULT_APPEND_SEARCH_TEXT", ""),
    "append_context_before": os.getenv("DEFAULT_APPEND_CONTEXT_BEFORE", "0"),
    "append_context_after": os.getenv("DEFAULT_APPEND_CONTEXT_AFTER", "0"),
    "append_time_range_minutes": os.getenv("DEFAULT_APPEND_TIME_RANGE_MINUTES", "0"),
    "append_dedupe_same_content": os.getenv("DEFAULT_APPEND_DEDUPE_SAME_CONTENT", "1"),
    # 主配置目录定时增量采集（与多搜索配置各条 enabled 无关）
    "main_log_collection_enabled": os.getenv("DEFAULT_MAIN_LOG_COLLECTION_ENABLED", "1"),
}
