"""Роутер, который открывает меню задач и возвращает в главное меню."""

from aiogram import Router, types, F
from tasks.menu import get_tasks_menu
from keyboards import get_main_menu

router = Router()


@router.message(F.text == "📋 Задачи")
async def show_tasks_menu(message: types.Message):
    """Открыть под-меню «Задачи»."""
    await message.answer(
        "Меню задач:",
        reply_markup=get_tasks_menu()
    )


@router.message(F.text == "⬅️ Назад")
async def back_to_main(message: types.Message):
    """Вернуться в главное меню."""
    await message.answer(
        "Главное меню:",
        reply_markup=get_main_menu(message.from_user.id)
    )
