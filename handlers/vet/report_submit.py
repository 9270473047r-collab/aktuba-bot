# handlers/vet/report_submit.py
# ⟁ Полный рабочий файл: сбор 3 ветеринарных отчётов, хранение в БД бота (SQLite)
#  - vet_report1_submit (0–3 мес.) расширенный + падёж/санубой по одному случаю через кнопки + PDF за день
#  - vet_report2_submit (коровы) простой (дата + числа) -> БД
#  - vet_report3_submit (ортопедия) простой (дата + числа) -> БД

from __future__ import annotations

import asyncio
import json
import html
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Set

from aiogram import Router, types, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter

from db import db
from utils.pdf_vet_0_3_reports import (
    build_vet_0_3_daily_pdf_bytes,
    build_vet_0_3_monthly_pdf_bytes,
)
from utils.pdf_vet_simple_reports import (
    build_vet_simple_daily_pdf_bytes,
    build_vet_simple_monthly_pdf_bytes,
)
logger = logging.getLogger(__name__)
router = Router()

# ────────────────────────────── КНОПКИ ──────────────────────────────
def kb_yesno(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"{prefix}:yes"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"{prefix}:no"),
            ]
        ]
    )

def kb_dead_type() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="☠️ Падеж", callback_data="vet0_3_dead_type:dead"),
                InlineKeyboardButton(text="🧊 Санубой", callback_data="vet0_3_dead_type:san"),
            ]
        ]
    )

# ────────────────────────────── FSM (0–3) ──────────────────────────────
class Vet03FSM(StatesGroup):
    waiting_date = State()
    waiting_field = State()

    dead_start_yesno = State()
    dead_age = State()
    dead_diag = State()
    dead_type = State()
    dead_more_yesno = State()

# ────────────────────────────── FSM (простые отчёты) ──────────────────────────────
class VetSimpleFSM(StatesGroup):
    waiting_date = State()
    waiting_value = State()

# ────────────────────────────── МЕТА: 0–3 (вопросы) ──────────────────────────────
VET_0_3_FIELDS: List[Tuple[str, str, str]] = [
    ("total_0_3", "int", "Поголовье телят 0–3 мес., гол.:"),
    ("received", "int", "Поступило телят за сутки, гол.:"),
    ("moved_3_plus", "int", "Переведено в группу 3+ мес., гол.:"),
    ("to_sell", "int", "Сколько голов для реализации, гол.:"),  # в PDF не выводим, но в тексте выводим

    ("feed_morn_heads", "int", "Телята на выпойке УТРО, гол.:"),
    ("feed_morn_l", "int", "Выпойка УТРО, л:"),
    ("feed_even_heads", "int", "Телята на выпойке ВЕЧЕР, гол.:"),
    ("feed_even_l", "int", "Выпойка ВЕЧЕР, л:"),

    ("diarr_inj", "int", "Диарея 0–3 (инъекции), гол.:"),
    ("diarr_severe", "int", "Тяжёлая диарея (с дегидратацией), гол.:"),
    ("diarr_relapse", "int", "Рецидивы диареи (повторно), гол.:"),
    ("dyspepsia_0_14", "int", "Диспепсия 0–14 дн., гол.:"),
    ("gkt_15_plus", "int", "ЖКТ 15+ дн., гол.:"),
    ("diarr_bracelets", "int", "Диарея 0–3 (браслеты/перорально), гол.:"),

    ("pneumonia", "int", "Пневмония 0–3 (всего), гол.:"),
    ("pneumonia_inj", "int", "Пневмония на инъекциях (в лечении), гол.:"),
    ("pneumonia_repeat", "int", "Пневмония повторно, гол.:"),

    ("omphalitis", "int", "Омфалиты/патологии 0–3, гол.:"),
    ("injuries", "int", "Травмы/переломы/хромота телят, гол.:"),
    ("other_diseases", "text", "Прочие заболевания (кратко: диагноз — гол.):"),

    ("risk_death", "int", "Телята в тяжёлом состоянии (риск падежа), гол.:"),
    ("on_treatment", "int", "Телята на лечении всего, гол.:"),
    ("new_cases", "int", "Новые случаи (первично) за сутки, гол.:"),
    ("recovered", "int", "Выздоровело/снято с лечения, гол.:"),
    ("notes", "text", "Замечания по молозиву/качеству выпойки/санитарии (1–2 строки):"),
]

# ────────────────────────────── МЕТА: простые отчёты ──────────────────────────────
SIMPLE_REPORT_META: Dict[str, Dict[str, Any]] = {
    "vet_report2_submit": {
        "report_type": "vet_cows",
        "title": "Отчёт заболеваемости коров",
        "questions": [
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
        ],
        "keys": [
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
        ],
    },
    "vet_report3_submit": {
        "report_type": "vet_ortho",
        "title": "Отчёт по заболеваниям ортопедия",
        "questions": [
            "Количество обрезки:",
            "Количество лечений:",
            "Цифровой дерматит (Mortellaro):",
            "Язва подошвы (Rusterholz ulcer):",
            "Белая линия (white-line disease):",
            "Геморрагия подошвы / кровоподтёки:",
            "Ламинит:",
            "Некроз пальца (toe necrosis):",
            "Фузобактериозное гниение МКЩ (foot-rot):",
        ],
        "keys": [
            "trim_count",
            "treatments",
            "mortellaro",
            "sole_ulcer",
            "white_line",
            "sole_hemorrhage",
            "laminitis",
            "toe_necrosis",
            "foot_rot",
        ],
    },
}

# ────────────────────────────── УТИЛИТЫ ──────────────────────────────
def _parse_value(vtype: str, raw: str) -> Optional[Any]:
    raw = (raw or "").strip()
    if vtype == "int":
        try:
            v = int(raw)
            if v < 0:
                return None
            return v
        except Exception:
            return None
    if vtype == "text":
        return raw
    return raw

def _pct(part: int, total: int) -> float:
    if total > 0:
        return round((part / total) * 100.0, 2)
    return 0.0

def _get_admin_ids() -> Set[int]:
    admins: Set[int] = set()
    try:
        from config import ADMINS as CFG_ADMINS  # type: ignore
        admins |= {int(x) for x in (CFG_ADMINS or [])}
    except Exception:
        pass

    try:
        maybe = getattr(db, "ADMINS", None)
        if maybe:
            admins |= {int(x) for x in maybe}
    except Exception:
        pass

    try:
        maybe = getattr(db, "admins", None)
        if maybe:
            admins |= {int(x) for x in maybe}
    except Exception:
        pass

    return admins

async def _get_sender_context(message: types.Message) -> Dict[str, Any]:
    """
    Возвращает контекст отправителя:
      - location: отделение/блок или Админ/Не зарегистрированный пользователь
      - created_by_db: user_id из users (для FK) или None (чтобы FK не падал)
      - registered: bool
      - is_admin: bool (по ADMINS)
    """
    tg_user_id = int(message.from_user.id)
    tg_full_name = (message.from_user.full_name or "").strip()

    admins = _get_admin_ids()
    is_admin = tg_user_id in admins

    user = None
    try:
        user = await db.get_user(tg_user_id)
    except Exception:
        logger.exception("db.get_user failed")

    registered = user is not None

    if registered:
        location = ((user or {}).get("department") or (user or {}).get("block") or "Не указано").strip() or "Не указано"
        created_by_db = tg_user_id  # гарантированно есть в users.user_id
    else:
        location = "Админ" if is_admin else "Не зарегистрированный пользователь"
        created_by_db = None  # иначе FK упадёт

    return {
        "location": location,
        "created_by_db": created_by_db,
        "registered": registered,
        "is_admin": is_admin,
        "tg_user_id": tg_user_id,
        "tg_full_name": tg_full_name,
    }

async def _safe_upsert_vet_report(
    *,
    location: str,
    report_type: str,
    report_date: str,
    data_json: str,
    created_by_db: Optional[int],
) -> None:
    """
    Upsert в vet_reports. created_by_db может быть None (тогда FK не проверяется).
    """
    await db.conn.execute(
        """
        INSERT INTO vet_reports (location, report_type, report_date, data_json, created_by)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(location, report_type, report_date)
        DO UPDATE SET data_json=excluded.data_json, updated_at=CURRENT_TIMESTAMP;
        """,
        (location, report_type, report_date, data_json, created_by_db),
    )
    await db.conn.commit()

async def _send_document_with_retry(
    message: types.Message,
    file: BufferedInputFile,
    *,
    caption: str = "",
    attempts: int = 3,
    base_delay: float = 1.0,
) -> bool:
    """
    Усилитель: 3 попытки отправки документа (1s,2s,4s). Не валит процесс.
    Возвращает True если отправили, иначе False.
    """
    last_exc: Optional[BaseException] = None

    for i in range(1, attempts + 1):
        try:
            await message.answer_document(file, caption=caption)
            return True
        except TelegramRetryAfter as e:
            # Telegram сказал подождать
            wait_s = max(float(getattr(e, "retry_after", 1.0)), base_delay)
            logger.warning("TelegramRetryAfter while sending doc, wait %.2fs (attempt %s/%s)", wait_s, i, attempts)
            last_exc = e
            await asyncio.sleep(wait_s)
        except TelegramNetworkError as e:
            delay = base_delay * (2 ** (i - 1))
            logger.warning("TelegramNetworkError while sending doc: %s (attempt %s/%s), sleep %.2fs", e, i, attempts, delay)
            last_exc = e
            await asyncio.sleep(delay)
        except Exception as e:
            delay = base_delay * (2 ** (i - 1))
            logger.exception("Unexpected error while sending doc (attempt %s/%s), sleep %.2fs", i, attempts, delay)
            last_exc = e
            await asyncio.sleep(delay)

    logger.error("Failed to send document after %s attempts. Last error: %r", attempts, last_exc)
    return False


# ────────────────────────────── month helpers ──────────────────────────────
def _month_bounds(dt: datetime):
    start = dt.replace(day=1)
    if dt.month == 12:
        end = dt.replace(year=dt.year + 1, month=1, day=1)
    else:
        end = dt.replace(month=dt.month + 1, day=1)
    return start, end


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


def _esc(s: Any) -> str:
    """HTML-safe текст."""
    return html.escape(str(s or ""), quote=False)


def _format_case_list(title: str, cases: List[Dict[str, Any]]) -> str:
    """Форматирует список падежа/санубоя для текста (HTML)."""
    if not cases:
        return f"{title}: <b>0</b>"

    lines = [f"{title}: <b>{len(cases)}</b>"]
    for i, c in enumerate(cases, start=1):
        age = _esc(c.get("age_days", ""))
        diag = _esc(c.get("diagnosis", ""))
        lines.append(f"• {i}) {age} дн — {diag}")
    return "\n".join(lines)


def _format_vet03_full_text(location: str, report_date_h: str, payload: Dict[str, Any]) -> str:
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

    other = _esc(payload.get("other_diseases", "").strip()) or "—"
    notes = _esc(payload.get("notes", "").strip()) or "—"

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

    # Ключевые итоги
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

    # Движение
    lines.append("<b>Движение / поголовье</b>")
    lines.append(f"• Поступило: <b>{iv('received')}</b> гол.")
    lines.append(f"• Переведено 3+: <b>{iv('moved_3_plus')}</b> гол.")
    lines.append(f"• Для реализации: <b>{iv('to_sell')}</b> гол.")
    lines.append("")

    # Выпойка
    lines.append("<b>Выпойка</b>")
    lines.append(f"• Утро: <b>{iv('feed_morn_heads')}</b> гол / <b>{iv('feed_morn_l')}</b> л")
    lines.append(f"• Вечер: <b>{iv('feed_even_heads')}</b> гол / <b>{iv('feed_even_l')}</b> л")
    lines.append(f"• Итого: <b>{feed_total}</b> л | Средняя: <b>{feed_avg}</b> л/гол")
    lines.append("")

    # Заболеваемость
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

    # Лечение
    lines.append("<b>Статус лечения</b>")
    lines.append(f"• Выздоровело/снято: <b>{iv('recovered')}</b>")
    lines.append("")

    # Падёж/санубой детализация
    lines.append("<b>Падёж / санубой — детализация</b>")
    lines.append(_format_case_list("☠️ Падёж (случаи)", payload.get("dead_cases") or []))
    lines.append("")
    lines.append(_format_case_list("🧊 Санубой (случаи)", payload.get("san_cases") or []))
    lines.append("")

    lines.append("<b>Комментарий</b>")
    lines.append(f"• {notes}")

    return "\n".join(lines)

def _format_simple_full_text(title: str, location: str, report_date_h: str, questions: List[str], answers: List[int]) -> str:
    lines = [
        f"✅ <b>{title}</b> (все данные)",
        f"📍 {location}",
        f"📅 {report_date_h}",
        "",
        "<b>Показатели:</b>",
    ]
    for q, a in zip(questions, answers):
        lines.append(f"• {q} <b>{a}</b>")
    return "\n".join(lines)

# ────────────────────────────── СТАРТ 0–3 ──────────────────────────────
@router.callback_query(F.data == "vet_report1_submit")
async def start_vet_0_3(callback: types.CallbackQuery, state: FSMContext):
    prev = await state.get_data()
    selected_location = (prev.get("submit_farm_title") or prev.get("selected_location") or prev.get("location") or "").strip() or None

    await state.clear()
    await state.set_state(Vet03FSM.waiting_date)
    await state.update_data(
        idx=0,
        payload={},
        dead_cases=[],
        san_cases=[],
        current_case={},
        selected_location=selected_location,
    )
    head = "📄 <b>Ветеринария — Молодняк 0–3 мес.</b>"
    if selected_location:
        head += f"\n📍 Ферма: <b>{selected_location}</b>"

    await callback.message.answer(
        head + "\nВведите дату отчёта в формате <b>дд.мм.гггг</b>:",
        parse_mode="HTML",
    )
    await callback.answer()

@router.message(Vet03FSM.waiting_date)
async def receive_date_vet03(message: types.Message, state: FSMContext):
    try:
        date_obj = datetime.strptime((message.text or "").strip(), "%d.%m.%Y")
    except ValueError:
        await message.answer("⛔️ Неверный формат даты. Введите ещё раз: дд.мм.гггг")
        return

    await state.update_data(date=date_obj, idx=0, payload={})
    await state.set_state(Vet03FSM.waiting_field)
    await message.answer(VET_0_3_FIELDS[0][2])

@router.message(Vet03FSM.waiting_field)
async def receive_field_vet03(message: types.Message, state: FSMContext):
    st = await state.get_data()
    idx = int(st.get("idx", 0))
    payload: Dict[str, Any] = st.get("payload") or {}

    key, vtype, _question = VET_0_3_FIELDS[idx]
    val = _parse_value(vtype, message.text or "")

    if val is None:
        await message.answer("Введите корректное значение.")
        return

    payload[key] = val
    idx += 1

    if idx < len(VET_0_3_FIELDS):
        await state.update_data(idx=idx, payload=payload)
        await message.answer(VET_0_3_FIELDS[idx][2])
        return

    await state.update_data(payload=payload, idx=idx)
    await state.set_state(Vet03FSM.dead_start_yesno)
    await message.answer(
        "☠️ <b>Падёж 0–3 за сутки был?</b>",
        parse_mode="HTML",
        reply_markup=kb_yesno("vet0_3_dead_start"),
    )

# ────────────────────────────── ПАДЁЖ: старт (да/нет) ──────────────────────────────
@router.callback_query(Vet03FSM.dead_start_yesno, F.data.startswith("vet0_3_dead_start:"))
async def dead_start(callback: types.CallbackQuery, state: FSMContext):
    ans = callback.data.split(":", 1)[1]
    if ans == "no":
        await callback.answer()
        await _finalize_vet03_and_send(callback.message, state)
        return

    await state.update_data(current_case={})
    await state.set_state(Vet03FSM.dead_age)
    await callback.message.answer("Введите возраст телёнка (в днях):")
    await callback.answer()

@router.message(Vet03FSM.dead_age)
async def dead_age(message: types.Message, state: FSMContext):
    try:
        age_days = int((message.text or "").strip())
        if age_days < 0:
            raise ValueError
    except Exception:
        await message.answer("Введите неотрицательное целое число (возраст в днях).")
        return

    st = await state.get_data()
    current_case = st.get("current_case") or {}
    current_case["age_days"] = age_days
    await state.update_data(current_case=current_case)

    await state.set_state(Vet03FSM.dead_diag)
    await message.answer("Введите диагноз (текст):")

@router.message(Vet03FSM.dead_diag)
async def dead_diag(message: types.Message, state: FSMContext):
    diag = (message.text or "").strip()
    if not diag:
        await message.answer("Диагноз не должен быть пустым. Введите диагноз:")
        return

    st = await state.get_data()
    current_case = st.get("current_case") or {}
    current_case["diagnosis"] = diag
    await state.update_data(current_case=current_case)

    await state.set_state(Vet03FSM.dead_type)
    await message.answer("Как оформили?", reply_markup=kb_dead_type())

@router.callback_query(Vet03FSM.dead_type, F.data.startswith("vet0_3_dead_type:"))
async def dead_type(callback: types.CallbackQuery, state: FSMContext):
    t = callback.data.split(":", 1)[1]  # dead / san
    st = await state.get_data()
    current_case = st.get("current_case") or {}

    if "age_days" not in current_case or "diagnosis" not in current_case:
        await callback.message.answer("⚠️ Ошибка состояния. Начните ввод падежа заново.")
        await callback.answer()
        await state.set_state(Vet03FSM.dead_start_yesno)
        return

    if t == "dead":
        dead_cases = st.get("dead_cases") or []
        dead_cases.append(current_case)
        await state.update_data(dead_cases=dead_cases)
        await callback.message.answer("✅ Случай записан как <b>ПАДЁЖ</b>.", parse_mode="HTML")
    else:
        san_cases = st.get("san_cases") or []
        san_cases.append(current_case)
        await state.update_data(san_cases=san_cases)
        await callback.message.answer("✅ Случай записан как <b>САНУБОЙ</b>.", parse_mode="HTML")

    await state.update_data(current_case={})
    await state.set_state(Vet03FSM.dead_more_yesno)
    await callback.message.answer(
        "Был ли ещё падёж/санубой 0–3 за сутки?",
        reply_markup=kb_yesno("vet0_3_dead_more"),
    )
    await callback.answer()

@router.callback_query(Vet03FSM.dead_more_yesno, F.data.startswith("vet0_3_dead_more:"))
async def dead_more(callback: types.CallbackQuery, state: FSMContext):
    ans = callback.data.split(":", 1)[1]
    if ans == "yes":
        await state.update_data(current_case={})
        await state.set_state(Vet03FSM.dead_age)
        await callback.message.answer("Введите возраст телёнка (в днях):")
        await callback.answer()
        return

    await callback.answer()
    await _finalize_vet03_and_send(callback.message, state)

# ────────────────────────────── ФИНАЛ: 0–3 (авто-поля, БД, текст, PDF) ──────────────────────────────
async def _finalize_vet03_and_send(message: types.Message, state: FSMContext):
    st = await state.get_data()
    payload: Dict[str, Any] = st.get("payload") or {}
    dead_cases: List[Dict[str, Any]] = st.get("dead_cases") or []
    san_cases: List[Dict[str, Any]] = st.get("san_cases") or []

    if "date" not in st:
        await message.answer("⚠️ Ошибка состояния: не найдена дата отчёта. Начните заново.")
        await state.clear()
        return

    date_obj: datetime = st["date"]

    sender_ctx = await _get_sender_context(message)
    location: str = (st.get("selected_location") or "").strip() or sender_ctx["location"]
    created_by_db: Optional[int] = sender_ctx["created_by_db"]

    # доп. инфо об отправителе — всегда в JSON
    payload["_tg_user_id"] = sender_ctx["tg_user_id"]
    payload["_tg_full_name"] = sender_ctx["tg_full_name"]
    payload["_registered"] = bool(sender_ctx["registered"])
    payload["_is_admin"] = bool(sender_ctx["is_admin"])

    total = int(payload.get("total_0_3") or 0)

    # выпойка авто
    payload["feed_total_l"] = int(payload.get("feed_morn_l") or 0) + int(payload.get("feed_even_l") or 0)
    mh = int(payload.get("feed_morn_heads") or 0)
    eh = int(payload.get("feed_even_heads") or 0)
    avg_heads = (mh + eh) / 2 if (mh + eh) else 0
    payload["feed_avg_lph"] = round(payload["feed_total_l"] / avg_heads, 2) if avg_heads else 0.0

    # проценты по болезням/статусам (от total_0_3)
    for k in [
        "diarr_inj", "diarr_severe", "diarr_relapse", "dyspepsia_0_14", "gkt_15_plus", "diarr_bracelets",
        "pneumonia", "pneumonia_inj", "pneumonia_repeat",
        "omphalitis", "injuries", "risk_death", "on_treatment", "new_cases",
    ]:
        payload[f"{k}_pct"] = _pct(int(payload.get(k) or 0), total)

    # падёж/санубой
    payload["dead_cases"] = dead_cases
    payload["san_cases"] = san_cases
    payload["dead_count"] = len(dead_cases)
    payload["san_count"] = len(san_cases)
    payload["loss_total"] = payload["dead_count"] + payload["san_count"]
    payload["dead_pct"] = _pct(payload["dead_count"], total)
    payload["san_pct"] = _pct(payload["san_count"], total)
    payload["loss_total_pct"] = _pct(payload["loss_total"], total)

    report_date = date_obj.strftime("%Y-%m-%d")
    report_date_h = date_obj.strftime("%d.%m.%Y")

    # сохранить в БД (upsert)
    try:
        await _safe_upsert_vet_report(
            location=location,
            report_type="vet_0_3",
            report_date=report_date,
            data_json=json.dumps(payload, ensure_ascii=False),
            created_by_db=created_by_db,  # None для незарегистрированных
        )
    except Exception:
        logger.exception("Ошибка сохранения vet_0_3 в БД")
        await message.answer("❗️Ошибка при сохранении отчёта в БД. Посмотрите логи.")
        await state.clear()
        return

    # ТЕКСТ: все данные
    full_text = _format_vet03_full_text(location, report_date_h, payload)
    await message.answer(full_text, parse_mode="HTML")

    # PDF за день (усилитель 3 попытки)
    try:
        pdf_b = build_vet_0_3_daily_pdf_bytes(location, report_date_h, payload)
        ok = await _send_document_with_retry(
            message,
            BufferedInputFile(pdf_b, filename=f"Вет_0-3_{location}_{report_date_h}_ДЕНЬ.pdf"),
            caption="📄 PDF за день (0–3 мес.)",
            attempts=3,
            base_delay=1.0,
        )
        if not ok:
            await message.answer(
                "⚠️ Отчёт сохранён в БД, но Telegram не принял PDF (ошибка сети). "
                "Повторите позже — данные не потерялись."
            )
    except Exception:
        logger.exception("PDF build/send failed (vet_0_3). Отчёт сохранён, но PDF не ушёл.")
        await message.answer(
            "⚠️ Отчёт сохранён в БД, но PDF не удалось сформировать/отправить. "
            "Повторите позже — данные не потерялись."
        )



    # PDF за месяц
    try:
        rows, _start, _end = await _get_month_reports(location, "vet_0_3", date_obj)
        day_rows: List[Tuple[str, Dict[str, Any]]] = []
        for r in rows:
            d = datetime.strptime(r["report_date"], "%Y-%m-%d").strftime("%d.%m")
            day_rows.append((d, json.loads(r["data_json"])))

        month_title = date_obj.strftime("%m.%Y")
        pdf_m = build_vet_0_3_monthly_pdf_bytes(location, month_title, day_rows)
        await _send_document_with_retry(
            message,
            BufferedInputFile(pdf_m, filename=f"Вет_0-3_{location}_{month_title}_МЕСЯЦ.pdf"),
            caption="📊 PDF за месяц (0–3 мес.)",
            attempts=3,
            base_delay=1.0,
        )
    except Exception:
        logger.exception("Monthly PDF build/send failed (vet_0_3).")
        await message.answer(
            "⚠️ Отчёт сохранён в БД, но PDF за месяц не удалось сформировать/отправить. "
            "Данные не потерялись."
        )

    await state.clear()

# ────────────────────────────── СТАРТ простых отчётов (коровы/ортопедия) ──────────────────────────────
@router.callback_query(F.data.func(lambda d: d in SIMPLE_REPORT_META))
async def start_simple_report(callback: types.CallbackQuery, state: FSMContext):
    meta = SIMPLE_REPORT_META[callback.data]
    prev = await state.get_data()
    selected_location = (prev.get("submit_farm_title") or prev.get("selected_location") or prev.get("location") or "").strip() or None

    await state.clear()
    await state.set_state(VetSimpleFSM.waiting_date)
    await state.update_data(
        report_key=callback.data,
        report_type=meta["report_type"],
        title=meta["title"],
        questions=meta["questions"],
        keys=meta["keys"],
        answers=[],
        selected_location=selected_location,
    )
    head = f"📄 <b>{meta['title']}</b>"
    if selected_location:
        head += f"\n📍 Ферма: <b>{selected_location}</b>"

    await callback.message.answer(
        head + "\nВведите дату отчёта в формате <b>дд.мм.гггг</b>:",
        parse_mode="HTML",
    )
    await callback.answer()

@router.message(VetSimpleFSM.waiting_date)
async def receive_date_simple(message: types.Message, state: FSMContext):
    try:
        date_obj = datetime.strptime((message.text or "").strip(), "%d.%m.%Y")
    except ValueError:
        await message.answer("⛔️ Неверный формат даты. Введите ещё раз: дд.мм.гггг")
        return

    await state.update_data(date=date_obj)
    data = await state.get_data()
    await state.set_state(VetSimpleFSM.waiting_value)
    await message.answer(data["questions"][0])

@router.message(VetSimpleFSM.waiting_value)
async def receive_value_simple(message: types.Message, state: FSMContext):
    data = await state.get_data()
    answers: List[int] = data["answers"]
    questions: List[str] = data["questions"]

    # валидация числа
    try:
        val = int((message.text or "").strip())
        if val < 0:
            raise ValueError
    except Exception:
        await message.answer("Введите неотрицательное целое число.")
        return

    answers.append(val)
    await state.update_data(answers=answers)

    if len(answers) < len(questions):
        await message.answer(questions[len(answers)])
        return

    # все ответы собраны -> БД
    try:
        sender_ctx = await _get_sender_context(message)
        st = await state.get_data()
        location: str = (st.get("selected_location") or "").strip() or sender_ctx["location"]
        created_by_db: Optional[int] = sender_ctx["created_by_db"]

        report_type = data["report_type"]
        date_obj: datetime = data["date"]
        report_date = date_obj.strftime("%Y-%m-%d")
        report_date_h = date_obj.strftime("%d.%m.%Y")

        keys: List[str] = data["keys"]
        payload = {keys[i]: answers[i] for i in range(len(keys))}
        payload["_title"] = data["title"]
        payload["_questions"] = questions

        # кто отправил — всегда в JSON
        payload["_tg_user_id"] = sender_ctx["tg_user_id"]
        payload["_tg_full_name"] = sender_ctx["tg_full_name"]
        payload["_registered"] = bool(sender_ctx["registered"])
        payload["_is_admin"] = bool(sender_ctx["is_admin"])

        await _safe_upsert_vet_report(
            location=location,
            report_type=report_type,
            report_date=report_date,
            data_json=json.dumps(payload, ensure_ascii=False),
            created_by_db=created_by_db,
        )

        # ТЕКСТ: все данные
        full_text = _format_simple_full_text(data["title"], location, report_date_h, questions, answers)
        await message.answer(full_text, parse_mode="HTML")


        prefix = "Вет_Коровы" if report_type == "vet_cows" else "Вет_Ортопедия" if report_type == "vet_ortho" else "Вет"

        # PDF за день
        try:
            daily_b = build_vet_simple_daily_pdf_bytes(data["title"], location, report_date_h, questions, keys, payload)
            await _send_document_with_retry(
                message,
                BufferedInputFile(daily_b, filename=f"{prefix}_{location}_{report_date_h}_ДЕНЬ.pdf"),
                caption=f"📄 PDF за день ({data['title']})",
                attempts=3,
                base_delay=1.0,
            )
        except Exception:
            logger.exception("Daily PDF build/send failed (%s).", report_type)

        # PDF за месяц
        try:
            rows, _start, _end = await _get_month_reports(location, report_type, date_obj)
            day_rows: List[Tuple[str, Dict[str, Any]]] = []
            for r in rows:
                d = datetime.strptime(r["report_date"], "%Y-%m-%d").strftime("%d.%m")
                day_rows.append((d, json.loads(r["data_json"])))

            month_title = date_obj.strftime("%m.%Y")
            avg_keys = {"milking_cows"} if report_type == "vet_cows" else None

            monthly_b = build_vet_simple_monthly_pdf_bytes(
                data["title"],
                location,
                month_title,
                questions,
                keys,
                day_rows,
                avg_keys=avg_keys,
            )
            await _send_document_with_retry(
                message,
                BufferedInputFile(monthly_b, filename=f"{prefix}_{location}_{month_title}_МЕСЯЦ.pdf"),
                caption=f"📊 PDF за месяц ({data['title']})",
                attempts=3,
                base_delay=1.0,
            )
        except Exception:
            logger.exception("Monthly PDF build/send failed (%s).", report_type)

    except Exception:
        logger.exception("Ошибка сохранения вет-отчёта в БД")
        await message.answer("❗️Ошибка при сохранении отчёта в БД. Посмотрите логи.")
    finally:
        await state.clear()