from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

from utils.pdf_common import add_title, new_pdf, section, table, pdf_bytes
from db import MILK_PRICE_DEFAULTS


MILK_DENSITY_DEFAULT = 1.03  # кг/л

GRADE1_ORDER = [
    "ООО «Канталь»",
    "ООО «ЧМК»",
    "ООО «Сыйфатлы Ит»",
    "ООО «ТН-УРС»",
    "Столовая",
    "В счёт ЗП",
]
GRADE2_ORDER = [
    "ООО «Зай»",
]

SOYUZ_LOCATIONS: List[Tuple[str, str]] = [
    ("ЖК", "aktuba"),
    ("Карамалы", "karamaly"),
    ("Шереметьево", "sheremetyovo"),
]


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

    kantal_kg = _to_float(data.get("sale_kantal_kg"))
    chmk_kg = _to_float(data.get("sale_chmk_kg"))
    siyfat_kg = _to_float(data.get("sale_siyfat_kg"))
    tnurs_kg = _to_float(data.get("sale_tnurs_kg"))
    zai_kg = _to_float(data.get("sale_zai_kg"))

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


def _grade_totals(
    sales: Dict[str, Dict[str, float]],
    names: List[str],
) -> Dict[str, float]:
    filtered = {k: v for k, v in sales.items() if k in names}
    return _sales_totals(filtered)


def _render_sales_grade(pdf, font, theme, title: str, sales, order):
    section(pdf, font, theme, title)
    headers = ["Канал", "Кг", "Л", "Цена, руб/кг", "Сумма, руб", "Примечание"]
    widths = [54, 22, 22, 26, 30, 32]
    aligns = ["L", "R", "R", "R", "R", "L"]
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
    gtot = _grade_totals(sales, order)
    rows.append([
        "Итого",
        fmt_int(gtot["total_kg"]),
        fmt_int(gtot["total_l"]),
        fmt_float(gtot["avg_price"], 2),
        fmt_int(gtot["total_rub"]),
        "",
    ])
    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns)


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

    # ── Реализация — Высший сорт
    sales = _sales_lines(data, density, prices=prices)
    _render_sales_grade(pdf, font, theme, "Реализация молока — Высший сорт", sales, GRADE1_ORDER)

    # ── Реализация — 2 сорт (ООО «Зай»)
    _render_sales_grade(pdf, font, theme, 'Реализация молока — 2 сорт (ООО "Зай")', sales, GRADE2_ORDER)

    # ── Реализация — общие итоги
    totals = _sales_totals(sales)
    section(pdf, font, theme, "Реализация молока (общие итоги)")
    headers = ["Показатель", "Кг", "Л", "Сумма, руб", "Средняя цена, руб/кг"]
    widths = [62, 26, 26, 34, 38]
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


# ─────────────────────────────────────────────────────────────
# Союз-Агро: сводный PDF (колонки: ЖК | Карамалы | Шереметьево | Итого)
# ─────────────────────────────────────────────────────────────

def _loc_data(
    all_data: Dict[str, Dict[str, Any]],
    all_prices: Dict[str, Dict[str, float]],
    density: float,
) -> List[Tuple[str, str, Dict, Dict, Dict]]:
    """Возвращает [(col_title, code, data, sales, totals), ...] для каждой локации."""
    result = []
    for col_title, code in SOYUZ_LOCATIONS:
        d = all_data.get(code, {})
        p = all_prices.get(code)
        s = _sales_lines(d, density, prices=p)
        t = _sales_totals(s)
        result.append((col_title, code, d, s, t))
    return result


def build_soyuz_agro_milk_pdf_bytes(
    all_data: Dict[str, Dict[str, Any]],
    all_prices: Dict[str, Dict[str, float]],
    density: float = MILK_DENSITY_DEFAULT,
) -> bytes:
    """
    all_data:   {"aktuba": {...}, "karamaly": {...}, "sheremetyovo": {...}}
    all_prices: {"aktuba": {...}, "karamaly": {...}, "sheremetyovo": {...}}
    """
    pdf, font, theme = new_pdf("L")

    any_date = ""
    for code in ("aktuba", "karamaly", "sheremetyovo"):
        d = all_data.get(code, {})
        if d.get("report_date"):
            any_date = str(d["report_date"])
            break
    if not any_date:
        any_date = datetime.now().strftime("%d.%m.%Y")

    subtitle = f"Дата: {any_date} | Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    add_title(pdf, font, theme, "ООО «Союз-Агро» — Сводка по молоку", subtitle)

    locs = _loc_data(all_data, all_prices, density)
    col_headers = ["Показатель"] + [t for t, *_ in locs] + ["Итого"]
    n_cols = len(col_headers)
    first_w = 52
    data_w = (270 - first_w) / (n_cols - 1)
    widths = [first_w] + [data_w] * (n_cols - 1)
    aligns = ["L"] + ["R"] * (n_cols - 1)

    # ── Молоко
    section(pdf, font, theme, "Молоко")
    rows_milk = []
    for label, field in [("Валовый надой, кг", "gross_kg"), ("Валовый надой, л", "gross_l")]:
        vals = []
        total = 0.0
        for _, code, d, _, _ in locs:
            big = _to_float(d.get("big_dz_kg"))
            small = _to_float(d.get("small_dz_kg"))
            gross_kg = big + small
            if field == "gross_l":
                v = kg_to_l(gross_kg, density)
            else:
                v = gross_kg
            vals.append(v)
            total += v
        rows_milk.append([label] + [fmt_int(v) for v in vals] + [fmt_int(total)])
    table(pdf, font, theme, headers=col_headers, rows=rows_milk, widths=widths, aligns=aligns)

    # ── Продуктивность
    section(pdf, font, theme, "Продуктивность")
    rows_prod = []
    for label, num_field, den_field in [
        ("На 1 фуражную, кг/гол", "gross_kg", "forage_cows"),
        ("На 1 дойную, кг/гол", "gross_kg", "milking_cows"),
    ]:
        vals = []
        total_num = 0.0
        total_den = 0
        for _, code, d, _, _ in locs:
            gross = _to_float(d.get("big_dz_kg")) + _to_float(d.get("small_dz_kg"))
            den = _to_int(d.get(den_field))
            v = (gross / den) if den > 0 else 0.0
            vals.append(v)
            total_num += gross
            total_den += den
        total_v = (total_num / total_den) if total_den > 0 else 0.0
        rows_prod.append([label] + [fmt_float(v, 2) for v in vals] + [fmt_float(total_v, 2)])

    for label, den_field in [("Фуражные коровы, гол", "forage_cows"), ("Дойные коровы, гол", "milking_cows")]:
        vals = []
        total = 0
        for _, code, d, _, _ in locs:
            v = _to_int(d.get(den_field))
            vals.append(v)
            total += v
        rows_prod.append([label] + [fmt_int(v) for v in vals] + [fmt_int(total)])

    table(pdf, font, theme, headers=col_headers, rows=rows_prod, widths=widths, aligns=aligns)

    # ── Реализация — Высший сорт
    section(pdf, font, theme, "Реализация молока — Высший сорт")
    rows_g1 = []
    for cname in GRADE1_ORDER:
        row_vals = []
        total_kg = 0.0
        for _, code, d, s, _ in locs:
            v = s.get(cname, {}).get("kg", 0.0)
            row_vals.append(v)
            total_kg += v
        rows_g1.append([cname] + [fmt_int(v) for v in row_vals] + [fmt_int(total_kg)])
    g1_totals_per_loc = []
    g1_grand = 0.0
    for _, code, d, s, _ in locs:
        t = _grade_totals(s, GRADE1_ORDER)
        g1_totals_per_loc.append(t["total_kg"])
        g1_grand += t["total_kg"]
    rows_g1.append(["Итого В/С"] + [fmt_int(v) for v in g1_totals_per_loc] + [fmt_int(g1_grand)])
    table(pdf, font, theme, headers=col_headers, rows=rows_g1, widths=widths, aligns=aligns)

    # ── Реализация — 2 сорт
    section(pdf, font, theme, 'Реализация молока — 2 сорт (ООО "Зай")')
    rows_g2 = []
    for cname in GRADE2_ORDER:
        row_vals = []
        total_kg = 0.0
        for _, code, d, s, _ in locs:
            v = s.get(cname, {}).get("kg", 0.0)
            row_vals.append(v)
            total_kg += v
        rows_g2.append([cname] + [fmt_int(v) for v in row_vals] + [fmt_int(total_kg)])
    table(pdf, font, theme, headers=col_headers, rows=rows_g2, widths=widths, aligns=aligns)

    # ── Реализация — общие итоги
    section(pdf, font, theme, "Реализация молока (общие итоги)")
    total_per_loc_kg = []
    total_per_loc_rub = []
    grand_kg = 0.0
    grand_rub = 0.0
    for _, code, d, s, t in locs:
        total_per_loc_kg.append(t["total_kg"])
        total_per_loc_rub.append(t["total_rub"])
        grand_kg += t["total_kg"]
        grand_rub += t["total_rub"]
    grand_avg = (grand_rub / grand_kg) if grand_kg > 0 else 0.0
    rows_total = [
        ["Всего, кг"] + [fmt_int(v) for v in total_per_loc_kg] + [fmt_int(grand_kg)],
        ["Всего, руб"] + [fmt_int(v) for v in total_per_loc_rub] + [fmt_int(grand_rub)],
        ["Средняя цена"] + [
            fmt_float((total_per_loc_rub[i] / total_per_loc_kg[i]) if total_per_loc_kg[i] > 0 else 0.0, 2)
            for i in range(len(locs))
        ] + [fmt_float(grand_avg, 2)],
    ]
    table(pdf, font, theme, headers=col_headers, rows=rows_total, widths=widths, aligns=aligns)

    # ── Выпойка и потери
    section(pdf, font, theme, "Выпойка и потери")
    rows_wp = []
    for label, field in [("Выпойка всего, кг", "milk_calves_total_kg"), ("Утилизация, кг", "disposal_kg")]:
        vals = []
        total = 0.0
        for _, code, d, _, _ in locs:
            v = _to_float(d.get(field))
            vals.append(v)
            total += v
        rows_wp.append([label] + [fmt_int(v) for v in vals] + [fmt_int(total)])
    table(pdf, font, theme, headers=col_headers, rows=rows_wp, widths=widths, aligns=aligns)

    # ── Качество
    section(pdf, font, theme, "Качество")
    rows_q = []
    for label, field in [("Жир, %", "fat"), ("Белок, %", "protein")]:
        vals = []
        total_val = 0.0
        cnt = 0
        for _, code, d, _, _ in locs:
            v = _to_float(d.get(field))
            vals.append(v)
            if v > 0:
                total_val += v
                cnt += 1
        avg_val = (total_val / cnt) if cnt > 0 else 0.0
        rows_q.append([label] + [fmt_float(v, 2) for v in vals] + [fmt_float(avg_val, 2)])
    table(pdf, font, theme, headers=col_headers, rows=rows_q, widths=widths, aligns=aligns)

    # ── Остатки
    section(pdf, font, theme, "Остаток (конец суток)")
    rows_tank = []
    for label, field in [("Большой танк, кг", "tank_big_kg"), ("Малый танк, кг", "tank_small_kg")]:
        vals = []
        total = 0.0
        for _, code, d, _, _ in locs:
            v = _to_float(d.get(field))
            vals.append(v)
            total += v
        rows_tank.append([label] + [fmt_int(v) for v in vals] + [fmt_int(total)])
    table(pdf, font, theme, headers=col_headers, rows=rows_tank, widths=widths, aligns=aligns)

    return pdf_bytes(pdf)
