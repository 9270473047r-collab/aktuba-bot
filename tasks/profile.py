from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta

from admin_keyboards import get_admin_menu
from keyboards import get_main_menu

from config import ADMIN_IDS
from db import db

router = Router()


@router.message(F.text == "👤 Мой профиль")
async def show_profile_summary(message: types.Message, state: FSMContext):
    now = datetime.now()

    # границы текущего месяца
    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    next_month  = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end   = next_month.strftime("%Y-%m-%d")

    # ── задачи
    tasks = await db.execute_query(
        """
        SELECT status
        FROM tasks
        WHERE assigned_to = ?
          AND date(created_at) >= date(?)
          AND date(created_at) <  date(?)
        """,
        (message.from_user.id, month_start, month_end)
    )

    # ── штрафы
    fine_row = await db.execute_query(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM fines
        WHERE user_id = ?
          AND status = 'confirmed'
          AND date(created_at) >= date(?)
          AND date(created_at) <  date(?)
        """,
        (message.from_user.id, month_start, month_end)
    )
    total_fine = fine_row[0]["total"] if fine_row else 0

    # ── статистика
    total        = len(tasks)
    completed    = sum(1 for t in tasks if t["status"] == "completed")
    in_progress  = sum(1 for t in tasks if t["status"] == "in_progress")
    pending      = sum(1 for t in tasks if t["status"] == "pending")
    wait_confirm = sum(1 for t in tasks if t["status"] == "wait_confirm")
    overdue      = sum(1 for t in tasks if t["status"] == "overdue")
    canceled     = sum(1 for t in tasks if t["status"] == "canceled")

    rating = completed * 10 - overdue * 5 - total_fine // 100

    text = (
        f"<b>👤 Профиль: {message.from_user.full_name}</b>\n"
        f"⭐ <b>Рейтинг: {rating} баллов</b>\n\n"
        f"📅 <b>Статистика задач за {now.strftime('%B %Y')}:</b>\n"
        f"• Всего задач: <b>{total}</b>\n"
        f"• Выполнено: <b>{completed}</b>\n"
        f"• В работе: <b>{in_progress}</b>\n"
        f"• Ожидают начала: <b>{pending}</b>\n"
        f"• Ожидает подтверждения: <b>{wait_confirm}</b>\n"
        f"• Просрочено: <b>{overdue}</b>\n"
        f"• Отклонено/отменено: <b>{canceled}</b>\n"
        f"\n💸 <b>Сумма штрафов: {total_fine} ₽</b>"
    )

    kb = get_admin_menu() if message.from_user.id in ADMIN_IDS else get_main_menu(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)
