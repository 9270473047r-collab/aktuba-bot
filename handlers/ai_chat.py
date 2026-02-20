from aiogram import Router, types, F

router = Router()

@router.message(F.text == "🤖 Чат с ИИ-ассистентом")
async def ai_stub(message: types.Message):
    await message.answer("ИИ-ассистент готовится к запуску. Введите /ask <вопрос> чтобы попробовать.")
