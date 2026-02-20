from __future__ import annotations

"""Ежедневный контроль сдачи отчётов + рассылка PDF всем пользователям.

Требование:
  - каждый день в 16:00 (MSK) отправлять всем пользователям:
      1) список: какая ферма/отдел и какая сводка НЕ сдана
      2) PDF-пакет за сутки со всеми уже сданными отчётами

Файл вызывается планировщиком (scheduler.py).
"""

import json
import logging
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import BufferedInputFile

from db import db

# Молоко (PDF)
from handlers.milk_summary import get_milk_report_by_date
from utils.pdf_milk_summary_pdf import build_milk_summary_pdf_bytes

# Вет (PDF)
from utils.pdf_vet_0_3_reports import build_vet_0_3_daily_pdf_bytes
from utils.pdf_vet_simple_reports import build_vet_simple_daily_pdf_bytes

# Стадо (PDF)
from handlers.prod.herd_movement_v2 import (
    aggregate_flow,
    get_reports_in_range,
    month_range_from_iso,
    year_range_from_iso,
)
from utils.pdf_herd_movement_reports import build_herd_daily_pdf_bytes

# МТП (PDF)
from utils.pdf_mtp_daily_summary import build_mtp_daily_pdf_bytes

try:
    from PyPDF2 import PdfMerger  # type: ignore
except Exception:  # pragma: no cover
    PdfMerger = None  # type: ignore

logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")

FARMS: List[Tuple[str, str]] = [
    ("ЖК «Актюба»", "aktuba"),
    ("Карамалы", "karamaly"),
    ("Шереметьево", "sheremetyovo"),
]


def _today_iso_msk() -> str:
    return datetime.now(MSK).strftime("%Y-%m-%d")


def _today_h_msk() -> str:
    return datetime.now(MSK).strftime("%d.%m.%Y")


async def _list_active_user_ids() -> List[int]:
    # активные + подтверждённые
    cur = await db.conn.execute(
        "SELECT user_id FROM users WHERE is_active=1 AND is_confirmed=1 ORDER BY user_id"
    )
    rows = await cur.fetchall()
    await cur.close()
    return [int(r["user_id"]) for r in rows]


# ─────────────────────────────────────────────────────────────
# CHECKS: существует ли отчёт за дату
# ─────────────────────────────────────────────────────────────
async def _exists_milk(location_code: str, report_date_iso: str) -> bool:
    try:
        row = await get_milk_report_by_date(location_code, report_date_iso)
        return bool(row)
    except Exception:
        logger.exception("milk check failed")
        return False


async def _exists_vet(location_title: str, report_type: str, report_date_iso: str) -> bool:
    try:
        cur = await db.conn.execute(
            """
            SELECT 1 FROM vet_reports
            WHERE location=? AND report_type=? AND report_date=?
            LIMIT 1
            """,
            (location_title, report_type, report_date_iso),
        )
        row = await cur.fetchone()
        await cur.close()
        return bool(row)
    except Exception:
        logger.exception("vet check failed")
        return False


async def _exists_herd(location_code: str, report_date_iso: str) -> bool:
    try:
        cur = await db.conn.execute(
            """
            SELECT 1 FROM herd_movement_reports
            WHERE location=? AND report_date=?
            LIMIT 1
            """,
            (location_code, report_date_iso),
        )
        row = await cur.fetchone()
        await cur.close()
        return bool(row)
    except Exception:
        # таблица может не быть создана — трактуем как "не сдано"
        return False


async def _exists_mtp(location_code: str, report_date_iso: str) -> bool:
    try:
        cur = await db.conn.execute(
            """
            SELECT 1 FROM mtp_daily_reports
            WHERE location=? AND report_date=?
            LIMIT 1
            """,
            (location_code, report_date_iso),
        )
        row = await cur.fetchone()
        await cur.close()
        return bool(row)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# PDF BUILDERS (по одному отчёту)
# ─────────────────────────────────────────────────────────────
async def _pdf_milk(location_title: str, location_code: str, report_date_iso: str) -> Optional[bytes]:
    row = await get_milk_report_by_date(location_code, report_date_iso)
    if not row:
        return None
    data = json.loads(row["data_json"])
    # всем пользователям отправляем "public" (без закрытых полей)
    prices = await db.get_milk_prices(location_code)
    return build_milk_summary_pdf_bytes(location_title, data, mode="public", density=1.03, prices=prices)


async def _pdf_vet_0_3(location_title: str, report_date_iso: str) -> Optional[bytes]:
    cur = await db.conn.execute(
        "SELECT data_json FROM vet_reports WHERE location=? AND report_type='vet_0_3' AND report_date=? LIMIT 1",
        (location_title, report_date_iso),
    )
    row = await cur.fetchone()
    await cur.close()
    if not row:
        return None
    data = json.loads(row["data_json"])
    report_date_h = datetime.strptime(report_date_iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    return build_vet_0_3_daily_pdf_bytes(location_title, report_date_h, data)


async def _pdf_vet_simple(location_title: str, report_type: str, report_date_iso: str) -> Optional[bytes]:
    cur = await db.conn.execute(
        "SELECT data_json FROM vet_reports WHERE location=? AND report_type=? AND report_date=? LIMIT 1",
        (location_title, report_type, report_date_iso),
    )
    row = await cur.fetchone()
    await cur.close()
    if not row:
        return None
    data = json.loads(row["data_json"])
    report_date_h = datetime.strptime(report_date_iso, "%Y-%m-%d").strftime("%d.%m.%Y")

    # titles для PDF
    if report_type == "vet_cows":
        title = "Ветеринария — Заболеваемость коров"
    elif report_type == "vet_ortho":
        title = "Ветеринария — Ортопедия"
    else:
        title = "Ветеринария"

    return build_vet_simple_daily_pdf_bytes(title, location_title, report_date_h, data, report_type=report_type)


async def _pdf_herd_aktuba(report_date_iso: str) -> Optional[bytes]:
    # берём данные за день
    cur = await db.conn.execute(
        "SELECT data_json FROM herd_movement_reports WHERE location='aktuba' AND report_date=? LIMIT 1",
        (report_date_iso,),
    )
    row = await cur.fetchone()
    await cur.close()
    if not row:
        return None

    answers: Dict[str, Any] = json.loads(row["data_json"])

    # агрегаты месяц/год как в обработчике
    m_from, m_to = month_range_from_iso(report_date_iso)
    y_from, y_to = year_range_from_iso(report_date_iso)

    month_reports = await get_reports_in_range("aktuba", m_from, m_to)
    year_reports = await get_reports_in_range("aktuba", y_from, y_to)
    month_flow = aggregate_flow(month_reports)
    year_flow = aggregate_flow(year_reports)

    report_date_h = datetime.strptime(report_date_iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    return build_herd_daily_pdf_bytes("ЖК «Актюба»", report_date_h, answers, month_flow, year_flow)


async def _pdf_mtp_aktuba(report_date_iso: str) -> Optional[bytes]:
    cur = await db.conn.execute(
        "SELECT data_json FROM mtp_daily_reports WHERE location='aktuba' AND report_date=? LIMIT 1",
        (report_date_iso,),
    )
    row = await cur.fetchone()
    await cur.close()
    if not row:
        return None
    data = json.loads(row["data_json"])
    report_date_h = datetime.strptime(report_date_iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    return build_mtp_daily_pdf_bytes("ЖК «Актюба»", report_date_h, data)


def _merge_pdfs(parts: List[Tuple[str, bytes]]) -> bytes:
    if PdfMerger is None:
        # fallback: вернём первый PDF (если библиотека недоступна)
        return parts[0][1]

    merger = PdfMerger()
    for _name, pdf_b in parts:
        merger.append(BytesIO(pdf_b))
    out = BytesIO()
    merger.write(out)
    merger.close()
    return out.getvalue()


async def build_daily_pdf_parts(report_date_iso: str) -> List[Tuple[str, bytes]]:
    """Собирает список PDF (по одному на каждый имеющийся отчёт) за указанную дату."""
    parts: List[Tuple[str, bytes]] = []

    for farm_title, farm_code in FARMS:
        # Молоко
        try:
            b = await _pdf_milk(farm_title, farm_code, report_date_iso)
            if b:
                parts.append((f"milk_{farm_code}", b))
        except Exception:
            logger.exception("milk pdf build failed")

        # Вет
        try:
            b = await _pdf_vet_0_3(farm_title, report_date_iso)
            if b:
                parts.append((f"vet_0_3_{farm_code}", b))
        except Exception:
            logger.exception("vet 0-3 pdf build failed")

        try:
            b = await _pdf_vet_simple(farm_title, "vet_cows", report_date_iso)
            if b:
                parts.append((f"vet_cows_{farm_code}", b))
        except Exception:
            logger.exception("vet cows pdf build failed")

        try:
            b = await _pdf_vet_simple(farm_title, "vet_ortho", report_date_iso)
            if b:
                parts.append((f"vet_ortho_{farm_code}", b))
        except Exception:
            logger.exception("vet ortho pdf build failed")

    # Стадо и МТП (только Актюба)
    try:
        b = await _pdf_herd_aktuba(report_date_iso)
        if b:
            parts.append(("herd_aktuba", b))
    except Exception:
        logger.exception("herd pdf build failed")

    try:
        b = await _pdf_mtp_aktuba(report_date_iso)
        if b:
            parts.append(("mtp_aktuba", b))
    except Exception:
        logger.exception("mtp pdf build failed")

    return parts


async def build_daily_pdf_package(report_date_iso: str) -> Optional[Tuple[bytes, str]]:
    """Собирает единый PDF-пакет за сутки (если доступен PdfMerger)."""
    parts = await build_daily_pdf_parts(report_date_iso)
    if not parts:
        return None

    pdf_b = _merge_pdfs(parts)
    date_tag = report_date_iso.replace("-", "")
    filename = f"Пакет_отчетов_за_{date_tag}.pdf"
    return pdf_b, filename


# ─────────────────────────────────────────────────────────────
# MESSAGE: что не сдано
# ─────────────────────────────────────────────────────────────
async def build_missing_reports_message(report_date_iso: str) -> str:
    date_h = datetime.strptime(report_date_iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    lines: List[str] = []
    lines.append(f"🕓 <b>Контроль сдачи сводок</b> (срез на 16:00)\n📅 Дата: <b>{date_h}</b>")
    lines.append("")

    for farm_title, farm_code in FARMS:
        missing: List[str] = []

        if not await _exists_milk(farm_code, report_date_iso):
            missing.append("🍼 Сводка по молоку")

        if not await _exists_vet(farm_title, "vet_0_3", report_date_iso):
            missing.append("🩺 Ветеринария: 0–3 мес")
        if not await _exists_vet(farm_title, "vet_cows", report_date_iso):
            missing.append("🐄 Ветеринария: коровы")
        if not await _exists_vet(farm_title, "vet_ortho", report_date_iso):
            missing.append("🦶 Ветеринария: ортопедия")

        if farm_code == "aktuba":
            if not await _exists_herd("aktuba", report_date_iso):
                missing.append("🔄 Производство: движение поголовья")
            if not await _exists_mtp("aktuba", report_date_iso):
                missing.append("🚜 Инженерная служба: сводка МТП")

        lines.append(f"📍 <b>{farm_title}</b>")
        if not missing:
            lines.append("✅ Все обязательные отчёты сданы")
        else:
            for m in missing:
                lines.append(f"❌ {m} — <b>НЕ СДАНО</b>")
        lines.append("")

    lines.append("Если отчёт уже сдали — обновите/пересдайте и проверьте, что сохранение прошло успешно.")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# MAIN JOB
# ─────────────────────────────────────────────────────────────
async def send_daily_deadline_and_pdfs(bot: Bot):
    """Задача планировщика на 16:00."""
    report_date_iso = _today_iso_msk()

    user_ids = await _list_active_user_ids()
    if not user_ids:
        return

    # 1) уведомление о несданных
    msg = await build_missing_reports_message(report_date_iso)
    for uid in user_ids:
        try:
            await bot.send_message(uid, msg, parse_mode="HTML")
        except Exception:
            continue

    # 2) PDF за сутки
    parts = await build_daily_pdf_parts(report_date_iso)
    if not parts:
        note = f"📄 PDF за {_today_h_msk()} не сформирован: нет сохранённых отчётов за сутки."
        for uid in user_ids:
            try:
                await bot.send_message(uid, note)
            except Exception:
                continue
        return

    # Если доступен PdfMerger — отправляем одним файлом, иначе — отдельными PDF.
    if PdfMerger is not None:
        pack = await build_daily_pdf_package(report_date_iso)
        if not pack:
            return
        pdf_b, filename = pack
        caption = f"📄 <b>Пакет отчётов за сутки</b> ({_today_h_msk()})"
        for uid in user_ids:
            try:
                doc = BufferedInputFile(pdf_b, filename=filename)
                await bot.send_document(uid, document=doc, caption=caption, parse_mode="HTML")
            except Exception:
                continue
        return

    # fallback: отправка по частям
    date_tag = report_date_iso.replace("-", "")
    for uid in user_ids:
        for name, pdf_b in parts:
            try:
                fn = f"{name}_{date_tag}.pdf"
                doc = BufferedInputFile(pdf_b, filename=fn)
                await bot.send_document(uid, document=doc)
            except Exception:
                continue


__all__ = ["send_daily_deadline_and_pdfs"]
