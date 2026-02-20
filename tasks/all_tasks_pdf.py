# tasks/all_tasks_pdf.py
from __future__ import annotations

import os, sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from aiogram import Router, types, F
from aiogram.types import FSInputFile
from fpdf import FPDF

from config      import ADMIN_IDS, TASK_VIEWERS
from db          import DB_PATH
from tasks.menu  import get_tasks_menu

router = Router()

# ─────────────────────────────────────────────────────────────────────────────
EXCLUDED_STATUSES = [
    "Завершена", "Отклонена",              # русские
    "completed", "done", "rejected", "canceled",
]

STATUS_RU = {
    "new":          "Ожидание",
    "pending":      "Ожидание",
    "in_progress":  "В работе",
    "wait_confirm": "Ожидает подтверждения",
    "overdue":      "Просрочена",
    "rejected":     "Отклонена",
    "canceled":     "Отклонена",
    "completed":    "Завершена",
    "done":         "Завершена",
    "Завершена":    "Завершена",
    "Отклонена":    "Отклонена",
}
def get_status_ru(code: str) -> str:
    return STATUS_RU.get(code, code)

# ───────── вспом-функции ────────────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def _group_by_user(rows: list[sqlite3.Row]) -> dict[int, dict]:
    """Группируем задачи по исполнителю."""
    grouped: dict[int, dict] = {}
    for r in rows:
        uid = r["assignee_id"]
        grouped.setdefault(
            uid,
            {
                "name":          r["assignee_name"] or "Неизвестно",
                "tasks":         [],
                "total_penalty": r["total_penalty"] or 0,
            },
        )
        grouped[uid]["tasks"].append(r)
    return grouped

def _safe(text: str) -> str:
    """fpdf2 ≤ 2.x не умеет символы > 0xFFFF → уберём эмодзи и прочее."""
    return "".join(ch for ch in text if ord(ch) <= 0xFFFF)

# ─────────────────────────────────────────────────────────────────────────────
@router.message(F.text == "Все задачи")
async def send_all_tasks_pdf(message: types.Message):
    uid = message.from_user.id
    if uid not in (*ADMIN_IDS, *TASK_VIEWERS):
        await message.answer("⛔ У вас нет доступа к этому разделу.", reply_markup=get_tasks_menu())
        return

    # Период – текущий месяц
    now          = datetime.now()
    month_start  = now.replace(day=1).strftime("%Y-%m-%d")
    month_end    = (now.replace(day=28) + timedelta(days=4)).replace(day=1).strftime("%Y-%m-%d")

    excl_q  = ",".join("?" for _ in EXCLUDED_STATUSES)
    admin_q = ",".join("?" for _ in ADMIN_IDS)

    with _conn() as con:
        cur  = con.cursor()
        base = f"""
            SELECT  t.id, t.title, t.description, t.deadline, t.status,
                    t.created_at, t.global_num,
                    u.user_id   AS assignee_id,
                    u.full_name AS assignee_name,
                    cr.full_name AS creator_name,
                    (
                        SELECT SUM(f.amount)
                        FROM   fines f
                        WHERE  f.user_id = u.user_id
                          AND  date(f.created_at) >= date(?)
                          AND  date(f.created_at) <  date(?)
                    ) AS total_penalty
            FROM   tasks t
            LEFT JOIN users u  ON u.user_id  = t.assigned_to
            LEFT JOIN users cr ON cr.user_id = t.assigned_by
            WHERE  t.assigned_to NOT IN ({admin_q})
        """

        # активные
        cur.execute(
            base + f" AND t.status NOT IN ({excl_q}) ORDER BY t.assigned_to, t.deadline",
            (month_start, month_end, *ADMIN_IDS, *EXCLUDED_STATUSES),
        )
        active_rows = cur.fetchall()

        # завершённые («done» и «Завершена»)
        cur.execute(
            base + " AND t.status IN ('done','Завершена') ORDER BY t.assigned_to, t.deadline",
            (month_start, month_end, *ADMIN_IDS),
        )
        done_rows = cur.fetchall()

    active = _group_by_user(active_rows)
    done   = _group_by_user(done_rows)

    # ───────── генерируем PDF ───────────────────────────────────────────────
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)

    # шрифт DejaVu (полная кириллица); если нет — останется Core/Helvetica
    FONT_DIR = Path(__file__).parent / "fonts"
    ttf_path = (
        FONT_DIR / "DejaVuSans.ttf"
        if (FONT_DIR / "DejaVuSans.ttf").exists()
        else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    )
    FONT = "Core"
    try:
        pdf.add_font("DejaVu", "", str(ttf_path), uni=True)
        pdf.add_font("DejaVu", "B", str(ttf_path.with_name("DejaVuSans-Bold.ttf")), uni=True)
        FONT = "DejaVu"
    except Exception:
        pass

    def header(title: str):
        pdf.set_font(FONT, "B" if FONT != "Core" else "", 16)
        pdf.cell(0, 10, _safe(title), ln=1, align="C")
        pdf.set_font(FONT, "", 12)
        pdf.cell(0, 8, f"Период: {now.strftime('%B %Y')}", ln=1, align="C")
        pdf.ln(8)

    def user_block(info: dict, completed: bool = False):
        pdf.set_font(FONT, "B", 12)
        pdf.cell(0, 8, _safe(f"Исполнитель: {info['name']}"), ln=1)
        pdf.set_font(FONT, "", 10)
        pdf.cell(0, 6, f"Сумма штрафов: {info['total_penalty']} руб.", ln=1)
        pdf.ln(2)

        for t in info["tasks"]:
            deadline = (
                datetime.strptime(t["deadline"], "%Y-%m-%d").strftime("%d.%m.%Y")
                if t["deadline"] else "не указан"
            )
            created  = datetime.strptime(t["created_at"], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")

            pdf.set_font(FONT, "B", 10)
            pdf.cell(0, 6, _safe(f"#{t['global_num']} {t['title']} ({get_status_ru(t['status'])})"), ln=1)

            pdf.set_font(FONT, "", 10)
            pdf.cell(0, 6, _safe(f"Постановщик: {t['creator_name'] or 'Неизвестно'}"), ln=1)
            pdf.cell(0, 6, f"Создана: {created} | Срок: {deadline}", ln=1)
            if t["description"]:
                pdf.multi_cell(0, 6, _safe(f"Описание: {t['description']}"))
            pdf.ln(2)

        # краткая статистика
        if not completed:
            sts   = [get_status_ru(t["status"]) for t in info["tasks"]]
            stats = {s: sts.count(s) for s in ("В работе", "Ожидание", "Ожидает подтверждения",
                                               "Просрочена", "Отклонена")}
            pdf.set_font(FONT, "B", 10)
            pdf.cell(0, 6, "Статистика:", ln=1)
            pdf.set_font(FONT, "", 10)
            pdf.cell(50, 6, f"Всего активных: {len(info['tasks'])}")
            pdf.cell(50, 6, f"В работе: {stats.get('В работе', 0)}")
            pdf.cell(0,  6, f"На подтверждении: {stats.get('Ожидает подтверждения', 0)}", ln=1)
            pdf.cell(50, 6, f"Ожидание: {stats.get('Ожидание', 0)}")
            pdf.cell(50, 6, f"Просрочено: {stats.get('Просрочена', 0)}")
            pdf.cell(0,  6, f"Отклонено: {stats.get('Отклонена', 0)}", ln=1)
        else:
            pdf.set_font(FONT, "", 10)
            pdf.cell(0, 6, f"Всего завершено: {len(info['tasks'])}", ln=1)
        pdf.ln(8)

    # --- активные задачи
    pdf.add_page()
    header("Активные задачи")
    for u in active.values():
        user_block(u, completed=False)

    # --- завершённые задачи
    if done:
        pdf.add_page()
        header("Завершённые задачи")
        for u in done.values():
            user_block(u, completed=True)

    # ───────── отправляем файл ───────────────────────────────────────────────
    file_name = f"tasks_report_{now.strftime('%Y%m')}_{uid}.pdf"
    pdf.output(file_name)

    await message.answer_document(
        FSInputFile(file_name),
        caption=(
            f"📊 Сводный отчёт за {now.strftime('%B %Y')}\n"
            f"• Активные задачи: {len(active_rows)}\n"
            f"• Завершённые задачи: {len(done_rows)}"
        ),
        reply_markup=get_tasks_menu(),
    )
    try:
        os.remove(file_name)
    except Exception:
        pass
