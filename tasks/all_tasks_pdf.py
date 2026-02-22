# tasks/all_tasks_pdf.py — красивый PDF «Все задачи» по отделам/блокам
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from aiogram import Router, types, F
from aiogram.types import BufferedInputFile

from config import ADMIN_IDS, TASK_VIEWERS
from db import db
from tasks.menu import get_tasks_menu
from utils.pdf_common import new_pdf, add_title, section, table, pdf_bytes, safe_text

router = Router()

EXCLUDED_STATUSES = [
    "Завершена", "Отклонена",
    "completed", "done", "rejected", "canceled",
]

STATUS_RU = {
    "new": "Ожидание",
    "pending": "Ожидание",
    "in_progress": "В работе",
    "wait_confirm": "На подтверждении",
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


async def _fetch_tasks(admin_ids: List[int], excluded_statuses: List[str]) -> Tuple[List[Dict], List[Dict]]:
    """Возвращает (active_rows, done_rows) с полями department, block, assignee_name и т.д."""
    place_admins = ",".join("?" for _ in admin_ids)
    place_excl = ",".join("?" for _ in excluded_statuses)

    q = f"""
        SELECT
            t.id, t.global_num, t.title, t.description, t.deadline, t.status, t.created_at,
            u.user_id AS assignee_id,
            COALESCE(NULLIF(TRIM(u.full_name), ''), '—') AS assignee_name,
            COALESCE(NULLIF(TRIM(u.department), ''), '—') AS department,
            COALESCE(NULLIF(TRIM(u.block), ''), '—') AS block,
            COALESCE(NULLIF(TRIM(cr.full_name), ''), '—') AS creator_name
        FROM tasks t
        LEFT JOIN users u  ON u.user_id = t.assigned_to
        LEFT JOIN users cr ON cr.user_id = t.assigned_by
        WHERE t.assigned_to NOT IN ({place_admins})
    """

    # активные (не завершённые и не отклонённые)
    active = await db.execute_query(
        q + f" AND t.status NOT IN ({place_excl}) ORDER BY u.department, u.block, t.deadline, t.id",
        (*admin_ids, *excluded_statuses),
    )
    active = active or []

    # завершённые
    done = await db.execute_query(
        q + " AND t.status IN ('completed','done','Завершена') ORDER BY u.department, u.block, t.deadline, t.id",
        admin_ids,
    )
    done = done or []

    return active, done


def _group_by_dept_block(rows: List[Dict]) -> Dict[Tuple[str, str], List[Dict]]:
    out: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
    for r in rows:
        dept = (r.get("department") or "—").strip() or "—"
        block = (r.get("block") or "—").strip() or "—"
        out[(dept, block)].append(r)
    return dict(out)


def _build_tasks_pdf(active_rows: List[Dict], done_rows: List[Dict], now: datetime) -> bytes:
    pdf, font, theme = new_pdf("P")
    subtitle = f"Период: {now.strftime('%d.%m.%Y %H:%M')}  |  Активных: {len(active_rows)}  |  Завершённых: {len(done_rows)}"
    add_title(pdf, font, theme, "Все задачи", subtitle)

    widths = [22, 50, 35, 22, 32]
    aligns = ["L", "L", "L", "C", "L"]
    headers = ["№", "Название", "Исполнитель", "Срок", "Статус"]

    def render_group(label: str, rows: List[Dict]) -> None:
        if not rows:
            return
        grouped = _group_by_dept_block(rows)
        for (dept, block), items in sorted(grouped.items(), key=lambda x: (x[0][0], x[0][1])):
            section_title = f"{dept}  /  {block}" if block and block != "—" else dept
            section(pdf, font, theme, section_title)
            table_rows = []
            for t in items:
                table_rows.append([
                    safe_text(t.get("global_num") or "—"),
                    safe_text((t.get("title") or "—")[:48]),
                    safe_text((t.get("assignee_name") or "—")[:28]),
                    _fmt_date(t.get("deadline")),
                    get_status_ru(t.get("status") or ""),
                ])
            table(pdf, font, theme, headers=headers, rows=table_rows,
                  widths=widths, aligns=aligns, data_font_size=9)

    if active_rows:
        section(pdf, font, theme, "Активные задачи")
        render_group("Активные", active_rows)

    if done_rows:
        section(pdf, font, theme, "Завершённые задачи")
        render_group("Завершённые", done_rows)

    if not active_rows and not done_rows:
        section(pdf, font, theme, "Нет задач")
        table(pdf, font, theme, headers=["Нет данных"], rows=[["Задачи не найдены или все назначены администраторам."]],
              widths=[pdf.w - pdf.l_margin - pdf.r_margin], aligns=["L"])

    return pdf_bytes(pdf)


async def get_all_tasks_pdf_bytes() -> Tuple[bytes, str]:
    """Сформировать PDF и подпись. Для кнопок «Все задачи» и «Список задач по отделам/блокам»."""
    now = datetime.now()
    active, done = await _fetch_tasks(ADMIN_IDS, EXCLUDED_STATUSES)
    pdf_b = _build_tasks_pdf(active, done, now)
    caption = (
        f"📋 Все задачи по отделам/блокам\n"
        f"• Активных: {len(active)}\n"
        f"• Завершённых: {len(done)}"
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
        BufferedInputFile(pdf_b, filename=f"vse_zadachi_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"),
        caption=caption,
        reply_markup=get_tasks_menu(),
    )
