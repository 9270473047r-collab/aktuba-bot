from __future__ import annotations

from datetime import datetime
from collections import defaultdict

from fpdf import FPDF


FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _pdf_bytes(pdf: FPDF) -> bytes:
    out = pdf.output(dest="S")
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return out.encode("latin1")


def _safe(s) -> str:
    if s is None:
        return ""
    return str(s)


def _fmt_int(x) -> str:
    try:
        return f"{int(round(float(x))):,}".replace(",", " ")
    except Exception:
        return "0"


def _init_pdf(title: str, subtitle: str) -> tuple[FPDF, str, str]:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    pdf.add_font("DejaVu", "", FONT_REG, uni=True)
    pdf.add_font("DejaVu", "B", FONT_BOLD, uni=True)

    font = "DejaVu"
    bold = "DejaVu"

    # Header bar
    pdf.set_fill_color(245, 245, 245)
    pdf.rect(0, 0, 210, 20, "F")
    pdf.set_xy(12, 6)
    pdf.set_font(bold, "B", 14)
    pdf.cell(0, 7, _safe(title), ln=1)
    pdf.set_x(12)
    pdf.set_font(font, "", 10)
    pdf.cell(0, 5, _safe(subtitle), ln=1)

    pdf.ln(2)
    return pdf, font, bold


def _section(pdf: FPDF, bold: str, name: str):
    pdf.ln(2)
    pdf.set_font(bold, "B", 11)
    pdf.set_fill_color(230, 240, 255)
    pdf.cell(0, 7, _safe(name), ln=1, fill=True)
    pdf.ln(1)


def _kv2(pdf: FPDF, font: str, bold: str, left: str, right: str):
    pdf.set_font(bold, "B", 10)
    pdf.cell(95, 6, _safe(left), border=0)
    pdf.set_font(font, "", 10)
    pdf.cell(0, 6, _safe(right), ln=1, border=0)


def _table(pdf: FPDF, font: str, bold: str, headers: list[str], rows: list[list[str]]):
    col_w = [62, 78, 32]  # Подразделение | Группа | Кол-во
    pdf.set_font(bold, "B", 10)
    pdf.set_fill_color(245, 245, 245)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, _safe(h), border=1, fill=True)
    pdf.ln(7)

    pdf.set_font(font, "", 10)
    for r in rows:
        pdf.cell(col_w[0], 6, _safe(r[0]), border=1)
        pdf.cell(col_w[1], 6, _safe(r[1]), border=1)
        pdf.cell(col_w[2], 6, _safe(r[2]), border=1, ln=1)


def build_herd_daily_pdf_bytes(
    location_title: str,
    report_date_iso: str,
    daily: dict,
    month_flow: dict,
    year_flow: dict,
) -> bytes:
    dt = datetime.strptime(report_date_iso, "%Y-%m-%d")
    subtitle = f"Суточный отчёт за {dt.strftime('%d.%m.%Y')}"

    pdf, font, bold = _init_pdf(f"Движение поголовья — {location_title}", subtitle)

    # ── Снимок поголовья
    _section(pdf, bold, "Поголовье (факт на утро)")

    total_cattle = (
        int(daily.get("forage_cows", 0) or 0)
        + int(daily.get("heifers_total", 0) or 0)
        + int(daily.get("heifers_0_3", 0) or 0)
        + int(daily.get("heifers_3_6", 0) or 0)
        + int(daily.get("heifers_6_12", 0) or 0)
        + int(daily.get("heifers_12_18", 0) or 0)
        + int(daily.get("heifers_18_plus", 0) or 0)
        + int(daily.get("bulls_0_3", 0) or 0)
    )

    _kv2(pdf, font, bold, "Всего КРС, гол", _fmt_int(total_cattle))
    _kv2(pdf, font, bold, "Фуражные коровы, гол", _fmt_int(daily.get("forage_cows", 0)))
    _kv2(pdf, font, bold, "Дойные коровы, гол", _fmt_int(daily.get("milking_cows", 0)))
    _kv2(pdf, font, bold, "в т.ч. РО, гол", _fmt_int(daily.get("ro_cows", 0)))
    _kv2(pdf, font, bold, "Сухостой, гол", _fmt_int(daily.get("dry_cows", 0)))
    _kv2(pdf, font, bold, "Стельные коровы, гол", _fmt_int(daily.get("pregnant_cows", 0)))

    # ── Молодняк
    _section(pdf, bold, "Молодняк")
    _kv2(pdf, font, bold, "Тёлки 0–3 мес", _fmt_int(daily.get("heifers_0_3", 0)))
    _kv2(pdf, font, bold, "Тёлки 3–6 мес", _fmt_int(daily.get("heifers_3_6", 0)))
    _kv2(pdf, font, bold, "Тёлки 6–12 мес", _fmt_int(daily.get("heifers_6_12", 0)))
    _kv2(pdf, font, bold, "Тёлки 12–18 мес", _fmt_int(daily.get("heifers_12_18", 0)))
    _kv2(pdf, font, bold, "Тёлки 18+ мес", _fmt_int(daily.get("heifers_18_plus", 0)))
    _kv2(pdf, font, bold, "Бычки 0–3 мес", _fmt_int(daily.get("bulls_0_3", 0)))
    _kv2(pdf, font, bold, "Нетели", _fmt_int(daily.get("heifers_total", 0)))

    # ── Состояние стада
    _section(pdf, bold, "Состояние стада")
    _kv2(pdf, font, bold, "Госпиталь, гол", _fmt_int(daily.get("hospital", 0)))
    _kv2(pdf, font, bold, "Мастит, гол", _fmt_int(daily.get("mastitis", 0)))
    _kv2(pdf, font, bold, "Брак (на выбытие), гол", _fmt_int(daily.get("cull", 0)))

    # ── Движение за сутки (потоки)
    _section(pdf, bold, "Движение за сутки")
    _kv2(pdf, font, bold, "Запуск, гол", _fmt_int(daily.get("launch", 0)))
    _kv2(pdf, font, bold, "Отёлы — коровы, гол", _fmt_int(daily.get("calv_cows", 0)))
    _kv2(pdf, font, bold, "Отёлы — нетели, гол", _fmt_int(daily.get("calv_neteli", 0)))
    _kv2(pdf, font, bold, "Родилось — тёлки, гол", _fmt_int(daily.get("calves_heifers_day", 0)))
    _kv2(pdf, font, bold, "Родилось — бычки, гол", _fmt_int(daily.get("calves_bulls_day", 0)))
    _kv2(pdf, font, bold, "Мертворождённые, гол", _fmt_int(daily.get("stillborn_day", 0)))
    _kv2(pdf, font, bold, "Аборты, гол", _fmt_int(daily.get("abort_day", 0)))

    _kv2(pdf, font, bold, "Падёж — коровы, гол", _fmt_int(daily.get("death_cows", 0)))
    _kv2(pdf, font, bold, "Падёж — 0–3 мес, гол", _fmt_int(daily.get("death_calves_0_3", 0)))
    _kv2(pdf, font, bold, "Падёж — >3 мес, гол", _fmt_int(daily.get("death_young_over_3", 0)))

    _kv2(pdf, font, bold, "Реализация — коровы, гол", _fmt_int(daily.get("sale_cows", 0)))
    _kv2(pdf, font, bold, "Реализация — нетели, гол", _fmt_int(daily.get("sale_neteli", 0)))
    _kv2(pdf, font, bold, "Реализация — тёлки, гол", _fmt_int(daily.get("sale_heifers", 0)))
    _kv2(pdf, font, bold, "Реализация — бычки, гол", _fmt_int(daily.get("sale_bulls", 0)))

    _kv2(pdf, font, bold, "Племпродажа, гол", _fmt_int(daily.get("breeding_sale", 0)))

    # ── Переводы
    out_list = daily.get("transfers_out", []) or []
    in_list = daily.get("transfers_in", []) or []

    if out_list:
        _section(pdf, bold, "Переводы из ЖК в подразделения")
        rows = []
        total = 0
        for it in out_list:
            qty = int(it.get("qty", 0) or 0)
            total += qty
            rows.append([_safe(it.get("unit_title")), _safe(it.get("group_title")), _fmt_int(qty)])
        _table(pdf, font, bold, ["Подразделение", "Группа", "Кол-во"], rows)
        pdf.ln(1)
        _kv2(pdf, font, bold, "Итого переводов (из ЖК), гол", _fmt_int(total))

    if in_list:
        _section(pdf, bold, "Поступили в ЖК из подразделений")
        rows = []
        total = 0
        for it in in_list:
            qty = int(it.get("qty", 0) or 0)
            total += qty
            rows.append([_safe(it.get("unit_title")), _safe(it.get("group_title")), _fmt_int(qty)])
        _table(pdf, font, bold, ["Подразделение", "Группа", "Кол-во"], rows)
        pdf.ln(1)
        _kv2(pdf, font, bold, "Итого поступлений (в ЖК), гол", _fmt_int(total))

    # ── Итоги месяца/года (потоки)
    _section(pdf, bold, "Итого потоки (месяц / с начала года)")
    _kv2(pdf, font, bold, "Запуск, гол", f"{_fmt_int(month_flow.get('launch', 0))} / {_fmt_int(year_flow.get('launch', 0))}")
    _kv2(pdf, font, bold, "Отёлы (коровы+нетели), гол",
         f"{_fmt_int(month_flow.get('calv_total', 0))} / {_fmt_int(year_flow.get('calv_total', 0))}")
    _kv2(pdf, font, bold, "Родилось (тёлки+бычки), гол",
         f"{_fmt_int(month_flow.get('born_total', 0))} / {_fmt_int(year_flow.get('born_total', 0))}")
    _kv2(pdf, font, bold, "Падёж (всего), гол",
         f"{_fmt_int(month_flow.get('death_total', 0))} / {_fmt_int(year_flow.get('death_total', 0))}")
    _kv2(pdf, font, bold, "Реализация (всего), гол",
         f"{_fmt_int(month_flow.get('sale_total', 0))} / {_fmt_int(year_flow.get('sale_total', 0))}")
    _kv2(pdf, font, bold, "Племпродажа, гол",
         f"{_fmt_int(month_flow.get('breeding_sale', 0))} / {_fmt_int(year_flow.get('breeding_sale', 0))}")
    _kv2(pdf, font, bold, "Переводы из ЖК, гол",
         f"{_fmt_int(month_flow.get('transfers_out', 0))} / {_fmt_int(year_flow.get('transfers_out', 0))}")
    _kv2(pdf, font, bold, "Поступили в ЖК, гол",
         f"{_fmt_int(month_flow.get('transfers_in', 0))} / {_fmt_int(year_flow.get('transfers_in', 0))}")

    return _pdf_bytes(pdf)


def build_herd_month_pdf_bytes(
    location_title: str,
    month_from_iso: str,
    month_to_iso: str,
    flow_month: dict,
    transfers_out_agg: dict,
    transfers_in_agg: dict,
) -> bytes:
    subtitle = f"Итого за месяц: {month_from_iso} — {month_to_iso}"
    pdf, font, bold = _init_pdf(f"Движение поголовья — {location_title}", subtitle)

    _section(pdf, bold, "Потоки за месяц")
    _kv2(pdf, font, bold, "Запуск, гол", _fmt_int(flow_month.get("launch", 0)))
    _kv2(pdf, font, bold, "Отёлы (коровы), гол", _fmt_int(flow_month.get("calv_cows", 0)))
    _kv2(pdf, font, bold, "Отёлы (нетели), гол", _fmt_int(flow_month.get("calv_neteli", 0)))
    _kv2(pdf, font, bold, "Родилось (тёлки), гол", _fmt_int(flow_month.get("calves_heifers_day", 0)))
    _kv2(pdf, font, bold, "Родилось (бычки), гол", _fmt_int(flow_month.get("calves_bulls_day", 0)))
    _kv2(pdf, font, bold, "Мертворождённые, гол", _fmt_int(flow_month.get("stillborn_day", 0)))
    _kv2(pdf, font, bold, "Аборты, гол", _fmt_int(flow_month.get("abort_day", 0)))

    _kv2(pdf, font, bold, "Падёж (коровы), гол", _fmt_int(flow_month.get("death_cows", 0)))
    _kv2(pdf, font, bold, "Падёж (0–3 мес), гол", _fmt_int(flow_month.get("death_calves_0_3", 0)))
    _kv2(pdf, font, bold, "Падёж (>3 мес), гол", _fmt_int(flow_month.get("death_young_over_3", 0)))

    _kv2(pdf, font, bold, "Реализация (коровы), гол", _fmt_int(flow_month.get("sale_cows", 0)))
    _kv2(pdf, font, bold, "Реализация (нетели), гол", _fmt_int(flow_month.get("sale_neteli", 0)))
    _kv2(pdf, font, bold, "Реализация (тёлки), гол", _fmt_int(flow_month.get("sale_heifers", 0)))
    _kv2(pdf, font, bold, "Реализация (бычки), гол", _fmt_int(flow_month.get("sale_bulls", 0)))

    _kv2(pdf, font, bold, "Племпродажа, гол", _fmt_int(flow_month.get("breeding_sale", 0)))

    # Переводы OUT
    if transfers_out_agg:
        _section(pdf, bold, "Переводы из ЖК (агрегировано)")
        rows = []
        total = 0
        for k, qty in sorted(transfers_out_agg.items(), key=lambda x: (-x[1], x[0])):
            unit, group = k.split("||", 1)
            total += int(qty or 0)
            rows.append([unit, group, _fmt_int(qty)])
        _table(pdf, font, bold, ["Подразделение", "Группа", "Кол-во"], rows)
        pdf.ln(1)
        _kv2(pdf, font, bold, "Итого переводов (из ЖК), гол", _fmt_int(total))

    # Переводы IN
    if transfers_in_agg:
        _section(pdf, bold, "Поступили в ЖК (агрегировано)")
        rows = []
        total = 0
        for k, qty in sorted(transfers_in_agg.items(), key=lambda x: (-x[1], x[0])):
            unit, group = k.split("||", 1)
            total += int(qty or 0)
            rows.append([unit, group, _fmt_int(qty)])
        _table(pdf, font, bold, ["Подразделение", "Группа", "Кол-во"], rows)
        pdf.ln(1)
        _kv2(pdf, font, bold, "Итого поступлений (в ЖК), гол", _fmt_int(total))

    return _pdf_bytes(pdf)


def aggregate_flows(reports: list[dict]) -> tuple[dict, dict, dict]:
    """
    Возвращает:
      - flow: суммы по ключам (включая launch/death/sale/...)
      - transfers_out_agg: dict("unit||group" -> qty)
      - transfers_in_agg: dict("unit||group" -> qty)
    """
    flow_keys = [
        "launch",
        "calv_cows", "calv_neteli",
        "calves_heifers_day", "calves_bulls_day",
        "stillborn_day", "abort_day",
        "death_cows", "death_calves_0_3", "death_young_over_3",
        "sale_cows", "sale_neteli", "sale_heifers", "sale_bulls",
        "breeding_sale",
    ]
    flow = {k: 0 for k in flow_keys}

    out_agg = defaultdict(int)
    in_agg = defaultdict(int)

    for r in reports:
        d = r["data"]
        for k in flow_keys:
            flow[k] += int(d.get(k, 0) or 0)

        for it in (d.get("transfers_out", []) or []):
            key = f"{it.get('unit_title','')}||{it.get('group_title','')}"
            out_agg[key] += int(it.get("qty", 0) or 0)

        for it in (d.get("transfers_in", []) or []):
            key = f"{it.get('unit_title','')}||{it.get('group_title','')}"
            in_agg[key] += int(it.get("qty", 0) or 0)

    # вычисляем “итоговые” поля
    flow["calv_total"] = flow["calv_cows"] + flow["calv_neteli"]
    flow["born_total"] = flow["calves_heifers_day"] + flow["calves_bulls_day"]
    flow["death_total"] = flow["death_cows"] + flow["death_calves_0_3"] + flow["death_young_over_3"]
    flow["sale_total"] = flow["sale_cows"] + flow["sale_neteli"] + flow["sale_heifers"] + flow["sale_bulls"]
    flow["transfers_out"] = sum(out_agg.values())
    flow["transfers_in"] = sum(in_agg.values())

    return flow, dict(out_agg), dict(in_agg)
