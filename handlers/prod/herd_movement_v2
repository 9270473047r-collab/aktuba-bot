import json
from datetime import datetime, date

from aiogram import Router, types, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from db import db  # используем общую bot.db


router = Router()

LOCATION_CODE = "aktuba"
LOCATION_TITLE = "ЖК «Актюба»"


# ─────────────────────────────────────────────────────────────
# FSM
# ─────────────────────────────────────────────────────────────
class HerdWizard(StatesGroup):
    active = State()


# ─────────────────────────────────────────────────────────────
# Парсинг
# ─────────────────────────────────────────────────────────────
def fmt_int(x: float | int) -> str:
    return f"{int(round(x)):,}".replace(",", " ")


def fmt_float(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def parse_number(text: str) -> int:
    t = (text or "").strip().replace(" ", "").replace(",", ".")
    if t == "":
        raise ValueError("Пустое значение")
    x = float(t)
    if x < 0:
        raise ValueError("Число не может быть отрицательным")
    return int(round(x))


def parse_date_ddmmyyyy(text: str) -> str:
    t = (text or "").strip()
    if t.lower() in ("0", "сегодня", "today"):
        return datetime.now().strftime("%d.%m.%Y")
    dt = datetime.strptime(t, "%d.%m.%Y")
    return dt.strftime("%d.%m.%Y")


def iso_from_ddmmyyyy(date_str: str) -> str:
    return datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")


def month_range_from_iso(iso_date: str) -> tuple[str, str]:
    d = datetime.strptime(iso_date, "%Y-%m-%d").date()
    first = d.replace(day=1)
    return first.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d")


def year_range_from_iso(iso_date: str) -> tuple[str, str]:
    d = datetime.strptime(iso_date, "%Y-%m-%d").date()
    first = date(d.year, 1, 1)
    return first.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────
# DB: таблица herd_movement_reports
# ─────────────────────────────────────────────────────────────
async def ensure_table():
    await db.conn.execute("""
        CREATE TABLE IF NOT EXISTS herd_movement_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT NOT NULL,
            report_date DATE NOT NULL,
            data_json TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(location, report_date)
        );
    """)
    await db.conn.commit()


async def upsert_report(location: str, report_date: str, data: dict, created_by: int):
    await ensure_table()
    await db.conn.execute("""
        INSERT INTO herd_movement_reports (location, report_date, data_json, created_by)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(location, report_date) DO UPDATE SET
            data_json  = excluded.data_json,
            created_by = excluded.created_by,
            created_at = CURRENT_TIMESTAMP
    """, (location, report_date, json.dumps(data, ensure_ascii=False), created_by))
    await db.conn.commit()


async def get_latest_report(location: str):
    await ensure_table()
    cur = await db.conn.execute("""
        SELECT location, report_date, data_json, created_by, created_at
        FROM herd_movement_reports
        WHERE location = ?
        ORDER BY report_date DESC, created_at DESC
        LIMIT 1
    """, (location,))
    row = await cur.fetchone()
    await cur.close()
    return dict(row) if row else None


async def get_reports_in_range(location: str, date_from: str, date_to: str) -> list[dict]:
    await ensure_table()
    cur = await db.conn.execute("""
        SELECT report_date, data_json
        FROM herd_movement_reports
        WHERE location = ?
          AND report_date BETWEEN ? AND ?
        ORDER BY report_date ASC
    """, (location, date_from, date_to))
    rows = await cur.fetchall()
    await cur.close()
    out = []
    for r in rows:
        out.append({"report_date": r["report_date"], "data": json.loads(r["data_json"])})
    return out


def sum_fields(reports: list[dict], keys: list[str]) -> dict:
    totals = {k: 0 for k in keys}
    for r in reports:
        d = r["data"]
        for k in keys:
            totals[k] += int(d.get(k, 0) or 0)
    return totals


# ─────────────────────────────────────────────────────────────
# ШАГИ ВОПРОСОВ (всё по одному вопросу)
# ─────────────────────────────────────────────────────────────
STEPS = [
    ("report_date", "Введите дату отчёта <b>ДД.ММ.ГГГГ</b> (или <b>0</b> = сегодня):", parse_date_ddmmyyyy, "пример: 31.12.2025"),

    # Поголовье (факт на утро)
    ("forage_cows", "Фуражные коровы (гол):", parse_number, "пример: 3288"),
    ("milking_cows", "Дойные коровы (гол):", parse_number, "пример: 3066"),
    ("ro_cows", "в т.ч. в РО (гол):", parse_number, "пример: 412"),
    ("dry_cows", "Сухостой (гол):", parse_number, "пример: 222"),
    ("pregnant_cows", "Стельные коровы (гол):", parse_number, "пример: 2540"),

    # Молодняк
    ("heifers_0_3", "Тёлки 0–3 мес (гол):", parse_number, "пример: 368"),
    ("heifers_3_6", "Тёлки 3–6 мес (гол):", parse_number, "пример: 787"),
    ("heifers_6_12", "Тёлки 6–12 мес (гол):", parse_number, "пример: 898"),
    ("heifers_12_18", "Тёлки 12–18 мес (гол):", parse_number, "пример: 213"),
    ("heifers_18_plus", "Тёлки старше 18 мес (гол):", parse_number, "пример: 29"),
    ("bulls_0_3", "Бычки 0–3 мес (гол):", parse_number, "пример: 83"),
    ("heifers_total", "Нетели (гол):", parse_number, "пример: 1014"),

    # Состояние стада
    ("hospital", "Госпиталь (гол):", parse_number, "пример: 37"),
    ("mastitis", "Мастит (гол):", parse_number, "пример: 10"),
    ("cull", "Брак (на выбытие) (гол):", parse_number, "пример: 18"),

    # Подразделения
    ("ch_neteli", "Чемодурово — Нетели (гол):", parse_number, "пример: 412"),
    ("ch_heifers_0_3", "Чемодурово — Тёлки 0–3 мес (гол):", parse_number, "пример: 214"),
    ("ch_heifers_3_6", "Чемодурово — Тёлки 3–6 мес (гол):", parse_number, "пример: 386"),
    ("ch_heifers_6_12", "Чемодурово — Тёлки 6–12 мес (гол):", parse_number, "пример: 401"),
    ("ch_heifers_12_plus", "Чемодурово — Тёлки старше 12 мес (гол):", parse_number, "пример: 96"),
    ("ch_bulls_0_3", "Чемодурово — Бычки 0–3 мес (гол):", parse_number, "пример: 43"),

    ("np_neteli", "Нетельная площадка — Нетели (гол):", parse_number, "пример: 602"),
    ("np_heifers_6_12", "Нетельная площадка — Тёлки 6–12 мес (гол):", parse_number, "пример: 497"),
    ("np_heifers_12_plus", "Нетельная площадка — Тёлки старше 12 мес (гол):", parse_number, "пример: 136"),

    # Движение за сутки
    ("launch", "Запуск за сутки (гол):", parse_number, "пример: 0"),

    ("calv_cows", "Отёлы за день — коровы (гол):", parse_number, "пример: 7"),
    ("calv_neteli", "Отёлы за день — нетели (гол):", parse_number, "пример: 7"),
    ("calves_heifers_day", "Тёлки (родилось за день) (гол):", parse_number, "пример: 7"),
    ("calves_bulls_day", "Бычки (родилось за день) (гол):", parse_number, "пример: 7"),
    ("stillborn_day", "Мертворождённые за день (гол):", parse_number, "пример: 0"),
    ("abort_day", "Аборт за день (гол):", parse_number, "пример: 0"),

    # Падёж за сутки
    ("death_cows", "Падёж за сутки — коровы (гол):", parse_number, "пример: 0"),
    ("death_calves_0_3", "Падёж за сутки — телята 0–3 мес (гол):", parse_number, "пример: 0"),
    ("death_young_over_3", "Падёж за сутки — молодняк старше 3 мес (гол):", parse_number, "пример: 0"),

    # Реализация за сутки (вводим по категориям — ИТОГО считается автоматически)
    ("sale_cows", "Реализация за сутки — коровы (гол):", parse_number, "пример: 0"),
    ("sale_neteli", "Реализация за сутки — нетели (гол):", parse_number, "пример: 0"),
    ("sale_heifers", "Реализация за сутки — тёлки (гол):", parse_number, "пример: 0"),
    ("sale_bulls", "Реализация за сутки — бычки (гол):", parse_number, "пример: 0"),
]


async def ask_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    step_idx = int(data.get("step_idx", 0))

    _, q, _, hint = STEPS[step_idx]
    await message.answer(
        f"📊 <b>Отчёт: Движение поголовья — {LOCATION_TITLE}</b>\n"
        f"Шаг <b>{step_idx + 1}</b> из <b>{len(STEPS)}</b>\n\n"
        f"{q}\n<i>{hint}</i>\n\n"
        f"Для отмены: <b>отмена</b>",
        parse_mode="HTML"
    )


def build_report_text(daily: dict, month_tot: dict, year_tot: dict) -> str:
    date_str = daily.get("report_date", datetime.now().strftime("%d.%m.%Y"))
    iso = iso_from_ddmmyyyy(date_str)

    forage = int(daily.get("forage_cows", 0))
    milking = int(daily.get("milking_cows", 0))
    ro = int(daily.get("ro_cows", 0))
    dry = int(daily.get("dry_cows", 0))
    preg = int(daily.get("pregnant_cows", 0))

    he0_3 = int(daily.get("heifers_0_3", 0))
    he3_6 = int(daily.get("heifers_3_6", 0))
    he6_12 = int(daily.get("heifers_6_12", 0))
    he12_18 = int(daily.get("heifers_12_18", 0))
    he18p = int(daily.get("heifers_18_plus", 0))
    bulls0_3 = int(daily.get("bulls_0_3", 0))
    neteli = int(daily.get("heifers_total", 0))

    total_cattle = forage + neteli + he0_3 + he3_6 + he6_12 + he12_18 + he18p + bulls0_3

    preg_pct = (preg / forage * 100) if forage > 0 else 0.0

    hosp = int(daily.get("hospital", 0))
    mast = int(daily.get("mastitis", 0))
    cull = int(daily.get("cull", 0))

    # подразделения
    ch_neteli = int(daily.get("ch_neteli", 0))
    ch_h0_3 = int(daily.get("ch_heifers_0_3", 0))
    ch_h3_6 = int(daily.get("ch_heifers_3_6", 0))
    ch_h6_12 = int(daily.get("ch_heifers_6_12", 0))
    ch_h12p = int(daily.get("ch_heifers_12_plus", 0))
    ch_b0_3 = int(daily.get("ch_bulls_0_3", 0))

    np_neteli = int(daily.get("np_neteli", 0))
    np_h6_12 = int(daily.get("np_heifers_6_12", 0))
    np_h12p = int(daily.get("np_heifers_12_plus", 0))

    # движение
    launch = int(daily.get("launch", 0))

    calv_cows = int(daily.get("calv_cows", 0))
    calv_neteli = int(daily.get("calv_neteli", 0))
    calv_total = calv_cows + calv_neteli

    calves_h_day = int(daily.get("calves_heifers_day", 0))
    calves_b_day = int(daily.get("calves_bulls_day", 0))
    still_day = int(daily.get("stillborn_day", 0))
    abort_day = int(daily.get("abort_day", 0))

    # падёж
    d_cows = int(daily.get("death_cows", 0))
    d_calves = int(daily.get("death_calves_0_3", 0))
    d_young = int(daily.get("death_young_over_3", 0))

    # реализация
    s_cows = int(daily.get("sale_cows", 0))
    s_neteli = int(daily.get("sale_neteli", 0))
    s_heifers = int(daily.get("sale_heifers", 0))
    s_bulls = int(daily.get("sale_bulls", 0))
    s_total = s_cows + s_neteli + s_heifers + s_bulls

    # месячные/годовые суммы
    m_calv_total = month_tot["calv_cows"] + month_tot["calv_neteli"]
    y_calv_total = year_tot["calv_cows"] + year_tot["calv_neteli"]

    m_calves_total = month_tot["calves_heifers_day"] + month_tot["calves_bulls_day"]
    y_calves_total = year_tot["calves_heifers_day"] + year_tot["calves_bulls_day"]

    m_heifer_pct = (month_tot["calves_heifers_day"] / m_calves_total * 100) if m_calves_total > 0 else 0.0
    y_heifer_pct = (year_tot["calves_heifers_day"] / y_calves_total * 100) if y_calves_total > 0 else 0.0

    m_sale_total = month_tot["sale_cows"] + month_tot["sale_neteli"] + month_tot["sale_heifers"] + month_tot["sale_bulls"]
    y_sale_total = year_tot["sale_cows"] + year_tot["sale_neteli"] + year_tot["sale_heifers"] + year_tot["sale_bulls"]

    text = (
        f"📊 <b>Сводка по стаду {LOCATION_TITLE}</b>\n"
        f"за <b>{date_str}</b>\n\n"

        f"🐄 <b>Поголовье (факт на утро)</b>\n\n"
        f"• Всего КРС — <b>{fmt_int(total_cattle)}</b> гол\n"
        f"• Фуражные коровы — <b>{fmt_int(forage)}</b>\n"
        f"• Дойные коровы — <b>{fmt_int(milking)}</b>\n"
        f"  в т.ч. в РО — <b>{fmt_int(ro)}</b> гол\n"
        f"• Сухостой — <b>{fmt_int(dry)}</b>\n"
        f"• Стельные коровы — <b>{fmt_int(preg)}</b>\n"
        f"• Стельность — <b>{fmt_float(preg_pct, 1)}</b> % (к фуражным)\n\n"

        f"<b>Молодняк</b>\n"
        f"• Тёлки 0–3 мес — <b>{fmt_int(he0_3)}</b>\n"
        f"• Тёлки 3–6 мес — <b>{fmt_int(he3_6)}</b>\n"
        f"• Тёлки 6–12 мес — <b>{fmt_int(he6_12)}</b>\n"
        f"• Тёлки 12–18 мес — <b>{fmt_int(he12_18)}</b>\n"
        f"• Тёлки старше 18 мес — <b>{fmt_int(he18p)}</b>\n"
        f"• Бычки 0–3 мес — <b>{fmt_int(bulls0_3)}</b>\n\n"

        f"Состояние стада\n"
        f"• Госпиталь — <b>{fmt_int(hosp)}</b> гол\n"
        f"• Мастит — <b>{fmt_int(mast)}</b> гол\n"
        f"• Брак (на выбытие) — <b>{fmt_int(cull)}</b> гол\n\n"

        f"• Нетели — <b>{fmt_int(neteli)}</b>\n\n"

        f"🏠 <b>Поголовье по подразделениям</b>\n\n"
        f"Чемодурово\n"
        f"• Нетели — <b>{fmt_int(ch_neteli)}</b>\n"
        f"• Тёлки 0–3 мес — <b>{fmt_int(ch_h0_3)}</b>\n"
        f"• Тёлки 3–6 мес — <b>{fmt_int(ch_h3_6)}</b>\n"
        f"• Тёлки 6–12 мес — <b>{fmt_int(ch_h6_12)}</b>\n"
        f"• Тёлки старше 12 мес — <b>{fmt_int(ch_h12p)}</b>\n"
        f"• Бычки 0–3 мес — <b>{fmt_int(ch_b0_3)}</b>\n\n"

        f"Нетельная площадка\n"
        f"• Нетели — <b>{fmt_int(np_neteli)}</b>\n"
        f"• Тёлки 6–12 мес — <b>{fmt_int(np_h6_12)}</b>\n"
        f"• Тёлки старше 12 мес — <b>{fmt_int(np_h12p)}</b>\n\n"

        f"🔄 <b>Движение стада за сутки</b>\n\n"
        f"Запуск — <b>{fmt_int(launch)}</b> гол\n\n"
        f"Отёлы за день — <b>{fmt_int(calv_total)}</b> гол, в том числе:\n"
        f"• коровы — <b>{fmt_int(calv_cows)}</b>\n"
        f"• нетели — <b>{fmt_int(calv_neteli)}</b>\n"
        f"• тёлки — <b>{fmt_int(calves_h_day)}</b>\n"
        f"• бычки — <b>{fmt_int(calves_b_day)}</b>\n"
        f"• мертворождённые — <b>{fmt_int(still_day)}</b>\n"
        f"• аборт — <b>{fmt_int(abort_day)}</b>\n\n"

        f"📅 <b>Отёлы</b>\n\n"
        f"За месяц — <b>{fmt_int(m_calv_total)}</b> гол, в т.ч.:\n"
        f"• коровы — <b>{fmt_int(month_tot['calv_cows'])}</b>\n"
        f"• нетели — <b>{fmt_int(month_tot['calv_neteli'])}</b>\n"
        f"• тёлки — <b>{fmt_int(month_tot['calves_heifers_day'])}</b>\n"
        f"• бычки — <b>{fmt_int(month_tot['calves_bulls_day'])}</b>\n"
        f"• мертворождённые — <b>{fmt_int(month_tot['stillborn_day'])}</b>\n"
        f"• аборты — <b>{fmt_int(month_tot['abort_day'])}</b>\n\n"

        f"С начала года — <b>{fmt_int(y_calv_total)}</b> гол, в т.ч.:\n"
        f"• коровы — <b>{fmt_int(year_tot['calv_cows'])}</b>\n"
        f"• нетели — <b>{fmt_int(year_tot['calv_neteli'])}</b>\n"
        f"• тёлки — <b>{fmt_int(year_tot['calves_heifers_day'])}</b>\n"
        f"• бычки — <b>{fmt_int(year_tot['calves_bulls_day'])}</b>\n"
        f"• мертворождённые — <b>{fmt_int(year_tot['stillborn_day'])}</b>\n"
        f"• аборты — <b>{fmt_int(year_tot['abort_day'])}</b>\n\n"

        f"Выход тёлок (с начала года) — <b>{fmt_float(y_heifer_pct, 1)}</b> %\n\n"

        f"⚠️ <b>Падёж</b>\n\n"
        f"За сутки:\n"
        f"• коровы — <b>{fmt_int(d_cows)}</b> гол\n"
        f"• телята 0–3 мес — <b>{fmt_int(d_calves)}</b> гол\n"
        f"• молодняк старше 3 мес — <b>{fmt_int(d_young)}</b> гол\n\n"

        f"🚚 <b>Реализация КРС</b>\n\n"
        f"За сутки — <b>{fmt_int(s_total)}</b> гол\n\n"
        f"За месяц — <b>{fmt_int(m_sale_total)}</b> гол, в т.ч.:\n"
        f"• коровы — <b>{fmt_int(month_tot['sale_cows'])}</b>\n"
        f"• нетели — <b>{fmt_int(month_tot['sale_neteli'])}</b>\n"
        f"• тёлки — <b>{fmt_int(month_tot['sale_heifers'])}</b>\n"
        f"• бычки — <b>{fmt_int(month_tot['sale_bulls'])}</b>\n\n"

        f"С начала года — <b>{fmt_int(y_sale_total)}</b> гол, в т.ч.:\n"
        f"• коровы — <b>{fmt_int(year_tot['sale_cows'])}</b>\n"
        f"• нетели — <b>{fmt_int(year_tot['sale_neteli'])}</b>\n"
        f"• тёлки — <b>{fmt_int(year_tot['sale_heifers'])}</b>\n"
        f"• бычки — <b>{fmt_int(year_tot['sale_bulls'])}</b>\n"
    )
    return text


# ─────────────────────────────────────────────────────────────
# SUBMIT: Производство -> Отчет 1
# callback: prod_report1_submit
# ─────────────────────────────────────────────────────────────
@router.callback_query(F.data == "prod_report1_submit")
async def start_submit(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HerdWizard.active)
    await state.update_data(step_idx=0, answers={})

    await callback.message.answer(
        "✅ Начинаем сдачу отчёта <b>«Движение поголовья»</b>.\n"
        "Бот будет задавать вопросы по одному.",
        parse_mode="HTML"
    )
    await ask_step(callback.message, state)
    await callback.answer()


@router.message(HerdWizard.active)
async def wizard_input(message: types.Message, state: FSMContext):
    txt = (message.text or "").strip()

    if txt.lower() in ("отмена", "cancel", "/cancel", "стоп"):
        await state.clear()
        await message.answer("⛔ Сдача отчёта отменена.")
        return

    data = await state.get_data()
    step_idx = int(data.get("step_idx", 0))
    answers = data.get("answers", {})

    key, _, parser, _ = STEPS[step_idx]

    try:
        value = parser(txt)
    except Exception as e:
        await message.answer(f"❗️Ошибка ввода: {e}\nПовторите ещё раз.")
        await ask_step(message, state)
        return

    answers[key] = value
    step_idx += 1

    # Если закончили — сохраняем и показываем сводку
    if step_idx >= len(STEPS):
        if "report_date" not in answers:
            answers["report_date"] = datetime.now().strftime("%d.%m.%Y")

        report_date_iso = iso_from_ddmmyyyy(str(answers["report_date"]))
        await upsert_report(LOCATION_CODE, report_date_iso, answers, message.from_user.id)

        # Суммы по месяцу/году
        m_from, m_to = month_range_from_iso(report_date_iso)
        y_from, y_to = year_range_from_iso(report_date_iso)

        month_reports = await get_reports_in_range(LOCATION_CODE, m_from, m_to)
        year_reports = await get_reports_in_range(LOCATION_CODE, y_from, y_to)

        sum_keys = [
            "calv_cows", "calv_neteli",
            "calves_heifers_day", "calves_bulls_day",
            "stillborn_day", "abort_day",
            "sale_cows", "sale_neteli", "sale_heifers", "sale_bulls",
        ]

        month_tot = sum_fields(month_reports, sum_keys)
        year_tot = sum_fields(year_reports, sum_keys)

        text = build_report_text(answers, month_tot, year_tot)

        await state.clear()
        await message.answer("✅ <b>Отчёт сохранён.</b>\n\n" + text, parse_mode="HTML")
        return

    await state.update_data(step_idx=step_idx, answers=answers)
    await ask_step(message, state)


# ─────────────────────────────────────────────────────────────
# VIEW: Производство -> Отчет 1
# callback: prod_report1_view
# ─────────────────────────────────────────────────────────────
@router.callback_query(F.data == "prod_report1_view")
async def view_latest(callback: types.CallbackQuery):
    row = await get_latest_report(LOCATION_CODE)
    if not row:
        await callback.message.answer("❗️Отчётов «Движение поголовья» ещё нет.")
        await callback.answer()
        return

    daily = json.loads(row["data_json"])
    report_date_iso = row["report_date"]

    m_from, m_to = month_range_from_iso(report_date_iso)
    y_from, y_to = year_range_from_iso(report_date_iso)

    month_reports = await get_reports_in_range(LOCATION_CODE, m_from, m_to)
    year_reports = await get_reports_in_range(LOCATION_CODE, y_from, y_to)

    sum_keys = [
        "calv_cows", "calv_neteli",
        "calves_heifers_day", "calves_bulls_day",
        "stillborn_day", "abort_day",
        "sale_cows", "sale_neteli", "sale_heifers", "sale_bulls",
    ]

    month_tot = sum_fields(month_reports, sum_keys)
    year_tot = sum_fields(year_reports, sum_keys)

    text = build_report_text(daily, month_tot, year_tot)
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()
