import os
import json
import re
import aiosqlite
from datetime import datetime, date

from aiogram import Router, types, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

from utils.pdf_milk_summary_pdf import (
    build_milk_summary_pdf_bytes,
    build_soyuz_agro_milk_pdf_bytes,
    SOYUZ_LOCATIONS,
)
from db import db, MILK_PRICE_DEFAULTS


router = Router()

MILK_DENSITY = 1.03  # кг/л
LAB_TECH_ID = 1732643047
FACT_VIEW_EXTRA_ID = 5183512024

DB_PATH = os.getenv("DATABASE_PATH", "data/aktuba.db")
GROUP_CHAT_ID = int(os.getenv("MILK_SUMMARY_GROUP_CHAT_ID", "0") or "0")


def _parse_ids(raw: str) -> set[int]:
    if not raw:
        return set()
    out = set()
    for x in raw.split(","):
        x = x.strip()
        if x.isdigit():
            out.add(int(x))
    return out


ADMIN_IDS = _parse_ids(os.getenv("ADMIN_IDS", ""))
FACT_VIEWERS_STATIC = set(ADMIN_IDS) | {FACT_VIEW_EXTRA_ID}

COUNTERPARTY_LABELS = {
    "kantal": "ООО «Канталь»",
    "chmk": "ООО «ЧМК»",
    "siyfat": "ООО «Сыйфатлы Ит»",
    "tnurs": "ООО «ТН-УРС»",
    "zai": "ООО «Зай»",
    "cafeteria": "Столовая",
    "salary": "В счёт ЗП",
}

FIELD_TO_COUNTERPARTY = {
    "sale_kantal_kg": "kantal",
    "sale_chmk_kg": "chmk",
    "sale_siyfat_kg": "siyfat",
    "sale_tnurs_kg": "tnurs",
    "sale_zai_kg": "zai",
    "sale_cafeteria_l": "cafeteria",
    "sale_salary_l": "salary",
}


VIEW_KEYS = {
    "milk_aktuba": ("aktuba", "ЖК «Актюба»"),
    "milk_karamaly": ("karamaly", "Карамалы"),
    "milk_sheremetyovo": ("sheremetyovo", "Шереметьево"),
    "milk_biryuchevka": ("biryuchevka", "Бирючевка"),
    "milk_soyuz_agro": ("soyuz_agro", "ООО «Союз-Агро»"),
}

SUBMIT_KEYS = {
    "milk_submit_aktuba": ("aktuba", "ЖК «Актюба»"),
    "milk_submit_karamaly": ("karamaly", "Карамалы"),
    "milk_submit_sheremetyovo": ("sheremetyovo", "Шереметьево"),
    "milk_submit_biryuchevka": ("biryuchevka", "Бирючевка"),
}


class MilkWizard(StatesGroup):
    active = State()


def fmt_int(x: float | int) -> str:
    return f"{int(round(x)):,}".replace(",", " ")


def fmt_float(x: float, digits: int = 2) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def l_to_kg(l: float) -> float:
    return l * MILK_DENSITY


def kg_to_l(kg: float) -> float:
    return kg / MILK_DENSITY


def parse_number(text: str) -> float:
    t = (text or "").strip()
    t = t.replace(" ", "")
    t = t.replace(",", ".")
    t = re.sub(r"[^0-9.]", "", t)
    if t == "":
        raise ValueError("Пустое значение")
    return float(t)


def parse_int(text: str) -> int:
    x = parse_number(text)
    if x < 0:
        raise ValueError("Число не может быть отрицательным")
    return int(round(x))


def parse_percent(text: str) -> float:
    x = parse_number(text)
    if x < 0 or x > 100:
        raise ValueError("Процент должен быть 0–100")
    return x


def parse_date_ddmmyyyy(text: str) -> str:
    t = (text or "").strip()
    if t.lower() in ("0", "сегодня", "today"):
        return datetime.now().strftime("%d.%m.%Y")
    dt = datetime.strptime(t, "%d.%m.%Y")
    return dt.strftime("%d.%m.%Y")


def iso_from_ddmmyyyy(date_str: str) -> str:
    return datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")


async def _db_connect():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = await aiosqlite.connect(DB_PATH, timeout=30)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL;")
    await conn.execute("PRAGMA foreign_keys = ON;")
    return conn


async def _ensure_milk_table(conn: aiosqlite.Connection):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS milk_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT NOT NULL,
            report_date DATE NOT NULL,
            data_json TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(location, report_date)
        );
    """)
    await conn.commit()


async def upsert_milk_report(location: str, report_date: str, data_json: str, created_by: int):
    conn = await _db_connect()
    try:
        await _ensure_milk_table(conn)
        await conn.execute("""
            INSERT INTO milk_reports (location, report_date, data_json, created_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(location, report_date) DO UPDATE SET
                data_json  = excluded.data_json,
                created_by = excluded.created_by,
                created_at = CURRENT_TIMESTAMP
        """, (location, report_date, data_json, created_by))
        await conn.commit()
    finally:
        await conn.close()


async def get_latest_milk_report(location: str):
    conn = await _db_connect()
    try:
        await _ensure_milk_table(conn)
        cur = await conn.execute("""
            SELECT location, report_date, data_json, created_by, created_at
            FROM milk_reports
            WHERE location = ?
            ORDER BY report_date DESC, created_at DESC
            LIMIT 1
        """, (location,))
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await conn.close()


async def get_milk_report_by_date(location: str, report_date: str):
    conn = await _db_connect()
    try:
        await _ensure_milk_table(conn)
        cur = await conn.execute("""
            SELECT location, report_date, data_json, created_by, created_at
            FROM milk_reports
            WHERE location = ? AND report_date = ?
            LIMIT 1
        """, (location, report_date))
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await conn.close()


async def is_admin_user(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True

    conn = await _db_connect()
    try:
        cur = await conn.execute("""SELECT is_admin FROM users WHERE user_id = ? LIMIT 1""", (user_id,))
        row = await cur.fetchone()
        if row and int(row["is_admin"] or 0) == 1:
            return True
    except Exception:
        pass
    finally:
        await conn.close()

    return False


async def can_view_fact(user_id: int) -> bool:
    if user_id in FACT_VIEWERS_STATIC:
        return True
    return await is_admin_user(user_id)


STEPS_BASE = [
    ("report_date", "Введите дату отчёта <b>ДД.ММ.ГГГГ</b> (или <b>0</b> = сегодня):", parse_date_ddmmyyyy, "пример: 31.12.2025"),

    ("big_dz_kg", "Валовый надой <b>Большой ДЗ</b>, <b>кг</b>:", parse_number, "пример: 98450"),
    ("small_dz_kg", "Валовый надой <b>Малый ДЗ</b>, <b>кг</b>:", parse_number, "пример: 24568"),

    ("forage_cows", "Количество <b>фуражных коров</b>, <b>гол</b>:", parse_int, "пример: 3250"),
    ("milking_cows", "Количество <b>дойных коров</b>, <b>гол</b>:", parse_int, "пример: 3100"),

    ("sale_kantal_kg", "Реализация молока <b>ООО «Канталь»</b>, <b>кг</b>:", parse_number, ""),
    ("sale_chmk_kg", "Реализация молока <b>ООО «ЧМК»</b>, <b>кг</b>:", parse_number, ""),
    ("sale_siyfat_kg", "Реализация молока <b>ООО «Сыйфатлы Ит»</b>, <b>кг</b>:", parse_number, ""),
    ("sale_tnurs_kg", "Реализация молока <b>ООО «ТН-УРС»</b>, <b>кг</b>:", parse_number, ""),
    ("sale_zai_kg", "Реализация молока <b>ООО «Зай»</b>, <b>кг</b>:", parse_number, ""),

    ("sale_cafeteria_l", "Реализация молока <b>столовая</b>, <b>л</b>:", parse_number, ""),
    ("sale_salary_l", "Реализация молока <b>в счёт ЗП</b>, <b>л</b>:", parse_number, ""),

    ("milk_calves_total_kg", "Молока на выпойку <b>всего</b>, <b>кг</b>:", parse_number, "пример: 2020"),
    ("disposal_kg", "Утилизация, <b>кг</b>:", parse_number, "пример: 455"),

    ("fat", "Жир, <b>%</b>:", parse_percent, "пример: 4,15"),
    ("protein", "Белок, <b>%</b>:", parse_percent, "пример: 3,61"),

    ("tank_big_kg", "Остаток молока <b>Большой танк</b>, <b>кг</b>:", parse_number, "пример: 19420"),
    ("tank_small_kg", "Остаток молока <b>Малый танк</b>, <b>кг</b>:", parse_number, "пример: 671"),
]

FACT_STEP = ("actual_gross_kg", "Фактический валовый надой, <b>кг</b>:", parse_number, "виден только админу и 5183512024")


async def get_location_prices(location_code: str) -> dict[str, float]:
    try:
        return await db.get_milk_prices(location_code)
    except Exception:
        return dict(MILK_PRICE_DEFAULTS.get(location_code, {}))


async def ask_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    step_idx = data.get("step_idx", 0)
    loc_title = data.get("location_title", "ЖК")
    loc_code = data.get("location_code", "aktuba")
    steps = data.get("steps") or STEPS_BASE

    key, q, _, hint = steps[step_idx]
    if key in FIELD_TO_COUNTERPARTY:
        cp_code = FIELD_TO_COUNTERPARTY[key]
        prices = await get_location_prices(loc_code)
        price = float(prices.get(cp_code, 0.0))
        cp_title = COUNTERPARTY_LABELS.get(cp_code, cp_code)
        hint = f"текущая цена {cp_title}: {fmt_float(price, 2)} руб/кг"
    progress = f"Шаг <b>{step_idx + 1}</b> из <b>{len(steps)}</b>"

    await message.answer(
        f"🍼 <b>Сводка по молоку — {loc_title}</b>\n"
        f"{progress}\n\n"
        f"{q}\n"
        f"<i>{hint}</i>\n\n"
        f"Для отмены напишите: <b>отмена</b>",
        parse_mode="HTML"
    )


def calc_sales_totals(data: dict, prices: dict[str, float]) -> dict:
    kantal_kg = float(data.get("sale_kantal_kg", 0) or 0)
    chmk_kg = float(data.get("sale_chmk_kg", 0) or 0)
    siyfat_kg = float(data.get("sale_siyfat_kg", 0) or 0)
    tnurs_kg = float(data.get("sale_tnurs_kg", 0) or 0)
    zai_kg = float(data.get("sale_zai_kg", 0) or 0)

    cafeteria_l = float(data.get("sale_cafeteria_l", 0) or 0)
    salary_l = float(data.get("sale_salary_l", 0) or 0)

    cafeteria_kg = l_to_kg(cafeteria_l)
    salary_kg = l_to_kg(salary_l)

    total_kg = kantal_kg + chmk_kg + siyfat_kg + tnurs_kg + zai_kg + cafeteria_kg + salary_kg
    total_l = kg_to_l(total_kg)

    total_rub = (
        (kantal_kg * float(prices.get("kantal", 0.0))) +
        (chmk_kg * float(prices.get("chmk", 0.0))) +
        (siyfat_kg * float(prices.get("siyfat", 0.0))) +
        (tnurs_kg * float(prices.get("tnurs", 0.0))) +
        (cafeteria_kg * float(prices.get("cafeteria", 0.0))) +
        (salary_kg * float(prices.get("salary", 0.0))) +
        (zai_kg * float(prices.get("zai", 0.0)))
    )

    avg_price = (total_rub / total_kg) if total_kg > 0 else 0.0
    return {"total_kg": total_kg, "total_l": total_l, "total_rub": total_rub, "avg_price": avg_price}


def _calc_grade_totals(data: dict, prices: dict[str, float], grade_keys: list[str]) -> dict:
    """Считает итоги реализации только для указанных контрагентов."""
    field_map = {
        "kantal": "sale_kantal_kg",
        "chmk": "sale_chmk_kg",
        "siyfat": "sale_siyfat_kg",
        "tnurs": "sale_tnurs_kg",
        "zai": "sale_zai_kg",
        "cafeteria": "sale_cafeteria_l",
        "salary": "sale_salary_l",
    }
    total_kg = 0.0
    total_rub = 0.0
    for key in grade_keys:
        field = field_map.get(key, "")
        raw = float(data.get(field, 0) or 0)
        if key in ("cafeteria", "salary"):
            kg = l_to_kg(raw)
        else:
            kg = raw
        total_kg += kg
        total_rub += kg * float(prices.get(key, 0.0))
    total_l = kg_to_l(total_kg)
    avg_price = (total_rub / total_kg) if total_kg > 0 else 0.0
    return {"total_kg": total_kg, "total_l": total_l, "total_rub": total_rub, "avg_price": avg_price}


GRADE1_KEYS = ["kantal", "chmk", "siyfat", "tnurs", "cafeteria", "salary"]
GRADE2_KEYS = ["zai"]


def build_report(location_title: str, data: dict, mode: str, prices: dict[str, float]) -> str:
    date_str = str(data.get("report_date") or datetime.now().strftime("%d.%m.%Y"))

    big_kg = float(data.get("big_dz_kg", 0) or 0)
    small_kg = float(data.get("small_dz_kg", 0) or 0)
    gross_kg = big_kg + small_kg
    gross_l = kg_to_l(gross_kg)

    forage_cows = int(data.get("forage_cows") or 0)
    milking_cows = int(data.get("milking_cows") or 0)

    prod_forage_kg = (gross_kg / forage_cows) if forage_cows > 0 else 0.0
    prod_forage_l = (gross_l / forage_cows) if forage_cows > 0 else 0.0

    prod_milking_kg = (gross_kg / milking_cows) if milking_cows > 0 else 0.0
    prod_milking_l = (gross_l / milking_cows) if milking_cows > 0 else 0.0

    actual_gross_kg = float(data.get("actual_gross_kg", 0) or 0)
    actual_gross_l = kg_to_l(actual_gross_kg)

    fact_block = ""
    if mode == "admin":
        if actual_gross_kg > 0:
            fact_block = f"• Факт валовый надой: <b>{fmt_int(actual_gross_l)}</b> л / <b>{fmt_int(actual_gross_kg)}</b> кг\n"
        else:
            fact_block = "• Факт валовый надой: <b>нет данных</b>\n"

    dz_block = ""
    if mode != "group":
        big_l = kg_to_l(big_kg)
        small_l = kg_to_l(small_kg)
        dz_block = (
            f"• По ДЗ:\n"
            f"•  Большой — <b>{fmt_int(big_l)}</b> л / <b>{fmt_int(big_kg)}</b> кг\n"
            f"•  Малый — <b>{fmt_int(small_l)}</b> л / <b>{fmt_int(small_kg)}</b> кг\n"
        )

    prod_lines = ""
    if forage_cows > 0:
        prod_lines += f"• На 1 фуражную: <b>{fmt_float(prod_forage_l, 2)}</b> л/гол | <b>{fmt_float(prod_forage_kg, 2)}</b> кг/гол\n"
    else:
        prod_lines += "• На 1 фуражную: <b>нет данных</b>\n"

    if milking_cows > 0:
        prod_lines += f"• На 1 дойную: <b>{fmt_float(prod_milking_l, 2)}</b> л/гол | <b>{fmt_float(prod_milking_kg, 2)}</b> кг/гол\n"
    else:
        prod_lines += "• На 1 дойную: <b>нет данных</b>\n"

    g1 = _calc_grade_totals(data, prices, GRADE1_KEYS)
    g2 = _calc_grade_totals(data, prices, GRADE2_KEYS)
    sales = calc_sales_totals(data, prices)

    milk_calves_total_kg = float(data.get("milk_calves_total_kg", 0) or 0)
    milk_calves_total_l = kg_to_l(milk_calves_total_kg)

    disposal_kg = float(data.get("disposal_kg", 0) or 0)
    disposal_l = kg_to_l(disposal_kg)

    fat = float(data.get("fat", 0) or 0)
    protein = float(data.get("protein", 0) or 0)

    tank_big_kg = float(data.get("tank_big_kg", 0) or 0)
    tank_small_kg = float(data.get("tank_small_kg", 0) or 0)
    tank_big_l = kg_to_l(tank_big_kg)
    tank_small_l = kg_to_l(tank_small_kg)

    text = (
        f"📊 <b>Сводка по молоку — {location_title}</b>\n"
        f"за <b>{date_str}</b>\n\n"

        f"🥛 <b>Молоко</b>\n"
        f"• Валовый надой: <b>{fmt_int(gross_l)}</b> л / <b>{fmt_int(gross_kg)}</b> кг\n"
        f"{dz_block}"
        f"{fact_block}\n"

        f"🐄 <b>Продуктивность</b>\n"
        f"{prod_lines}\n"

        f"🚚 <b>Реализация — Высший сорт</b>\n"
        f"• Кг: <b>{fmt_int(g1['total_kg'])}</b> | Л: <b>{fmt_int(g1['total_l'])}</b>\n"
        f"• Сумма: <b>{fmt_int(g1['total_rub'])}</b> руб | Ср. цена: <b>{fmt_float(g1['avg_price'], 2)}</b> руб/кг\n\n"

        f'🚚 <b>Реализация — 2 сорт (ООО «Зай»)</b>\n'
        f"• Кг: <b>{fmt_int(g2['total_kg'])}</b> | Л: <b>{fmt_int(g2['total_l'])}</b>\n"
        f"• Сумма: <b>{fmt_int(g2['total_rub'])}</b> руб | Ср. цена: <b>{fmt_float(g2['avg_price'], 2)}</b> руб/кг\n\n"

        f"📦 <b>Реализация — ИТОГО</b>\n"
        f"• Всего: <b>{fmt_int(sales['total_kg'])}</b> кг / <b>{fmt_int(sales['total_l'])}</b> л\n"
        f"• На сумму: <b>{fmt_int(sales['total_rub'])}</b> руб\n"
        f"• Средняя цена: <b>{fmt_float(sales['avg_price'], 2)}</b> руб/кг\n\n"

        f"🍼 <b>Выпойка и потери</b>\n"
        f"• Выпойка всего: <b>{fmt_int(milk_calves_total_l)}</b> л / <b>{fmt_int(milk_calves_total_kg)}</b> кг\n"
        f"• Утилизация: <b>{fmt_int(disposal_l)}</b> л / <b>{fmt_int(disposal_kg)}</b> кг\n\n"

        f"🧪 <b>Качество</b>\n"
        f"• Жир — <b>{fmt_float(fat, 2)}</b> % | Белок — <b>{fmt_float(protein, 2)}</b> %\n\n"

        f"🛢 <b>Остаток (конец суток)</b>\n"
        f"• Большой танк — <b>{fmt_int(tank_big_l)}</b> л / <b>{fmt_int(tank_big_kg)}</b> кг\n"
        f"• Малый танк — <b>{fmt_int(tank_small_l)}</b> л / <b>{fmt_int(tank_small_kg)}</b> кг\n"
    )
    return text


def _make_pdf_filename(location_code: str, report_date_ddmmyyyy: str, mode: str) -> str:
    safe_loc = (location_code or "milk").replace(" ", "_")
    safe_date = (report_date_ddmmyyyy or datetime.now().strftime("%d.%m.%Y")).replace(".", "")
    return f"milk_{safe_loc}_{safe_date}_{mode}.pdf"


async def _send_text_and_pdf(chat, location_title: str, location_code: str, data: dict, mode: str):
    prices = await get_location_prices(location_code)
    text = build_report(location_title, data, mode=mode, prices=prices)
    await chat.answer(text, parse_mode="HTML")

    pdf_b = build_milk_summary_pdf_bytes(location_title, data, mode=mode, density=MILK_DENSITY, prices=prices)
    filename = _make_pdf_filename(location_code, str(data.get("report_date") or ""), mode)
    await chat.answer_document(BufferedInputFile(pdf_b, filename=filename))


@router.callback_query(F.data == "milk_soyuz_agro")
async def view_soyuz_agro_milk(callback: types.CallbackQuery):
    all_data: dict[str, dict] = {}
    all_prices: dict[str, dict] = {}
    missing = []

    for col_title, code in SOYUZ_LOCATIONS:
        row = await get_latest_milk_report(code)
        if not row:
            missing.append(col_title)
            all_data[code] = {}
        else:
            all_data[code] = json.loads(row["data_json"])
        all_prices[code] = await get_location_prices(code)

    if len(missing) == len(SOYUZ_LOCATIONS):
        await callback.message.answer(
            "❗️ Нет данных ни по одному подразделению для формирования сводки Союз-Агро.",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    if missing:
        await callback.message.answer(
            f"⚠️ Нет данных по: {', '.join(missing)}. Сводка будет неполной.",
            parse_mode="HTML",
        )

    pdf_b = build_soyuz_agro_milk_pdf_bytes(all_data, all_prices, density=MILK_DENSITY)
    any_date = ""
    for code in ("aktuba", "karamaly", "sheremetyovo"):
        d = all_data.get(code, {})
        if d.get("report_date"):
            any_date = str(d["report_date"])
            break
    filename = _make_pdf_filename("soyuz_agro", any_date or "", "public")
    await callback.message.answer_document(BufferedInputFile(pdf_b, filename=filename))
    await callback.answer()


@router.callback_query(F.data.in_(list(VIEW_KEYS.keys())))
async def view_milk_summary(callback: types.CallbackQuery):
    key = callback.data
    loc_code, loc_title = VIEW_KEYS[key]

    if loc_code == "soyuz_agro":
        return

    row = await get_latest_milk_report(loc_code)
    if not row:
        await callback.message.answer(
            f"❗️ Сводка по молоку для <b>{loc_title}</b> ещё не сдавалась.",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    data = json.loads(row["data_json"])
    mode = "admin" if await can_view_fact(callback.from_user.id) else "public"

    await _send_text_and_pdf(callback.message, loc_title, loc_code, data, mode=mode)
    await callback.answer()


@router.callback_query(F.data.in_(list(SUBMIT_KEYS.keys())))
async def start_submit_milk(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data
    loc_code, loc_title = SUBMIT_KEYS[key]

    if loc_code == "aktuba" and callback.from_user.id != LAB_TECH_ID:
        await callback.answer("Нет доступа", show_alert=True)
        await callback.message.answer("⛔️ Сводку по молоку по ЖК «Актюба» сдаёт только лаборант.")
        return

    include_fact_question = False
    if loc_code == "aktuba" and callback.from_user.id == LAB_TECH_ID:
        include_fact_question = True
    elif await can_view_fact(callback.from_user.id):
        include_fact_question = True

    steps = list(STEPS_BASE)
    if include_fact_question:
        steps.append(FACT_STEP)

    await state.set_state(MilkWizard.active)
    await state.update_data(
        location_code=loc_code,
        location_title=loc_title,
        step_idx=0,
        steps=steps,
        answers={}
    )

    await callback.message.answer(
        f"✅ Начинаем сдачу сводки по молоку: <b>{loc_title}</b>\n\n"
        f"Формат ввода:\n"
        f"• все значения — <b>кг</b>\n"
        f"• исключения: <b>столовая</b> и <b>в счёт ЗП</b> — <b>литры</b>\n"
        f"Пересчёт: <b>{MILK_DENSITY}</b> кг/л",
        parse_mode="HTML"
    )

    await ask_step(callback.message, state)
    await callback.answer()


@router.message(MilkWizard.active)
async def milk_wizard_input(message: types.Message, state: FSMContext):
    txt = (message.text or "").strip()

    if txt.lower() in ("отмена", "cancel", "стоп", "/cancel"):
        await state.clear()
        await message.answer("⛔ Сдача сводки отменена.")
        return

    data = await state.get_data()
    step_idx = int(data.get("step_idx", 0))
    steps = data.get("steps") or STEPS_BASE
    answers = data.get("answers", {})
    loc_code = data.get("location_code")
    loc_title = data.get("location_title", "ЖК")

    key, _, parser, _ = steps[step_idx]

    try:
        value = parser(txt)
    except Exception as e:
        await message.answer(f"❗️ Ошибка ввода: {e}\nПопробуйте ещё раз.")
        await ask_step(message, state)
        return

    answers[key] = value
    step_idx += 1

    if step_idx >= len(steps):
        if "report_date" not in answers:
            answers["report_date"] = datetime.now().strftime("%d.%m.%Y")

        report_date_iso = iso_from_ddmmyyyy(str(answers["report_date"]))

        await upsert_milk_report(
            location=loc_code,
            report_date=report_date_iso,
            data_json=json.dumps(answers, ensure_ascii=False),
            created_by=message.from_user.id
        )

        await state.clear()
        await message.answer("✅ <b>Сводка сохранена.</b>", parse_mode="HTML")
        await _send_text_and_pdf(message, loc_title, loc_code, answers, mode="public")
        return

    await state.update_data(step_idx=step_idx, answers=answers)
    await ask_step(message, state)


async def send_daily_group_milk_summary(bot):
    if not GROUP_CHAT_ID:
        return

    today_iso = date.today().strftime("%Y-%m-%d")
    row = await get_milk_report_by_date("aktuba", today_iso)
    if not row:
        row = await get_latest_milk_report("aktuba")

    if not row:
        await bot.send_message(GROUP_CHAT_ID, "❗️ Сводка по молоку: данных нет.")
        return

    data = json.loads(row["data_json"])

    prices = await get_location_prices("aktuba")
    text = build_report("ЖК «Актюба»", data, mode="group", prices=prices)
    await bot.send_message(GROUP_CHAT_ID, text, parse_mode="HTML")

    pdf_b = build_milk_summary_pdf_bytes("ЖК «Актюба»", data, mode="group", density=MILK_DENSITY, prices=prices)
    filename = _make_pdf_filename("aktuba", str(data.get("report_date") or ""), "group")
    await bot.send_document(GROUP_CHAT_ID, document=BufferedInputFile(pdf_b, filename=filename))
