from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from keyboards import get_main_menu                # главное меню (у всех)
from admin_keyboards import (                       # все админ-клавиатуры
    get_admin_menu,
    get_user_management_keyboard,
)
from config import ADMIN_IDS                     # список ID админов
from utils.cleaner import auto_clean_chat

router = Router()

# ───────────────────── помощник ─────────────────────
def user_is_admin(user_id: int) -> bool:
    """Проверка прав администратора."""
    return user_id in ADMIN_IDS                     # или await db.is_admin(...)

# ───────────────────── /admin ───────────────────────
@router.message(F.text == "/admin")
@auto_clean_chat()
async def admin_menu(message: types.Message, state: FSMContext):
    if not user_is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора!")
        return
    sent = await message.answer(
        "🔐 Административное меню:",
        reply_markup=get_admin_menu()
    )
    await state.update_data(last_bot_message_id=sent.message_id)

# ─────────────── «👥 Пользователи» ───────────────────
@router.message(F.text == "👥 Пользователи")
@auto_clean_chat()
async def handle_users_menu(message: types.Message, state: FSMContext):
    if not user_is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён!")
        return
    sent = await message.answer(
        "🔐 Раздел управления пользователями:",
        reply_markup=get_user_management_keyboard()
    )
    await state.update_data(last_bot_message_id=sent.message_id)

# ─────────── «⬅️ Назад в админ меню» ────────────────
@router.message(F.text == "⬅️ Назад в админ меню")
@auto_clean_chat()
async def back_to_admin_menu(message: types.Message, state: FSMContext):
    if not user_is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён!")
        return
    sent = await message.answer(
        "🔐 Административное меню:",
        reply_markup=get_admin_menu()
    )
    await state.update_data(last_bot_message_id=sent.message_id)

