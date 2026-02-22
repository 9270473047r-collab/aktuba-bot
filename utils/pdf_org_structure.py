from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Tuple

from utils.pdf_common import (
    new_pdf, add_title, section, table, pdf_bytes, set_font, safe_text,
    _ensure_space,
)
from org.models import ORG_STRUCTURE


DEPT_COLOR = (30, 80, 160)
BLOCK_COLOR = (60, 60, 60)
ROLE_COLOR = (0, 0, 0)
VACANT_COLOR = (180, 0, 0)
FILLED_COLOR = (0, 120, 0)


def _fio_short(fio: str) -> str:
    parts = (fio or "").split()
    if len(parts) >= 2:
        res = f"{parts[0]} {parts[1][0]}."
        if len(parts) > 2:
            res += f"{parts[2][0]}."
        return res
    return fio or "—"


def _build_assigned(users: List[Dict[str, Any]]) -> Dict[Tuple, List[str]]:
    assigned: Dict[Tuple, List[str]] = defaultdict(list)
    for r in users:
        fio = r.get("full_name") or ""
        dept = (r.get("department") or "").strip()
        block = (r.get("block") or "").strip()
        role = (r.get("role") or "").strip()
        role_clean = role.split(" (")[0].strip() if role else ""
        if dept and block and role_clean:
            assigned[(dept, block, role_clean)].append(_fio_short(fio))
    return assigned


def _render_department(pdf, font, theme, dept_name: str, blocks: dict,
                       assigned: dict, widths, aligns):
    section(pdf, font, theme, dept_name)

    for block_name, positions in blocks.items():
        headers = [block_name, "Сотрудник"]
        rows = []
        colors = []
        for pos in positions:
            staff = assigned.get((dept_name, block_name, pos), [])
            if staff:
                fio_text = ", ".join(staff)
                row_c = [None, FILLED_COLOR]
            else:
                fio_text = "Свободно"
                row_c = [None, VACANT_COLOR]
            rows.append([pos, fio_text])
            colors.append(row_c)
        table(pdf, font, theme, headers=headers, rows=rows,
              widths=widths, aligns=aligns, cell_colors=colors)


def build_org_pdf_full(users: List[Dict[str, Any]]) -> bytes:
    """Полная оргструктура: Отдел -> ЖК -> остальные."""
    pdf, font, theme = new_pdf("P")
    subtitle = f"Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    add_title(pdf, font, theme, "Оргструктура — ООО «Союз-Агро»", subtitle)

    assigned = _build_assigned(users)
    widths = [90, 96]
    aligns = ["L", "L"]

    order = [
        "Отдел животноводства",
        "Животноводческий комплекс «Актюба»",
        "1 отдел. Производство",
        "2 отдел. Ветеринария",
        "3 отдел. Инженерная служба",
        "4 отдел. Административно-хозяйственное обеспечение",
        "5 отдел. Бухгалтерия, учет",
    ]

    for dept_name in order:
        blocks = ORG_STRUCTURE.get(dept_name)
        if blocks:
            _render_department(pdf, font, theme, dept_name, blocks, assigned, widths, aligns)

    return pdf_bytes(pdf)


def build_org_pdf_zhk(users: List[Dict[str, Any]]) -> bytes:
    """Оргструктура ЖК «Актюба» (все отделы ЖК, без Отдела животноводства)."""
    pdf, font, theme = new_pdf("P")
    subtitle = f"Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    add_title(pdf, font, theme, "Оргструктура — ЖК «Актюба»", subtitle)

    assigned = _build_assigned(users)
    widths = [90, 96]
    aligns = ["L", "L"]

    order = [
        "Животноводческий комплекс «Актюба»",
        "1 отдел. Производство",
        "2 отдел. Ветеринария",
        "3 отдел. Инженерная служба",
        "4 отдел. Административно-хозяйственное обеспечение",
        "5 отдел. Бухгалтерия, учет",
    ]

    for dept_name in order:
        blocks = ORG_STRUCTURE.get(dept_name)
        if blocks:
            _render_department(pdf, font, theme, dept_name, blocks, assigned, widths, aligns)

    return pdf_bytes(pdf)


def build_org_pdf_subdivision(users: List[Dict[str, Any]], subdivision: str) -> bytes:
    """Оргструктура для Карамалы / Шереметьево / Бирючевка — список сотрудников."""
    pdf, font, theme = new_pdf("P")
    subtitle = f"Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    add_title(pdf, font, theme, f"Оргструктура — {subdivision}", subtitle)

    staff = [u for u in users if (u.get("department") or "").strip() == subdivision]

    section(pdf, font, theme, subdivision)
    headers = ["ФИО", "Должность"]
    widths = [100, 86]
    aligns = ["L", "L"]
    rows = []
    for u in staff:
        fio = _fio_short(u.get("full_name") or "")
        role = (u.get("role") or "").strip()
        rows.append([fio, role])

    if not rows:
        rows.append(["Нет сотрудников", ""])

    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns)

    return pdf_bytes(pdf)
