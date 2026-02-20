import json
from datetime import datetime, date
from typing import Any, Dict, Tuple

from aiogram import Router, types, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from db import db
from utils.pdf_herd_movement_reports import (
    build_herd_daily_pdf_bytes,
    build_herd_monthly_pdf_bytes,
    build_herd_yearly_pdf_bytes,
)

router = Router()

LOCATION_CODE = "aktuba"
LOCATION_TITLE = "ЖК «Актюба»"


# ─────────────────────────────────────────────────────────────
# FSM
# ─────────────────────────────────────────────────────────────
class HerdWizard(StatesGroup):
    choose_date = State()
    input = State()

    tr_out_unit = State()
    tr_out_unit_custom = State()
    tr_out_group = State()
    tr_out_count = State()

    tr_in_unit = State()
    tr_in_unit_custom = State()
    tr_in_group = State()
    tr_in_count = State()

    breed_group = State()
    breed_count = State()
    breed_to = State()
    breed_comment = State()


# ─────────────────────────────────────────────────────────────
# справочники
# ─────────────────────────────────────────────────────────────
UNITS = [
    "Чемодурово",
    "Нетельная площадка",
    "Бирючевка",
    "Карамалы",
    "Шереметьево",
    "Другое (ввести)",
]

GROUPS = [
    "Коровы",
    "Нетели",
    "Тёлки 0–3 мес",
    "Тёлки 3–6 мес",
    "Тёлки 6–12 мес",
    "Тёлки 12–18 мес",
    "Тёлки старше 18 мес",
    "Бычки 0–3 мес",
    "Молодняк старше 3 мес",
]


# ─────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────
def fmt_int(x: float | int) -> str:
    return f"{int(round(x)):,}".replace(",", " ")


def fmt_pct(x: float, digits: int = 1) -> str:
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


def ddmmyyyy_from_iso(iso_date: str) -> str:
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d.%m.%Y")


def month_range_from_iso(iso_date: str) -> tuple[str, str]:
    d = datetime.strptime(iso_date, "%Y-%m-%d").date()
    first = d.replace(day=1)
    return first.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d")


def year_range_from_iso(iso_date: str) -> tuple[str, str]:
    d = datetime.strptime(iso_date, "%Y-%m-%d").date()
    first = date(d.year, 1, 1)
    return first.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d")


def _pct(part: float, total: float) -> float:
    return (part / total * 100.0) if total > 0 else 0.0


def _strip(s: Any) -> str:
    return str(s or "").strip()


def kb_yes_no(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Да", callback_data=f"{prefix}:yes"),
        InlineKeyboardButton(text="Нет", callback_data=f"{prefix}:no"),
    ]])

def kb_choose_report_date() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Сдать за сегодня", callback_data="herd_date:today")],
            [InlineKeyboardButton(text="🗓 Исправить дату", callback_data="herd_date:pick")],
        ]
    )




def kb_units(prefix: str) -> InlineKeyboardMarkup:
    rows = []
    for u in UNITS:
        rows.append([InlineKeyboardButton(text=u, callback_data=f"{prefix}:{u}")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data=f"{prefix}:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_groups(prefix: str) -> InlineKeyboardMarkup:
    rows = []
    for g in GROUPS:
        rows.append([InlineKeyboardButton(text=g, callback_data=f"{prefix}:{g}")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data=f"{prefix}:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─────────────────────────────────────────────────────────────
# DB
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


# ─────────────────────────────────────────────────────────────
# Агрегирование "потока" (месяц/год) + переводы/поступления + племпродажа
# ─────────────────────────────────────────────────────────────
FLOW_KEYS = [
    "calv_cows", "calv_neteli",
    "calves_h_cows", "calves_b_cows",
    "calves_h_neteli", "calves_b_neteli",
    "stillborn_day", "abort_day",
    "death_cows", "death_calves_0_3", "death_young_over_3",
    "sale_cows", "sale_neteli", "sale_heifers", "sale_bulls",
]


def aggregate_flow(reports: list[dict]) -> dict:
    tot = {k: 0 for k in FLOW_KEYS}
    out_agg: Dict[Tuple[str, str], int] = {}
    in_agg: Dict[Tuple[str, str], int] = {}
    breed_agg: Dict[Tuple[str, str], int] = {}  # (to, group)

    for r in reports:
        d = r["data"]
        for k in FLOW_KEYS:
            tot[k] += int(d.get(k, 0) or 0)

        for it in (d.get("transfers_out") or []):
            unit = _strip(it.get("unit"))
            group = _strip(it.get("group"))
            cnt = int(it.get("count", 0) or 0)
            out_agg[(unit, group)] = out_agg.get((unit, group), 0) + cnt

        for it in (d.get("transfers_in") or []):
            unit = _strip(it.get("unit"))
            group = _strip(it.get("group"))
            cnt = int(it.get("count", 0) or 0)
            in_agg[(unit, group)] = in_agg.get((unit, group), 0) + cnt

        for it in (d.get("breeding_sales") or []):
            to = _strip(it.get("to"))
            group = _strip(it.get("group"))
            cnt = int(it.get("count", 0) or 0)
            breed_agg[(to, group)] = breed_agg.get((to, group), 0) + cnt

    tot["transfers_out"] = [{"unit": u, "group": g, "count": c} for (u, g), c in out_agg.items()]
    tot["transfers_in"] = [{"unit": u, "group": g, "count": c} for (u, g), c in in_agg.items()]
    tot["breeding_sales"] = [{"to": to, "group": g, "count": c} for (to, g), c in breed_agg.items()]
    return tot


# ─────────────────────────────────────────────────────────────
# ШАГИ (полная "Сводка по стаду")
# ВАЖНО: total_cattle оставили как вводимый, но в отчёте используем КАЛЬКУЛЯЦИЮ:
# Всего КРС = фуражные + весь молодняк (вкл. нетели)
# ─────────────────────────────────────────────────────────────
STEPS = [
    ("report_date", "Введите дату отчёта <b>ДД.ММ.ГГГГ</b> (или <b>0</b> = сегодня):", parse_date_ddmmyyyy, "пример: 23.01.2026"),

    # Поголовье (факт на утро)
    ("total_cattle", "Всего КРС (гол):", parse_number, "пример: 6847"),
    ("forage_cows", "Фуражные коровы (гол):", parse_number, "пример: 3422"),
    ("milking_cows", "Дойные коровы (гол):", parse_number, "пример: 3056"),
    ("ro_cows", "в т.ч. в РО (гол):", parse_number, "пример: 400"),
    ("dry_cows", "Сухостой (гол):", parse_number, "пример: 230"),
    ("pregnant_cows", "Стельные коровы (гол):", parse_number, "пример: 2600"),

    # Молодняк
    ("heifers_0_3", "Тёлки 0–3 мес (гол):", parse_number, "пример: 370"),
    ("heifers_3_6", "Тёлки 3–6 мес (гол):", parse_number, "пример: 780"),
    ("heifers_6_12", "Тёлки 6–12 мес (гол):", parse_number, "пример: 900"),
    ("heifers_12_18", "Тёлки 12–18 мес (гол):", parse_number, "пример: 220"),
    ("heifers_18_plus", "Тёлки старше 18 мес (гол):", parse_number, "пример: 50"),
    ("neteli_total", "Нетели (гол):", parse_number, "пример: 1015"),
    ("bulls_0_3", "Бычки 0–3 мес (гол):", parse_number, "пример: 90"),

    # Состояние стада
    ("hospital", "Госпиталь (гол):", parse_number, "пример: 42"),
    ("mastitis", "Мастит (гол):", parse_number, "пример: 50"),
    ("cull", "Брак (на выбытие) (гол):", parse_number, "пример: 10"),

    # Поголовье по подразделениям
    ("sub_chemo_neteli", "Чемодурово — Нетели (гол):", parse_number, "пример: 150"),
    ("sub_chemo_h_0_3", "Чемодурово — Тёлки 0–3 мес (гол):", parse_number, "пример: 0"),
    ("sub_chemo_h_3_6", "Чемодурово — Тёлки 3–6 мес (гол):", parse_number, "пример: 0"),
    ("sub_chemo_h_6_12", "Чемодурово — Тёлки 6–12 мес (гол):", parse_number, "пример: 150"),
    ("sub_chemo_h_gt_12", "Чемодурово — Тёлки старше 12 мес (гол):", parse_number, "пример: 25"),
    ("sub_chemo_b_0_3", "Чемодурово — Бычки 0–3 мес (гол):", parse_number, "пример: 114"),

    ("sub_site_neteli", "Нетельная площадка — Нетели (гол):", parse_number, "пример: 170"),
    ("sub_site_h_6_12", "Нетельная площадка — Тёлки 6–12 мес (гол):", parse_number, "пример: 0"),
    ("sub_site_h_gt_12", "Нетельная площадка — Тёлки старше 12 мес (гол):", parse_number, "пример: 0"),

    # Движение (сутки)
    ("launch", "Запуск за сутки (гол):", parse_number, "пример: 43"),

    ("calv_cows", "Отёлы за день — <b>коровы</b> (гол):", parse_number, "пример: 15"),
    ("calv_neteli", "Отёлы за день — <b>нетели</b> (гол):", parse_number, "пример: 16"),

    ("calves_h_cows", "Приплод — <b>тёлки от коров</b> (гол):", parse_number, "пример: 0"),
    ("calves_b_cows", "Приплод — <b>бычки от коров</b> (гол):", parse_number, "пример: 0"),
    ("calves_h_neteli", "Приплод — <b>тёлки от нетелей</b> (гол):", parse_number, "пример: 24"),
    ("calves_b_neteli", "Приплод — <b>бычки от нетелей</b> (гол):", parse_number, "пример: 7"),

    ("stillborn_day", "Мертворождённые за день (гол):", parse_number, "пример: 2"),
    ("abort_day", "Аборт за день (гол):", parse_number, "пример: 0"),

    # Падёж
    ("death_cows", "Падёж за сутки — коровы (гол):", parse_number, "пример: 0"),
    ("death_calves_0_3", "Падёж за сутки — телята 0–3 мес (гол):", parse_number, "пример: 1"),
    ("death_young_over_3", "Падёж за сутки — молодняк старше 3 мес (гол):", parse_number, "пример: 0"),

    # Реализация
    ("sale_cows", "Реализация за сутки — коровы (гол):", parse_number, "пример: 0"),
    ("sale_neteli", "Реализация за сутки — нетели (гол):", parse_number, "пример: 0"),
    ("sale_heifers", "Реализация за сутки — тёлки (гол):", parse_number, "пример: 3"),
    ("sale_bulls", "Реализация за сутки — бычки (гол):", parse_number, "пример: 0"),
]


async def ask_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    step_idx = int(data.get("step_idx", 0))
    _, q, _, hint = STEPS[step_idx]

    await message.answer(
        f"📋 <b>Отчёт: Сводка по стаду — {LOCATION_TITLE}</b>\n"
        f"Шаг <b>{step_idx + 1}</b> из <b>{len(STEPS)}</b>\n\n"
        f"{q}\n<i>{hint}</i>\n\n"
        f"Для отмены: <b>отмена</b>",
        parse_mode="HTML"
    )


def _sum_list(lst: list[dict], key: str = "count") -> int:
    return sum(int(x.get(key, 0) or 0) for x in (lst or []) if isinstance(x, dict))


def _render_tr_out(items: list[dict]) -> str:
    if not items:
        return "• нет"
    lines = []
    for it in items:
        unit = _strip(it.get("unit"))
        group = _strip(it.get("group"))
        cnt = int(it.get("count", 0) or 0)
        lines.append(f"• {group} — {fmt_int(cnt)} — из {LOCATION_TITLE} в {unit}")
    return "\n".join(lines)


def _render_tr_in(items: list[dict]) -> str:
    if not items:
        return "• нет"
    lines = []
    for it in items:
        unit = _strip(it.get("unit"))
        group = _strip(it.get("group"))
        cnt = int(it.get("count", 0) or 0)
        lines.append(f"• {group} — {fmt_int(cnt)} — из {unit} в {LOCATION_TITLE}")
    return "\n".join(lines)


def _render_breeding(items: list[dict]) -> str:
    if not items:
        return "• нет"
    lines = []
    for it in items:
        group = _strip(it.get("group"))
        to = _strip(it.get("to"))
        cnt = int(it.get("count", 0) or 0)
        cmt = _strip(it.get("comment"))
        s = f"• {group} — {fmt_int(cnt)} — {to}"
        if cmt:
            s += f" ({cmt})"
        lines.append(s)
    return "\n".join(lines)


def build_text_report(daily: dict, month_flow: dict, year_flow: dict) -> str:
    date_str = daily.get("report_date", datetime.now().strftime("%d.%m.%Y"))

    # Поголовье — считаем правильно
    entered_total = int(daily.get("total_cattle", 0) or 0)
    forage = int(daily.get("forage_cows", 0) or 0)
    milking = int(daily.get("milking_cows", 0) or 0)
    ro = int(daily.get("ro_cows", 0) or 0)
    dry = int(daily.get("dry_cows", 0) or 0)
    pregnant = int(daily.get("pregnant_cows", 0) or 0)
    preg_pct = _pct(pregnant, forage)

    # Молодняк
    h_0_3 = int(daily.get("heifers_0_3", 0) or 0)
    h_3_6 = int(daily.get("heifers_3_6", 0) or 0)
    h_6_12 = int(daily.get("heifers_6_12", 0) or 0)
    h_12_18 = int(daily.get("heifers_12_18", 0) or 0)
    h_18p = int(daily.get("heifers_18_plus", 0) or 0)
    neteli = int(daily.get("neteli_total", 0) or 0)
    b_0_3 = int(daily.get("bulls_0_3", 0) or 0)

    young_total = h_0_3 + h_3_6 + h_6_12 + h_12_18 + h_18p + neteli + b_0_3
    total_cattle_calc = forage + young_total  # ✅ основная формула

    # Состояние стада
    hospital = int(daily.get("hospital", 0) or 0)
    mastitis = int(daily.get("mastitis", 0) or 0)
    cull = int(daily.get("cull", 0) or 0)

    # Подразделения (итого молодняк)
    sub_chemo_neteli = int(daily.get("sub_chemo_neteli", 0) or 0)
    sub_chemo_h_0_3 = int(daily.get("sub_chemo_h_0_3", 0) or 0)
    sub_chemo_h_3_6 = int(daily.get("sub_chemo_h_3_6", 0) or 0)
    sub_chemo_h_6_12 = int(daily.get("sub_chemo_h_6_12", 0) or 0)
    sub_chemo_h_gt_12 = int(daily.get("sub_chemo_h_gt_12", 0) or 0)
    sub_chemo_b_0_3 = int(daily.get("sub_chemo_b_0_3", 0) or 0)
    chemo_total = sub_chemo_neteli + sub_chemo_h_0_3 + sub_chemo_h_3_6 + sub_chemo_h_6_12 + sub_chemo_h_gt_12 + sub_chemo_b_0_3

    sub_site_neteli = int(daily.get("sub_site_neteli", 0) or 0)
    sub_site_h_6_12 = int(daily.get("sub_site_h_6_12", 0) or 0)
    sub_site_h_gt_12 = int(daily.get("sub_site_h_gt_12", 0) or 0)
    site_total = sub_site_neteli + sub_site_h_6_12 + sub_site_h_gt_12

    # Движение (сутки)
    launch = int(daily.get("launch", 0) or 0)

    calv_cows = int(daily.get("calv_cows", 0) or 0)
    calv_net = int(daily.get("calv_neteli", 0) or 0)
    calv_total = calv_cows + calv_net

    h_cows = int(daily.get("calves_h_cows", 0) or 0)
    b_cows = int(daily.get("calves_b_cows", 0) or 0)
    h_net = int(daily.get("calves_h_neteli", 0) or 0)
    b_net = int(daily.get("calves_b_neteli", 0) or 0)

    heifers_day = h_cows + h_net
    bulls_day = b_cows + b_net

    stillborn = int(daily.get("stillborn_day", 0) or 0)
    aborts = int(daily.get("abort_day", 0) or 0)

    calves_live_day = heifers_day + bulls_day
    calves_all_day = calves_live_day + stillborn  # ✅ требование: тёлки+бычки+мертворожд.
    still_pct_day = _pct(stillborn, calv_total)

    # Месяц/год — % мертвородов
    calv_m = int(month_flow.get("calv_cows", 0) or 0) + int(month_flow.get("calv_neteli", 0) or 0)
    heifers_m = int(month_flow.get("calves_h_cows", 0) or 0) + int(month_flow.get("calves_h_neteli", 0) or 0)
    bulls_m = int(month_flow.get("calves_b_cows", 0) or 0) + int(month_flow.get("calves_b_neteli", 0) or 0)
    still_m = int(month_flow.get("stillborn_day", 0) or 0)
    abort_m = int(month_flow.get("abort_day", 0) or 0)
    out_heifers_m = _pct(heifers_m, heifers_m + bulls_m)
    still_pct_m = _pct(still_m, calv_m)

    calv_y = int(year_flow.get("calv_cows", 0) or 0) + int(year_flow.get("calv_neteli", 0) or 0)
    heifers_y = int(year_flow.get("calves_h_cows", 0) or 0) + int(year_flow.get("calves_h_neteli", 0) or 0)
    bulls_y = int(year_flow.get("calves_b_cows", 0) or 0) + int(year_flow.get("calves_b_neteli", 0) or 0)
    still_y = int(year_flow.get("stillborn_day", 0) or 0)
    abort_y = int(year_flow.get("abort_day", 0) or 0)
    out_heifers_y = _pct(heifers_y, heifers_y + bulls_y)
    still_pct_y = _pct(still_y, calv_y)

    # Падёж
    death_cows = int(daily.get("death_cows", 0) or 0)
    death_0_3 = int(daily.get("death_calves_0_3", 0) or 0)
    death_gt3 = int(daily.get("death_young_over_3", 0) or 0)

    death_cows_m = int(month_flow.get("death_cows", 0) or 0)
    death_0_3_m = int(month_flow.get("death_calves_0_3", 0) or 0)
    death_gt3_m = int(month_flow.get("death_young_over_3", 0) or 0)

    # Реализация
    sale_cows = int(daily.get("sale_cows", 0) or 0)
    sale_neteli = int(daily.get("sale_neteli", 0) or 0)
    sale_heifers = int(daily.get("sale_heifers", 0) or 0)
    sale_bulls = int(daily.get("sale_bulls", 0) or 0)
    sale_day = sale_cows + sale_neteli + sale_heifers + sale_bulls

    sale_cows_m = int(month_flow.get("sale_cows", 0) or 0)
    sale_neteli_m = int(month_flow.get("sale_neteli", 0) or 0)
    sale_heifers_m = int(month_flow.get("sale_heifers", 0) or 0)
    sale_bulls_m = int(month_flow.get("sale_bulls", 0) or 0)
    sale_m = sale_cows_m + sale_neteli_m + sale_heifers_m + sale_bulls_m

    sale_cows_y = int(year_flow.get("sale_cows", 0) or 0)
    sale_neteli_y = int(year_flow.get("sale_neteli", 0) or 0)
    sale_heifers_y = int(year_flow.get("sale_heifers", 0) or 0)
    sale_bulls_y = int(year_flow.get("sale_bulls", 0) or 0)
    sale_y = sale_cows_y + sale_neteli_y + sale_heifers_y + sale_bulls_y

    transfers_out = daily.get("transfers_out") or []
    transfers_in = daily.get("transfers_in") or []
    breeding_sales = daily.get("breeding_sales") or []

    bs_day = _sum_list(breeding_sales, "count")
    bs_m = _sum_list(month_flow.get("breeding_sales") or [], "count")
    bs_y = _sum_list(year_flow.get("breeding_sales") or [], "count")

    # Контроль несоответствий
    warns = []
    if milking > forage:
        warns.append("Дойные коровы больше фуражных.")
    if ro > milking:
        warns.append("РО больше дойных коров.")
    if pregnant > forage:
        warns.append("Стельные коровы больше фуражных.")
    # ✅ теперь сравниваем: (тёлки+бычки+мертворожд.) vs отёлы
    if calves_all_day != calv_total:
        warns.append(f"Несоответствие: приплод (тёлки+бычки+мертворождённые={calves_all_day}) ≠ отёлы (коровы+нетели={calv_total}).")
    # контроль "ввели всего КРС" vs расчёт
    if entered_total and entered_total != total_cattle_calc:
        warns.append(f"Всего КРС введено {entered_total}, по формуле (фуражные + молодняк) = {total_cattle_calc}.")

    warn_block = ""
    if warns:
        warn_block = "\n\n⚠️ Проверка несоответствий:\n" + "\n".join([f"• {w}" for w in warns])

    text = (
        f"📋 <b>Сводка по стаду — {LOCATION_TITLE}</b>\n"
        f"за <b>{date_str}</b>\n\n"

        f"🐄 <b>Поголовье (факт на утро)</b>\n\n"
        f"• Всего КРС — <b>{fmt_int(total_cattle_calc)}</b> гол\n"
        f"• Фуражные коровы — <b>{fmt_int(forage)}</b>\n"
        f"• Дойные коровы — <b>{fmt_int(milking)}</b>\n"
        f"  в т.ч. в РО — <b>{fmt_int(ro)}</b> гол\n"
        f"• Сухостой — <b>{fmt_int(dry)}</b>\n"
        f"• Стельные коровы — <b>{fmt_int(pregnant)}</b>\n"
        f"• Стельность — <b>{fmt_pct(preg_pct, 1)}</b> % (к фуражным)\n\n"

        f"<b>Молодняк</b>\n"
        f"• Тёлки 0–3 мес — <b>{fmt_int(h_0_3)}</b>\n"
        f"• Тёлки 3–6 мес — <b>{fmt_int(h_3_6)}</b>\n"
        f"• Тёлки 6–12 мес — <b>{fmt_int(h_6_12)}</b>\n"
        f"• Тёлки 12–18 мес — <b>{fmt_int(h_12_18)}</b>\n"
        f"• Тёлки старше 18 мес — <b>{fmt_int(h_18p)}</b>\n"
        f"• Нетели — <b>{fmt_int(neteli)}</b>\n"
        f"• Бычки 0–3 мес — <b>{fmt_int(b_0_3)}</b>\n"
        f"• Итого молодняк (вкл. нетели) — <b>{fmt_int(young_total)}</b>\n\n"

        f"<b>Состояние стада</b>\n"
        f"• Госпиталь — <b>{fmt_int(hospital)}</b> гол\n"
        f"• Мастит — <b>{fmt_int(mastitis)}</b> гол\n"
        f"• Брак (на выбытие) — <b>{fmt_int(cull)}</b> гол\n\n"

        f"🏠 <b>Поголовье по подразделениям</b>\n\n"
        f"<b>Чемодурово</b>\n"
        f"• Нетели — <b>{fmt_int(sub_chemo_neteli)}</b>\n"
        f"• Тёлки 0–3 мес — <b>{fmt_int(sub_chemo_h_0_3)}</b>\n"
        f"• Тёлки 3–6 мес — <b>{fmt_int(sub_chemo_h_3_6)}</b>\n"
        f"• Тёлки 6–12 мес — <b>{fmt_int(sub_chemo_h_6_12)}</b>\n"
        f"• Тёлки старше 12 мес — <b>{fmt_int(sub_chemo_h_gt_12)}</b>\n"
        f"• Бычки 0–3 мес — <b>{fmt_int(sub_chemo_b_0_3)}</b>\n"
        f"• Итого молодняк Чемодурово — <b>{fmt_int(chemo_total)}</b>\n\n"

        f"<b>Нетельная площадка</b>\n"
        f"• Нетели — <b>{fmt_int(sub_site_neteli)}</b>\n"
        f"• Тёлки 6–12 мес — <b>{fmt_int(sub_site_h_6_12)}</b>\n"
        f"• Тёлки старше 12 мес — <b>{fmt_int(sub_site_h_gt_12)}</b>\n"
        f"• Итого молодняк НП — <b>{fmt_int(site_total)}</b>\n\n"

        f"🔄 <b>Движение стада за сутки</b>\n\n"
        f"Запуск — <b>{fmt_int(launch)}</b> гол\n\n"
        f"Отёлы за день — <b>{fmt_int(calv_total)}</b> гол, в том числе:\n"
        f"• коровы — <b>{fmt_int(calv_cows)}</b>\n"
        f"• нетели — <b>{fmt_int(calv_net)}</b>\n"
        f"• мертворождённые — <b>{fmt_int(stillborn)}</b> ({fmt_pct(still_pct_day, 1)} % к отёлу)\n"
        f"• аборт — <b>{fmt_int(aborts)}</b>\n\n"
        f"Получена приплода за сутки:\n"
        f"• тёлки — <b>{fmt_int(heifers_day)}</b>\n"
        f"• бычки — <b>{fmt_int(bulls_day)}</b>\n"
        f"• всего (тёлки+бычки+мертворожд.) — <b>{fmt_int(calves_all_day)}</b>\n\n"

        f"📅 <b>Отёлы</b>\n\n"
        f"За месяц — <b>{fmt_int(calv_m)}</b> гол, в т.ч.:\n"
        f"• коровы — <b>{fmt_int(int(month_flow.get('calv_cows', 0) or 0))}</b>\n"
        f"• нетели — <b>{fmt_int(int(month_flow.get('calv_neteli', 0) or 0))}</b>\n"
        f"• тёлки — <b>{fmt_int(heifers_m)}</b>\n"
        f"• бычки — <b>{fmt_int(bulls_m)}</b>\n"
        f"• мертворождённые — <b>{fmt_int(still_m)}</b> ({fmt_pct(still_pct_m, 1)} % к отёлу)\n"
        f"• аборты — <b>{fmt_int(abort_m)}</b>\n"
        f"Выход тёлок (за месяц) — <b>{fmt_pct(out_heifers_m, 1)}</b> %\n\n"

        f"С начала года — <b>{fmt_int(calv_y)}</b> гол, в т.ч.:\n"
        f"• коровы — <b>{fmt_int(int(year_flow.get('calv_cows', 0) or 0))}</b>\n"
        f"• нетели — <b>{fmt_int(int(year_flow.get('calv_neteli', 0) or 0))}</b>\n"
        f"• тёлки — <b>{fmt_int(heifers_y)}</b>\n"
        f"• бычки — <b>{fmt_int(bulls_y)}</b>\n"
        f"• мертворождённые — <b>{fmt_int(still_y)}</b> ({fmt_pct(still_pct_y, 1)} % к отёлу)\n"
        f"• аборты — <b>{fmt_int(abort_y)}</b>\n"
        f"Выход тёлок (с начала года) — <b>{fmt_pct(out_heifers_y, 1)}</b> %\n\n"

        f"Переводы (за сутки):\n{_render_tr_out(transfers_out)}\n\n"
        f"Поступления (за сутки):\n{_render_tr_in(transfers_in)}\n\n"

        f"⚠️ <b>Падёж</b>\n\n"
        f"За сутки:\n"
        f"• коровы — <b>{fmt_int(death_cows)}</b> гол\n"
        f"• телята 0–3 мес — <b>{fmt_int(death_0_3)}</b> гол\n"
        f"• молодняк старше 3 мес — <b>{fmt_int(death_gt3)}</b> гол\n\n"
        f"За месяц:\n"
        f"• коровы — <b>{fmt_int(death_cows_m)}</b> гол\n"
        f"• телята 0–3 мес — <b>{fmt_int(death_0_3_m)}</b> гол\n"
        f"• молодняк старше 3 мес — <b>{fmt_int(death_gt3_m)}</b> гол\n\n"

        f"🚚 <b>Реализация КРС</b>\n\n"
        f"За сутки — <b>{fmt_int(sale_day)}</b> гол, в т.ч.:\n"
        f"• коровы — <b>{fmt_int(sale_cows)}</b>\n"
        f"• нетели — <b>{fmt_int(sale_neteli)}</b>\n"
        f"• тёлки — <b>{fmt_int(sale_heifers)}</b>\n"
        f"• бычки — <b>{fmt_int(sale_bulls)}</b>\n\n"
        f"За месяц — <b>{fmt_int(sale_m)}</b> гол, в т.ч.:\n"
        f"• коровы — <b>{fmt_int(sale_cows_m)}</b>\n"
        f"• нетели — <b>{fmt_int(sale_neteli_m)}</b>\n"
        f"• тёлки — <b>{fmt_int(sale_heifers_m)}</b>\n"
        f"• бычки — <b>{fmt_int(sale_bulls_m)}</b>\n\n"
        f"С начала года — <b>{fmt_int(sale_y)}</b> гол, в т.ч.:\n"
        f"• коровы — <b>{fmt_int(sale_cows_y)}</b>\n"
        f"• нетели — <b>{fmt_int(sale_neteli_y)}</b>\n"
        f"• тёлки — <b>{fmt_int(sale_heifers_y)}</b>\n"
        f"• бычки — <b>{fmt_int(sale_bulls_y)}</b>\n\n"

        f"🧬 <b>Племпродажа</b>\n"
        f"• За сутки — <b>{fmt_int(bs_day)}</b> гол\n"
        f"{_render_breeding(breeding_sales)}\n\n"
        f"• За месяц — <b>{fmt_int(bs_m)}</b> гол\n"
        f"• За год — <b>{fmt_int(bs_y)}</b> гол"
        f"{warn_block}"
    )
    return text


# ─────────────────────────────────────────────────────────────
# SUBMIT / VIEW
# ─────────────────────────────────────────────────────────────
@router.callback_query(F.data == "prod_report1_submit")
async def start_submit(callback: types.CallbackQuery, state: FSMContext):
    # Сначала предлагаем выбрать: сдаём за сегодня или вводим дату (исправляем/вносим задним числом)
    await state.clear()
    await state.set_state(HerdWizard.choose_date)

    await callback.message.answer(
        "🧾 <b>Движение поголовья</b>\n\n"
        "Выберите вариант сдачи отчёта:",
        parse_mode="HTML",
        reply_markup=kb_choose_report_date(),
    )
    await callback.answer()


@router.callback_query(F.data == "herd_date:today")
async def herd_date_today(callback: types.CallbackQuery, state: FSMContext):
    today_ddmmyyyy = datetime.now().strftime("%d.%m.%Y")

    await state.set_state(HerdWizard.input)
    await state.update_data(
        step_idx=1,  # пропускаем шаг ввода даты
        answers={"report_date": today_ddmmyyyy},
        transfers_out=[],
        transfers_in=[],
        breeding_sales=[],
    )

    await callback.message.answer(
        "✅ Сдаём отчёт <b>за сегодня</b>.\n"
        "Бот задаёт вопросы по одному.",
        parse_mode="HTML",
    )
    await ask_step(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "herd_date:pick")
async def herd_date_pick(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HerdWizard.input)
    await state.update_data(step_idx=0, answers={}, transfers_out=[], transfers_in=[], breeding_sales=[])

    await callback.message.answer(
        "🗓 Введите дату отчёта в формате <b>ДД.ММ.ГГГГ</b> (например: <b>15.02.2026</b>).",
        parse_mode="HTML",
    )
    await ask_step(callback.message, state)
    await callback.answer()



@router.message(HerdWizard.input)
async def wizard_input(message: types.Message, state: FSMContext):
    txt = (message.text or "").strip()

    if txt.lower() in ("отмена", "cancel", "/cancel", "стоп"):
        await state.clear()
        await message.answer("⛔ Сдача отчёта отменена.")
        return

    data = await state.get_data()
    step_idx = int(data.get("step_idx", 0))
    answers = data.get("answers", {}) or {}

    key, _, parser, _ = STEPS[step_idx]

    try:
        value = parser(txt)
    except Exception as e:
        await message.answer(f"❗️Ошибка ввода: {e}\nПовторите ещё раз.")
        await ask_step(message, state)
        return

    answers[key] = value
    step_idx += 1

    if step_idx >= len(STEPS):
        if "report_date" not in answers:
            answers["report_date"] = datetime.now().strftime("%d.%m.%Y")

        await state.update_data(step_idx=step_idx, answers=answers)
        await message.answer("🔄 Были <b>переводы</b> из ЖК в другие подразделения?", parse_mode="HTML", reply_markup=kb_yes_no("tr_out"))
        return

    await state.update_data(step_idx=step_idx, answers=answers)
    await ask_step(message, state)


# ─────────────────────────────────────────────────────────────
# Переводы OUT
# ─────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("tr_out:"))
async def tr_out_yesno(callback: types.CallbackQuery, state: FSMContext):
    ans = callback.data.split(":", 1)[1]
    if ans == "no":
        await callback.message.answer("📥 Были <b>поступления</b> в ЖК из подразделений/источников?", parse_mode="HTML", reply_markup=kb_yes_no("tr_in"))
        await callback.answer()
        return

    await state.set_state(HerdWizard.tr_out_unit)
    await callback.message.answer("Куда перевели? Выберите подразделение:", reply_markup=kb_units("tr_out_unit"))
    await callback.answer()


@router.callback_query(HerdWizard.tr_out_unit, F.data.startswith("tr_out_unit:"))
async def tr_out_pick_unit(callback: types.CallbackQuery, state: FSMContext):
    unit = callback.data.split(":", 1)[1]
    if unit == "cancel":
        await callback.message.answer("📥 Были <b>поступления</b> в ЖК из подразделений/источников?", parse_mode="HTML", reply_markup=kb_yes_no("tr_in"))
        await callback.answer()
        return

    if unit == "Другое (ввести)":
        await state.set_state(HerdWizard.tr_out_unit_custom)
        await callback.message.answer("Введите название подразделения/куда перевели (текст):")
        await callback.answer()
        return

    await state.update_data(tr_out_unit=unit)
    await state.set_state(HerdWizard.tr_out_group)
    await callback.message.answer("Выберите половозрастную группу:", reply_markup=kb_groups("tr_out_group"))
    await callback.answer()


@router.message(HerdWizard.tr_out_unit_custom)
async def tr_out_unit_custom_input(message: types.Message, state: FSMContext):
    unit = (message.text or "").strip()
    if not unit:
        await message.answer("Введите название (не пустое).")
        return
    await state.update_data(tr_out_unit=unit)
    await state.set_state(HerdWizard.tr_out_group)
    await message.answer("Выберите половозрастную группу:", reply_markup=kb_groups("tr_out_group"))


@router.callback_query(HerdWizard.tr_out_group, F.data.startswith("tr_out_group:"))
async def tr_out_pick_group(callback: types.CallbackQuery, state: FSMContext):
    group = callback.data.split(":", 1)[1]
    if group == "cancel":
        await state.set_state(HerdWizard.tr_out_unit)
        await callback.message.answer("Куда перевели? Выберите подразделение:", reply_markup=kb_units("tr_out_unit"))
        await callback.answer()
        return

    await state.update_data(tr_out_group=group)
    await state.set_state(HerdWizard.tr_out_count)
    await callback.message.answer("Введите количество (гол):")
    await callback.answer()


@router.message(HerdWizard.tr_out_count)
async def tr_out_count_input(message: types.Message, state: FSMContext):
    try:
        cnt = parse_number((message.text or "").strip())
    except Exception as e:
        await message.answer(f"❗️Ошибка: {e}\nВведите количество (гол) ещё раз.")
        return

    data = await state.get_data()
    unit = data.get("tr_out_unit")
    group = data.get("tr_out_group")
    transfers_out = data.get("transfers_out", []) or []

    transfers_out.append({"unit": unit, "group": group, "count": cnt})
    await state.update_data(transfers_out=transfers_out)

    await state.set_state(HerdWizard.tr_out_unit)
    await message.answer("Еще переводы были?", reply_markup=kb_yes_no("tr_out_more"))


@router.callback_query(F.data.startswith("tr_out_more:"))
async def tr_out_more(callback: types.CallbackQuery, state: FSMContext):
    ans = callback.data.split(":", 1)[1]
    if ans == "yes":
        await state.set_state(HerdWizard.tr_out_unit)
        await callback.message.answer("Куда перевели? Выберите подразделение:", reply_markup=kb_units("tr_out_unit"))
        await callback.answer()
        return

    await callback.message.answer("📥 Были <b>поступления</b> в ЖК из подразделений/источников?", parse_mode="HTML", reply_markup=kb_yes_no("tr_in"))
    await callback.answer()


# ─────────────────────────────────────────────────────────────
# Поступления IN
# ─────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("tr_in:"))
async def tr_in_yesno(callback: types.CallbackQuery, state: FSMContext):
    ans = callback.data.split(":", 1)[1]
    if ans == "no":
        await callback.message.answer("🐄 Была <b>племпродажа</b> за сутки?", parse_mode="HTML", reply_markup=kb_yes_no("breed"))
        await callback.answer()
        return

    await state.set_state(HerdWizard.tr_in_unit)
    await callback.message.answer("Откуда поступили? Выберите подразделение/источник:", reply_markup=kb_units("tr_in_unit"))
    await callback.answer()


@router.callback_query(HerdWizard.tr_in_unit, F.data.startswith("tr_in_unit:"))
async def tr_in_pick_unit(callback: types.CallbackQuery, state: FSMContext):
    unit = callback.data.split(":", 1)[1]
    if unit == "cancel":
        await callback.message.answer("🐄 Была <b>племпродажа</b> за сутки?", parse_mode="HTML", reply_markup=kb_yes_no("breed"))
        await callback.answer()
        return

    if unit == "Другое (ввести)":
        await state.set_state(HerdWizard.tr_in_unit_custom)
        await callback.message.answer("Введите источник поступления (текст):")
        await callback.answer()
        return

    await state.update_data(tr_in_unit=unit)
    await state.set_state(HerdWizard.tr_in_group)
    await callback.message.answer("Выберите половозрастную группу:", reply_markup=kb_groups("tr_in_group"))
    await callback.answer()


@router.message(HerdWizard.tr_in_unit_custom)
async def tr_in_unit_custom_input(message: types.Message, state: FSMContext):
    unit = (message.text or "").strip()
    if not unit:
        await message.answer("Введите источник (не пусто).")
        return
    await state.update_data(tr_in_unit=unit)
    await state.set_state(HerdWizard.tr_in_group)
    await message.answer("Выберите половозрастную группу:", reply_markup=kb_groups("tr_in_group"))


@router.callback_query(HerdWizard.tr_in_group, F.data.startswith("tr_in_group:"))
async def tr_in_pick_group(callback: types.CallbackQuery, state: FSMContext):
    group = callback.data.split(":", 1)[1]
    if group == "cancel":
        await state.set_state(HerdWizard.tr_in_unit)
        await callback.message.answer("Откуда поступили? Выберите подразделение/источник:", reply_markup=kb_units("tr_in_unit"))
        await callback.answer()
        return

    await state.update_data(tr_in_group=group)
    await state.set_state(HerdWizard.tr_in_count)
    await callback.message.answer("Введите количество (гол):")
    await callback.answer()


@router.message(HerdWizard.tr_in_count)
async def tr_in_count_input(message: types.Message, state: FSMContext):
    try:
        cnt = parse_number((message.text or "").strip())
    except Exception as e:
        await message.answer(f"❗️Ошибка: {e}\nВведите количество (гол) ещё раз.")
        return

    data = await state.get_data()
    unit = data.get("tr_in_unit")
    group = data.get("tr_in_group")
    transfers_in = data.get("transfers_in", []) or []

    transfers_in.append({"unit": unit, "group": group, "count": cnt})
    await state.update_data(transfers_in=transfers_in)

    await state.set_state(HerdWizard.tr_in_unit)
    await message.answer("Еще поступления были?", reply_markup=kb_yes_no("tr_in_more"))


@router.callback_query(F.data.startswith("tr_in_more:"))
async def tr_in_more(callback: types.CallbackQuery, state: FSMContext):
    ans = callback.data.split(":", 1)[1]
    if ans == "yes":
        await state.set_state(HerdWizard.tr_in_unit)
        await callback.message.answer("Откуда поступили? Выберите подразделение/источник:", reply_markup=kb_units("tr_in_unit"))
        await callback.answer()
        return

    await callback.message.answer("🐄 Была <b>племпродажа</b> за сутки?", parse_mode="HTML", reply_markup=kb_yes_no("breed"))
    await callback.answer()


# ─────────────────────────────────────────────────────────────
# Племпродажа
# ─────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("breed:"))
async def breed_yesno(callback: types.CallbackQuery, state: FSMContext):
    ans = callback.data.split(":", 1)[1]
    if ans == "no":
        await finalize_and_send(callback.message, state, callback.from_user.id)
        await callback.answer()
        return

    await state.set_state(HerdWizard.breed_group)
    await callback.message.answer("Племпродажа — выберите половозрастную группу:", reply_markup=kb_groups("breed_group"))
    await callback.answer()


@router.callback_query(HerdWizard.breed_group, F.data.startswith("breed_group:"))
async def breed_pick_group(callback: types.CallbackQuery, state: FSMContext):
    group = callback.data.split(":", 1)[1]
    if group == "cancel":
        await finalize_and_send(callback.message, state, callback.from_user.id)
        await callback.answer()
        return

    await state.update_data(breed_group=group)
    await state.set_state(HerdWizard.breed_count)
    await callback.message.answer("Введите количество племпродажи (гол):")
    await callback.answer()


@router.message(HerdWizard.breed_count)
async def breed_count_input(message: types.Message, state: FSMContext):
    try:
        cnt = parse_number((message.text or "").strip())
    except Exception as e:
        await message.answer(f"❗️Ошибка: {e}\nВведите количество ещё раз.")
        return

    await state.update_data(breed_count=cnt)
    await state.set_state(HerdWizard.breed_to)
    await message.answer("Кому/куда (контрагент/район/хозяйство):")


@router.message(HerdWizard.breed_to)
async def breed_to_input(message: types.Message, state: FSMContext):
    to_txt = (message.text or "").strip()
    if not to_txt:
        await message.answer("Введите кому/куда (не пусто).")
        return
    await state.update_data(breed_to=to_txt)
    await state.set_state(HerdWizard.breed_comment)
    await message.answer("Комментарий (можно '-' если не нужно):")


@router.message(HerdWizard.breed_comment)
async def breed_comment_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    comment = (message.text or "").strip()
    if comment in ("-", "—"):
        comment = ""

    breeding_sales = data.get("breeding_sales", []) or []
    breeding_sales.append({
        "group": data.get("breed_group"),
        "count": int(data.get("breed_count", 0) or 0),
        "to": data.get("breed_to"),
        "comment": comment,
    })
    await state.update_data(breeding_sales=breeding_sales)

    await state.set_state(HerdWizard.breed_group)
    await message.answer("Еще племпродажа была?", reply_markup=kb_yes_no("breed_more"))


@router.callback_query(F.data.startswith("breed_more:"))
async def breed_more(callback: types.CallbackQuery, state: FSMContext):
    ans = callback.data.split(":", 1)[1]
    if ans == "yes":
        await state.set_state(HerdWizard.breed_group)
        await callback.message.answer("Племпродажа — выберите половозрастную группу:", reply_markup=kb_groups("breed_group"))
        await callback.answer()
        return

    await finalize_and_send(callback.message, state, callback.from_user.id)
    await callback.answer()


# ─────────────────────────────────────────────────────────────
# Финал: сохранить и отправить текст + PDF
# ─────────────────────────────────────────────────────────────
async def finalize_and_send(message: types.Message, state: FSMContext, user_id: int):
    data = await state.get_data()
    answers = data.get("answers", {}) or {}
    transfers_out = data.get("transfers_out", []) or []
    transfers_in = data.get("transfers_in", []) or []
    breeding_sales = data.get("breeding_sales", []) or []

    answers["transfers_out"] = transfers_out
    answers["transfers_in"] = transfers_in
    answers["breeding_sales"] = breeding_sales

    report_date_iso = iso_from_ddmmyyyy(str(answers["report_date"]))
    await upsert_report(LOCATION_CODE, report_date_iso, answers, user_id)

    m_from, m_to = month_range_from_iso(report_date_iso)
    y_from, y_to = year_range_from_iso(report_date_iso)

    month_reports = await get_reports_in_range(LOCATION_CODE, m_from, m_to)
    year_reports = await get_reports_in_range(LOCATION_CODE, y_from, y_to)

    month_flow = aggregate_flow(month_reports)
    year_flow = aggregate_flow(year_reports)

    text = build_text_report(answers, month_flow, year_flow)
    await message.answer("✅ <b>Отчёт сохранён.</b>\n\n" + text, parse_mode="HTML")

    # ✅ PDF (суточный): передаём ДАННЫЕ, чтобы PDF был красивый табличный
    date_ddmmyyyy = str(answers.get("report_date"))
    pdf_daily = build_herd_daily_pdf_bytes(LOCATION_TITLE, date_ddmmyyyy, answers, month_flow, year_flow)
    fn_daily = f"Сводка по стаду {LOCATION_TITLE} за {date_ddmmyyyy}.pdf"
    await message.answer_document(BufferedInputFile(pdf_daily, filename=fn_daily))

    # ✅ PDF (месячный): агрегаты + ПОЛНАЯ ДЕТАЛИЗАЦИЯ ПО ДНЯМ
    month_label = f"{ddmmyyyy_from_iso(m_from)} — {ddmmyyyy_from_iso(m_to)}"
    pdf_month = build_herd_monthly_pdf_bytes(LOCATION_TITLE, month_label, month_flow, month_reports)
    fn_month = f"Сводка по стаду {LOCATION_TITLE} за месяц {month_label}.pdf"
    await message.answer_document(BufferedInputFile(pdf_month, filename=fn_month))

    # ✅ PDF (год, по дням до текущей даты отчёта; пустые дни остаются пустыми)
    year_label = f"{ddmmyyyy_from_iso(y_from)} — {ddmmyyyy_from_iso(y_to)}"
    pdf_year = build_herd_yearly_pdf_bytes(LOCATION_TITLE, year_label, y_from, y_to, year_reports)
    fn_year = f"Сводка по стаду {LOCATION_TITLE} за год {year_label}.pdf"
    await message.answer_document(BufferedInputFile(pdf_year, filename=fn_year))

    await state.clear()


@router.callback_query(F.data == "prod_report1_view")
async def view_latest(callback: types.CallbackQuery):
    row = await get_latest_report(LOCATION_CODE)
    if not row:
        await callback.message.answer("❗️Нет заполненных отчётов «Сводка по стаду».")
        await callback.answer()
        return

    daily = json.loads(row["data_json"])
    report_date_iso = row["report_date"]

    m_from, m_to = month_range_from_iso(report_date_iso)
    y_from, y_to = year_range_from_iso(report_date_iso)

    month_reports = await get_reports_in_range(LOCATION_CODE, m_from, m_to)
    year_reports = await get_reports_in_range(LOCATION_CODE, y_from, y_to)

    month_flow = aggregate_flow(month_reports)
    year_flow = aggregate_flow(year_reports)

    text = build_text_report(daily, month_flow, year_flow)
    await callback.message.answer(text, parse_mode="HTML")

    # ✅ PDF (суточный): данные + агрегаты
    date_ddmmyyyy = daily.get("report_date", ddmmyyyy_from_iso(report_date_iso))
    pdf_daily = build_herd_daily_pdf_bytes(LOCATION_TITLE, date_ddmmyyyy, daily, month_flow, year_flow)
    fn_daily = f"Сводка по стаду {LOCATION_TITLE} за {date_ddmmyyyy}.pdf"
    await callback.message.answer_document(BufferedInputFile(pdf_daily, filename=fn_daily))

    # ✅ PDF (месячный): агрегаты + детализация
    month_label = f"{ddmmyyyy_from_iso(m_from)} — {ddmmyyyy_from_iso(m_to)}"
    pdf_month = build_herd_monthly_pdf_bytes(LOCATION_TITLE, month_label, month_flow, month_reports)
    fn_month = f"Сводка по стаду {LOCATION_TITLE} за месяц {month_label}.pdf"
    await callback.message.answer_document(BufferedInputFile(pdf_month, filename=fn_month))

    # ✅ PDF (год, по дням до текущей даты отчёта; пустые дни остаются пустыми)
    year_label = f"{ddmmyyyy_from_iso(y_from)} — {ddmmyyyy_from_iso(y_to)}"
    pdf_year = build_herd_yearly_pdf_bytes(LOCATION_TITLE, year_label, y_from, y_to, year_reports)
    fn_year = f"Сводка по стаду {LOCATION_TITLE} за год {year_label}.pdf"
    await callback.message.answer_document(BufferedInputFile(pdf_year, filename=fn_year))

    await callback.answer()
