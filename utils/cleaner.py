from functools import wraps

def auto_clean_chat():
    def decorator(handler_func):
        @wraps(handler_func)
        async def wrapper(message, state, *args, **kwargs):
            data = await state.get_data()
            # Удаляем прошлое сообщение пользователя
            last_user_id = data.get("last_user_message_id")
            if last_user_id:
                try:
                    await message.bot.delete_message(message.chat.id, last_user_id)
                except Exception:
                    pass
            # Удаляем прошлое сообщение бота
            last_bot_id = data.get("last_bot_message_id")
            if last_bot_id:
                try:
                    await message.bot.delete_message(message.chat.id, last_bot_id)
                except Exception:
                    pass
            # Сохраняем id текущего сообщения пользователя
            await state.update_data(last_user_message_id=message.message_id)
            return await handler_func(message, state, *args, **kwargs)
        return wrapper
    return decorator
