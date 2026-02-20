from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from tasks.menu import get_tasks_menu
from keyboards import get_main_menu
from .constants import ADMIN_ID           # пока не используется, но пригодится для будущих проверок
from .fsm import TaskFSM
from .db_helpers import get_employees
from db import db
from datetime import datetime

router = Router()


# ────────────────────────────
# ШАГ 1. Выбор типа назначения
# ────────────────────────────
@router.message(F.text == "➕ Добавить задачу")
async def add_task_btn(message: types.Message, state: FSMContext):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Задача себе",     callback_data="task:add:self")],
            [InlineKeyboardButton(text="➕ Делегировать",    callback_data="task:add:delegate")],
        ]
    )
    await message.answer("Кому назначить задачу?", reply_markup=kb)
    await state.set_state(TaskFSM.choose_action)


# ────────────────────────────
# ШАГ 2. Краткий заголовок
# ────────────────────────────
@router.callback_query(F.data == "task:add:self")
async def process_self(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(task_target="self")
    await callback.message.edit_text("Введите краткое название задачи:")
    await state.set_state(TaskFSM.title)
    await callback.answer()


@router.callback_query(F.data == "task:add:delegate")
async def process_delegate(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(task_target="delegate")
    await callback.message.edit_text("Введите краткое название задачи:")
    await state.set_state(TaskFSM.title)
    await callback.answer()


@router.message(TaskFSM.title)
async def got_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer("Опишите задачу подробнее:")
    await state.set_state(TaskFSM.description)


# ────────────────────────────
# ШАГ 3. Подробное описание + выбор исполнителя (если нужно)
# ────────────────────────────
@router.message(TaskFSM.description)
async def got_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    data = await state.get_data()

    if data.get("task_target") == "self":
        # назначаем себе → сразу спрашиваем срок
        await message.answer("Укажите срок задачи (ДД.ММ.ГГГГ):")
        await state.set_state(TaskFSM.deadline)
    else:
        # нужно выбрать исполнителя
        employees = await get_employees(exclude_id=message.from_user.id)
        if not employees:
            await message.answer("Нет доступных сотрудников.")
            await state.clear()
            return

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=emp["full_name"],
                                      callback_data=f"task:emp:{emp['user_id']}")]
                for emp in employees
            ]
        )
        await message.answer("Выберите исполнителя задачи:", reply_markup=kb)
        await state.set_state(TaskFSM.assignee)


# ────────────────────────────
# ШАГ 4. Выбор исполнителя (для делегирования)
# ────────────────────────────
@router.callback_query(F.data.startswith("task:emp:"), TaskFSM.assignee)
async def selected_employee(callback: types.CallbackQuery, state: FSMContext):
    assignee_id = int(callback.data.split(":")[-1])
    await state.update_data(assignee=assignee_id)
    await callback.message.edit_text("Укажите срок задачи (ДД.ММ.ГГГГ):")
    await state.set_state(TaskFSM.deadline)
    await callback.answer()


# ────────────────────────────
# ШАГ 5. Ввод срока и сохранение в БД
# ────────────────────────────
@router.message(TaskFSM.deadline)
async def create_task_record(message: types.Message, state: FSMContext):
    data = await state.get_data()
    deadline_raw = message.text.strip()

    # ───── проверяем формат даты
    try:
        dt = datetime.strptime(deadline_raw, "%d.%m.%Y")
    except ValueError:
        await message.answer("Неверный формат даты, попробуйте ещё раз (ДД.ММ.ГГГГ).")
        return

    assignee_id: int = data.get("assignee") or message.from_user.id
    assigner_id: int = message.from_user.id
    title        = data["title"]
    description  = data["description"]
    deadline_db  = dt.strftime("%Y-%m-%d")

    # ───── генерация сквозных номеров задачи
    month = dt.strftime("%m")
    task_count   = await db.execute_query(
        "SELECT COUNT(*) AS c FROM tasks WHERE strftime('%m', created_at)=?", (month,))
    global_num   = f"{month}-{task_count[0]['c'] + 1:04d}"

    user_count   = await db.execute_query(
        "SELECT COUNT(*) AS c FROM tasks WHERE assigned_to=? AND strftime('%m', created_at)=?",
        (assignee_id, month)
    )
    user_num     = user_count[0]['c'] + 1

    # ───── вставляем запись
    await db.execute_query(
        """
        INSERT INTO tasks (
            title, description,
            assigned_by, assigned_to,
            deadline,  status,
            global_num, user_num
        )
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
        """,
        (title, description, assigner_id, assignee_id, deadline_db, global_num, user_num)
    )

    # ───── получаем ID только что созданной задачи
    result   = await db.execute_query("SELECT last_insert_rowid() AS id")
    task_id  = result[0]["id"]

    # ───── уведомляем исполнителя (если это не мы сами)
    if assignee_id != assigner_id:
        from .controls import task_controls
        bot: Bot = message.bot
        await bot.send_message(
            assignee_id,
            f"📌 Вам назначена новая задача:\n<b>{title}</b>",
            reply_markup=task_controls(task_id),
            parse_mode="HTML"
        )

    await message.answer("✅ Задача создана", reply_markup=get_main_menu(message.from_user.id))
    await state.clear()
