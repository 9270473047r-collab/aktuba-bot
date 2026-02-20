from keyboards import get_main_menu
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from utils.cleaner import auto_clean_chat
from keyboards import main_menu  # ← Импортируй главное меню!

router = Router()

@router.message(F.text == "📈 Сдать KPI")
@auto_clean_chat()
async def kpi_input(message: types.Message, state: FSMContext):
    sent = await message.answer(
        "Ввод и просмотр KPI пока в разработке.",
        reply_markup=get_main_menu(message.from_user.id)
    )
    await state.update_data(last_bot_message_id=sent.message_id)
