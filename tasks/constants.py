"""Project‑wide constants

⚠️ Важно: администраторы задаются через .env (ADMIN_IDS).
"""

from config import ADMIN_IDS, DEPUTY_IDS, ADMIN_ID

# Единая карта статусов задачи.
STATUS_RU = {
    "pending":       "Ожидание",
    "in_progress":   "В работе",
    "wait_confirm":  "Ожидает подтверждения",   # ← НОВОЕ
    "completed":     "Завершена",
    "overdue":       "Просрочена",
    "canceled":      "Отклонена",
}
