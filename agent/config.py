"""全局配置：从项目根目录的 .env 读取密钥，初始化模型客户端与常量。"""

import os
from pathlib import Path

import httpx
from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKDIR = Path.cwd()


def _load_env(path: Path):
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(PROJECT_ROOT / ".env")

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
if not API_KEY or API_KEY == "sk-your-key-here":
    raise SystemExit(
        f"缺少 API Key：请在 {PROJECT_ROOT / '.env'} 中填写 DEEPSEEK_API_KEY"
        "（可参考 .env.example）。"
    )

client = OpenAI(
    api_key=API_KEY,
    base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    # 本机系统代理环境变量格式异常，httpx 解析会抛 InvalidURL，故忽略环境代理。
    http_client=httpx.Client(trust_env=False),
)

MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
PRIMARY_MODEL = MODEL
FALLBACK_MODEL = None

# 根据操作系统告诉模型，应该使用什么命令格式。
ENVIRONMENT_PROMPT = (
    "Windows：bash 工具通过 cmd.exe 执行，请使用 cmd.exe 语法，文件操作优先使用专用文件工具。"
    if os.name == "nt"
    else "Unix-like：bash 工具通过系统 shell 执行。"
)

SKILLS_DIR = WORKDIR / "skills"
TRANSCRIPT_DIR = WORKDIR / ".transcripts"
TOOL_RESULTS_DIR = WORKDIR / ".task_outputs" / "tool-results"

DEFAULT_MAX_TOKENS = 8000
ESCALATED_MAX_TOKENS = 16000
MAX_RETRIES = 3
MAX_CONSECUTIVE_529 = 2
MAX_RECOVERY_RETRIES = 2
BASE_DELAY_MS = 500
CONTEXT_LIMIT = 50000
KEEP_RECENT_TOOL_RESULTS = 3
PERSIST_THRESHOLD = 30000
CONTINUATION_PROMPT = "Continue from the previous response. Do not repeat completed work."
PROMPT = "\033[36ms15 >> \033[0m"
CLI_ACTIVE = False