# tasks/all_tasks_pdf.py — красивый PDF «Все задачи» (по исполнителям, как было)
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from aiogram import Router, types, F
from aiogram.types import BufferedInputFile

from config import ADMIN_IDS, TASK_VIEWERS
from db import db
from tasks.menu import get_tasks_menu
from utils.pdf_common import (
    new_pdf,
    add_title,
    section,
    table,
    pdf_bytes,
    safe_text,
    set_font,
    _merge_theme,
)

router = Router()

EXCLUDED_STATUSES = [
    "Завершена",
    "Отклонена",
    "completed",
    "done",
    "rejected",
    "canceled",
]

STATUS_RU = {
    "new": "Ожидание",
    "pending": "Ожидание",
    "in_progress": "В работе",
    "wait_confirm": "Ожидает подтверждения",
    "overdue": "Просрочена",
    "rejected": "Отклонена",
    "canceled": "Отклонена",
    "completed": "Завершена",
    "done": "Завершена",
    "Завершена": "Завершена",
    "Отклонена": "Отклонена",
}


def get_status_ru(code: str) -> str:
    return STATUS_RU.get(code, code or "—")


def _fmt_date(s: str | None) -> str:
    if not s:
        return "—"
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return s


def _fmt_datetime(s: str | None) -> str:
    if not s:
        return "—"
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
    except Exception:
        try:
            return _fmt_date(s)
        except Exception:
            return s


async def _fetch_penalties_by_user(month_start: str, month_end: str) -> Dict[int, int]:
    """Сумма штрафов по пользователям за период (текущий месяц)."""
    rows = await db.execute_query(
        """
        SELECT user_id, COALESCE(SUM(amount), 0) AS total_penalty
        FROM fines
        WHERE date(created_at) >= date(?)
          AND date(created_at) < date(?)
        GROUP BY user_id
        """,
        (month_start, month_end),
    )
    return {r["user_id"]: int(r.get("total_penalty") or 0) for r in (rows or [])}


async def _fetch_tasks(
    admin_ids: List[int],
    excluded_statuses: List[str],
) -> Tuple[List[Dict], List[Dict]]:
    """Возвращает (active_rows, done_rows) с полями постановщик, создана, срок, описание и т.д."""
    place_admins = ",".join("?" for _ in admin_ids)
    place_excl = ",".join("?" for _ in excluded_statuses)

    q = f"""
        SELECT
            t.id, t.global_num, t.title, t.description, t.deadline, t.status, t.created_at,
            u.user_id AS assignee_id,
            COALESCE(NULLIF(TRIM(u.full_name), ''), 'Неизвестно') AS assignee_name,
            COALESCE(NULLIF(TRIM(cr.full_name), ''), 'Неизвестно') AS creator_name
        FROM tasks t
        LEFT JOIN users u  ON u.user_id = t.assigned_to
        LEFT JOIN users cr ON cr.user_id = t.assigned_by
        WHERE t.assigned_to NOT IN ({place_admins})
    """

    active = await db.execute_query(
        q + f" AND t.status NOT IN ({place_excl}) ORDER BY t.assigned_to, t.deadline, t.id",
        (*admin_ids, *excluded_statuses),
    )
    active = active or []

    done = await db.execute_query(
        q + " AND t.status IN ('completed','done','Завершена') ORDER BY t.assigned_to, t.deadline, t.id",
        admin_ids,
    )
    done = done or []

    return active, done


def _group_by_user(rows: List[Dict]) -> Dict[int, Dict[str, Any]]:
    """Группировка по исполнителю (assignee_id)."""
    grouped: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        uid = r.get("assignee_id")
        if uid is None:
            uid = 0
        if uid not in grouped:
            grouped[uid] = {
                "name": r.get("assignee_name") or "Неизвестно",
                "tasks": [],
            }
        grouped[uid]["tasks"].append(r)
    return grouped


def _build_tasks_pdf(
    active_rows: List[Dict],
    done_rows: List[Dict],
    penalties: Dict[int, int],
    now: datetime,
) -> bytes:
    pdf, font, theme = new_pdf("P")
    th = _merge_theme(theme)

    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    month_end = (now.replace(day=28) + timedelta(days=4)).replace(day=1).strftime("%Y-%m-%d")

    subtitle = (
        f"Период: {now.strftime('%B %Y')}  |  "
        f"Активных: {len(active_rows)}  |  Завершённых: {len(done_rows)}"
    )
    add_title(pdf, font, theme, "Все задачи", subtitle)

    # Колонки: № | Название | Постановщик | Создана | Срок | Статус
    widths = [20, 48, 32, 22, 22, 28]
    aligns = ["L", "L", "L", "C", "C", "L"]
    headers = ["№", "Название", "Постановщик", "Создана", "Срок", "Статус"]

    def row_from_task(t: Dict) -> List[str]:
        title = (t.get("title") or "—")
        desc = (t.get("description") or "").strip()
        if desc:
            title = f"{title[:42]}…" if len(title) > 45 else title
        return [
            safe_text(t.get("global_num") or "—"),
            safe_text(title)[:50],
            safe_text((t.get("creator_name") or "—")[:28]),
            _fmt_datetime(t.get("created_at")),
            _fmt_date(t.get("deadline")),
            get_status_ru(t.get("status") or ""),
        ]

    def stats_line(tasks: List[Dict]) -> Dict[str, int]:
        sts = [get_status_ru(t.get("status")) for t in tasks]
        return {
            "В работе": sts.count("В работе"),
            "Ожидание": sts.count("Ожидание"),
            "Ожидает подтверждения": sts.count("Ожидает подтверждения"),
            "Просрочена": sts.count("Просрочена"),
            "Отклонена": sts.count("Отклонена"),
        }

    # —— Активные задачи (по исполнителям) ——
    if active_rows:
        section(pdf, font, theme, "Активные задачи")
        active_by_user = _group_by_user(active_rows)
        for assignee_id, info in sorted(active_by_user.items(), key=lambda x: (x[1]["name"], x[0])):
            name = info["name"]
            tasks = info["tasks"]
            penalty = penalties.get(assignee_id, 0)

            # Подзаголовок: Исполнитель + Сумма штрафов
            pdf.ln(1)
            set_font(pdf, bold=True, size=11)
            pdf.set_text_color(*th["text"])
            pdf.cell(0, 6, safe_text(f"Исполнитель: {name}"), ln=1)
            set_font(pdf, bold=False, size=10)
            pdf.set_text_color(*th["muted"])
            pdf.cell(0, 5, f"Сумма штрафов за период: {penalty} руб.", ln=1)
            pdf.set_text_color(*th["text"])
            pdf.ln(2)

            table_rows = [row_from_task(task) for task in tasks]
            table(pdf, font, theme, headers=headers, rows=table_rows, widths=widths, aligns=aligns, data_font_size=9)

            # Описание под таблицей для каждой задачи (если есть)
            for task in tasks:
                desc = (task.get("description") or "").strip()
                if desc:
                    set_font(pdf, bold=False, size=8)
                    pdf.set_text_color(*th["muted"])
                    pdf.cell(0, 4, safe_text(f"  #{task.get('global_num') or ''} Описание: {desc[:80]}{'…' if len(desc) > 80 else ''}"), ln=1)
                    pdf.set_text_color(*th["text"])

            # Статистика по исполнителю
            stats = stats_line(tasks)
            set_font(pdf, bold=True, size=9)
            pdf.cell(0, 5, "Статистика:", ln=1)
            set_font(pdf, bold=False, size=9)
            pdf.cell(45, 5, f"Всего активных: {len(tasks)}")
            pdf.cell(45, 5, f"В работе: {stats['В работе']}")
            pdf.cell(0, 5, f"На подтверждении: {stats['Ожидает подтверждения']}", ln=1)
            pdf.cell(45, 5, f"Ожидание: {stats['Ожидание']}")
            pdf.cell(45, 5, f"Просрочено: {stats['Просрочена']}")
            pdf.cell(0, 5, f"Отклонено: {stats['Отклонена']}", ln=1)
            pdf.ln(6)

    # —— Завершённые задачи (по исполнителям) ——
    if done_rows:
        section(pdf, font, theme, "Завершённые задачи")
        done_by_user = _group_by_user(done_rows)
        for assignee_id, info in sorted(done_by_user.items(), key=lambda x: (x[1]["name"], x[0])):
            name = info["name"]
            tasks = info["tasks"]
            penalty = penalties.get(assignee_id, 0)

            pdf.ln(1)
            set_font(pdf, bold=True, size=11)
            pdf.set_text_color(*th["text"])
            pdf.cell(0, 6, safe_text(f"Исполнитель: {name}"), ln=1)
            set_font(pdf, bold=False, size=10)
            pdf.set_text_color(*th["muted"])
            pdf.cell(0, 5, f"Сумма штрафов за период: {penalty} руб.", ln=1)
            pdf.set_text_color(*th["text"])
            pdf.ln(2)

            table_rows = [row_from_task(task) for task in tasks]
            table(pdf, font, theme, headers=headers, rows=table_rows, widths=widths, aligns=aligns, data_font_size=9)
            set_font(pdf, bold=False, size=9)
            pdf.cell(0, 5, f"Всего завершено: {len(tasks)}", ln=1)
            pdf.ln(6)

    if not active_rows and not done_rows:
        section(pdf, font, theme, "Нет задач")
        table(
            pdf,
            font,
            theme,
            headers=["Нет данных"],
            rows=[["Задачи не найдены или все назначены администраторам."]],
            widths=[pdf.w - pdf.l_margin - pdf.r_margin],
            aligns=["L"],
        )

    return pdf_bytes(pdf)


async def get_all_tasks_pdf_bytes() -> Tuple[bytes, str]:
    """Сформировать PDF и подпись. Для кнопок «Все задачи» и «Список задач по отделам/блокам»."""
    now = datetime.now()
    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    month_end = (now.replace(day=28) + timedelta(days=4)).replace(day=1).strftime("%Y-%m-%d")

    penalties = await _fetch_penalties_by_user(month_start, month_end)
    active, done = await _fetch_tasks(ADMIN_IDS, EXCLUDED_STATUSES)
    pdf_b = _build_tasks_pdf(active, done, penalties, now)

    caption = (
        f"📊 Сводный отчёт за {now.strftime('%B %Y')}\n"
        f"• Активные задачи: {len(active)}\n"
        f"• Завершённые задачи: {len(done)}"
    )
    return pdf_b, caption


@router.message(F.text == "Все задачи")
async def send_all_tasks_pdf(message: types.Message):
    uid = message.from_user.id
    if uid not in (*ADMIN_IDS, *TASK_VIEWERS):
        await message.answer("⛔ У вас нет доступа к этому разделу.", reply_markup=get_tasks_menu())
        return
    pdf_b, caption = await get_all_tasks_pdf_bytes()
    await message.answer_document(
        BufferedInputFile(pdf_b, filename=f"tasks_report_{datetime.now().strftime('%Y%m')}_{uid}.pdf"),
        caption=caption,
        reply_markup=get_tasks_menu(),
    )
