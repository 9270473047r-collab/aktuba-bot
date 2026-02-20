from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from utils.pdf_common import add_title, new_pdf, section, table, pdf_bytes
from db import MILK_PRICE_DEFAULTS


MILK_DENSITY_DEFAULT = 1.03  # кг/л


def _to_float(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        return float(str(x).replace(" ", "").replace(",", "."))
    except Exception:
        return 0.0


def _to_int(x: Any) -> int:
    try:
        return int(round(_to_float(x)))
    except Exception:
        return 0


def fmt_int(x: float | int) -> str:
    try:
        return f"{int(round(float(x))):,}".replace(",", " ")
    except Exception:
        return "0"


def fmt_float(x: float, digits: int = 2) -> str:
    try:
        return f"{float(x):.{digits}f}".replace(".", ",")
    except Exception:
        return "0,00"


def l_to_kg(l: float, density: float) -> float:
    return float(l) * float(density)


def kg_to_l(kg: float, density: float) -> float:
    d = float(density) if density else MILK_DENSITY_DEFAULT
    return float(kg) / d


def _sales_lines(
    data: Dict[str, Any],
    density: float,
    prices: Dict[str, float] | None = None,
) -> Dict[str, Dict[str, float]]:
    sales: Dict[str, Dict[str, float]] = {}

    # контрагенты (ввод кг)
    kantal_kg = _to_float(data.get("sale_kantal_kg"))
    chmk_kg = _to_float(data.get("sale_chmk_kg"))
    siyfat_kg = _to_float(data.get("sale_siyfat_kg"))
    tnurs_kg = _to_float(data.get("sale_tnurs_kg"))
    zai_kg = _to_float(data.get("sale_zai_kg"))

    # исключения (ввод л)
    cafeteria_l = _to_float(data.get("sale_cafeteria_l"))
    salary_l = _to_float(data.get("sale_salary_l"))
    cafeteria_kg = l_to_kg(cafeteria_l, density)
    salary_kg = l_to_kg(salary_l, density)

    prices = prices or dict(MILK_PRICE_DEFAULTS.get("aktuba", {}))
    PRICE_KANTAL = float(prices.get("kantal", 0.0))
    PRICE_CHMK = float(prices.get("chmk", 0.0))
    PRICE_SIYFAT = float(prices.get("siyfat", 0.0))
    PRICE_TNURS = float(prices.get("tnurs", 0.0))
    PRICE_ZAI = float(prices.get("zai", 0.0))
    PRICE_CAFE = float(prices.get("cafeteria", 0.0))
    PRICE_SALARY = float(prices.get("salary", 0.0))

    def add(name: str, kg: float, price: float, note: str = ""):
        l = kg_to_l(kg, density)
        rub = kg * price
        sales[name] = {
            "kg": float(kg),
            "l": float(l),
            "rub": float(rub),
            "price": float(price),
            "note": note,
        }

    add("ООО «Канталь»", kantal_kg, PRICE_KANTAL)
    add("ООО «ЧМК»", chmk_kg, PRICE_CHMK)
    add("ООО «Сыйфатлы Ит»", siyfat_kg, PRICE_SIYFAT)
    add("ООО «ТН-УРС»", tnurs_kg, PRICE_TNURS)
    add("ООО «Зай»", zai_kg, PRICE_ZAI)

    add("Столовая", cafeteria_kg, PRICE_CAFE, note=(f"ввод {fmt_int(cafeteria_l)} л" if cafeteria_l > 0 else ""))
    add("В счёт ЗП", salary_kg, PRICE_SALARY, note=(f"ввод {fmt_int(salary_l)} л" if salary_l > 0 else ""))

    return sales


def _sales_totals(sales: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    total_kg = sum(v.get("kg", 0.0) for v in sales.values())
    total_l = sum(v.get("l", 0.0) for v in sales.values())
    total_rub = sum(v.get("rub", 0.0) for v in sales.values())
    avg_price = (total_rub / total_kg) if total_kg > 0 else 0.0
    return {
        "total_kg": float(total_kg),
        "total_l": float(total_l),
        "total_rub": float(total_rub),
        "avg_price": float(avg_price),
    }


def build_milk_summary_pdf_bytes(
    location_title: str,
    data: Dict[str, Any],
    mode: str,
    density: float = MILK_DENSITY_DEFAULT,
    prices: Dict[str, float] | None = None,
) -> bytes:
    """
    mode:
      - admin  -> в PDF НЕ показываем "Факт валовый надой" (по требованию)
      - public -> ок
      - group  -> без блока По ДЗ
    """
    pdf, font, theme = new_pdf("P")

    date_str = str(data.get("report_date") or datetime.now().strftime("%d.%m.%Y"))
    subtitle = f"{location_title} | Дата: {date_str} | Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    add_title(pdf, font, theme, "Сводка по молоку", subtitle)

    # ── Молоко
    big_kg = _to_float(data.get("big_dz_kg"))
    small_kg = _to_float(data.get("small_dz_kg"))
    gross_kg = big_kg + small_kg

    big_l = kg_to_l(big_kg, density)
    small_l = kg_to_l(small_kg, density)
    gross_l = kg_to_l(gross_kg, density)

    section(pdf, font, theme, "Молоко")
    headers = ["Показатель", "Л", "Кг"]
    widths = [90, 48, 48]
    aligns = ["L", "R", "R"]
    rows = [["Валовый надой", fmt_int(gross_l), fmt_int(gross_kg)]]
    if mode != "group":
        rows += [
            ["По ДЗ — Большой", fmt_int(big_l), fmt_int(big_kg)],
            ["По ДЗ — Малый", fmt_int(small_l), fmt_int(small_kg)],
        ]
    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns)

    # ── Продуктивность
    forage_cows = _to_int(data.get("forage_cows"))
    milking_cows = _to_int(data.get("milking_cows"))

    prod_forage_kg = (gross_kg / forage_cows) if forage_cows > 0 else 0.0
    prod_forage_l = (gross_l / forage_cows) if forage_cows > 0 else 0.0
    prod_milking_kg = (gross_kg / milking_cows) if milking_cows > 0 else 0.0
    prod_milking_l = (gross_l / milking_cows) if milking_cows > 0 else 0.0

    section(pdf, font, theme, "Продуктивность")
    headers = ["Показатель", "Л/гол", "Кг/гол", "Поголовье"]
    widths = [72, 38, 38, 38]
    aligns = ["L", "R", "R", "R"]
    rows = []
    if forage_cows > 0:
        rows.append(["На 1 фуражную корову", fmt_float(prod_forage_l, 2), fmt_float(prod_forage_kg, 2), fmt_int(forage_cows)])
    else:
        rows.append(["На 1 фуражную корову", "нет данных", "", ""])
    if milking_cows > 0:
        rows.append(["На 1 дойную корову", fmt_float(prod_milking_l, 2), fmt_float(prod_milking_kg, 2), fmt_int(milking_cows)])
    else:
        rows.append(["На 1 дойную корову", "нет данных", "", ""])
    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns)

    # ── Реализация
    sales = _sales_lines(data, density, prices=prices)
    totals = _sales_totals(sales)

    section(pdf, font, theme, "Реализация молока (детализация)")
    headers = ["Канал", "Кг", "Л", "Цена, руб/кг", "Сумма, руб", "Примечание"]
    widths = [54, 22, 22, 26, 30, 32]  # = 186
    aligns = ["L", "R", "R", "R", "R", "L"]
    order = [
        "ООО «Канталь»",
        "ООО «ЧМК»",
        "ООО «Сыйфатлы Ит»",
        "ООО «ТН-УРС»",
        "ООО «Зай»",
        "Столовая",
        "В счёт ЗП",
    ]
    rows = []
    for name in order:
        v = sales.get(name, {})
        rows.append([
            name,
            fmt_int(v.get("kg", 0.0)),
            fmt_int(v.get("l", 0.0)),
            fmt_float(v.get("price", 0.0), 2),
            fmt_int(v.get("rub", 0.0)),
            str(v.get("note", "") or ""),
        ])
    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns)

    section(pdf, font, theme, "Реализация молока (итоги)")
    headers = ["Показатель", "Кг", "Л", "Сумма, руб", "Средняя цена, руб/кг"]
    widths = [62, 26, 26, 34, 38]  # = 186
    aligns = ["L", "R", "R", "R", "R"]
    rows = [[
        "Всего",
        fmt_int(totals["total_kg"]),
        fmt_int(totals["total_l"]),
        fmt_int(totals["total_rub"]),
        fmt_float(totals["avg_price"], 2),
    ]]
    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns)

    # ── Выпойка / потери
    milk_calves_total_kg = _to_float(data.get("milk_calves_total_kg"))
    milk_calves_total_l = kg_to_l(milk_calves_total_kg, density)
    disposal_kg = _to_float(data.get("disposal_kg"))
    disposal_l = kg_to_l(disposal_kg, density)

    section(pdf, font, theme, "Выпойка и потери")
    headers = ["Показатель", "Л", "Кг"]
    widths = [90, 48, 48]
    aligns = ["L", "R", "R"]
    rows = [
        ["Выпойка всего", fmt_int(milk_calves_total_l), fmt_int(milk_calves_total_kg)],
        ["Утилизация", fmt_int(disposal_l), fmt_int(disposal_kg)],
    ]
    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns)

    # ── Качество
    fat = _to_float(data.get("fat"))
    protein = _to_float(data.get("protein"))

    section(pdf, font, theme, "Качество")
    headers = ["Показатель", "Значение"]
    widths = [90, 96]
    aligns = ["L", "R"]
    rows = [
        ["Жир, %", fmt_float(fat, 2)],
        ["Белок, %", fmt_float(protein, 2)],
    ]
    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns)

    # ── Остатки
    tank_big_kg = _to_float(data.get("tank_big_kg"))
    tank_small_kg = _to_float(data.get("tank_small_kg"))
    tank_big_l = kg_to_l(tank_big_kg, density)
    tank_small_l = kg_to_l(tank_small_kg, density)

    section(pdf, font, theme, "Остаток (конец суток)")
    headers = ["Танк", "Л", "Кг"]
    widths = [90, 48, 48]
    aligns = ["L", "R", "R"]
    rows = [
        ["Большой танк", fmt_int(tank_big_l), fmt_int(tank_big_kg)],
        ["Малый танк", fmt_int(tank_small_l), fmt_int(tank_small_kg)],
    ]
    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns)

    return pdf_bytes(pdf)
