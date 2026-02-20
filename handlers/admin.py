from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from keyboards import get_main_menu                # главное меню (у всех)
from admin_keyboards import (                       # все админ-клавиатуры
    get_admin_menu,
    get_user_management_keyboard,
)
from config import ADMIN_IDS                     # список ID админов
from db import db
from utils.cleaner import auto_clean_chat

router = Router()

MILK_LOCATIONS = {
    "aktuba": "ЖК «Актюба»",
    "karamaly": "Карамалы",
    "sheremetyovo": "Шереметьево",
}

MILK_COUNTERPARTIES = {
    "kantal": "ООО «Канталь»",
    "chmk": "ООО «ЧМК»",
    "siyfat": "ООО «Сыйфатлы Ит»",
    "tnurs": "ООО «ТН-УРС»",
    "zai": "ООО «Зай»",
    "cafeteria": "Столовая",
    "salary": "В счёт ЗП",
}


class MilkPriceState(StatesGroup):
    waiting_price = State()

# ───────────────────── помощник ─────────────────────
def user_is_admin(user_id: int) -> bool:
    """Проверка прав администратора."""
    return user_id in ADMIN_IDS                     # или await db.is_admin(...)


def _fmt_price(x: float) -> str:
    return f"{float(x):.2f}".replace(".", ",")


def _location_title(code: str) -> str:
    return MILK_LOCATIONS.get(code, code)


def _counterparty_title(code: str) -> str:
    return MILK_COUNTERPARTIES.get(code, code)


def _milk_locations_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=title, callback_data=f"milkprice:loc:{code}")]
        for code, title in MILK_LOCATIONS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _milk_counterparties_kb(location_code: str, prices: dict[str, float]) -> InlineKeyboardMarkup:
    rows = []
    for cp_code, cp_title in MILK_COUNTERPARTIES.items():
        price = float(prices.get(cp_code, 0.0))
        rows.append([
            InlineKeyboardButton(
                text=f"{cp_title} — {_fmt_price(price)} руб/кг",
                callback_data=f"milkprice:cp:{location_code}:{cp_code}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад к подразделениям", callback_data="milkprice:back:loc")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ───────────────────── /admin ───────────────────────
@router.message(F.text == "/admin")
@auto_clean_chat()
async def admin_menu(message: types.Message, state: FSMContext):
    if not user_is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора!")
        return
    sent = await message.answer(
        "🔐 Административное меню:",
        reply_markup=get_admin_menu()
    )
    await state.update_data(last_bot_message_id=sent.message_id)

# ─────────────── «👥 Пользователи» ───────────────────
@router.message(F.text == "👥 Пользователи")
@auto_clean_chat()
async def handle_users_menu(message: types.Message, state: FSMContext):
    if not user_is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён!")
        return
    sent = await message.answer(
        "🔐 Раздел управления пользователями:",
        reply_markup=get_user_management_keyboard()
    )
    await state.update_data(last_bot_message_id=sent.message_id)

# ─────────── «⬅️ Назад в админ меню» ────────────────
@router.message(F.text == "⬅️ Назад в админ меню")
@auto_clean_chat()
async def back_to_admin_menu(message: types.Message, state: FSMContext):
    if not user_is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён!")
        return
    sent = await message.answer(
        "🔐 Административное меню:",
        reply_markup=get_admin_menu()
    )
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(F.text == "🥛 Изменить цены на молоко")
@auto_clean_chat()
async def milk_prices_menu(message: types.Message, state: FSMContext):
    if not user_is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён!")
        return
    sent = await message.answer(
        "Выберите подразделение для изменения цен на молоко:",
        reply_markup=_milk_locations_kb(),
    )
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(F.text == "📜 Журнал цен молока")
@auto_clean_chat()
async def milk_prices_log(message: types.Message, state: FSMContext):
    if not user_is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён!")
        return

    rows = await db.list_milk_price_logs(limit=20)
    if not rows:
        sent = await message.answer("Журнал изменений цен пока пуст.")
        await state.update_data(last_bot_message_id=sent.message_id)
        return

    lines = ["📜 <b>Журнал изменений цен на молоко</b> (последние 20)\n"]
    for r in rows:
        old_raw = r.get("old_price")
        old_price = "—" if old_raw is None else f"{_fmt_price(float(old_raw))}"
        new_price = _fmt_price(float(r.get("new_price") or 0.0))
        actor_id = int(r.get("changed_by") or 0)
        actor_name = (r.get("changed_by_name") or "").strip()
        actor = f"{actor_name} ({actor_id})" if actor_name else str(actor_id or "неизвестно")
        when = str(r.get("changed_at") or "")

        lines.append(
            f"• {when}\n"
            f"  {_location_title(str(r.get('location') or ''))} → {_counterparty_title(str(r.get('counterparty') or ''))}\n"
            f"  {old_price} → <b>{new_price}</b> руб/кг\n"
            f"  Кто: {actor}\n"
        )

    sent = await message.answer("\n".join(lines), parse_mode="HTML")
    await state.update_data(last_bot_message_id=sent.message_id)


@router.callback_query(F.data.startswith("milkprice:loc:"))
async def milk_prices_choose_location(callback: types.CallbackQuery, state: FSMContext):
    if not user_is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    location_code = callback.data.split(":")[-1]
    if location_code not in MILK_LOCATIONS:
        await callback.answer("Подразделение не найдено", show_alert=True)
        return

    prices = await db.get_milk_prices(location_code)
    await callback.message.edit_text(
        f"Подразделение: <b>{MILK_LOCATIONS[location_code]}</b>\nВыберите контрагента:",
        reply_markup=_milk_counterparties_kb(location_code, prices),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "milkprice:back:loc")
async def milk_prices_back_to_locations(callback: types.CallbackQuery):
    if not user_is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "Выберите подразделение для изменения цен на молоко:",
        reply_markup=_milk_locations_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("milkprice:cp:"))
async def milk_prices_choose_counterparty(callback: types.CallbackQuery, state: FSMContext):
    if not user_is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Некорректная команда", show_alert=True)
        return

    location_code = parts[2]
    cp_code = parts[3]
    if location_code not in MILK_LOCATIONS or cp_code not in MILK_COUNTERPARTIES:
        await callback.answer("Некорректные данные", show_alert=True)
        return

    prices = await db.get_milk_prices(location_code)
    current_price = float(prices.get(cp_code, 0.0))

    await state.set_state(MilkPriceState.waiting_price)
    await state.update_data(
        milk_price_location=location_code,
        milk_price_cp=cp_code,
    )

    await callback.message.answer(
        (
            f"Подразделение: <b>{MILK_LOCATIONS[location_code]}</b>\n"
            f"Контрагент: <b>{MILK_COUNTERPARTIES[cp_code]}</b>\n"
            f"Текущая цена: <b>{_fmt_price(current_price)}</b> руб/кг\n\n"
            "Введите новую цену (например: <b>41</b> или <b>41,5</b>)."
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(MilkPriceState.waiting_price)
@auto_clean_chat()
async def milk_prices_set_value(message: types.Message, state: FSMContext):
    if not user_is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⛔ Доступ запрещён!")
        return

    raw = (message.text or "").strip().replace(" ", "").replace(",", ".")
    try:
        value = float(raw)
        if value <= 0:
            raise ValueError
    except Exception:
        sent = await message.answer("Введите корректную цену больше 0. Пример: 40 или 40,5")
        await state.update_data(last_bot_message_id=sent.message_id)
        return

    data = await state.get_data()
    location_code = data.get("milk_price_location")
    cp_code = data.get("milk_price_cp")
    if location_code not in MILK_LOCATIONS or cp_code not in MILK_COUNTERPARTIES:
        await state.clear()
        await message.answer("❗️Не удалось определить подразделение/контрагента. Начните заново.")
        return

    await db.set_milk_price(location_code, cp_code, value, changed_by=message.from_user.id)
    prices = await db.get_milk_prices(location_code)

    await state.clear()
    await message.answer(
        (
            f"✅ Цена обновлена:\n"
            f"{MILK_LOCATIONS[location_code]} — {MILK_COUNTERPARTIES[cp_code]}\n"
            f"Новая цена: <b>{_fmt_price(value)}</b> руб/кг"
        ),
        parse_mode="HTML",
    )
    await message.answer(
        f"Подразделение: <b>{MILK_LOCATIONS[location_code]}</b>\nВыберите контрагента:",
        reply_markup=_milk_counterparties_kb(location_code, prices),
        parse_mode="HTML",
    )

