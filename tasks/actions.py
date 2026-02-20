from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from datetime import datetime, timedelta

from .fsm import AcceptFSM
from .db_helpers import get_employees
from db import db

router = Router()

# --- Принять задачу -------------------------------------------------------
@router.callback_query(F.data.startswith("task:accept:"))
async def accept_task(callback: types.CallbackQuery):
    """Исполнитель подтверждает, что берёт задачу в работу."""
    task_id = int(callback.data.split(":")[-1])

    # Изменяем статус в БД
    await db.execute_query(
        "UPDATE tasks SET status='in_progress', is_accepted=1 WHERE id=?",
        (task_id,)
    )

    # Убираем кнопки управления, чтобы их нельзя было нажать повторно
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        # Сообщение уже было изменено – игнорируем
        pass

    await callback.message.answer("✅ Задача принята в работу")
    await callback.answer()

# --- Делегировать ---------------------------------------------------------
@router.callback_query(F.data.startswith("task:delegate:"))
async def start_delegate(callback: types.CallbackQuery, state: FSMContext):
    """Запускаем выбор нового исполнителя."""
    task_id = int(callback.data.split(":")[-1])
    await state.update_data(task_id=task_id)

    # Убираем старую клавиатуру, чтобы не копить дубликаты
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Собираем список потенциальных сотрудников
    employees = await get_employees(exclude_id=callback.from_user.id)
    if not employees:
        await callback.message.answer("Не удалось найти сотрудников для делегирования.")
        await callback.answer()
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=e["full_name"],
                                  callback_data=f"task:delegate_to:{e['user_id']}")]
            for e in employees
        ]
    )

    await callback.message.answer("Выберите нового исполнителя:", reply_markup=kb)
    await state.set_state(AcceptFSM.waiting_for_delegate_target)
    await callback.answer()

@router.callback_query(F.data.startswith("task:delegate_to:"), AcceptFSM.waiting_for_delegate_target)
async def complete_delegate(callback: types.CallbackQuery, state: FSMContext):
    """Переназначаем задачу на другого пользователя."""
    assignee_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    task_id = data.get("task_id")

    await db.execute_query(
        """UPDATE tasks
               SET assigned_to=?, status='pending', is_accepted=0
               WHERE id=?""",
        (assignee_id, task_id)
    )

    await callback.message.answer("↪️ Задача успешно делегирована")
    await state.clear()
    await callback.answer()

# --- Отклонить ------------------------------------------------------------
@router.callback_query(F.data.startswith("task:reject:"))
async def start_reject(callback: types.CallbackQuery, state: FSMContext):
    """Запрашиваем комментарий для отказа."""
    task_id = int(callback.data.split(":")[-1])
    await state.update_data(task_id=task_id)

    # Скрываем старые кнопки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer("Укажите причину отклонения:")
    await state.set_state(AcceptFSM.waiting_for_reject_comment)
    await callback.answer()

@router.message(AcceptFSM.waiting_for_reject_comment)
async def save_reject(message: types.Message, state: FSMContext):
    """Сохраняем комментарий и меняем статус."""
    data = await state.get_data()
    task_id = data.get("task_id")
    comment = message.text.strip()

    await db.execute_query(
        """UPDATE tasks
               SET status='canceled', reject_comment=?
               WHERE id=?""",
        (comment, task_id)
    )

    await message.answer("❌ Задача отклонена")
    await state.clear()


# --- Продлить дедлайн ------------------------------------------------------
@router.callback_query(F.data.startswith("task:extend:"))
async def extend_deadline(callback: types.CallbackQuery):
    task_id = int(callback.data.split(":")[-1])

    row = await db.execute_query("SELECT deadline FROM tasks WHERE id=?", (task_id,))
    if not row or not row[0].get("deadline"):
        await callback.answer("Дедлайн не найден", show_alert=True)
        return

    # +3 дня (можно поменять на настройку)
    try:
        new_date = (
            datetime.strptime(row[0]["deadline"], "%Y-%m-%d") + timedelta(days=3)
        ).strftime("%Y-%m-%d")
    except ValueError:
        await callback.answer("Некорректный формат даты", show_alert=True)
        return

    await db.execute_query(
        "UPDATE tasks SET deadline=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (new_date, task_id)
    )

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer(f"⏳ Дедлайн продлён до {new_date}")
    await callback.answer()


# --- Завершить задачу ------------------------------------------------------
@router.callback_query(F.data.startswith("task:complete:"))
async def complete_task(callback: types.CallbackQuery):
    """Исполнитель отправляет задачу на подтверждение постановщику."""
    task_id = int(callback.data.split(":")[-1])

    await db.execute_query(
        """UPDATE tasks
               SET status='wait_confirm', confirm_status='wait', updated_at=CURRENT_TIMESTAMP
             WHERE id=?""",
        (task_id,)
    )

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer("✅ Отчёт отправлен руководителю на подтверждение")
    await callback.answer()


# --- Подтвердить выполнение ------------------------------------------------
@router.callback_query(F.data.startswith("task:confirm:"))
async def confirm_task_done(callback: types.CallbackQuery):
    task_id = int(callback.data.split(":")[-1])

    await db.execute_query(
        """UPDATE tasks
               SET status='completed', confirm_status='confirmed', completed_at=CURRENT_TIMESTAMP,
                   updated_at=CURRENT_TIMESTAMP
             WHERE id=?""",
        (task_id,)
    )

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer("👍 Выполнение подтверждено")
    await callback.answer()


# --- Вернуть в работу ------------------------------------------------------
@router.callback_query(F.data.startswith("task:return:"))
async def return_task_to_work(callback: types.CallbackQuery):
    task_id = int(callback.data.split(":")[-1])

    await db.execute_query(
        """UPDATE tasks
               SET status='in_progress', confirm_status='rejected', updated_at=CURRENT_TIMESTAMP
             WHERE id=?""",
        (task_id,)
    )

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer("↩️ Отчёт отклонён, задача возвращена в работу")
    await callback.answer()
