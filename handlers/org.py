from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

from db import db
from utils.cleaner import auto_clean_chat
from utils.pdf_org_structure import build_org_pdf

router = Router()


@router.message(F.text == "👥 Оргструктура")
@auto_clean_chat()
async def org_view(message: types.Message, state: FSMContext):
    users = await db.execute_query(
        "SELECT full_name, role, department, block FROM users WHERE is_confirmed = 1"
    ) or []

    pdf_b = build_org_pdf(users)
    await message.answer_document(
        BufferedInputFile(pdf_b, filename="org_structure.pdf"),
        caption="📋 Оргструктура — ООО «Союз-Агро»",
    )
