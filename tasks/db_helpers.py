
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from db import db  # глобальный инстанс Database создан в db.py

logger = logging.getLogger(__name__)

STATUS_RU = {
    "pending":       "Ожидание",
    "in_progress":   "В работе",
    "wait_confirm":  "Ожидает подтверждения",   # ← НОВОЕ
    "completed":     "Завершена",
    "overdue":       "Просрочена",
    "canceled":      "Отклонена",
}

def get_status_ru(status: str) -> str:
    return STATUS_RU.get(status, "Ожидание")

async def get_employees(exclude_id: int | None = None) -> List[Dict[str, Any]]:
    sql = "SELECT user_id, full_name FROM users WHERE is_confirmed = 1"
    params: list[Any] = []
    if exclude_id:
        sql += " AND user_id != ?"
        params.append(exclude_id)
    rows = await db.execute_query(sql, tuple(params) if params else ())
    return rows or []

async def calculate_penalties() -> None:
    """Автоматически начисляет штрафы за просроченные задачи."""
    today = datetime.now().date()
    # задачи в статусе new
    rows = await db.execute_query(
        """
        SELECT id, assigned_to 
        FROM tasks 
        WHERE status='pending' AND deadline <= date(?, '-1 day')
        """, (today,)
    )
    if rows:
        for row in rows:
            await _apply_penalty(row['id'], row['assigned_to'], "Просрочка задачи (Ожидание)", today)

    # задачи в статусе in_progress
    rows = await db.execute_query(
        """
        SELECT id, assigned_to 
        FROM tasks 
        WHERE status='in_progress' AND deadline < ?
        """, (today,)
    )
    if rows:
        for row in rows:
            await _apply_penalty(row['id'], row['assigned_to'], "Просрочка задачи (В работе)", today)

async def _apply_penalty(task_id: int, user_id: int, reason: str, today):
    await db.execute_query(
        """
        INSERT INTO fines (user_id, amount, reason, task_id, status, created_by)
        VALUES (?, 1000, ?, ?, 'pending', ?)
        """, (user_id, reason, task_id, user_id)
    )
    await db.execute_query(
        "UPDATE tasks SET status='overdue' WHERE id = ?", (task_id,)
    )
