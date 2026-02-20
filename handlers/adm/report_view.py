from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

router = Router()


def _selected_farm_for_view(data: dict) -> str:
    return (data.get("view_farm_title") or data.get("selected_location") or "").strip()


@router.callback_query(F.data.in_({"adm_report1_view", "adm_report2_view", "adm_report3_view"}))
async def report_view_handler(callback: types.CallbackQuery, state: FSMContext):
    farm = _selected_farm_for_view(await state.get_data())
    title = "АХО"
    if farm:
        await callback.message.answer(
            f"📍 Ферма: <b>{farm}</b>\n📊 Раздел: <b>{title}</b>\n\n⚙️ Просмотр пока в разработке.",
            parse_mode="HTML",
        )
    else:
        await callback.message.answer(
            f"📊 Раздел: <b>{title}</b>\n\n⚙️ Просмотр пока в разработке.",
            parse_mode="HTML",
        )
    await callback.answer()
