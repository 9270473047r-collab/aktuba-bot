from keyboards import get_main_menu
from aiogram import Router, types, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from org.models import ORG_STRUCTURE
from db import db
from utils.cleaner import auto_clean_chat

router = Router()

SUPERUSER_ID = 409710353  # Ваш user_id

class HeadAssignFSM(StatesGroup):
    waiting_for_department = State()
    waiting_for_block_or_role = State()
    waiting_for_employee = State()

@router.message(F.text == "👔 Назначить руководителя")
@auto_clean_chat()
async def choose_department(message: types.Message, state: FSMContext):
    if message.from_user.id != SUPERUSER_ID:
        sent = await message.answer("Нет доступа.", reply_markup=get_main_menu(message.from_user.id))
        await state.update_data(last_bot_message_id=sent.message_id)
        return
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text=dept, callback_data=f"assign_dept_{dept}")]
            for dept in ORG_STRUCTURE.keys()
        ]
    )
    sent = await message.answer("Выберите отдел:", reply_markup=keyboard)
    await state.update_data(last_bot_message_id=sent.message_id)
    await state.set_state(HeadAssignFSM.waiting_for_department)

@router.callback_query(F.data.startswith("assign_dept_"), HeadAssignFSM.waiting_for_department)
async def choose_block_or_role(callback: types.CallbackQuery, state: FSMContext):
    dept = callback.data.replace("assign_dept_", "")
    await state.update_data(department=dept)
    blocks_or_roles = list(ORG_STRUCTURE[dept].keys())
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text=block, callback_data=f"assign_block_{block}")]
            for block in blocks_or_roles
        ]
    )
    sent = await callback.message.answer("Выберите блок, отдел или спец. должность:", reply_markup=keyboard)
    await state.update_data(last_bot_message_id=sent.message_id)
    await state.set_state(HeadAssignFSM.waiting_for_block_or_role)

@router.callback_query(F.data.startswith("assign_block_"), HeadAssignFSM.waiting_for_block_or_role)
async def choose_employee(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    dept = data["department"]
    block = callback.data.replace("assign_block_", "")
    await state.update_data(block_or_role=block)
    # Получаем всех пользователей этого блока/роли
    with db() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT user_id, full_name, role FROM users WHERE department LIKE ? OR role LIKE ?",
            (f"%{dept}%", f"%{block}%")
        )
        employees = c.fetchall()
    if not employees:
        sent = await callback.message.answer("Нет сотрудников в этом блоке/роли!", reply_markup=get_main_menu(message.from_user.id))
        await state.update_data(last_bot_message_id=sent.message_id)
        await state.clear()
        return
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=f"{emp['full_name']} ({emp['role']})",
                    callback_data=f"assign_emp_{emp['user_id']}"
                )
            ] for emp in employees
        ]
    )
    sent = await callback.message.answer("Выберите сотрудника для назначения:", reply_markup=keyboard)
    await state.update_data(last_bot_message_id=sent.message_id)
    await state.set_state(HeadAssignFSM.waiting_for_employee)

@router.callback_query(F.data.startswith("assign_emp_"), HeadAssignFSM.waiting_for_employee)
async def assign_head(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    dept = data["department"]
    block = data["block_or_role"]
    user_id = int(callback.data.replace("assign_emp_", ""))
    with db() as conn:
        c = conn.cursor()
        # Удаляем старого руководителя если был
        c.execute("DELETE FROM department_block_heads WHERE department=? AND block=?", (dept, block))
        # Назначаем нового
        c.execute(
            "INSERT INTO department_block_heads (department, block, user_id, role) VALUES (?, ?, ?, ?)",
            (dept, block, user_id, "Руководитель")
        )
        conn.commit()
    sent = await callback.message.answer(
        f"Назначен руководитель для {block} в {dept}!",
        reply_markup=get_main_menu(message.from_user.id)
    )
    await state.update_data(last_bot_message_id=sent.message_id)
    await callback.bot.send_message(
        user_id,
        f"Вы назначены руководителем для {block} в {dept}."
    )
    await state.clear()
