from __future__ import annotations

import re
from typing import List

from aiogram import Router, types, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

from config import ADMIN_IDS
from db import db
from org.models import ORG_STRUCTURE
from keyboards.main_menu import get_main_menu
from utils.cleaner import auto_clean_chat

router = Router()


# ──────────────────────────────────────────────────────────────────────────────
# FSM: регистрация пользователя
# ──────────────────────────────────────────────────────────────────────────────
class RegV2(StatesGroup):
    full_name = State()
    phone = State()
    top_department = State()
    department = State()
    block = State()
    role_pick = State()
    role_custom = State()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers (клавиатуры)
# ──────────────────────────────────────────────────────────────────────────────

def _depts() -> List[str]:
    return list(ORG_STRUCTURE.keys())


TOP_DEPARTMENTS = [
    "Отдел животноводства",
    "ЖК Актюба",
    "Карамалы",
    "Шереметьево",
    "Бирючевка",
]


def _top_dept_kb() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=d, callback_data=f"regv2:top:{i}")]
        for i, d in enumerate(TOP_DEPARTMENTS)
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _zhk_depts() -> List[str]:
    return [d for d in _depts() if d != "Отдел животноводства"]


def _dept_kb(prefix: str = "regv2:ud:", include_back_to_top: bool = False) -> InlineKeyboardMarkup:
    dept_list = _zhk_depts() if prefix == "regv2:ud:" else _depts()
    buttons = [
        [InlineKeyboardButton(text=d, callback_data=f"{prefix}{i}")]
        for i, d in enumerate(dept_list)
    ]
    if include_back_to_top:
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="regv2:back:top")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _blocks(dept: str) -> List[str]:
    return list(ORG_STRUCTURE.get(dept, {}).keys())


def _block_kb(dept: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=b, callback_data=f"regv2:ub:{i}")]
        for i, b in enumerate(_blocks(dept))
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к отделам", callback_data="regv2:back:dept")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _roles(dept: str, block: str) -> List[str]:
    return list(ORG_STRUCTURE.get(dept, {}).get(block, []))


def _role_kb(dept: str, block: str) -> InlineKeyboardMarkup:
    r = _roles(dept, block)
    buttons = [
        [InlineKeyboardButton(text=x, callback_data=f"regv2:ur:{i}")]
        for i, x in enumerate(r)
    ]
    buttons.append([InlineKeyboardButton(text="✍️ Другая должность (ввести вручную)", callback_data="regv2:ur:custom")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к блокам", callback_data="regv2:back:block")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить мой номер", request_contact=True)],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _admin_request_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"regv2:approve:{user_id}"),
                InlineKeyboardButton(text="✏️ Изменить", callback_data=f"regv2:edit:{user_id}"),
            ],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"regv2:reject:{user_id}")],
        ]
    )


def _admin_position_kb(user_id: int, dept: str | None, block: str | None) -> InlineKeyboardMarkup:
    key_block = bool(block) and "ключев" in block.lower()

    if key_block:
        options = [
            ("Куратор отдела", "curator"),
            ("Руководитель отдела", "head_dept"),
            ("Сотрудник отдела", "staff"),
        ]
    else:
        options = [
            ("Руководитель блока", "head_block"),
            ("Сотрудник блока", "staff"),
        ]

    rows = [[InlineKeyboardButton(text=t, callback_data=f"regv2:setpos:{user_id}:{code}")]
            for t, code in options]

    rows.append([InlineKeyboardButton(text="✏️ Изменить отдел/блок/должность", callback_data=f"regv2:edit:{user_id}")])
    rows.append([InlineKeyboardButton(text="❌ Отклонить", callback_data=f"regv2:reject:{user_id}")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _format_user_card(u: dict) -> str:
    dept = u.get("department") or "—"
    block = u.get("block") or "—"
    role = u.get("role") or "—"
    phone = u.get("phone") or "—"
    uname = u.get("username") or "—"
    return (
        "🆕 <b>Заявка на регистрацию</b>\n"
        f"ФИО: <b>{u.get('full_name','—')}</b>\n"
        f"Телефон: {phone}\n"
        f"Отдел: {dept}\n"
        f"Блок: {block}\n"
        f"Должность: {role}\n"
        f"TG: @{uname}\n"
        f"ID: <code>{u.get('user_id')}</code>"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Пользовательская регистрация (V2)
# ──────────────────────────────────────────────────────────────────────────────

@router.message(RegV2.full_name)
@auto_clean_chat()
async def reg_full_name(message: types.Message, state: FSMContext):
    fio = (message.text or "").strip()

    # базовая валидация (не делаем жёсткой — люди пишут по-разному)
    if len(fio) < 7:
        sent = await message.answer("Введите ФИО полностью (пример: Иванов Иван Иванович):")
        await state.update_data(last_bot_message_id=sent.message_id)
        return

    # анти-дубликаты по ФИО (по желанию можно отключить)
    exists = await db.get_user_by_name(fio)
    if exists and exists.get("user_id") != message.from_user.id:
        sent = await message.answer("🚫 Такое ФИО уже зарегистрировано. Уточните ФИО или добавьте отчество.")
        await state.update_data(last_bot_message_id=sent.message_id)
        return

    await state.update_data(full_name=fio)

    sent = await message.answer(
        "Отправьте номер телефона (удобнее — кнопкой ниже) или введите вручную в формате +79XXXXXXXXX:",
        reply_markup=_phone_kb(),
    )
    await state.update_data(last_bot_message_id=sent.message_id)
    await state.set_state(RegV2.phone)


@router.message(RegV2.phone)
@auto_clean_chat()
async def reg_phone(message: types.Message, state: FSMContext):
    if message.text and message.text.strip().lower() == "отмена":
        await state.clear()
        await message.answer("Регистрация отменена. Для начала снова нажмите /start", reply_markup=ReplyKeyboardRemove())
        return

    phone: str | None = None

    if message.contact and message.contact.phone_number:
        raw = message.contact.phone_number
        # приводим к +79...
        if raw.startswith("8") and len(raw) == 11:
            phone = "+7" + raw[1:]
        elif raw.startswith("7") and len(raw) == 11:
            phone = "+" + raw
        elif raw.startswith("+"):
            phone = raw
        else:
            phone = "+" + raw
    else:
        raw = (message.text or "").strip()
        phone = raw

    # валидация телефона
    if not phone or not re.fullmatch(r"\+79\d{9}", phone):
        sent = await message.answer("🚫 Формат неверен. Введите телефон как +79179179797")
        await state.update_data(last_bot_message_id=sent.message_id)
        return

    # анти-дубликаты телефона
    exists = await db.get_user_by_phone(phone)
    if exists and exists.get("user_id") != message.from_user.id:
        sent = await message.answer("🚫 Этот телефон уже используется. Введите другой номер.")
        await state.update_data(last_bot_message_id=sent.message_id)
        return

    await state.update_data(phone=phone)

    # дальше — первый выбор подразделения
    sent = await message.answer(
        "Выберите подразделение:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.update_data(last_bot_message_id=sent.message_id)

    await message.answer(
        "Первый выбор:",
        reply_markup=_top_dept_kb(),
    )
    await state.set_state(RegV2.top_department)


@router.callback_query(RegV2.top_department, F.data.startswith("regv2:top:"))
async def reg_choose_top_department(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":")[-1])
    if idx < 0 or idx >= len(TOP_DEPARTMENTS):
        await callback.answer("Подразделение не найдено", show_alert=True)
        return

    top_dept = TOP_DEPARTMENTS[idx]

    if top_dept == "ЖК Актюба":
        await callback.message.edit_text(
            "Подразделение: <b>ЖК Актюба</b>\n\nВыберите отдел:",
            reply_markup=_dept_kb(include_back_to_top=True),
            parse_mode="HTML",
        )
        await state.set_state(RegV2.department)
        await callback.answer()
        return

    await state.update_data(department=top_dept, block=None)
    await callback.message.edit_text(
        f"Подразделение: <b>{top_dept}</b>\n\nВведите вашу должность текстом:",
        parse_mode="HTML",
    )
    await state.set_state(RegV2.role_custom)
    await callback.answer()


@router.callback_query(RegV2.department, F.data.startswith("regv2:ud:"))
async def reg_choose_dept(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":")[-1])
    depts = _zhk_depts()
    if idx < 0 or idx >= len(depts):
        await callback.answer("Отдел не найден", show_alert=True)
        return

    dept = depts[idx]
    await state.update_data(department=dept)

    await callback.message.edit_text(
        f"Отдел: <b>{dept}</b>\n\nВыберите блок:",
        reply_markup=_block_kb(dept),
        parse_mode="HTML",
    )
    await state.set_state(RegV2.block)
    await callback.answer()


@router.callback_query(RegV2.block, F.data.startswith("regv2:ub:"))
async def reg_choose_block(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":")[-1])
    data = await state.get_data()
    dept = data.get("department")
    if not dept:
        await callback.answer("Сначала выберите отдел", show_alert=True)
        return

    blocks = _blocks(dept)
    if idx < 0 or idx >= len(blocks):
        await callback.answer("Блок не найден", show_alert=True)
        return

    block = blocks[idx]
    await state.update_data(block=block)

    await callback.message.edit_text(
        f"Отдел: <b>{dept}</b>\nБлок: <b>{block}</b>\n\nВыберите должность:",
        reply_markup=_role_kb(dept, block),
        parse_mode="HTML",
    )
    await state.set_state(RegV2.role_pick)
    await callback.answer()


@router.callback_query(RegV2.role_pick, F.data == "regv2:ur:custom")
async def reg_role_custom(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите вашу должность текстом (пример: Оператор кормоцеха / Зоотехник / Инженер и т.д.):"
    )
    await state.set_state(RegV2.role_custom)
    await callback.answer()


@router.callback_query(RegV2.role_pick, F.data.startswith("regv2:ur:"))
async def reg_choose_role_from_list(callback: types.CallbackQuery, state: FSMContext):
    idx_str = callback.data.split(":")[-1]
    if not idx_str.isdigit():
        await callback.answer("Некорректный выбор", show_alert=True)
        return

    idx = int(idx_str)
    data = await state.get_data()
    dept = data.get("department")
    block = data.get("block")
    if not dept or not block:
        await callback.answer("Сначала выберите отдел и блок", show_alert=True)
        return

    roles = _roles(dept, block)
    if idx < 0 or idx >= len(roles):
        await callback.answer("Должность не найдена", show_alert=True)
        return

    role = roles[idx]
    await state.update_data(role=role)

    await _finish_registration(callback.message, callback.from_user, state)
    await callback.answer()


@router.message(RegV2.role_custom)
@auto_clean_chat()
async def reg_custom_role_text(message: types.Message, state: FSMContext):
    role = (message.text or "").strip()
    if len(role) < 2:
        sent = await message.answer("Введите должность текстом (не менее 2 символов):")
        await state.update_data(last_bot_message_id=sent.message_id)
        return

    await state.update_data(role=role)
    await _finish_registration(message, message.from_user, state)


@router.callback_query(F.data == "regv2:back:top", RegV2.department)
async def back_to_top_departments(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Выберите подразделение:", reply_markup=_top_dept_kb())
    await state.set_state(RegV2.top_department)
    await callback.answer()


@router.callback_query(F.data == "regv2:back:dept", RegV2.block)
async def back_to_depts(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Подразделение: <b>ЖК Актюба</b>\n\nВыберите отдел:",
        reply_markup=_dept_kb(include_back_to_top=True),
        parse_mode="HTML",
    )
    await state.set_state(RegV2.department)
    await callback.answer()


@router.callback_query(F.data == "regv2:back:block", RegV2.role_pick)
async def back_to_blocks(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    dept = data.get("department")
    if not dept:
        await callback.answer("Сначала выберите отдел", show_alert=True)
        return

    await callback.message.edit_text(
        f"Отдел: <b>{dept}</b>\n\nВыберите блок:",
        reply_markup=_block_kb(dept),
        parse_mode="HTML",
    )
    await state.set_state(RegV2.block)
    await callback.answer()


async def _finish_registration(msg_obj: types.Message, tg_user: types.User, state: FSMContext) -> None:
    data = await state.get_data()

    full_name = data.get("full_name")
    phone = data.get("phone")
    department = data.get("department")
    block = data.get("block")
    role = data.get("role")

    # upsert пользователя как НЕ подтверждённого
    await db.add_unconfirmed_user(
        user_id=tg_user.id,
        full_name=full_name,
        phone=phone,
        department=department,
        block=block,
        role=role,
    )

    # сохраняем username для карточки (не в БД, а временно)
    user_card = {
        "user_id": tg_user.id,
        "full_name": full_name,
        "phone": phone,
        "department": department,
        "block": block,
        "role": role,
        "username": tg_user.username or "",
    }

    # уведомляем админов
    for admin_id in ADMIN_IDS:
        try:
            await msg_obj.bot.send_message(
                admin_id,
                _format_user_card(user_card),
                reply_markup=_admin_request_kb(tg_user.id),
                parse_mode="HTML",
            )
        except Exception:
            # если админ ещё не написал боту или чат недоступен — пропускаем
            pass

    await msg_obj.answer(
        "Спасибо! Заявка отправлена администратору. После подтверждения появится главное меню.",
        reply_markup=ReplyKeyboardRemove(),
    )

    await state.clear()


# ──────────────────────────────────────────────────────────────────────────────
# Админ: управление заявками регистрации (без FSM)
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("regv2:approve:"))
async def admin_start_approve(callback: types.CallbackQuery):
    user_id = int(callback.data.split(":")[-1])
    u = await db.get_user(user_id)
    if not u:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    dept = u.get("department")
    block = u.get("block")

    await callback.message.edit_text(
        _format_user_card({
            "user_id": u.get("user_id"),
            "full_name": u.get("full_name"),
            "phone": u.get("phone"),
            "department": dept,
            "block": block,
            "role": u.get("role"),
            "username": "",
        })
        + "\n\nВыберите уровень доступа:",
        reply_markup=_admin_position_kb(user_id, dept, block),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("regv2:setpos:"))
async def admin_set_position(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    # regv2:setpos:<uid>:<code>
    if len(parts) != 4:
        await callback.answer("Некорректная команда", show_alert=True)
        return

    user_id = int(parts[2])
    code = parts[3]

    u = await db.get_user(user_id)
    if not u:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    pos_db_map = {
        "curator": "куратор",
        "head_dept": "рук_отдела",
        "head_block": "рук_блока",
        "staff": "сотрудник",
    }
    pos_human_map = {
        "curator": "Куратор отдела",
        "head_dept": "Руководитель отдела",
        "head_block": "Руководитель блока",
        "staff": "Сотрудник",
    }

    position_db = pos_db_map.get(code, "сотрудник")
    position_human = pos_human_map.get(code, "Сотрудник")

    dept = u.get("department") or "—"
    block = u.get("block") or "—"
    role = u.get("role") or "—"

    await db.confirm_user(user_id=user_id, department=dept, block=block, role=role)
    await db.set_position(user_id, position_db)

    # уведомляем пользователя
    try:
        await callback.bot.send_message(
            user_id,
            (
                f"✅ Ваша регистрация подтверждена.\n"
                f"Роль: <b>{position_human}</b>\n"
                f"Отдел: {dept}\n"
                f"Блок: {block}\n"
                f"Должность: {role}\n\n"
                "Выберите действие в меню ниже."
            ),
            reply_markup=get_main_menu(user_id),
            parse_mode="HTML",
        )
    except Exception:
        pass

    # обновляем сообщение админа
    await callback.message.edit_text(
        (
            "✅ Пользователь подтверждён\n\n"
            f"ФИО: <b>{u.get('full_name')}</b>\n"
            f"Отдел: {dept}\n"
            f"Блок: {block}\n"
            f"Должность: {role}\n"
            f"Уровень доступа: <b>{position_human}</b>"
        ),
        parse_mode="HTML",
    )

    await callback.answer("Готово")


@router.callback_query(F.data.startswith("regv2:reject:"))
async def admin_reject(callback: types.CallbackQuery):
    user_id = int(callback.data.split(":")[-1])
    u = await db.get_user(user_id)

    await db.delete_user(user_id)

    try:
        await callback.bot.send_message(user_id, "❌ Ваша заявка отклонена. Обратитесь к руководителю.")
    except Exception:
        pass

    fio = u.get("full_name") if u else str(user_id)
    await callback.message.edit_text(f"❌ Заявка отклонена: {fio}")
    await callback.answer()


# ──────────────────────────────────────────────────────────────────────────────
# Админ: изменение отдела/блока/должности (step-by-step через callback)
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("regv2:edit:"))
async def admin_edit(callback: types.CallbackQuery):
    user_id = int(callback.data.split(":")[-1])
    await callback.message.edit_text(
        f"✏️ Изменение заявки пользователя <code>{user_id}</code>\n\nВыберите отдел:",
        reply_markup=_dept_kb(prefix=f"regv2:setdept:{user_id}:") ,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("regv2:setdept:"))
async def admin_set_dept(callback: types.CallbackQuery):
    # regv2:setdept:<uid>:<dept_idx>
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Некорректная команда", show_alert=True)
        return

    user_id = int(parts[2])
    dept_idx = int(parts[3])
    depts = _depts()
    if dept_idx < 0 or dept_idx >= len(depts):
        await callback.answer("Отдел не найден", show_alert=True)
        return

    dept = depts[dept_idx]
    blocks = _blocks(dept)

    buttons = [
        [InlineKeyboardButton(text=b, callback_data=f"regv2:setblock:{user_id}:{dept_idx}:{i}")]
        for i, b in enumerate(blocks)
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"regv2:edit:{user_id}")])

    await callback.message.edit_text(
        f"Отдел: <b>{dept}</b>\n\nВыберите блок:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("regv2:setblock:"))
async def admin_set_block(callback: types.CallbackQuery):
    # regv2:setblock:<uid>:<dept_idx>:<block_idx>
    parts = callback.data.split(":")
    if len(parts) != 5:
        await callback.answer("Некорректная команда", show_alert=True)
        return

    user_id = int(parts[2])
    dept_idx = int(parts[3])
    block_idx = int(parts[4])

    depts = _depts()
    if dept_idx < 0 or dept_idx >= len(depts):
        await callback.answer("Отдел не найден", show_alert=True)
        return

    dept = depts[dept_idx]
    blocks = _blocks(dept)
    if block_idx < 0 or block_idx >= len(blocks):
        await callback.answer("Блок не найден", show_alert=True)
        return

    block = blocks[block_idx]

    roles = _roles(dept, block)
    role_buttons = [
        [InlineKeyboardButton(text=r, callback_data=f"regv2:setrole:{user_id}:{dept_idx}:{block_idx}:{i}")]
        for i, r in enumerate(roles)
    ]
    role_buttons.append([
        InlineKeyboardButton(text="✅ Оставить прежнюю должность", callback_data=f"regv2:keep_role:{user_id}:{dept_idx}:{block_idx}")
    ])
    role_buttons.append([InlineKeyboardButton(text="⬅️ Назад к блокам", callback_data=f"regv2:setdept:{user_id}:{dept_idx}")])

    await callback.message.edit_text(
        f"Отдел: <b>{dept}</b>\nБлок: <b>{block}</b>\n\nВыберите должность:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=role_buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("regv2:keep_role:"))
async def admin_keep_role(callback: types.CallbackQuery):
    # regv2:keep_role:<uid>:<dept_idx>:<block_idx>
    parts = callback.data.split(":")
    if len(parts) != 5:
        await callback.answer("Некорректная команда", show_alert=True)
        return

    user_id = int(parts[2])
    dept_idx = int(parts[3])
    block_idx = int(parts[4])

    depts = _depts()
    dept = depts[dept_idx]
    block = _blocks(dept)[block_idx]

    u = await db.get_user(user_id)
    if not u:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    # Обновляем только отдел и блок
    await db.add_unconfirmed_user(
        user_id=user_id,
        full_name=u.get("full_name"),
        phone=u.get("phone"),
        department=dept,
        block=block,
        role=u.get("role"),
    )

    await callback.message.edit_text(
        "✅ Заявка обновлена. Теперь выберите уровень доступа:",
        reply_markup=_admin_position_kb(user_id, dept, block),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("regv2:setrole:"))
async def admin_set_role(callback: types.CallbackQuery):
    # regv2:setrole:<uid>:<dept_idx>:<block_idx>:<role_idx>
    parts = callback.data.split(":")
    if len(parts) != 6:
        await callback.answer("Некорректная команда", show_alert=True)
        return

    user_id = int(parts[2])
    dept_idx = int(parts[3])
    block_idx = int(parts[4])
    role_idx = int(parts[5])

    depts = _depts()
    dept = depts[dept_idx]
    block = _blocks(dept)[block_idx]
    roles = _roles(dept, block)
    if role_idx < 0 or role_idx >= len(roles):
        await callback.answer("Должность не найдена", show_alert=True)
        return

    role = roles[role_idx]

    u = await db.get_user(user_id)
    if not u:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    await db.add_unconfirmed_user(
        user_id=user_id,
        full_name=u.get("full_name"),
        phone=u.get("phone"),
        department=dept,
        block=block,
        role=role,
    )

    await callback.message.edit_text(
        "✅ Заявка обновлена. Теперь выберите уровень доступа:",
        reply_markup=_admin_position_kb(user_id, dept, block),
    )
    await callback.answer()
