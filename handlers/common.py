from __future__ import annotations

from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from db import db
from keyboards.main_menu import get_main_menu
from utils.cleaner import auto_clean_chat

from .registration_v2 import RegV2

router = Router()


async def user_is_confirmed(user_id: int) -> bool:
    """Проверяем, подтверждён ли пользователь."""
    row = await db.get_user(user_id)
    return bool(row and row.get("is_confirmed") == 1)


@router.message(CommandStart())
@auto_clean_chat()
async def start_cmd(message: types.Message, state: FSMContext):
    """Единая точка входа. Если пользователь не подтверждён — запускаем регистрацию V2."""
    if not await user_is_confirmed(message.from_user.id):
        await state.clear()
        sent = await message.answer(
            "Добро пожаловать! Для доступа к меню пройдите регистрацию.\n\n"
            "Введите <b>ФИО</b> (пример: Иванов Иван Иванович):",
        )
        await state.update_data(last_bot_message_id=sent.message_id)
        await state.set_state(RegV2.full_name)
        return

    sent = await message.answer(
        "Добро пожаловать! Используйте меню для работы.",
        reply_markup=get_main_menu(message.from_user.id),
    )
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(F.text == "Меню")
async def menu_button_handler(message: types.Message):
    if not await user_is_confirmed(message.from_user.id):
        await message.answer("Сначала пройдите регистрацию через /start")
        return

    await message.answer(
        "Главное меню:",
        reply_markup=get_main_menu(message.from_user.id),
    )


@router.message(F.text == "⬅️ Выйти в главное меню")
async def to_main_menu(message: types.Message):
    if not await user_is_confirmed(message.from_user.id):
        await message.answer("Сначала пройдите регистрацию через /start")
        return

    await message.answer(
        "Главное меню:",
        reply_markup=get_main_menu(message.from_user.id),
    )
