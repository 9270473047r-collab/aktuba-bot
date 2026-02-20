from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from .fsm import AcceptFSM
from tasks.menu import get_tasks_menu
from keyboards import get_main_menu
from config import ADMIN_IDS
from .constants import ADMIN_ID                   # на случай, если поля нет
from db import db

router = Router()

# Статусы, доступные для завершения/продления
FINISHABLE_STATUSES  = ("pending", "in_progress", "wait_confirm", "overdue")
PROLONGABLE_STATUSES = FINISHABLE_STATUSES


# ──────────────────────────────── «Завершить задачу» ─────────────────────────
@router.message(F.text == "🔚 Завершить задачу")
async def finish_task_choose(message: types.Message, state: FSMContext):
    rows = await db.execute_query(
        f"""
        SELECT id, title, global_num
        FROM tasks
        WHERE assigned_to = ?
          AND status IN ({','.join('?' * len(FINISHABLE_STATUSES))})
        """,
        (message.from_user.id, *FINISHABLE_STATUSES)
    )
    if not rows:
        await message.answer("У вас нет задач для завершения.", reply_markup=get_tasks_menu())
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{row['title']} (#{row['global_num']})",
                                  callback_data=f"finish_{row['id']}")]
            for row in rows
        ]
    )
    await message.answer("Выберите задачу для завершения:", reply_markup=kb)
    await state.clear()


@router.callback_query(F.data.startswith("finish_"))
async def finish_task_callback(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.replace("finish_", ""))
    await state.set_state(AcceptFSM.waiting_for_report)
    await state.update_data(task_id=task_id)
    await callback.message.answer("Прикрепите фото/видео/документ по задаче или напишите отчёт сообщением:")
    await callback.answer()


# ─────────────────────────────── Отчёт по задаче ────────────────────────────
@router.message(AcceptFSM.waiting_for_report)
async def report_file_or_text(message: types.Message, state: FSMContext):
    data    = await state.get_data()
    task_id = data["task_id"]

    # --- что прислал сотрудник
    file_id, file_type, text_report = None, None, None
    if message.photo:
        file_id, file_type = message.photo[-1].file_id, "photo"
    elif message.video:
        file_id, file_type = message.video.file_id, "video"
    elif message.document:
        file_id, file_type = message.document.file_id, "document"
    elif message.text:
        text_report = message.text.strip()

    # --- переводим задачу в wait_confirm и сохраняем отчёт
    await db.execute_query(
        """
        UPDATE tasks
        SET file_id     = ?,
            file_type   = ?,
            status      = 'wait_confirm',
            updated_at  = CURRENT_TIMESTAMP,
            description = COALESCE(description, '') || ?
        WHERE id = ?
        """,
        (
            file_id,
            file_type,
            ("\n\nОтчёт: " + text_report) if text_report else "",
            task_id,
        ),
    )

    # --- достаём полную информацию о задаче
    row = await db.execute_query(
        """
        SELECT title, description, deadline, created_at,
               global_num, assigned_by
        FROM   tasks
        WHERE  id = ?
        """,
        (task_id,),
    )
    task = row[0]
    assigner_id = task["assigned_by"] or ADMIN_ID

    # форматируем даты
    deadline_txt = datetime.strptime(task["deadline"], "%Y-%m-%d").strftime("%d.%m.%Y")
    created_txt  = datetime.strptime(task["created_at"], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")

    # --- текст уведомления руководителю
    confirm_text = (
        f"<b>{message.from_user.full_name}</b> просит подтвердить выполнение задачи\n\n"
        f"<b>#{task['global_num']} — {task['title']}</b>\n"
        f"{task['description'] or 'Без описания'}\n\n"
        f"Поставлена: {created_txt}\n"
        f"Дедлайн:    {deadline_txt}\n"
    )
    if text_report:
        confirm_text += f"\n<b>Отчёт:</b>\n{text_report}\n"
    if file_type:
        confirm_text += f"\n📎 Приложен файл: {file_type}"

    # --- клавиатура (только 2 кнопки)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_task_{task_id}"),
            InlineKeyboardButton(text="❌ Отклонить",  callback_data=f"decline_task_{task_id}")
        ]]
    )

    # --- отправка руководителю (с учётом файла)
    if file_type == "photo":
        await message.bot.send_photo(assigner_id, file_id, caption=confirm_text,
                                     parse_mode="HTML", reply_markup=kb)
    elif file_type == "video":
        await message.bot.send_video(assigner_id, file_id, caption=confirm_text,
                                     parse_mode="HTML", reply_markup=kb)
    elif file_type == "document":
        await message.bot.send_document(assigner_id, file_id, caption=confirm_text,
                                        parse_mode="HTML", reply_markup=kb)
    else:
        await message.bot.send_message(assigner_id, confirm_text,
                                       parse_mode="HTML", reply_markup=kb)

    await message.answer("Ваш отчёт отправлен руководителю на подтверждение.")
    await state.clear()


# ─────────────────────────────── «Продлить задачу» ──────────────────────────
@router.message(F.text == "⏩ Продлить задачу")
async def prolong_task_choose(message: types.Message, state: FSMContext):
    rows = await db.execute_query(
        f"""
        SELECT id, title, global_num
        FROM tasks
        WHERE assigned_to = ?
          AND status IN ({','.join('?' * len(PROLONGABLE_STATUSES))})
        """,
        (message.from_user.id, *PROLONGABLE_STATUSES)
    )
    if not rows:
        await message.answer("Нет активных задач для продления.", reply_markup=get_tasks_menu())
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{row['title']} (#{row['global_num']})",
                                  callback_data=f"prolong_{row['id']}")]
            for row in rows
        ]
    )
    await message.answer("Выберите задачу для продления срока:", reply_markup=kb)
    await state.clear()


@router.callback_query(F.data.startswith("prolong_"))
async def prolong_task_callback(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.replace("prolong_", ""))
    await state.set_state(AcceptFSM.waiting_for_prolong_date)
    await state.update_data(task_id=task_id)
    await callback.message.answer("Введите новую дату (ДД.ММ.ГГГГ):")
    await callback.answer()


@router.message(AcceptFSM.waiting_for_prolong_date)
async def prolong_set_date(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_id = data["task_id"]
    deadline_raw = message.text.strip()

    try:
        deadline_db = datetime.strptime(deadline_raw, "%d.%m.%Y").strftime("%Y-%m-%d")
    except ValueError:
        await message.answer("Некорректный формат! Введите срок (ДД.ММ.ГГГГ):")
        return

    await db.execute_query(
        "UPDATE tasks SET deadline = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (deadline_db, task_id)
    )

    await message.answer("Срок задачи успешно обновлён.")
    await state.clear()


# ──────────────────────── Подтвердить / отклонить отчёт ──────────────────────
@router.callback_query(F.data.startswith("confirm_task_"))
async def confirm_task(callback: types.CallbackQuery):
    task_id = int(callback.data.replace("confirm_task_", ""))
    task_row = await db.execute_query(
        "SELECT assigned_to, assigned_by, global_num FROM tasks WHERE id = ?",
        (task_id,)
    )
    if not task_row:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    task = task_row[0]

    await db.execute_query(
        """
        UPDATE tasks
        SET status = 'completed',
            confirm_status = 'confirmed',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (task_id,)
    )

    await callback.message.answer("Задача подтверждена!")
    await callback.answer()

    await callback.bot.send_message(
        task["assigned_to"],
        f"✅ Ваша задача #{task['global_num']} подтверждена руководителем. Работа засчитана!"
    )
    await callback.bot.send_message(
        task["assigned_by"],
        f"✅ Задача #{task['global_num']} успешно подтверждена!"
    )


@router.callback_query(F.data.startswith("decline_task_"))
async def decline_task(callback: types.CallbackQuery):
    task_id = int(callback.data.replace("decline_task_", ""))
    task_row = await db.execute_query(
        "SELECT assigned_to, assigned_by, global_num FROM tasks WHERE id = ?",
        (task_id,)
    )
    if not task_row:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    task = task_row[0]

    await db.execute_query(
        """
        UPDATE tasks
        SET status = 'in_progress',
            confirm_status = 'rejected',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (task_id,)
    )

    await callback.message.answer("Выполнение задачи отклонено. Необходимо доработать!")
    await callback.answer()

    await callback.bot.send_message(
        task["assigned_to"],
        f"❌ Ваш отчёт по задаче #{task['global_num']} отклонён руководителем. Доработайте и отправьте снова!"
    )
    await callback.bot.send_message(
        task["assigned_by"],
        f"❌ Выполнение задачи #{task['global_num']} было отклонено."
    )
