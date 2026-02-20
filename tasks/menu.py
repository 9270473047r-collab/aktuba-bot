"""
Клавиатуры, относящиеся к разделу «Задачи».
"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_tasks_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔚 Завершить задачу"), KeyboardButton(text="⏩ Продлить задачу")],
            [KeyboardButton(text="Мои задачи"), KeyboardButton(text="Все задачи")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )

__all__ = ["get_tasks_menu"]
