from collections import defaultdict

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from db import db
from org.models import ORG_STRUCTURE
from keyboards import get_main_menu
from utils.cleaner import auto_clean_chat

router = Router()


def get_fio_short(fio: str) -> str:
    parts = (fio or "").split()
    if len(parts) >= 2:
        res = f"{parts[0]} {parts[1][0]}."
        if len(parts) > 2:
            res += f"{parts[2][0]}."
        return res
    return fio or "—"


@router.message(F.text == "👥 Оргструктура")
@auto_clean_chat()
async def org_view(message: types.Message, state: FSMContext):
    # Берём подтверждённых пользователей из БД (важно: block хранится отдельно!)
    rows = await db.execute_query(
        "SELECT full_name, role, department, block FROM users WHERE is_confirmed = 1"
    ) or []

    # {(dept, block, role): [fio1, fio2, ...]}
    assigned = defaultdict(list)
    for r in rows:
        fio = r.get("full_name") or ""
        dept = (r.get("department") or "").strip()
        block = (r.get("block") or "").strip()
        role = (r.get("role") or "").strip()
        role_clean = role.split(" (")[0].strip() if role else ""

        if dept and block and role_clean:
            assigned[(dept, block, role_clean)].append(get_fio_short(fio))

    # Формируем текст оргструктуры
    text = "<b>Оргструктура ЖК «Актюба»</b>\n"

    for dept, blocks in ORG_STRUCTURE.items():
        text += f"\n\n<b>{dept}</b>\n"
        for block, positions in blocks.items():
            text += f"  <b>{block}</b>:\n"
            for pos in positions:
                staff = assigned.get((dept, block, pos), [])
                fio_text = ", ".join(staff) if staff else "<i>Свободно</i>"
                text += f"    — {pos}: {fio_text}\n"

    sent = await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu(message.from_user.id))
    await state.update_data(last_bot_message_id=sent.message_id)
