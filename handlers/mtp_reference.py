from __future__ import annotations

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import BufferedInputFile

from utils.cleaner import auto_clean_chat

# Клавиатуры (если у вас уже есть в admin_keyboards.py — используем их)
try:
    from admin_keyboards import (
        get_reglament_menu,
        get_reference_menu,
        get_mtp_reference_menu,
        get_cancel_keyboard,
    )
except Exception:
    # Фолбек (если нет admin_keyboards)
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

    def get_reglament_menu():
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📚 Справочник")], [KeyboardButton(text="⬅️ Назад")]],
            resize_keyboard=True,
        )

    def get_reference_menu():
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🚜 Справочник МТП")], [KeyboardButton(text="⬅️ Назад в документацию")]],
            resize_keyboard=True,
        )

    def get_mtp_reference_menu():
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✍️ Заполнить справочник"), KeyboardButton(text="👀 Посмотреть справочник")],
                [KeyboardButton(text="⬅️ Назад в справочник")],
            ],
            resize_keyboard=True,
        )

    def get_cancel_keyboard():
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

from utils.mtp_directory_storage import MtpDirectoryStorage
from utils.pdf_mtp_directory import build_mtp_directory_pdf


router = Router()
storage = MtpDirectoryStorage()


class MtpDirectoryFSM(StatesGroup):
    unit_name = State()
    equipment_name = State()
    inv_number = State()
    year = State()
    responsible = State()
    comment = State()


# ─────────────────────────────── Меню справочника ───────────────────────────────

@router.message(F.text.in_(("📚 Справочник", "Справочник")))
@auto_clean_chat()
async def open_reference_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Справочники:", reply_markup=get_reference_menu())


@router.message(F.text.in_(("🚜 Справочник МТП", "Справочник МТП")))
@auto_clean_chat()
async def open_mtp_reference_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🚜 Справочник МТП:", reply_markup=get_mtp_reference_menu())


@router.message(F.text == "⬅️ Назад в документацию")
@auto_clean_chat()
async def back_to_docs(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Меню документации:", reply_markup=get_reglament_menu())


@router.message(F.text == "⬅️ Назад в справочник")
@auto_clean_chat()
async def back_to_reference(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Справочники:", reply_markup=get_reference_menu())


# ─────────────────────────────── Заполнение ───────────────────────────────

@router.message(F.text.in_(("✍️ Заполнить справочник", "Заполнить справочник")))
@auto_clean_chat()
async def mtp_fill_start(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(MtpDirectoryFSM.unit_name)
    await message.answer(
        "Введите подразделение/отделение (пример: МТП, ЖК Актюба, Карамалы):",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(F.text.in_(("❌ Отмена", "Отмена")))
@auto_clean_chat()
async def mtp_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🚜 Справочник МТП:", reply_markup=get_mtp_reference_menu())


@router.message(MtpDirectoryFSM.unit_name)
@auto_clean_chat()
async def mtp_fill_unit(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    await state.update_data(unit_name=text)
    await state.set_state(MtpDirectoryFSM.equipment_name)
    await message.answer("Введите технику (марка/модель), пример: МТЗ-82, JCB, КамАЗ 65115:")


@router.message(MtpDirectoryFSM.equipment_name)
@auto_clean_chat()
async def mtp_fill_equipment(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    await state.update_data(equipment_name=text)
    await state.set_state(MtpDirectoryFSM.inv_number)
    await message.answer("Введите номер техники (инвентарный/госномер):")


@router.message(MtpDirectoryFSM.inv_number)
@auto_clean_chat()
async def mtp_fill_number(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    await state.update_data(inv_number=text)
    await state.set_state(MtpDirectoryFSM.year)
    await message.answer("Введите год выпуска (или '-' если не знаете):")


@router.message(MtpDirectoryFSM.year)
@auto_clean_chat()
async def mtp_fill_year(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    year = None if text == "-" else text
    await state.update_data(year=year)
    await state.set_state(MtpDirectoryFSM.responsible)
    await message.answer("Введите ответственного (ФИО/должность):")


@router.message(MtpDirectoryFSM.responsible)
@auto_clean_chat()
async def mtp_fill_responsible(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    await state.update_data(responsible=text)
    await state.set_state(MtpDirectoryFSM.comment)
    await message.answer("Комментарий (можно 0):")


@router.message(MtpDirectoryFSM.comment)
@auto_clean_chat()
async def mtp_fill_finish(message: types.Message, state: FSMContext):
    comment_raw = (message.text or "").strip()
    comment = None if comment_raw in ("0", "-", "нет", "Нет") else comment_raw

    data = await state.get_data()

    await storage.add_item(
        unit_name=data["unit_name"],
        equipment_name=data["equipment_name"],
        inv_number=data["inv_number"],
        year=data.get("year"),
        responsible=data["responsible"],
        comment=comment,
        created_by=message.from_user.id,
    )

    await state.clear()
    await message.answer("✅ Запись добавлена в 🚜 Справочник МТП.", reply_markup=get_mtp_reference_menu())


# ─────────────────────────────── Просмотр PDF ───────────────────────────────

@router.message(F.text.in_(("👀 Посмотреть справочник", "Посмотреть справочник")))
@auto_clean_chat()
async def mtp_view_pdf(message: types.Message, state: FSMContext):
    items = await storage.list_items(limit=200)  # можете увеличить/уменьшить

    pdf_bytes, filename = build_mtp_directory_pdf(
        items=items,
        org_title="ЖК «Актюба»",
        report_title="Справочник МТП",
    )

    file = BufferedInputFile(pdf_bytes, filename=filename)
    await message.answer_document(
        document=file,
        caption="📄 Справочник МТП (PDF)",
        reply_markup=get_mtp_reference_menu(),
    )
