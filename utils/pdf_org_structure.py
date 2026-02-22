from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple

from utils.pdf_common import new_pdf, add_title, section, table, pdf_bytes
from org.models import ORG_STRUCTURE


VACANT_COLOR = (180, 0, 0)
FILLED_COLOR = (0, 120, 0)

ZHK_DEPARTMENTS = [
    "Животноводческий комплекс «Актюба»",
    "1 отдел. Производство",
    "2 отдел. Ветеринария",
    "3 отдел. Инженерная служба",
    "4 отдел. Административно-хозяйственное обеспечение",
    "5 отдел. Бухгалтерия, учет",
]

OTDEL_POSITIONS = [
    ("Начальник отдела", "Салихов Ринат Аскатович"),
    ("Главный технолог", None),
    ("Главный ветеринарный врач", None),
    ("Главный инженер", None),
    ("Ведущий специалист по учету", None),
]

SUBDIVISIONS = ["Карамалы", "Шереметьево", "Бирючевка"]


def _build_assigned(users: List[Dict[str, Any]]) -> Dict[Tuple, List[str]]:
    assigned: Dict[Tuple, List[str]] = defaultdict(list)
    for r in users:
        fio = (r.get("full_name") or "").strip()
        dept = (r.get("department") or "").strip()
        block = (r.get("block") or "").strip()
        role = (r.get("role") or "").strip()
        if dept and role and fio:
            assigned[(dept, block, role)].append(fio)
    return assigned


def _find_staff(assigned: dict, dept: str, block: str, pos: str) -> List[str]:
    """Только точное совпадение (department, block, role). Учетчик (№1) и (№2) — разные должности."""
    return assigned.get((dept, block, pos), [])


def _users_by_dept(users: List[Dict[str, Any]], department: str) -> List[Dict[str, Any]]:
    return [u for u in users if (u.get("department") or "").strip() == department]


def _all_zhk_dept_names() -> Set[str]:
    names = {"Отдел животноводства"}
    for d in ZHK_DEPARTMENTS:
        names.add(d)
    return names


def build_org_pdf(users: List[Dict[str, Any]]) -> bytes:
    pdf, font, theme = new_pdf("P")
    subtitle = f"Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    add_title(pdf, font, theme, "Оргструктура — ООО «Союз-Агро»", subtitle)

    assigned = _build_assigned(users)
    widths = [90, 96]
    aligns = ["L", "L"]
    shown_user_ids: Set[str] = set()

    # ── 1. Отдел животноводства (фиксированные должности)
    section(pdf, font, theme, "Отдел животноводства")
    headers = ["Должность", "Сотрудник"]
    rows = []
    colors = []
    for pos, fixed_fio in OTDEL_POSITIONS:
        if fixed_fio:
            fio_text = fixed_fio
            row_c = [None, FILLED_COLOR]
            shown_user_ids.add(fixed_fio)
        else:
            staff = _find_staff(assigned, "Отдел животноводства", "Ключевые должности отдела", pos)
            if staff:
                fio_text = "\n".join(staff)
                row_c = [None, FILLED_COLOR]
                for s in staff:
                    shown_user_ids.add(s)
            else:
                fio_text = "Свободно"
                row_c = [None, VACANT_COLOR]
        rows.append([pos, fio_text])
        colors.append(row_c)

    otdel_extra = [u for u in _users_by_dept(users, "Отдел животноводства")
                   if (u.get("full_name") or "").strip() not in shown_user_ids]
    for u in otdel_extra:
        fio = (u.get("full_name") or "").strip()
        role = (u.get("role") or "").strip()
        rows.append([role or "—", fio])
        colors.append([None, FILLED_COLOR])
        shown_user_ids.add(fio)

    table(pdf, font, theme, headers=headers, rows=rows,
          widths=widths, aligns=aligns, cell_colors=colors)

    # ── 2. ЖК «Актюба» (из ORG_STRUCTURE)
    for dept_name in ZHK_DEPARTMENTS:
        blocks = ORG_STRUCTURE.get(dept_name)
        if not blocks:
            continue
        section(pdf, font, theme, dept_name)
        for block_name, positions in blocks.items():
            headers = [block_name, "Сотрудник"]
            rows = []
            colors = []
            for pos in positions:
                staff = _find_staff(assigned, dept_name, block_name, pos)
                if staff:
                    fio_text = "\n".join(staff)
                    row_c = [None, FILLED_COLOR]
                    for s in staff:
                        shown_user_ids.add(s)
                else:
                    fio_text = "Свободно"
                    row_c = [None, VACANT_COLOR]
                rows.append([pos, fio_text])
                colors.append(row_c)
            table(pdf, font, theme, headers=headers, rows=rows,
                  widths=widths, aligns=aligns, cell_colors=colors)

        dept_users = _users_by_dept(users, dept_name)
        extra = [u for u in dept_users
                 if (u.get("full_name") or "").strip() not in shown_user_ids]
        if extra:
            headers = ["Прочие должности", "Сотрудник"]
            rows = []
            colors = []
            for u in extra:
                fio = (u.get("full_name") or "").strip()
                role = (u.get("role") or "").strip()
                rows.append([role or "—", fio])
                colors.append([None, FILLED_COLOR])
                shown_user_ids.add(fio)
            table(pdf, font, theme, headers=headers, rows=rows,
                  widths=widths, aligns=aligns, cell_colors=colors)

    # ── 3. Карамалы, Шереметьево, Бирючевка (из БД)
    for subdiv in SUBDIVISIONS:
        staff = _users_by_dept(users, subdiv)
        section(pdf, font, theme, subdiv)
        headers = ["Должность", "Сотрудник"]
        rows = []
        colors = []
        for u in staff:
            fio = (u.get("full_name") or "").strip()
            role = (u.get("role") or "").strip()
            rows.append([role or "—", fio or "—"])
            colors.append([None, FILLED_COLOR])
            shown_user_ids.add(fio)
        if not rows:
            rows.append(["—", "Нет сотрудников"])
            colors.append([None, VACANT_COLOR])
        table(pdf, font, theme, headers=headers, rows=rows,
              widths=widths, aligns=aligns, cell_colors=colors)

    # ── 4. Пользователи не попавшие ни в одну секцию
    zhk_depts = _all_zhk_dept_names()
    subdiv_set = set(SUBDIVISIONS)
    remaining = [u for u in users
                 if (u.get("full_name") or "").strip() not in shown_user_ids
                 and (u.get("department") or "").strip() not in zhk_depts
                 and (u.get("department") or "").strip() not in subdiv_set]
    if remaining:
        section(pdf, font, theme, "Прочие сотрудники")
        headers = ["Должность", "Сотрудник"]
        rows = []
        colors = []
        for u in remaining:
            fio = (u.get("full_name") or "").strip()
            role = (u.get("role") or "").strip()
            dept = (u.get("department") or "").strip()
            rows.append([f"{role} ({dept})" if dept else role or "—", fio or "—"])
            colors.append([None, FILLED_COLOR])
        table(pdf, font, theme, headers=headers, rows=rows,
              widths=widths, aligns=aligns, cell_colors=colors)

    return pdf_bytes(pdf)
