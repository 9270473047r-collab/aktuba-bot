from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

router = Router()


def _selected_farm_for_submit(data: dict) -> str:
    return (data.get("submit_farm_title") or data.get("selected_location") or "").strip()


@router.callback_query(F.data.in_({"prod_report2_submit", "prod_report3_submit"}))
async def report_submit_handler(callback: types.CallbackQuery, state: FSMContext):
    farm = _selected_farm_for_submit(await state.get_data())
    title = "Производство"
    if farm:
        await callback.message.answer(
            f"📍 Ферма: <b>{farm}</b>\n🧾 Раздел: <b>{title}</b>\n\n⚙️ Этот отчёт пока в разработке.",
            parse_mode="HTML",
        )
    else:
        await callback.message.answer(
            f"🧾 Раздел: <b>{title}</b>\n\n⚙️ Этот отчёт пока в разработке.",
            parse_mode="HTML",
        )
    await callback.answer()


# Backward compatibility (если где-то ещё используется старый callback)
@router.callback_query(F.data == "prod_report_submit")
async def report_submit_handler_legacy(callback: types.CallbackQuery):
    await callback.message.answer("Пришлите файл, фото или текст отчёта для производственного отдела.")
    await callback.answer()
