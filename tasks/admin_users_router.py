# tasks/admin_users_router.py
# ─────────────────────────────────────────────────────────────────────────────
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from config import ADMIN_IDS                         # ← только отсюда!
from keyboards import get_back_keyboard
from admin_keyboards import get_admin_menu, get_user_management_keyboard
from db import db

from fpdf import FPDF
import tempfile
import os

router = Router()

# ─────────────────────────────── FSM ─────────────────────────────────────────
class AddUserFSM(StatesGroup):
    waiting_for_user_id  = State()
    waiting_for_fullname = State()
    waiting_for_role     = State()

class DeleteUserFSM(StatesGroup):
    waiting_for_user_id  = State()

class ChangeRoleFSM(StatesGroup):
    waiting_for_user_id  = State()
    waiting_for_new_role = State()

"""Управление пользователями.

В этом проекте поле users.role используется как <должность/профессия>.
Уровень доступа хранится в users.position.
"""


# ───────────────────── «👥 Пользователи» (вход) ──────────────────────────────
@router.message(F.text == "👥 Пользователи")
async def open_user_management(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("⛔ У вас нет доступа.")
    await message.answer(
        "🔐 Раздел управления пользователями:",
        reply_markup=get_user_management_keyboard(),
    )


# ───────────────────────── «📋 Список пользователей» ─────────────────────────
@router.message(F.text == "📋 Список пользователей")
async def show_user_list(message: types.Message):
    rows = await db.execute_query(
        "SELECT user_id, full_name, role, is_confirmed FROM users ORDER BY role, full_name"
    )
    if not rows:
        return await message.answer("В базе нет пользователей.", reply_markup=get_back_keyboard())

    import tempfile
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    # Используем системный шрифт DejaVu Sans (универсальный для кириллицы)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    pdf.add_font("DejaVu", "", font_path, uni=True)
    pdf.set_font("DejaVu", size=12)
    pdf.cell(0, 10, "Список пользователей", ln=1, align="C")
    pdf.ln(5)
    pdf.set_font("DejaVu", size=10)
    pdf.cell(0, 10, "Статус  |  Telegram ID  |  ФИО  |  Роль", ln=1)

    for r in rows:
        status = "✅" if r.get("is_confirmed") else "⏳"
        role   = r.get("role") or "user"
        full_name = str(r.get("full_name") or "")
        if len(full_name) > 43:
            full_name = full_name[:40] + "..."
        try:
            line = f"{status}   |   {r.get('user_id')}   |   {full_name}   |   {role}"
        except Exception as e:
            line = f"ОШИБКА ПОЛЯ: {e}"
        pdf.cell(0, 8, line, ln=1)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        pdf.output(tmp_file.name)
        tmp_file_path = tmp_file.name

    await message.answer_document(types.FSInputFile(tmp_file_path), caption="📋 Список пользователей (PDF)", reply_markup=get_back_keyboard())
    os.remove(tmp_file_path)

# ───────────────────────── «👤 Добавить пользователя» ────────────────────────
@router.message(F.text == "👤 Добавить пользователя")
async def add_user_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Введите Telegram-ID нового пользователя:", reply_markup=get_back_keyboard())
    await state.set_state(AddUserFSM.waiting_for_user_id)

@router.message(AddUserFSM.waiting_for_user_id)
async def add_user_get_id(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.clear()
        return await open_user_management(message)
    if not message.text.isdigit():
        return await message.answer("ID должен быть числом.")
    await state.update_data(user_id=int(message.text))
    await message.answer("Введите ФИО пользователя:")
    await state.set_state(AddUserFSM.waiting_for_fullname)

@router.message(AddUserFSM.waiting_for_fullname)
async def add_user_get_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await message.answer("Введите должность пользователя (пример: Инженер, Оператор, Зоотехник):")
    await state.set_state(AddUserFSM.waiting_for_role)

@router.message(AddUserFSM.waiting_for_role)
async def add_user_finish(message: types.Message, state: FSMContext):
    role = message.text.strip()
    if len(role) < 2:
        return await message.answer("Введите должность (минимум 2 символа).")
    data = await state.get_data()
    await db.execute_query(
        "INSERT OR IGNORE INTO users (user_id, full_name, role, is_confirmed) VALUES (?, ?, ?, 0)",
        (data["user_id"], data["full_name"], role)
    )
    await message.answer("✅ Пользователь добавлен (пока не подтверждён).",
                         reply_markup=get_user_management_keyboard())
    await state.clear()


# ───────────────────────── «🗑 Удалить пользователя» ────────────────────────
@router.message(F.text == "🗑 Удалить пользователя")
async def del_user_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Введите Telegram-ID пользователя для удаления:",
                         reply_markup=get_back_keyboard())
    await state.set_state(DeleteUserFSM.waiting_for_user_id)

@router.message(DeleteUserFSM.waiting_for_user_id)
async def del_user_finish(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.clear()
        return await open_user_management(message)
    if not message.text.isdigit():
        return await message.answer("ID должен быть числом.")
    uid = int(message.text)
    rows = await db.execute_query("DELETE FROM users WHERE user_id = ?", (uid,))
    await message.answer("✅ Пользователь удалён." if rows else "Пользователь не найден.",
                         reply_markup=get_user_management_keyboard())
    await state.clear()


# ───────────────────────── «🔄 Изменить роль» ───────────────────────────────
@router.message(F.text == "🔄 Изменить роль")
async def change_role_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Введите Telegram-ID пользователя:",
                         reply_markup=get_back_keyboard())
    await state.set_state(ChangeRoleFSM.waiting_for_user_id)

@router.message(ChangeRoleFSM.waiting_for_user_id)
async def change_role_get_id(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.clear()
        return await open_user_management(message)
    if not message.text.isdigit():
        return await message.answer("ID должен быть числом.")
    await state.update_data(user_id=int(message.text))
    await message.answer("Введите новую должность пользователя:")
    await state.set_state(ChangeRoleFSM.waiting_for_new_role)

@router.message(ChangeRoleFSM.waiting_for_new_role)
async def change_role_finish(message: types.Message, state: FSMContext):
    role = message.text.strip()
    if len(role) < 2:
        return await message.answer("Введите должность (минимум 2 символа).")
    data = await state.get_data()
    await db.execute_query("UPDATE users SET role = ? WHERE user_id = ?", (role, data["user_id"]))
    await message.answer("✅ Роль обновлена.", reply_markup=get_user_management_keyboard())
    await state.clear()


# ───────────────────────── «⬅️ Назад в админ меню» ──────────────────────────
@router.message(F.text == "⬅️ Назад в админ меню")
async def back_to_admin_menu(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("🔐 Административное меню:", reply_markup=get_admin_menu())
