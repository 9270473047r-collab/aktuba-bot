import os
from datetime import datetime
from aiogram.types import FSInputFile
from utils.pdf_mtp_directory import build_mtp_directory_pdf_bytes
from aiogram.types import BufferedInputFile
from utils.pdf_mtp_directory import build_mtp_directory_pdf
from keyboards import get_main_menu
from admin_keyboards import (
    get_reglament_menu,
    get_reference_menu,
    get_mtp_reference_menu,
    get_cancel_keyboard,
)

from aiogram import Router, types, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from utils.cleaner import auto_clean_chat
from db import db
from org.models import ORG_STRUCTURE

router = Router()


# ─────────────────────────────── FSM: «Справочник МТП» ───────────────────────
class MtpDirectoryFSM(StatesGroup):
    unit_name = State()
    equipment_name = State()
    inv_number = State()
    year = State()
    responsible = State()
    comment = State()


# ─────────────────────────────── «Документация» ──────────────────────────────
@router.message(F.text.in_(("📄 Документация", "Документация")))
@auto_clean_chat()
async def show_reglament_menu(message: types.Message, state: FSMContext):
    sent = await message.answer("Меню регламентов:", reply_markup=get_reglament_menu())
    await state.update_data(last_bot_message_id=sent.message_id)


# ─────────────────────────────── «Справочник» ───────────────────────────────
@router.message(F.text.in_(("📚 Справочник", "Справочник")))
@auto_clean_chat()
async def show_reference_menu(message: types.Message, state: FSMContext):
    sent = await message.answer("Справочники:", reply_markup=get_reference_menu())
    await state.update_data(last_bot_message_id=sent.message_id)


# ─────────────────────────────── «Справочник МТП» ───────────────────────────
@router.message(F.text.in_(("🚜 Справочник МТП", "Справочник МТП")))
@auto_clean_chat()
async def show_mtp_reference_menu(message: types.Message, state: FSMContext):
    sent = await message.answer("🚜 Справочник МТП:", reply_markup=get_mtp_reference_menu())
    await state.update_data(last_bot_message_id=sent.message_id)


# ─────────────────────────────── «Заполнить справочник» ─────────────────────
@router.message(F.text.in_(("✍️ Заполнить справочник", "Заполнить справочник")))
@auto_clean_chat()
async def mtp_directory_fill_start(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(MtpDirectoryFSM.unit_name)
    sent = await message.answer(
        "Введите подразделение/отделение (например: МТП, ЖК Актюба, Карамалы):",
        reply_markup=get_cancel_keyboard(),
    )
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(MtpDirectoryFSM.unit_name)
@auto_clean_chat()
async def mtp_directory_fill_unit(message: types.Message, state: FSMContext):
    if (message.text or "").strip() in ("❌ Отмена", "Отмена"):
        await state.clear()
        sent = await message.answer("🚜 Справочник МТП:", reply_markup=get_mtp_reference_menu())
        await state.update_data(last_bot_message_id=sent.message_id)
        return

    await state.update_data(unit_name=(message.text or "").strip())
    await state.set_state(MtpDirectoryFSM.equipment_name)
    sent = await message.answer("Введите наименование техники (например: Трактор МТЗ-82, Погрузчик, КамАЗ):")
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(MtpDirectoryFSM.equipment_name)
@auto_clean_chat()
async def mtp_directory_fill_equipment(message: types.Message, state: FSMContext):
    if (message.text or "").strip() in ("❌ Отмена", "Отмена"):
        await state.clear()
        sent = await message.answer("🚜 Справочник МТП:", reply_markup=get_mtp_reference_menu())
        await state.update_data(last_bot_message_id=sent.message_id)
        return

    await state.update_data(equipment_name=(message.text or "").strip())
    await state.set_state(MtpDirectoryFSM.inv_number)
    sent = await message.answer("Введите инвентарный/гос номер (как у вас принято):")
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(MtpDirectoryFSM.inv_number)
@auto_clean_chat()
async def mtp_directory_fill_inv(message: types.Message, state: FSMContext):
    if (message.text or "").strip() in ("❌ Отмена", "Отмена"):
        await state.clear()
        sent = await message.answer("🚜 Справочник МТП:", reply_markup=get_mtp_reference_menu())
        await state.update_data(last_bot_message_id=sent.message_id)
        return

    await state.update_data(inv_number=(message.text or "").strip())
    await state.set_state(MtpDirectoryFSM.year)
    sent = await message.answer("Введите год выпуска (или напишите '-' если не знаете):")
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(MtpDirectoryFSM.year)
@auto_clean_chat()
async def mtp_directory_fill_year(message: types.Message, state: FSMContext):
    if (message.text or "").strip() in ("❌ Отмена", "Отмена"):
        await state.clear()
        sent = await message.answer("🚜 Справочник МТП:", reply_markup=get_mtp_reference_menu())
        await state.update_data(last_bot_message_id=sent.message_id)
        return

    year = (message.text or "").strip()
    if year == "-":
        year = None
    await state.update_data(year=year)
    await state.set_state(MtpDirectoryFSM.responsible)
    sent = await message.answer("Введите ответственного (ФИО/должность):")
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(MtpDirectoryFSM.responsible)
@auto_clean_chat()
async def mtp_directory_fill_responsible(message: types.Message, state: FSMContext):
    if (message.text or "").strip() in ("❌ Отмена", "Отмена"):
        await state.clear()
        sent = await message.answer("🚜 Справочник МТП:", reply_markup=get_mtp_reference_menu())
        await state.update_data(last_bot_message_id=sent.message_id)
        return

    await state.update_data(responsible=(message.text or "").strip())
    await state.set_state(MtpDirectoryFSM.comment)
    sent = await message.answer("Комментарий (можно 0):")
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(MtpDirectoryFSM.comment)
@auto_clean_chat()
async def mtp_directory_fill_finish(message: types.Message, state: FSMContext):
    if (message.text or "").strip() in ("❌ Отмена", "Отмена"):
        await state.clear()
        sent = await message.answer("🚜 Справочник МТП:", reply_markup=get_mtp_reference_menu())
        await state.update_data(last_bot_message_id=sent.message_id)
        return

    data = await state.get_data()
    comment = (message.text or "").strip()
    if comment in ("0", "-", "нет", "Нет"):
        comment = None

    await db.add_mtp_directory_item(
        unit_name=data.get("unit_name"),
        equipment_name=data.get("equipment_name"),
        inv_number=data.get("inv_number"),
        year=data.get("year"),
        responsible=data.get("responsible"),
        comment=comment,
        created_by=message.from_user.id,
    )

    await state.clear()
    sent = await message.answer("✅ Запись добавлена в 🚜 Справочник МТП.", reply_markup=get_mtp_reference_menu())
    await state.update_data(last_bot_message_id=sent.message_id)


# ─────────────────────────────── «Посмотреть справочник» ────────────────────
@router.message(F.text.in_(("👀 Посмотреть справочник", "Посмотреть справочник")))
@auto_clean_chat()
async def mtp_directory_view(message: types.Message, state: FSMContext):
    items = await db.list_mtp_directory_items(limit=200)
    if not items:
        sent = await message.answer(
            "🚜 Справочник МТП пока пуст.\nНажмите «✍️ Заполнить справочник», чтобы добавить первую запись.",
            reply_markup=get_mtp_reference_menu(),
        )
        await state.update_data(last_bot_message_id=sent.message_id)
        return

    pdf_bytes = build_mtp_directory_pdf_bytes("🚜 Справочник МТП", items)
    file_name = f"mtp_directory_{message.from_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    with open(file_name, "wb") as f:
        f.write(pdf_bytes)

    await message.answer_document(
        FSInputFile(file_name),
        caption="🚜 Справочник МТП (PDF)",
        reply_markup=get_mtp_reference_menu(),
    )

    try:
        os.remove(file_name)
    except Exception:
        pass

# ─────────────────────────────── Навигация внутри документации ──────────────
@router.message(F.text == "⬅️ Назад в документацию")
@auto_clean_chat()
async def back_to_docs_menu(message: types.Message, state: FSMContext):
    await state.clear()
    sent = await message.answer("Меню регламентов:", reply_markup=get_reglament_menu())
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(F.text == "⬅️ Назад в справочник")
@auto_clean_chat()
async def back_to_reference_menu(message: types.Message, state: FSMContext):
    await state.clear()
    sent = await message.answer("Справочники:", reply_markup=get_reference_menu())
    await state.update_data(last_bot_message_id=sent.message_id)


# ─────────────────────────────── «Назад» ──────────────────────────────────────
@router.message(F.text == "⬅️ Назад")
@auto_clean_chat()
async def back_to_main_menu(message: types.Message, state: FSMContext):
    sent = await message.answer("Главное меню:", reply_markup=get_main_menu(message.from_user.id))
    await state.update_data(last_bot_message_id=sent.message_id)
    await state.clear()


# ─────────────────────────────── Заглушки ─────────────────────────────────────
@router.message(F.text == "📑 Регламенты")
@auto_clean_chat()
async def show_reglaments(message: types.Message, state: FSMContext):
    sent = await message.answer("Здесь будут регламенты.", reply_markup=get_reglament_menu())
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(F.text == "📖 Инструкция")
@auto_clean_chat()
async def show_instruction(message: types.Message, state: FSMContext):
    sent = await message.answer("Здесь будет инструкция.", reply_markup=get_reglament_menu())
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(F.text == "📋 Протокола")
@auto_clean_chat()
async def show_protocols(message: types.Message, state: FSMContext):
    sent = await message.answer("Здесь будут протоколы.", reply_markup=get_reglament_menu())
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(F.text == "📋 Протоколы")
@auto_clean_chat()
async def show_protocols_plural(message: types.Message, state: FSMContext):
    sent = await message.answer("Здесь будут протоколы.", reply_markup=get_reglament_menu())
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(F.text == "✔️ Чек-листы")
@auto_clean_chat()
async def show_checklists(message: types.Message, state: FSMContext):
    sent = await message.answer("Здесь будут чек-листы.", reply_markup=get_reglament_menu())
    await state.update_data(last_bot_message_id=sent.message_id)
