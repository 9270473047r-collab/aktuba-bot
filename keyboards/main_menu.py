from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_menu(user_id: int) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📋 Задачи"),
                KeyboardButton(text="➕ Добавить задачу"),
            ],
            [
                KeyboardButton(text="📄 Отчеты"),
                KeyboardButton(text="📈 KPI"),
            ],
            [
                KeyboardButton(text="📄 Документация"),
                KeyboardButton(text="👤 Мой профиль"),
            ],
        ],
        resize_keyboard=True,
    )

def get_back_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True,
    )
