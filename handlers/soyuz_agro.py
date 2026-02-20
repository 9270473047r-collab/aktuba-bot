from aiogram import Router, types, F

router = Router()

# Эта функция сработает только на CallbackQuery с data == "soyuz_agro"
@router.callback_query(F.data == "soyuz_agro")
async def soyuz_agro_callback(callback: types.CallbackQuery):
    await callback.message.answer("Здесь будет отдельный отчёт по ООО «Союз-Агро».")
    await callback.answer()
