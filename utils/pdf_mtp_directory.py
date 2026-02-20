from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

from utils.pdf_common import add_title, new_pdf, section, table, pdf_bytes


def build_mtp_directory_pdf_bytes(title: str, items: List[Dict[str, Any]]) -> bytes:
    pdf, font, theme = new_pdf(orientation="L")

    subtitle = f"Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    add_title(pdf, font, theme, title, subtitle)

    section(pdf, font, theme, f"Записей: {len(items)}")

    headers = ["ID", "Подразделение", "Техника", "Инв./гос №", "Год", "Ответственный", "Комментарий"]
    widths = [10, 38, 70, 32, 18, 55, 55]
    aligns = ["C", "L", "L", "L", "C", "L", "L"]

    rows: List[List[str]] = []
    for it in items:
        rows.append([
            str(it.get("id", "")),
            str(it.get("unit_name", "")),
            str(it.get("equipment_name", "")),
            str(it.get("inv_number", "")),
            str(it.get("year", "") or "-"),
            str(it.get("responsible", "")),
            str(it.get("comment", "") or "-"),
        ])

    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns)
    return pdf_bytes(pdf)


# Совместимость со старым импортом:
# from utils.pdf_mtp_directory import build_mtp_directory_pdf
def build_mtp_directory_pdf(
    items: List[Dict[str, Any]],
    org_title: str = "ЖК «Актюба»",
    report_title: str = "Справочник МТП",
) -> Tuple[bytes, str]:
    title = f"{report_title} — {org_title}" if org_title else report_title
    b = build_mtp_directory_pdf_bytes(title, items)
    filename = f"spravochnik_mtp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return b, filename


__all__ = ["build_mtp_directory_pdf_bytes", "build_mtp_directory_pdf"]
