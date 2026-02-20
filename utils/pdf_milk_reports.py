from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

from utils.pdf_common import add_title, new_pdf, section, kv, table, pdf_bytes


MILK_DENSITY_DEFAULT = 1.03


def _to_float(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        return float(str(x).replace(" ", "").replace(",", "."))
    except Exception:
        return 0.0


def _fmt_int(x: Any) -> str:
    try:
        return f"{int(round(_to_float(x))):,}".replace(",", " ")
    except Exception:
        return "0"


def _fmt_float(x: Any, digits: int = 2) -> str:
    try:
        return f"{_to_float(x):.{digits}f}"
    except Exception:
        return "0"


def calc_gross_kg(d: Dict[str, Any], density: float) -> float:
    milk_total_l = _to_float(d.get("milk_total_l"))
    milk_small_l = _to_float(d.get("milk_small_l"))
    return (milk_total_l + milk_small_l) * density


def calc_sale_kg(d: Dict[str, Any], density: float) -> float:
    milk_buyer_l = _to_float(d.get("milk_buyer_l"))
    milk_trade_l = _to_float(d.get("milk_trade_l"))
    milk_sold_l = _to_float(d.get("milk_sold_l"))
    if milk_sold_l > 0:
        sold_l = milk_sold_l
    else:
        sold_l = milk_buyer_l + milk_trade_l
    return sold_l * density


def build_milk_daily_pdf_bytes(
    location_title: str,
    report_date_iso: str,
    d: Dict[str, Any],
    include_fact: bool = False,
    density: float = MILK_DENSITY_DEFAULT,
) -> bytes:
    pdf, font, theme = new_pdf("P")

    date_str = datetime.strptime(report_date_iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    subtitle = f"{location_title} | Дата: {date_str} | Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    add_title(pdf, font, theme, "Сводка по молоку", subtitle)

    gross_kg = calc_gross_kg(d, density)
    sold_kg = calc_sale_kg(d, density)

    calves_kg = _to_float(d.get("milk_calves_l")) * density
    disposal_kg = _to_float(d.get("milk_disposal_l")) * density
    tank_total_kg = _to_float(d.get("milk_tank_total_kg"))
    fat = _to_float(d.get("fat_pct"))
    protein = _to_float(d.get("protein_pct"))

    section(pdf, font, theme, "Итоги")
    kv(pdf, font, "Валовый надой (кг):", _fmt_int(gross_kg))
    if include_fact:
        kv(pdf, font, "Факт валовый (кг):", _fmt_int(d.get("gross_fact_kg")))
        kv(pdf, font, "Отклонение факт−расчёт (кг):", _fmt_int(_to_float(d.get("gross_fact_kg")) - gross_kg))
    kv(pdf, font, "Реализация (кг):", _fmt_int(sold_kg))
    kv(pdf, font, "На выпойку (кг):", _fmt_int(calves_kg))
    kv(pdf, font, "Утиль (кг):", _fmt_int(disposal_kg))
    kv(pdf, font, "Танк (кг):", _fmt_int(tank_total_kg))

    section(pdf, font, theme, "Качество")
    kv(pdf, font, "Жир (%):", _fmt_float(fat, 2))
    kv(pdf, font, "Белок (%):", _fmt_float(protein, 2))

    section(pdf, font, theme, "Детализация")
    kv(pdf, font, "Молокопровод (л):", _fmt_int(d.get("milk_total_l")))
    kv(pdf, font, "Малая ферма (л):", _fmt_int(d.get("milk_small_l")))
    kv(pdf, font, "Покупатель (л):", _fmt_int(d.get("milk_buyer_l")))
    kv(pdf, font, "Население (л):", _fmt_int(d.get("milk_trade_l")))
    kv(pdf, font, "Всего реализовано (л):", _fmt_int(d.get("milk_sold_l")))

    return pdf_bytes(pdf)


def build_milk_monthly_pdf_bytes(
    location_title: str,
    month_start_iso: str,
    month_end_iso: str,
    reports: List[Tuple[str, Dict[str, Any]]],
    include_fact: bool = False,
    density: float = MILK_DENSITY_DEFAULT,
) -> bytes:
    pdf, font, theme = new_pdf("L")

    period_label = f"Период: {month_start_iso} — {month_end_iso}"
    subtitle = f"{location_title} | {period_label} | Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    add_title(pdf, font, theme, "Сводка по молоку — месяц", subtitle)

    section(pdf, font, theme, f"Записей: {len(reports)}")

    headers = ["Дата", "Валовый кг", "Реализация кг", "Выпойка кг", "Утиль кг", "Танк кг", "Жир %", "Белок %"]
    widths = [22, 28, 30, 26, 22, 24, 18, 20]
    aligns = ["C", "R", "R", "R", "R", "R", "R", "R"]

    if include_fact:
        headers.insert(2, "Факт кг")
        widths.insert(2, 26)
        aligns.insert(2, "R")

    rows: List[List[str]] = []
    tot_gross = tot_fact = tot_sold = tot_calves = tot_disp = tot_tank = 0.0
    fat_vals: List[float] = []
    prot_vals: List[float] = []

    for report_date_iso, d in reports:
        date_str = datetime.strptime(report_date_iso, "%Y-%m-%d").strftime("%d.%m")
        gross_kg = calc_gross_kg(d, density)
        sold_kg = calc_sale_kg(d, density)
        calves_kg = _to_float(d.get("milk_calves_l")) * density
        disp_kg = _to_float(d.get("milk_disposal_l")) * density
        tank_kg = _to_float(d.get("milk_tank_total_kg"))
        fat = _to_float(d.get("fat_pct"))
        prot = _to_float(d.get("protein_pct"))

        tot_gross += gross_kg
        tot_sold += sold_kg
        tot_calves += calves_kg
        tot_disp += disp_kg
        tot_tank += tank_kg
        if fat > 0:
            fat_vals.append(fat)
        if prot > 0:
            prot_vals.append(prot)

        row = [date_str, _fmt_int(gross_kg)]
        if include_fact:
            fact_kg = _to_float(d.get("gross_fact_kg"))
            tot_fact += fact_kg
            row.append(_fmt_int(fact_kg))
        row += [
            _fmt_int(sold_kg),
            _fmt_int(calves_kg),
            _fmt_int(disp_kg),
            _fmt_int(tank_kg),
            _fmt_float(fat, 2),
            _fmt_float(prot, 2),
        ]
        rows.append(row)

    avg_fat = sum(fat_vals) / len(fat_vals) if fat_vals else 0.0
    avg_prot = sum(prot_vals) / len(prot_vals) if prot_vals else 0.0

    total_row = ["ИТОГО", _fmt_int(tot_gross)]
    if include_fact:
        total_row.append(_fmt_int(tot_fact))
    total_row += [
        _fmt_int(tot_sold),
        _fmt_int(tot_calves),
        _fmt_int(tot_disp),
        _fmt_int(tot_tank),
        _fmt_float(avg_fat, 2),
        _fmt_float(avg_prot, 2),
    ]
    rows.append(total_row)

    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns)

    return pdf_bytes(pdf)


__all__ = [
    "build_milk_daily_pdf_bytes",
    "build_milk_monthly_pdf_bytes",
    "MILK_DENSITY_DEFAULT",
]
