from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional

from utils.pdf_common import add_title, new_pdf, section, table, pdf_bytes
from db import MILK_PRICE_DEFAULTS


MILK_DENSITY_DEFAULT = 1.03

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

COLOR_RED = (200, 0, 0)
COLOR_GREEN = (0, 140, 0)
COLOR_BLACK = None


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


def _delta(cur: float, prev: float, fmt=fmt_int) -> Tuple[str, Optional[Tuple]]:
    delta = cur - prev
    text = fmt(cur)
    if abs(delta) < 0.5:
        return text, COLOR_BLACK
    sign = "+" if delta > 0 else ""
    text = f"{fmt(cur)} ({sign}{fmt(delta)})"
    color = COLOR_GREEN if delta > 0 else COLOR_RED
    return text, color


def _delta_float(cur: float, prev: float, digits: int = 2) -> Tuple[str, Optional[Tuple]]:
    delta = cur - prev
    text = fmt_float(cur, digits)
    if abs(delta) < 0.005:
        return text, COLOR_BLACK
    sign = "+" if delta > 0 else ""
    text = f"{fmt_float(cur, digits)} ({sign}{fmt_float(delta, digits)})"
    color = COLOR_GREEN if delta > 0 else COLOR_RED
    return text, color


def _gross_kg(data: Dict[str, Any]) -> float:
    return _to_float(data.get("big_dz_kg")) + _to_float(data.get("small_dz_kg"))


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

    if prices is None:
        prices = dict(MILK_PRICE_DEFAULTS.get("aktuba", {}))

    def _p(k: str) -> float:
        return float(prices.get(k, 0.0))

    def add(name: str, kg: float, price: float, note: str = ""):
        l = kg_to_l(kg, density)
        rub = kg * price
        sales[name] = {"kg": float(kg), "l": float(l), "rub": float(rub), "price": float(price), "note": note}

    add("ООО «Канталь»", kantal_kg, _p("kantal"))
    add("ООО «ЧМК»", chmk_kg, _p("chmk"))
    add("ООО «Сыйфатлы Ит»", siyfat_kg, _p("siyfat"))
    add("ООО «ТН-УРС»", tnurs_kg, _p("tnurs"))
    add("ООО «Зай»", zai_kg, _p("zai"))
    add("Столовая", cafeteria_kg, _p("cafeteria"),
        note=(f"ввод {fmt_int(cafeteria_l)} л" if cafeteria_l > 0 else ""))
    add("В счёт ЗП", salary_kg, _p("salary"),
        note=(f"ввод {fmt_int(salary_l)} л" if salary_l > 0 else ""))

    return sales


def _sales_totals(sales: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    total_kg = sum(v.get("kg", 0.0) for v in sales.values())
    total_l = sum(v.get("l", 0.0) for v in sales.values())
    total_rub = sum(v.get("rub", 0.0) for v in sales.values())
    avg_price = (total_rub / total_kg) if total_kg > 0 else 0.0
    return {"total_kg": float(total_kg), "total_l": float(total_l),
            "total_rub": float(total_rub), "avg_price": float(avg_price)}


def _grade_totals(sales: Dict[str, Dict[str, float]], names: List[str]) -> Dict[str, float]:
    filtered = {k: v for k, v in sales.items() if k in names}
    return _sales_totals(filtered)


def _render_sales_grade(pdf, font, theme, title, sales, order,
                        prev_sales=None):
    section(pdf, font, theme, title)
    headers = ["Канал", "Кг", "Л", "Цена", "Сумма", "Прим."]
    widths = [54, 22, 22, 26, 30, 32]
    aligns = ["L", "R", "R", "R", "R", "L"]
    rows = []
    colors = []
    for name in order:
        v = sales.get(name, {})
        pv = (prev_sales or {}).get(name, {})
        kg_t, kg_c = _delta(v.get("kg", 0.0), pv.get("kg", 0.0))
        l_t, l_c = _delta(v.get("l", 0.0), pv.get("l", 0.0))
        pr_t, pr_c = _delta_float(v.get("price", 0.0), pv.get("price", 0.0))
        rub_t, rub_c = _delta(v.get("rub", 0.0), pv.get("rub", 0.0))
        rows.append([name, kg_t, l_t, pr_t, rub_t, str(v.get("note", "") or "")])
        colors.append([None, kg_c, l_c, pr_c, rub_c, None])
    gtot = _grade_totals(sales, order)
    pgtot = _grade_totals(prev_sales or {}, order) if prev_sales else {"total_kg": 0, "total_l": 0, "avg_price": 0, "total_rub": 0}
    tk_t, tk_c = _delta(gtot["total_kg"], pgtot["total_kg"])
    tl_t, tl_c = _delta(gtot["total_l"], pgtot["total_l"])
    ta_t, ta_c = _delta_float(gtot["avg_price"], pgtot["avg_price"])
    tr_t, tr_c = _delta(gtot["total_rub"], pgtot["total_rub"])
    rows.append(["Итого", tk_t, tl_t, ta_t, tr_t, ""])
    colors.append([None, tk_c, tl_c, ta_c, tr_c, None])
    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns,
          cell_colors=colors)


# ─────────────────────────────────────────────────────────────
# Индивидуальный PDF по подразделению
# ─────────────────────────────────────────────────────────────

def build_milk_summary_pdf_bytes(
    location_title: str,
    data: Dict[str, Any],
    mode: str,
    density: float = MILK_DENSITY_DEFAULT,
    prices: Dict[str, float] | None = None,
    prev_data: Dict[str, Any] | None = None,
) -> bytes:
    pdf, font, theme = new_pdf("P")

    date_str = str(data.get("report_date") or datetime.now().strftime("%d.%m.%Y"))
    subtitle = f"{location_title} | Дата: {date_str} | Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    add_title(pdf, font, theme, "Сводка по молоку", subtitle)

    prev = prev_data or {}
    has_prev = bool(prev)

    big_kg = _to_float(data.get("big_dz_kg"))
    small_kg = _to_float(data.get("small_dz_kg"))
    gross_kg = big_kg + small_kg
    gross_l = kg_to_l(gross_kg, density)

    prev_gross_kg = _gross_kg(prev) if has_prev else 0.0
    prev_gross_l = kg_to_l(prev_gross_kg, density) if has_prev else 0.0

    section(pdf, font, theme, "Молоко")
    headers = ["Показатель", "Л", "Кг"]
    widths = [90, 48, 48]
    aligns = ["L", "R", "R"]

    if has_prev:
        gl_t, gl_c = _delta(gross_l, prev_gross_l)
        gk_t, gk_c = _delta(gross_kg, prev_gross_kg)
        rows = [["Валовый надой", gl_t, gk_t]]
        colors = [[None, gl_c, gk_c]]
    else:
        rows = [["Валовый надой", fmt_int(gross_l), fmt_int(gross_kg)]]
        colors = None

    if mode != "group":
        big_l = kg_to_l(big_kg, density)
        small_l = kg_to_l(small_kg, density)
        rows += [
            ["По ДЗ — Большой", fmt_int(big_l), fmt_int(big_kg)],
            ["По ДЗ — Малый", fmt_int(small_l), fmt_int(small_kg)],
        ]
        if colors is not None:
            colors += [[None, None, None], [None, None, None]]
    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns,
          cell_colors=colors)

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

    sales = _sales_lines(data, density, prices=prices)
    prev_sales = _sales_lines(prev, density, prices=prices) if has_prev else None
    _render_sales_grade(pdf, font, theme, "Реализация молока — Высший сорт",
                        sales, GRADE1_ORDER, prev_sales=prev_sales)
    _render_sales_grade(pdf, font, theme, 'Реализация молока — 2 сорт (ООО "Зай")',
                        sales, GRADE2_ORDER, prev_sales=prev_sales)

    totals = _sales_totals(sales)
    section(pdf, font, theme, "Реализация молока (общие итоги)")
    headers = ["Показатель", "Кг", "Л", "Сумма, руб", "Ср. цена"]
    widths = [62, 26, 26, 34, 38]
    aligns = ["L", "R", "R", "R", "R"]
    if has_prev:
        ptot = _sales_totals(_sales_lines(prev, density, prices=prices))
        tk_t, tk_c = _delta(totals["total_kg"], ptot["total_kg"])
        tl_t, tl_c = _delta(totals["total_l"], ptot["total_l"])
        tr_t, tr_c = _delta(totals["total_rub"], ptot["total_rub"])
        ta_t, ta_c = _delta_float(totals["avg_price"], ptot["avg_price"])
        rows = [["Всего", tk_t, tl_t, tr_t, ta_t]]
        colors = [[None, tk_c, tl_c, tr_c, ta_c]]
    else:
        rows = [["Всего", fmt_int(totals["total_kg"]), fmt_int(totals["total_l"]),
                 fmt_int(totals["total_rub"]), fmt_float(totals["avg_price"], 2)]]
        colors = None
    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns,
          cell_colors=colors)

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

    fat = _to_float(data.get("fat"))
    protein = _to_float(data.get("protein"))

    section(pdf, font, theme, "Качество")
    headers = ["Показатель", "Значение"]
    widths = [90, 96]
    aligns = ["L", "R"]
    rows = [["Жир, %", fmt_float(fat, 2)], ["Белок, %", fmt_float(protein, 2)]]
    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns)

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
# Союз-Агро: сводный PDF (книжный, колонки: ЖК | Карамалы | Шереметьево | Итого)
# ─────────────────────────────────────────────────────────────

def _loc_data(
    all_data: Dict[str, Dict[str, Any]],
    all_prices: Dict[str, Dict[str, float]],
    density: float,
) -> List[Tuple[str, str, Dict, Dict, Dict]]:
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
    prev_all_data: Dict[str, Dict[str, Any]] | None = None,
    report_status: Dict[str, Dict[str, bool]] | None = None,
) -> bytes:
    pdf, font, theme = new_pdf("P")

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
    prev_locs = _loc_data(prev_all_data or {}, all_prices, density) if prev_all_data else None

    col_headers = ["Показатель"] + [t for t, *_ in locs] + ["Итого"]
    n_cols = len(col_headers)
    first_w = 50
    data_w = (186 - first_w) / (n_cols - 1)
    widths = [first_w] + [data_w] * (n_cols - 1)
    aligns = ["L"] + ["R"] * (n_cols - 1)

    # ── Статус сдачи отчётов
    if report_status:
        section(pdf, font, theme, "Статус сдачи отчётов")
        st_headers = ["Подразделение", "Молоко", "Вет 0-3", "Вет коровы", "Вет орто"]
        st_widths = [50, 34, 34, 34, 34]
        st_aligns = ["L", "C", "C", "C", "C"]
        st_rows = []
        st_colors = []
        for title, code in SOYUZ_LOCATIONS:
            st = report_status.get(code, {})
            row = [title]
            row_c = [None]
            for key in ("milk", "vet_0_3", "vet_cows", "vet_ortho"):
                ok = st.get(key, False)
                row.append("OK" if ok else "НЕ СДАНО")
                row_c.append(COLOR_GREEN if ok else COLOR_RED)
            st_rows.append(row)
            st_colors.append(row_c)
        table(pdf, font, theme, headers=st_headers, rows=st_rows, widths=st_widths,
              aligns=st_aligns, cell_colors=st_colors)

    # ── Молоко
    section(pdf, font, theme, "Молоко")
    rows_milk = []
    colors_milk = []
    for label, use_liters in [("Валовый надой, кг", False), ("Валовый надой, л", True)]:
        vals = []
        prev_vals = []
        for i, (_, code, d, _, _) in enumerate(locs):
            g = _gross_kg(d)
            v = kg_to_l(g, density) if use_liters else g
            vals.append(v)
            pv = 0.0
            if prev_locs:
                pg = _gross_kg(prev_locs[i][2])
                pv = kg_to_l(pg, density) if use_liters else pg
            prev_vals.append(pv)
        total = sum(vals)
        prev_total = sum(prev_vals)
        row = [label]
        row_c = [None]
        for j in range(len(locs)):
            t, c = _delta(vals[j], prev_vals[j]) if prev_locs else (fmt_int(vals[j]), None)
            row.append(t)
            row_c.append(c)
        tt, tc = _delta(total, prev_total) if prev_locs else (fmt_int(total), None)
        row.append(tt)
        row_c.append(tc)
        rows_milk.append(row)
        colors_milk.append(row_c)
    table(pdf, font, theme, headers=col_headers, rows=rows_milk, widths=widths, aligns=aligns,
          cell_colors=colors_milk)

    # ── Продуктивность
    section(pdf, font, theme, "Продуктивность")
    rows_prod = []
    for label, den_field in [
        ("На 1 фуражную, кг/гол", "forage_cows"),
        ("На 1 дойную, кг/гол", "milking_cows"),
    ]:
        vals = []
        total_num = 0.0
        total_den = 0
        for _, code, d, _, _ in locs:
            gross = _gross_kg(d)
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
    colors_g1 = []
    for cname in GRADE1_ORDER:
        row_vals = []
        prev_row_vals = []
        for i, (_, code, d, s, _) in enumerate(locs):
            v = s.get(cname, {}).get("kg", 0.0)
            row_vals.append(v)
            pv = prev_locs[i][3].get(cname, {}).get("kg", 0.0) if prev_locs else 0.0
            prev_row_vals.append(pv)
        total = sum(row_vals)
        prev_total = sum(prev_row_vals)
        row = [cname]
        row_c = [None]
        for j in range(len(locs)):
            t, c = _delta(row_vals[j], prev_row_vals[j]) if prev_locs else (fmt_int(row_vals[j]), None)
            row.append(t)
            row_c.append(c)
        tt, tc = _delta(total, prev_total) if prev_locs else (fmt_int(total), None)
        row.append(tt)
        row_c.append(tc)
        rows_g1.append(row)
        colors_g1.append(row_c)

    g1_vals = []
    g1_prev = []
    for i, (_, code, d, s, _) in enumerate(locs):
        g = _grade_totals(s, GRADE1_ORDER)["total_kg"]
        g1_vals.append(g)
        pg = _grade_totals(prev_locs[i][3], GRADE1_ORDER)["total_kg"] if prev_locs else 0.0
        g1_prev.append(pg)
    g1_grand = sum(g1_vals)
    g1_pgrand = sum(g1_prev)
    row = ["Итого В/С"]
    row_c = [None]
    for j in range(len(locs)):
        t, c = _delta(g1_vals[j], g1_prev[j]) if prev_locs else (fmt_int(g1_vals[j]), None)
        row.append(t)
        row_c.append(c)
    tt, tc = _delta(g1_grand, g1_pgrand) if prev_locs else (fmt_int(g1_grand), None)
    row.append(tt)
    row_c.append(tc)
    rows_g1.append(row)
    colors_g1.append(row_c)
    table(pdf, font, theme, headers=col_headers, rows=rows_g1, widths=widths, aligns=aligns,
          cell_colors=colors_g1)

    # ── Реализация — 2 сорт
    section(pdf, font, theme, 'Реализация молока — 2 сорт (ООО "Зай")')
    rows_g2 = []
    colors_g2 = []
    for cname in GRADE2_ORDER:
        row_vals = []
        prev_row_vals = []
        for i, (_, code, d, s, _) in enumerate(locs):
            v = s.get(cname, {}).get("kg", 0.0)
            row_vals.append(v)
            pv = prev_locs[i][3].get(cname, {}).get("kg", 0.0) if prev_locs else 0.0
            prev_row_vals.append(pv)
        total = sum(row_vals)
        prev_total = sum(prev_row_vals)
        row = [cname]
        row_c = [None]
        for j in range(len(locs)):
            t, c = _delta(row_vals[j], prev_row_vals[j]) if prev_locs else (fmt_int(row_vals[j]), None)
            row.append(t)
            row_c.append(c)
        tt, tc = _delta(total, prev_total) if prev_locs else (fmt_int(total), None)
        row.append(tt)
        row_c.append(tc)
        rows_g2.append(row)
        colors_g2.append(row_c)
    table(pdf, font, theme, headers=col_headers, rows=rows_g2, widths=widths, aligns=aligns,
          cell_colors=colors_g2)

    # ── Реализация — общие итоги
    section(pdf, font, theme, "Реализация молока (общие итоги)")
    total_per_loc_kg = []
    total_per_loc_rub = []
    prev_per_loc_kg = []
    prev_per_loc_rub = []
    for i, (_, code, d, s, t) in enumerate(locs):
        total_per_loc_kg.append(t["total_kg"])
        total_per_loc_rub.append(t["total_rub"])
        if prev_locs:
            prev_per_loc_kg.append(prev_locs[i][4]["total_kg"])
            prev_per_loc_rub.append(prev_locs[i][4]["total_rub"])
        else:
            prev_per_loc_kg.append(0.0)
            prev_per_loc_rub.append(0.0)

    grand_kg = sum(total_per_loc_kg)
    grand_rub = sum(total_per_loc_rub)
    pgrand_kg = sum(prev_per_loc_kg)
    pgrand_rub = sum(prev_per_loc_rub)
    grand_avg = (grand_rub / grand_kg) if grand_kg > 0 else 0.0
    pgrand_avg = (pgrand_rub / pgrand_kg) if pgrand_kg > 0 else 0.0

    rows_total = []
    colors_total = []
    for label, vals, pvals, use_float in [
        ("Всего, кг", total_per_loc_kg, prev_per_loc_kg, False),
        ("Всего, руб", total_per_loc_rub, prev_per_loc_rub, False),
    ]:
        row = [label]
        row_c = [None]
        gv = sum(vals)
        gpv = sum(pvals)
        for j in range(len(locs)):
            t, c = _delta(vals[j], pvals[j]) if prev_locs else (fmt_int(vals[j]), None)
            row.append(t)
            row_c.append(c)
        tt, tc = _delta(gv, gpv) if prev_locs else (fmt_int(gv), None)
        row.append(tt)
        row_c.append(tc)
        rows_total.append(row)
        colors_total.append(row_c)

    row = ["Средняя цена"]
    row_c = [None]
    for j in range(len(locs)):
        cur_avg = (total_per_loc_rub[j] / total_per_loc_kg[j]) if total_per_loc_kg[j] > 0 else 0.0
        prev_avg = (prev_per_loc_rub[j] / prev_per_loc_kg[j]) if prev_per_loc_kg[j] > 0 else 0.0
        t, c = _delta_float(cur_avg, prev_avg) if prev_locs else (fmt_float(cur_avg, 2), None)
        row.append(t)
        row_c.append(c)
    tt, tc = _delta_float(grand_avg, pgrand_avg) if prev_locs else (fmt_float(grand_avg, 2), None)
    row.append(tt)
    row_c.append(tc)
    rows_total.append(row)
    colors_total.append(row_c)
    table(pdf, font, theme, headers=col_headers, rows=rows_total, widths=widths, aligns=aligns,
          cell_colors=colors_total)

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

    return pdf_bytes(pdf)
