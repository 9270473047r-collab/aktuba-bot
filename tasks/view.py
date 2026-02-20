# tasks/my_tasks.py
from __future__ import annotations

import sqlite3
import textwrap
from datetime import datetime

from aiogram import Router, types, F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .db_helpers import calculate_penalties, get_status_ru
from .menu        import get_tasks_menu          # показываем, когда задач нет
from .controls    import task_controls
from db           import db, DB_PATH             # async-wrapper

router = Router()

# ──────────────────── helpers ──────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    """Синхронное подключение (read-only) к SQLite."""
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


async def _cleanup_orphan_tasks() -> None:
    """Удаляем задачи без существующего исполнителя."""
    await db.execute_query(
        """
        DELETE FROM tasks
        WHERE assigned_to NOT IN (SELECT user_id FROM users)
        """
    )

# ──────────────────── основной хэндлер «Мои задачи» ───────────────────
@router.message(F.text == "Мои задачи")
async def show_my_tasks(msg: types.Message) -> None:
    uid = msg.from_user.id

    # 1) чистим базу от висящих задач
    await _cleanup_orphan_tasks()

    # 2) перерасчёт просрочек / штрафов (внутри пропускаем несуществующих пользователей)
    await calculate_penalties()

    # 3) выбираем задачи: мои активные + мои же, ожидающие подтверждения
    sql = """
        SELECT  t.id, t.title, t.description, t.status,
                t.deadline, t.created_at,
                t.confirm_status, t.assigned_to, t.assigned_by,
                cr.full_name AS creator_name
        FROM    tasks t
        LEFT JOIN users cr ON cr.user_id = t.assigned_by
        WHERE   (t.assigned_to = :me
                 AND t.status IN ('pending','in_progress','overdue'))
            OR  (t.assigned_by  = :me
                 AND t.status          = 'wait_confirm'
                 AND t.confirm_status  = 'wait')
        ORDER BY
                CASE t.status
                    WHEN 'overdue'      THEN 0
                    WHEN 'pending'      THEN 1
                    WHEN 'in_progress'  THEN 2
                    WHEN 'wait_confirm' THEN 3
                    ELSE 4
                END,
                t.deadline
        LIMIT 50
    """

    with _conn() as con:
        rows = con.execute(sql, {"me": uid}).fetchall()

    # если задач нет — выводим лаконичное сообщение и меню «Задачи»
    if not rows:
        await msg.answer("🎉 Активных задач нет!", reply_markup=get_tasks_menu())
        return

    now = datetime.now()

    def fmt(raw: str | None, out: str = "%d.%m.%Y") -> str:
        """Удобное форматирование даты (или «—»)."""
        if not raw:
            return "—"
        for inp in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(raw, inp).strftime(out)
            except ValueError:
                continue
        return "—"

    for t in rows:
        # ─── данные из строки ───────────────────────────────────────
        tid         = t["id"]
        status_eng  = t["status"] or "pending"
        status_ru   = get_status_ru(status_eng)
        desc        = t["description"] or "Без описания"
        creator     = t["creator_name"] or "Неизвестно"

        deadline    = fmt(t["deadline"])
        created     = fmt(t["created_at"])
        days_passed = "—"
        if t["created_at"]:
            try:
                days_passed = (
                    now - datetime.strptime(t["created_at"], "%Y-%m-%d %H:%M:%S")
                ).days
            except ValueError:
                pass

        # ─── текст карточки ────────────────────────────────────────
        card = textwrap.dedent(f"""
            <b>{status_ru}</b>
            <b>#{tid}: {t['title']}</b>
            {desc}

            Постановщик: {creator}
            Поставлена:  {created} (дней: {days_passed})
            Дедлайн:     {deadline}
        """)

        # ─── клавиатура ────────────────────────────────────────────
        kb_markup: InlineKeyboardMarkup | None = None

        # 1. задача ждёт принятия
        if status_eng == "pending" and t["assigned_to"] == uid:
            kb_markup = task_controls(tid)

        # 2. в работе или просрочена
        elif status_eng in ("in_progress", "overdue") and t["assigned_to"] == uid:
            kb_markup = InlineKeyboardMarkup(
                inline_keyboard=[[ 
                    InlineKeyboardButton(text="⏳ Продлить",  callback_data=f"task:extend:{tid}"),
                    InlineKeyboardButton(text="✔️ Завершить", callback_data=f"task:complete:{tid}"),
                ]]
            )

        # 3. исполнитель прислал отчёт; автор подтверждает
        elif (status_eng == "wait_confirm"
              and t["confirm_status"] == "wait"
              and t["assigned_by"] == uid):
            kb_markup = InlineKeyboardMarkup(
                inline_keyboard=[[ 
                    InlineKeyboardButton(text="👍 Подтвердить", callback_data=f"task:confirm:{tid}"),
                    InlineKeyboardButton(text="↩️ Отклонить",   callback_data=f"task:return:{tid}"),
                ]]
            )

        await msg.answer(card, parse_mode="HTML", reply_markup=kb_markup)

    # Никакого дополнительного меню в конце — только карточки задач
