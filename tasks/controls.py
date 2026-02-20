from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def task_controls(task_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для управления входящей задачей."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять", callback_data=f"task:accept:{task_id}"),
                InlineKeyboardButton(text="↪️ Делегировать", callback_data=f"task:delegate:{task_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"task:reject:{task_id}")
            ]
        ]
    )
