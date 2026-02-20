import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

# ── токены ───────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ── вспомогательное ─────────────────────────────────────────────────────────
def _parse_ids(raw: str) -> list[int]:
    """Строку '1, 2 ,3' → [1,2,3]  (пустые / неверные отбросит)."""
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]

# ── «мой» ID (не обязателен) ────────────────────────────────────────────────
MY_ADMIN_ID: int | None = (
    int(os.getenv("MY_ADMIN_ID")) if os.getenv("MY_ADMIN_ID", "").isdigit() else None
)

# ── админы (полная админ-панель) ─────────────────────────────────────────────
ADMIN_IDS: list[int] = _parse_ids(os.getenv("ADMIN_IDS", ""))
if MY_ADMIN_ID and MY_ADMIN_ID not in ADMIN_IDS:
    ADMIN_IDS.append(MY_ADMIN_ID)

ADMIN_ID: int | None = ADMIN_IDS[0] if ADMIN_IDS else None
DEPUTY_IDS: list[int] = ADMIN_IDS.copy()

# ── пользователи с доступом к «Все задачи» ──────────────────────────────────
TASK_VIEWERS: list[int] = _parse_ids(os.getenv("TASK_VIEWERS", ""))

# гарантируем, что все админы автоматически становятся TASK_VIEWERS
for _id in ADMIN_IDS:
    if _id not in TASK_VIEWERS:
        TASK_VIEWERS.append(_id)

# ── dataclass Config ────────────────────────────────────────────────────────
@dataclass
class Config:
    api_token: str
    openai_api_key: str | None
    admin_ids: list[int]
    admin_id: int | None
    deputy_ids: list[int]
    task_viewers: list[int]          # ← НОВОЕ

def load_config() -> Config:
    return Config(
        api_token      = BOT_TOKEN,
        openai_api_key = OPENAI_API_KEY,
        admin_ids      = ADMIN_IDS,
        admin_id       = ADMIN_ID,
        deputy_ids     = DEPUTY_IDS,
        task_viewers   = TASK_VIEWERS,
    )

