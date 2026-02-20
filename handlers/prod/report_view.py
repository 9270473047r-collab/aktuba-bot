from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

router = Router()


def _selected_farm_for_view(data: dict) -> str:
    return (data.get("view_farm_title") or data.get("selected_location") or "").strip()


@router.callback_query(F.data.in_({"prod_report2_view", "prod_report3_view"}))
async def report_view_handler(callback: types.CallbackQuery, state: FSMContext):
    farm = _selected_farm_for_view(await state.get_data())
    title = "Производство"
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


# Backward compatibility (если где-то ещё используется старый callback)
@router.callback_query(F.data == "prod_report_view")
async def report_view_handler_legacy(callback: types.CallbackQuery):
    await callback.message.answer("Вот последние отчёты по производственного отдела.")
    await callback.answer()