from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

from db import db
from keyboards import get_main_menu
from utils.cleaner import auto_clean_chat
from utils.pdf_org_structure import (
    build_org_pdf_full,
    build_org_pdf_zhk,
    build_org_pdf_subdivision,
)

router = Router()

SUBDIVISION_DEPARTMENTS = {"Карамалы", "Шереметьево", "Бирючевка"}


async def _get_confirmed_users():
    return await db.execute_query(
        "SELECT full_name, role, department, block FROM users WHERE is_confirmed = 1"
    ) or []


async def _get_user_department(user_id: int) -> str:
    user = await db.get_user(user_id)
    return ((user or {}).get("department") or "").strip()


@router.message(F.text == "👥 Оргструктура")
@auto_clean_chat()
async def org_view(message: types.Message, state: FSMContext):
    dept = await _get_user_department(message.from_user.id)
    users = await _get_confirmed_users()

    if dept == "Отдел животноводства":
        pdf_b = build_org_pdf_full(users)
        title = "Союз-Агро"
    elif dept in SUBDIVISION_DEPARTMENTS:
        pdf_b = build_org_pdf_subdivision(users, dept)
        title = dept
    else:
        pdf_b = build_org_pdf_zhk(users)
        title = "ЖК Актюба"

    filename = f"org_{title.replace(' ', '_')}.pdf"
    await message.answer_document(
        BufferedInputFile(pdf_b, filename=filename),
        caption=f"📋 Оргструктура — {title}",
    )
