import os
import re
import json
import aiosqlite

from datetime import datetime, date, timedelta

from aiogram import Router, types, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from config import ADMIN_IDS

from utils.pdf_milk_reports import (
    build_milk_daily_pdf_bytes,
    build_milk_monthly_pdf_bytes,
    MILK_DENSITY_DEFAULT,
)

router = Router()

DB_PATH = os.getenv("DATABASE_PATH", "data/aktuba.db")
GROUP_CHAT_ID = os.getenv("MILK_GROUP_CHAT_ID")

MILK_DENSITY = MILK_DENSITY_DEFAULT


# ─────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────
async def ensure_milk_reports_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS milk_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location TEXT NOT NULL,
                report_date DATE NOT NULL,
                data_json TEXT NOT NULL,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(location, report_date)
            );
        """)
        await db.commit()


async def upsert_milk_report(location: str, report_date_iso: str, data: dict, created_by: int):
    await ensure_milk_reports_table()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO milk_reports (location, report_date, data_json, created_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(location, report_date) DO UPDATE SET
                data_json=excluded.data_json,
                created_by=excluded.created_by,
                created_at=CURRENT_TIMESTAMP
        """, (location, report_date_iso, json.dumps(data, ensure_ascii=False), created_by))
        await db.commit()


async def get_latest_milk_report(location: str):
    await ensure_milk_reports_table()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT location, report_date, data_json, created_by, created_at
            FROM milk_reports
            WHERE location=?
            ORDER BY report_date DESC, created_at DESC
            LIMIT 1
        """, (location,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_milk_report_by_date(location: str, report_date_iso: str):
    await ensure_milk_reports_table()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT location, report_date, data_json, created_by, created_at
            FROM milk_reports
            WHERE location=? AND report_date=?
            LIMIT 1
        """, (location, report_date_iso))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_nearest_milk_report(location: str, target_date_iso: str):
    """Самая ближайшая дата к target (включая прошлое/будущее), если есть ошибки ввода дат."""
    await ensure_milk_reports_table()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT location, report_date, data_json, created_by, created_at
            FROM milk_reports
            WHERE location=?
            ORDER BY ABS(julianday(report_date) - julianday(?)) ASC, report_date DESC
            LIMIT 1
        """, (location, target_date_iso))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_milk_reports_in_range(location: str, date_from_iso: str, date_to_iso: str):
    """[date_from, date_to]"""
    await ensure_milk_reports_table()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT report_date, data_json
            FROM milk_reports
            WHERE location=? AND report_date>=? AND report_date<=?
            ORDER BY report_date ASC
        """, (location, date_from_iso, date_to_iso))
        rows = await cur.fetchall()
        return [(r["report_date"], json.loads(r["data_json"])) for r in rows]


def month_range_from_iso(report_date_iso: str) -> tuple[str, str]:
    dt = datetime.strptime(report_date_iso, "%Y-%m-%d")
    start = dt.replace(day=1)
    # конец месяца
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    end = next_month - timedelta(days=1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────
# FSM
# ─────────────────────────────────────────────────────────────
class MilkWizard(StatesGroup):
    active = State()


# ─────────────────────────────────────────────────────────────
# Utils
# ─────────────────────────────────────────────────────────────
def fmt_int(x: float | int) -> str:
    return f"{int(round(float(x))):,}".replace(",", " ")


def fmt_float(x: float, digits: int = 2) -> str:
    return f"{x:.{digits}f}"


def parse_number(text: str) -> float:
    t = (text or "").strip().replace(" ", "").replace(",", ".")
    t = re.sub(r"[^0-9.]", "", t)
    if t == "":
        raise ValueError("Пустое значение")
    return float(t)


def parse_int(text: str) -> int:
    v = parse_number(text)
    if v < 0:
        raise ValueError("Число не может быть отрицательным")
    return int(round(v))


def parse_float(text: str) -> float:
    v = parse_number(text)
    if v < 0:
        raise ValueError("Число не может быть отрицательным")
    return float(v)


def parse_date_ddmmyyyy(text: str) -> str:
    t = (text or "").strip()
    if t.lower() in ("0", "сегодня", "today"):
        return datetime.now().strftime("%d.%m.%Y")
    dt = datetime.strptime(t, "%d.%m.%Y")
    return dt.strftime("%d.%m.%Y")


def iso_from_ddmmyyyy(date_str: str) -> str:
    return datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")


def yesno(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in ("да", "д", "yes", "y", "1", "+"):
        return True
    if t in ("нет", "н", "no", "n", "0", "-"):
        return False
    raise ValueError("Введите: да или нет")


# ─────────────────────────────────────────────────────────────
# Steps
# ─────────────────────────────────────────────────────────────
STEPS = [
    ("report_date", "Введите дату отчёта <b>ДД.ММ.ГГГГ</b> (или <b>0</b> = сегодня):", parse_date_ddmmyyyy, "пример: 23.01.2026"),
    ("milk_total_l", "Молокопровод (л):", parse_float, "пример: 102500"),
    ("milk_small_l", "Малая ферма (л):", parse_float, "пример: 3500"),
    ("milk_buyer_l", "Реализация покупатель (л):", parse_float, "пример: 98000"),
    ("milk_trade_l", "Реализация население (л):", parse_float, "пример: 500"),
    ("milk_sold_l", "Всего реализовано (л) (если не считаете — 0):", parse_float, "пример: 98500"),
    ("milk_calves_l", "На выпойку (л):", parse_float, "пример: 1200"),
    ("milk_disposal_l", "Утиль (л):", parse_float, "пример: 150"),
    ("milk_tank_total_kg", "Танк всего (кг):", parse_float, "пример: 102000"),
    ("fat_pct", "Жир (%):", parse_float, "пример: 3.85"),
    ("protein_pct", "Белок (%):", parse_float, "пример: 3.22"),
    ("use_fact", "Есть фактический валовый надой по ДЗ? (да/нет):", yesno, "пример: да"),
    # gross_fact_kg спрашиваем условно
]


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def build_report(location_title: str, d: dict, mode: str = "public") -> str:
    milk_total_l = float(d.get("milk_total_l", 0) or 0)
    milk_small_l = float(d.get("milk_small_l", 0) or 0)
    gross_l = milk_total_l + milk_small_l
    gross_kg = gross_l * MILK_DENSITY

    milk_buyer_l = float(d.get("milk_buyer_l", 0) or 0)
    milk_trade_l = float(d.get("milk_trade_l", 0) or 0)
    milk_sold_l = float(d.get("milk_sold_l", 0) or 0)
    if milk_sold_l > 0:
        sold_l = milk_sold_l
    else:
        sold_l = milk_buyer_l + milk_trade_l
    sold_kg = sold_l * MILK_DENSITY

    calves_kg = float(d.get("milk_calves_l", 0) or 0) * MILK_DENSITY
    disposal_kg = float(d.get("milk_disposal_l", 0) or 0) * MILK_DENSITY
    tank_kg = float(d.get("milk_tank_total_kg", 0) or 0)

    fat = float(d.get("fat_pct", 0) or 0)
    protein = float(d.get("protein_pct", 0) or 0)

    report_date = d.get("report_date", datetime.now().strftime("%d.%m.%Y"))

    lines = []
    lines.append(f"🍼 <b>Сводка по молоку</b> — {location_title}")
    lines.append(f"Дата: <b>{report_date}</b>\n")
    lines.append(f"Валовый надой: <b>{fmt_int(gross_kg)}</b> кг")

    if mode in ("admin", "group") and d.get("gross_fact_kg") is not None:
        fact = float(d.get("gross_fact_kg") or 0)
        diff = fact - gross_kg
        sign = "+" if diff > 0 else ""
        lines.append(f"Факт (по ДЗ): <b>{fmt_int(fact)}</b> кг (откл.: <b>{sign}{fmt_int(diff)}</b>)")

    lines.append(f"Реализация: <b>{fmt_int(sold_kg)}</b> кг")
    lines.append(f"На выпойку: <b>{fmt_int(calves_kg)}</b> кг")
    lines.append(f"Утиль: <b>{fmt_int(disposal_kg)}</b> кг")
    lines.append(f"Танк: <b>{fmt_int(tank_kg)}</b> кг\n")

    lines.append(f"Жир: <b>{fmt_float(fat, 2)}</b> %")
    lines.append(f"Белок: <b>{fmt_float(protein, 2)}</b> %\n")

    lines.append("Детализация (л):")
    lines.append(f"• молокопровод: <b>{fmt_int(milk_total_l)}</b>")
    lines.append(f"• малая ферма: <b>{fmt_int(milk_small_l)}</b>")
    lines.append(f"• покупатель: <b>{fmt_int(milk_buyer_l)}</b>")
    lines.append(f"• население: <b>{fmt_int(milk_trade_l)}</b>")
    lines.append(f"• всего реализовано: <b>{fmt_int(milk_sold_l)}</b>")

    return "\n".join(lines)


async def ask_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    idx = int(data.get("step_idx", 0))
    answers = data.get("answers", {})

    # динамический шаг gross_fact_kg
    steps = list(STEPS)
    if idx > 0:
        # если use_fact уже введён
        if "use_fact" in answers and answers["use_fact"] is True:
            # добавить вопрос факта сразу после use_fact
            keys = [s[0] for s in steps]
            if "gross_fact_kg" not in keys:
                # после use_fact
                pos = keys.index("use_fact") + 1
                steps.insert(pos, ("gross_fact_kg", "Факт валовый надой по ДЗ (кг):", parse_float, "пример: 106000"))

    # пересчитать idx если шагов стало больше после вставки
    if idx >= len(steps):
        idx = len(steps) - 1

    key, q, _, hint = steps[idx]
    await state.update_data(runtime_steps=steps)

    await message.answer(
        f"🍼 <b>Сводка по молоку</b>\n"
        f"Шаг <b>{idx + 1}</b> из <b>{len(steps)}</b>\n\n"
        f"{q}\n<i>{hint}</i>\n\n"
        f"Для отмены: <b>отмена</b>",
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────────────
# Menu callbacks (просмотр)
# ─────────────────────────────────────────────────────────────
@router.callback_query(F.data == "milk_summary")
async def milk_summary_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="ЖК «Актюба»", callback_data="milk_aktuba")],
            [InlineKeyboardButton(text="Карамалы", callback_data="milk_karamaly")],
            [InlineKeyboardButton(text="Шереметьево", callback_data="milk_sheremetyovo")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="milk_summary_back")],
        ]
    )
    await callback.message.answer("🍼 Выберите локацию:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "milk_summary_back")
async def milk_summary_back(callback: types.CallbackQuery):
    from keyboards.reports_inline import get_view_keyboard
    await callback.message.answer("📊 Выберите раздел:", reply_markup=get_view_keyboard())
    await callback.answer()


# ─────────────────────────────────────────────────────────────
# Submit callbacks
# ─────────────────────────────────────────────────────────────
@router.callback_query(F.data == "milk_summary_submit")
async def milk_submit_menu(callback: types.CallbackQuery):
    from keyboards.reports_inline import get_milk_summary_submit_keyboard
    await callback.message.answer(
        "🍼 Куда сдаём сводку по молоку?",
        reply_markup=get_milk_summary_submit_keyboard(include_soyuz_agro=False),
    )
    await callback.answer()


@router.callback_query(F.data == "milk_submit_back")
async def milk_submit_back(callback: types.CallbackQuery):
    from keyboards.reports_inline import get_submit_keyboard
    await callback.message.answer("📝 Выберите раздел:", reply_markup=get_submit_keyboard())
    await callback.answer()


def location_from_cb(cb: str) -> tuple[str, str]:
    if cb == "milk_submit_aktuba":
        return "aktuba", "ЖК «Актюба»"
    if cb == "milk_submit_karamaly":
        return "karamaly", "Карамалы"
    if cb == "milk_submit_sheremetyovo":
        return "sheremetyovo", "Шереметьево"
    return "aktuba", "ЖК «Актюба»"


@router.callback_query(F.data.in_(["milk_submit_aktuba", "milk_submit_karamaly", "milk_submit_sheremetyovo"]))
async def start_submit_milk(callback: types.CallbackQuery, state: FSMContext):
    loc_code, loc_title = location_from_cb(callback.data)

    await state.set_state(MilkWizard.active)
    await state.update_data(step_idx=0, answers={}, location_code=loc_code, location_title=loc_title, runtime_steps=None)

    await callback.message.answer(
        f"✅ Начинаем сдачу <b>«Сводки по молоку»</b> ({loc_title}).\n"
        f"Бот задаст вопросы по одному.",
        parse_mode="HTML",
    )
    await ask_step(callback.message, state)
    await callback.answer()


@router.message(MilkWizard.active)
async def milk_wizard_input(message: types.Message, state: FSMContext):
    txt = (message.text or "").strip()
    if txt.lower() in ("отмена", "cancel", "/cancel", "стоп"):
        await state.clear()
        await message.answer("⛔ Сдача сводки отменена.")
        return

    data = await state.get_data()
    idx = int(data.get("step_idx", 0))
    answers = data.get("answers", {})
    loc_code = data.get("location_code", "aktuba")
    loc_title = data.get("location_title", "ЖК «Актюба»")

    steps = data.get("runtime_steps")
    if not steps:
        steps = list(STEPS)

    key, _, parser, _ = steps[idx]

    try:
        value = parser(txt)
    except Exception as e:
        await message.answer(f"❗️Ошибка ввода: {e}\nПовторите ещё раз.")
        await ask_step(message, state)
        return

    answers[key] = value

    # если вводим use_fact и ответ "нет" — удалим gross_fact_kg если есть
    if key == "use_fact" and value is False:
        answers.pop("gross_fact_kg", None)

    idx += 1

    if idx >= len(steps):
        # финал
        if "report_date" not in answers:
            answers["report_date"] = datetime.now().strftime("%d.%m.%Y")

        report_date_iso = iso_from_ddmmyyyy(str(answers["report_date"]))
        answers["report_date_iso"] = report_date_iso

        # если админ и был факт — сохраняем как gross_fact_kg
        if is_admin(message.from_user.id) and answers.get("gross_fact_kg") is not None:
            answers["gross_fact_kg"] = float(answers.get("gross_fact_kg") or 0)

        await upsert_milk_report(loc_code, report_date_iso, answers, message.from_user.id)

        # текст
        text = build_report(loc_title, answers, mode="admin" if is_admin(message.from_user.id) else "public")
        await state.clear()
        await message.answer("✅ <b>Сводка сохранена.</b>\n\n" + text, parse_mode="HTML")

        # PDF (день)
        include_fact = is_admin(message.from_user.id)
        pdf_day = build_milk_daily_pdf_bytes(loc_title, report_date_iso, answers, include_fact=include_fact, density=MILK_DENSITY)
        day_name = f"milk_{loc_code}_{report_date_iso}_{message.from_user.id}.pdf"
        with open(day_name, "wb") as f:
            f.write(pdf_day)
        await message.answer_document(FSInputFile(day_name), caption="🍼 Сводка по молоку (PDF за сутки)")
        try:
            os.remove(day_name)
        except Exception:
            pass

        # PDF (месяц)
        m_from, m_to = month_range_from_iso(report_date_iso)
        month_reports = await get_milk_reports_in_range(loc_code, m_from, m_to)
        pdf_month = build_milk_monthly_pdf_bytes(loc_title, m_from, m_to, month_reports, include_fact=include_fact, density=MILK_DENSITY)
        mon_name = f"milk_month_{loc_code}_{m_from}_{message.from_user.id}.pdf"
        with open(mon_name, "wb") as f:
            f.write(pdf_month)
        await message.answer_document(FSInputFile(mon_name), caption="🍼 Сводка по молоку (PDF за месяц)")
        try:
            os.remove(mon_name)
        except Exception:
            pass

        return

    await state.update_data(step_idx=idx, answers=answers, runtime_steps=steps)
    await ask_step(message, state)


# ─────────────────────────────────────────────────────────────
# VIEW (текст + PDF сутки + PDF месяц)
# ─────────────────────────────────────────────────────────────
async def view_milk_location(callback: types.CallbackQuery, location_code: str, location_title: str):
    today_iso = date.today().strftime("%Y-%m-%d")
    row = await get_nearest_milk_report(location_code, today_iso)

    if not row:
        await callback.message.answer("❗️Нет заполненных отчётов по молоку.")
        return

    d = json.loads(row["data_json"])
    report_date_iso = row["report_date"]
    report_date_str = datetime.strptime(report_date_iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    d["report_date"] = d.get("report_date") or report_date_str

    mode = "admin" if is_admin(callback.from_user.id) else "public"
    text = build_report(location_title, d, mode=mode)

    # 1) текст
    await callback.message.answer(text, parse_mode="HTML")

    # 2) PDF сутки
    include_fact = is_admin(callback.from_user.id)
    pdf_day = build_milk_daily_pdf_bytes(location_title, report_date_iso, d, include_fact=include_fact, density=MILK_DENSITY)
    day_name = f"milk_view_{location_code}_{report_date_iso}_{callback.from_user.id}.pdf"
    with open(day_name, "wb") as f:
        f.write(pdf_day)
    await callback.message.answer_document(FSInputFile(day_name), caption=f"🍼 PDF за сутки ({report_date_str})")
    try:
        os.remove(day_name)
    except Exception:
        pass

    # 3) PDF месяц
    m_from, m_to = month_range_from_iso(report_date_iso)
    month_reports = await get_milk_reports_in_range(location_code, m_from, m_to)
    pdf_month = build_milk_monthly_pdf_bytes(location_title, m_from, m_to, month_reports, include_fact=include_fact, density=MILK_DENSITY)
    mon_name = f"milk_view_month_{location_code}_{m_from}_{callback.from_user.id}.pdf"
    with open(mon_name, "wb") as f:
        f.write(pdf_month)
    await callback.message.answer_document(FSInputFile(mon_name), caption=f"🍼 PDF за месяц ({m_from} — {m_to})")
    try:
        os.remove(mon_name)
    except Exception:
        pass


@router.callback_query(F.data == "milk_aktuba")
async def view_milk_aktuba(callback: types.CallbackQuery):
    await view_milk_location(callback, "aktuba", "ЖК «Актюба»")
    await callback.answer()


@router.callback_query(F.data == "milk_karamaly")
async def view_milk_karamaly(callback: types.CallbackQuery):
    await view_milk_location(callback, "karamaly", "Карамалы")
    await callback.answer()


@router.callback_query(F.data == "milk_sheremetyovo")
async def view_milk_sheremetyovo(callback: types.CallbackQuery):
    await view_milk_location(callback, "sheremetyovo", "Шереметьево")
    await callback.answer()


# ─────────────────────────────────────────────────────────────
# Scheduler: отправка в группу (как было: текст)
# ─────────────────────────────────────────────────────────────
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
    text = build_report("ЖК «Актюба»", data, mode="group")
    await bot.send_message(GROUP_CHAT_ID, text, parse_mode="HTML")
