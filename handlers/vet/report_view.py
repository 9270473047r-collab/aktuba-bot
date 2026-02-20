# handlers/vet/report_view.py
# Просмотр вет-отчётов из БД + отправка текста + 2 PDF (день и месяц)

from __future__ import annotations

import json
import html
from datetime import datetime
from typing import Any, Dict, List, Tuple

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

from db import db

from utils.pdf_vet_0_3_reports import (
    build_vet_0_3_daily_pdf_bytes,
    build_vet_0_3_monthly_pdf_bytes,
)
from utils.pdf_vet_simple_reports import (
    build_vet_simple_daily_pdf_bytes,
    build_vet_simple_monthly_pdf_bytes,
)

router = Router()


# ────────────────────────────── helpers ──────────────────────────────
def _month_bounds(dt: datetime):
    start = dt.replace(day=1)
    if dt.month == 12:
        end = dt.replace(year=dt.year + 1, month=1, day=1)
    else:
        end = dt.replace(month=dt.month + 1, day=1)
    return start, end


def _safe_int(x: Any) -> int:
    try:
        return int(x)
    except Exception:
        return 0


def _fmt_date_h(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")


def _fmt_day_mmdd(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m")


def _fmt_values_text(title: str, location: str, report_date_h: str, questions: List[str], keys: List[str], data: Dict[str, Any]) -> str:
    lines = [
        f"📍 <b>{location}</b>",
        f"📅 <b>{title}</b>: <b>{report_date_h}</b>",
        "",
        "<b>Показатели:</b>",
    ]
    for q, k in zip(questions, keys):
        lines.append(f"• {q} <b>{_safe_int(data.get(k, 0))}</b>")
    return "\n".join(lines)


def _esc(s: Any) -> str:
    """HTML-safe текст."""
    return html.escape(str(s or ""), quote=False)


def _format_case_list(title: str, cases: List[Dict[str, Any]]) -> str:
    if not cases:
        return f"{title}: <b>0</b>"

    lines = [f"{title}: <b>{len(cases)}</b>"]
    for i, c in enumerate(cases, start=1):
        age = _esc(c.get("age_days", ""))
        diag = _esc(c.get("diagnosis", ""))
        lines.append(f"• {i}) {age} дн — {diag}")
    return "\n".join(lines)


def _format_vet03_pretty_text(location: str, report_date_h: str, payload: Dict[str, Any]) -> str:
    """Красиво оформленный детализированный текст по молодняку 0–3."""

    total = int(payload.get("total_0_3") or 0)

    def iv(key: str) -> int:
        try:
            return int(payload.get(key) or 0)
        except Exception:
            return 0

    def pv(key: str):
        return payload.get(f"{key}_pct", 0)

    def line_pct(key: str, label: str) -> str:
        v = iv(key)
        if total > 0:
            return f"• {label}: <b>{v}</b> (<b>{pv(key)}%</b>)"
        return f"• {label}: <b>{v}</b>"

    other = _esc((payload.get("other_diseases") or "").strip()) or "—"
    notes = _esc((payload.get("notes") or "").strip()) or "—"

    feed_total = iv("feed_total_l")
    feed_avg = payload.get("feed_avg_lph", 0)

    dead_c = iv("dead_count")
    san_c = iv("san_count")
    loss_total = iv("loss_total")

    lines: List[str] = []
    lines.append("✅ <b>Ветеринария — Молодняк 0–3 мес.</b>")
    lines.append(f"📍 Ферма: <b>{_esc(location)}</b>")
    lines.append(f"📅 Дата: <b>{_esc(report_date_h)}</b>")
    lines.append("")

    lines.append("<b>Ключевые итоги</b>")
    lines.append(f"• Поголовье 0–3: <b>{iv('total_0_3')}</b> гол.")
    lines.append(line_pct("new_cases", "Новые случаи за сутки"))
    lines.append(line_pct("on_treatment", "На лечении всего"))
    lines.append(line_pct("risk_death", "Тяжёлые (риск падежа)"))
    if total > 0:
        lines.append(
            f"• Потери (падёж/санубой): <b>{dead_c}</b> / <b>{san_c}</b> "
            f"(итого <b>{loss_total}</b>, <b>{payload.get('loss_total_pct', 0)}%</b>)"
        )
    else:
        lines.append(f"• Потери (падёж/санубой): <b>{dead_c}</b> / <b>{san_c}</b> (итого <b>{loss_total}</b>)")
    lines.append("")

    lines.append("<b>Движение / поголовье</b>")
    lines.append(f"• Поступило: <b>{iv('received')}</b> гол.")
    lines.append(f"• Переведено 3+: <b>{iv('moved_3_plus')}</b> гол.")
    lines.append(f"• Для реализации: <b>{iv('to_sell')}</b> гол.")
    lines.append("")

    lines.append("<b>Выпойка</b>")
    lines.append(f"• Утро: <b>{iv('feed_morn_heads')}</b> гол / <b>{iv('feed_morn_l')}</b> л")
    lines.append(f"• Вечер: <b>{iv('feed_even_heads')}</b> гол / <b>{iv('feed_even_l')}</b> л")
    lines.append(f"• Итого: <b>{feed_total}</b> л | Средняя: <b>{feed_avg}</b> л/гол")
    lines.append("")

    lines.append("<b>Заболеваемость за сутки</b>")
    lines.append("<u>ЖКТ / диарея</u>")
    lines.append(line_pct("diarr_inj", "Диарея (инъекции)"))
    lines.append(line_pct("diarr_severe", "Тяжёлая диарея (дегидратация)"))
    lines.append(line_pct("diarr_relapse", "Рецидивы диареи"))
    lines.append(line_pct("dyspepsia_0_14", "Диспепсия 0–14"))
    lines.append(line_pct("gkt_15_plus", "ЖКТ 15+"))
    lines.append(line_pct("diarr_bracelets", "Диарея (перорально/браслеты)"))
    lines.append("")

    lines.append("<u>Пневмонии</u>")
    lines.append(line_pct("pneumonia", "Пневмония всего"))
    lines.append(line_pct("pneumonia_inj", "Пневмония на инъекциях (в лечении)"))
    lines.append(line_pct("pneumonia_repeat", "Пневмония повторно"))
    lines.append("")

    lines.append("<u>Прочее</u>")
    lines.append(line_pct("omphalitis", "Омфалиты / патологии"))
    lines.append(line_pct("injuries", "Травмы / переломы / хромота"))
    lines.append(f"• Прочие заболевания: {other}")
    lines.append("")

    lines.append("<b>Статус лечения</b>")
    lines.append(f"• Выздоровело/снято: <b>{iv('recovered')}</b>")
    lines.append("")

    lines.append("<b>Падёж / санубой — детализация</b>")
    lines.append(_format_case_list("☠️ Падёж (случаи)", payload.get("dead_cases") or []))
    lines.append("")
    lines.append(_format_case_list("🧊 Санубой (случаи)", payload.get("san_cases") or []))
    lines.append("")

    lines.append("<b>Комментарий</b>")
    lines.append(f"• {notes}")

    return "\n".join(lines)


async def _get_user_location(user_id: int) -> str:
    u = await db.get_user(user_id)
    return (u.get("department") or u.get("block") or "Не указано").strip()


async def _get_selected_location(state: FSMContext, user_id: int) -> str:
    """Локация для просмотра = выбранная ферма в меню «Отчёты»."""
    try:
        st = await state.get_data()
        loc = (st.get("view_farm_title") or st.get("selected_location") or "").strip()
        if loc:
            return loc
    except Exception:
        pass
    return await _get_user_location(user_id)


async def _get_latest_report(location: str, report_type: str):
    cur = await db.conn.execute(
        """
        SELECT report_date, data_json
        FROM vet_reports
        WHERE location=? AND report_type=?
        ORDER BY report_date DESC
        LIMIT 1
        """,
        (location, report_type),
    )
    row = await cur.fetchone()
    await cur.close()
    return row


async def _get_month_reports(location: str, report_type: str, any_day_in_month: datetime):
    start, end = _month_bounds(any_day_in_month)
    cur = await db.conn.execute(
        """
        SELECT report_date, data_json
        FROM vet_reports
        WHERE location=? AND report_type=?
          AND report_date >= ? AND report_date < ?
        ORDER BY report_date ASC
        """,
        (location, report_type, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
    )
    rows = await cur.fetchall()
    await cur.close()
    return rows, start, end


# ────────────────────────────── Report 1: 0–3 мес. ──────────────────────────────
@router.callback_query(F.data == "vet_report1_view")
async def view_vet_0_3(callback: types.CallbackQuery, state: FSMContext):
    location = await _get_selected_location(state, callback.from_user.id)

    row = await _get_latest_report(location, "vet_0_3")
    if not row:
        await callback.message.answer("❗️Нет сохранённых вет-отчётов 0–3 мес. по выбранной ферме.")
        await callback.answer()
        return

    report_date_iso = row["report_date"]
    data: Dict[str, Any] = json.loads(row["data_json"])

    dt = datetime.strptime(report_date_iso, "%Y-%m-%d")
    report_date_h = dt.strftime("%d.%m.%Y")
    month_title = dt.strftime("%m.%Y")

    # Текст (детализация)
    text = _format_vet03_pretty_text(location, report_date_h, data) + "\n\nСейчас отправлю 2 PDF: <b>за день</b> и <b>за месяц</b>."
    await callback.message.answer(text, parse_mode="HTML")

    # PDF за день
    daily_b = build_vet_0_3_daily_pdf_bytes(location, report_date_h, data)
    await callback.message.answer_document(
        BufferedInputFile(daily_b, filename=f"Вет_0-3_{location}_{report_date_h}_ДЕНЬ.pdf"),
        caption="📄 PDF за день (0–3 мес.)",
    )

    # PDF за месяц
    rows, _, _ = await _get_month_reports(location, "vet_0_3", dt)
    day_rows: List[Tuple[str, Dict[str, Any]]] = []
    for r in rows:
        d = _fmt_day_mmdd(r["report_date"])
        day_rows.append((d, json.loads(r["data_json"])))

    monthly_b = build_vet_0_3_monthly_pdf_bytes(location, month_title, day_rows)
    await callback.message.answer_document(
        BufferedInputFile(monthly_b, filename=f"Вет_0-3_{location}_{month_title}_МЕСЯЦ.pdf"),
        caption="📊 PDF за месяц (0–3 мес.)",
    )

    await callback.answer()


# ────────────────────────────── Report 2: cows ──────────────────────────────
@router.callback_query(F.data == "vet_report2_view")
async def view_vet_cows(callback: types.CallbackQuery, state: FSMContext):
    location = await _get_selected_location(state, callback.from_user.id)

    row = await _get_latest_report(location, "vet_cows")
    if not row:
        await callback.message.answer("❗️Нет сохранённых вет-отчётов «Коровы» по выбранной ферме.")
        await callback.answer()
        return

    report_date_iso = row["report_date"]
    data: Dict[str, Any] = json.loads(row["data_json"])

    dt = datetime.strptime(report_date_iso, "%Y-%m-%d")
    report_date_h = dt.strftime("%d.%m.%Y")
    month_title = dt.strftime("%m.%Y")

    title = data.get("_title") or "Отчёт заболеваемости коров"
    questions = data.get("_questions") or [
        "Количество дойного поголовья:",
        "Количество отёлов:",
        "Количество гипергликемии:",
        "Количество кетоза на лечении:",
        "Количество парезов:",
        "Количество метритов всего:",
        "Количество метритов на выдержке:",
        "Количество задержаний последов:",
        "Количество мастита на лечении:",
        "Количество мастита на выдержке:",
    ]
    keys = [
        "milking_cows",
        "calvings",
        "hyperglycemia",
        "ketosis_treatment",
        "paresis",
        "metritis_total",
        "metritis_hold",
        "retained_placenta",
        "mastitis_treatment",
        "mastitis_hold",
    ]

    await callback.message.answer(
        _fmt_values_text(title, location, report_date_h, questions, keys, data)
        + "\n\nСейчас отправлю 2 PDF: <b>за день</b> и <b>за месяц</b>.",
        parse_mode="HTML",
    )

    daily_b = build_vet_simple_daily_pdf_bytes(title, location, report_date_h, questions, keys, data)
    await callback.message.answer_document(
        BufferedInputFile(daily_b, filename=f"Вет_Коровы_{location}_{report_date_h}_ДЕНЬ.pdf"),
        caption="📄 PDF за день (Коровы)",
    )

    rows, _, _ = await _get_month_reports(location, "vet_cows", dt)
    day_rows: List[Tuple[str, Dict[str, Any]]] = []
    for r in rows:
        d = _fmt_day_mmdd(r["report_date"])
        day_rows.append((d, json.loads(r["data_json"])))

    monthly_b = build_vet_simple_monthly_pdf_bytes(
        title,
        location,
        month_title,
        questions,
        keys,
        day_rows,
        avg_keys={"milking_cows"},  # поголовье — среднее за месяц
    )
    await callback.message.answer_document(
        BufferedInputFile(monthly_b, filename=f"Вет_Коровы_{location}_{month_title}_МЕСЯЦ.pdf"),
        caption="📊 PDF за месяц (Коровы)",
    )

    await callback.answer()


# ────────────────────────────── Report 3: ortho ──────────────────────────────
@router.callback_query(F.data == "vet_report3_view")
async def view_vet_ortho(callback: types.CallbackQuery, state: FSMContext):
    location = await _get_selected_location(state, callback.from_user.id)

    row = await _get_latest_report(location, "vet_ortho")
    if not row:
        await callback.message.answer("❗️Нет сохранённых вет-отчётов «Ортопедия» по выбранной ферме.")
        await callback.answer()
        return

    report_date_iso = row["report_date"]
    data: Dict[str, Any] = json.loads(row["data_json"])

    dt = datetime.strptime(report_date_iso, "%Y-%m-%d")
    report_date_h = dt.strftime("%d.%m.%Y")
    month_title = dt.strftime("%m.%Y")

    title = data.get("_title") or "Отчёт по заболеваниям ортопедия"
    questions = data.get("_questions") or [
        "Количество обрезки:",
        "Количество лечений:",
        "Цифровой дерматит (Mortellaro):",
        "Язва подошвы (Rusterholz ulcer):",
        "Белая линия (white-line disease):",
        "Геморрагия подошвы / кровоподтёки:",
        "Ламинит:",
        "Некроз пальца (toe necrosis):",
        "Фузобактериозное гниение МКЩ (foot-rot):",
    ]
    keys = [
        "trim_count",
        "treatments",
        "mortellaro",
        "sole_ulcer",
        "white_line",
        "sole_hemorrhage",
        "laminitis",
        "toe_necrosis",
        "foot_rot",
    ]

    await callback.message.answer(
        _fmt_values_text(title, location, report_date_h, questions, keys, data)
        + "\n\nСейчас отправлю 2 PDF: <b>за день</b> и <b>за месяц</b>.",
        parse_mode="HTML",
    )

    daily_b = build_vet_simple_daily_pdf_bytes(title, location, report_date_h, questions, keys, data)
    await callback.message.answer_document(
        BufferedInputFile(daily_b, filename=f"Вет_Ортопедия_{location}_{report_date_h}_ДЕНЬ.pdf"),
        caption="📄 PDF за день (Ортопедия)",
    )

    rows, _, _ = await _get_month_reports(location, "vet_ortho", dt)
    day_rows: List[Tuple[str, Dict[str, Any]]] = []
    for r in rows:
        d = _fmt_day_mmdd(r["report_date"])
        day_rows.append((d, json.loads(r["data_json"])))

    monthly_b = build_vet_simple_monthly_pdf_bytes(title, location, month_title, questions, keys, day_rows)
    await callback.message.answer_document(
        BufferedInputFile(monthly_b, filename=f"Вет_Ортопедия_{location}_{month_title}_МЕСЯЦ.pdf"),
        caption="📊 PDF за месяц (Ортопедия)",
    )

    await callback.answer()
