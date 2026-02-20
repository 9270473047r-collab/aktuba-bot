import re
from io import BytesIO
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib import colors


# ─────────────────────────────────────────────────────────────
# Theme
# ─────────────────────────────────────────────────────────────
C_PRIMARY = colors.HexColor("#1E88E5")
C_PRIMARY_D = colors.HexColor("#1565C0")
C_BG = colors.HexColor("#F6F8FB")
C_GRID = colors.HexColor("#D7DEE8")
C_TEXT = colors.HexColor("#1F2A37")
C_MUTED = colors.HexColor("#6B7280")


# ─────────────────────────────────────────────────────────────
# Fonts (Cyrillic)
# ─────────────────────────────────────────────────────────────
def _register_fonts():
    try:
        pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
        return "DejaVu", "DejaVu-Bold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


def _fmt_int(x: Any) -> str:
    try:
        n = int(x or 0)
    except Exception:
        n = 0
    return f"{n:,}".replace(",", " ")


def _pct(part: int, total: int, digits: int = 1) -> float:
    if total <= 0:
        return 0.0
    return round(part / total * 100.0, digits)


def _strip_html(s: str) -> str:
    s = s or ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</p\s*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[\U0001F000-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF]", "", s)
    return s


def _base_styles():
    font, font_bold = _register_fonts()
    styles = getSampleStyleSheet()

    st_title = ParagraphStyle(
        "TitleX", parent=styles["Title"], fontName=font_bold,
        fontSize=14.5, leading=18, alignment=TA_CENTER, textColor=colors.white
    )
    st_sub = ParagraphStyle(
        "SubX", parent=styles["Normal"], fontName=font,
        fontSize=10, leading=13, alignment=TA_CENTER, textColor=colors.white
    )
    st_h = ParagraphStyle(
        "Hx", parent=styles["Heading2"], fontName=font_bold,
        fontSize=12.2, leading=15, textColor=C_TEXT, spaceBefore=10, spaceAfter=6
    )
    st_p = ParagraphStyle(
        "Px", parent=styles["Normal"], fontName=font,
        fontSize=10.5, leading=13.5, textColor=C_TEXT
    )
    st_note = ParagraphStyle(
        "Nx", parent=styles["Normal"], fontName=font,
        fontSize=9, leading=12, textColor=C_MUTED
    )
    return font, font_bold, st_title, st_sub, st_h, st_p, st_note


def _header_table(title: str, subtitle: str) -> Table:
    _, _, st_title, st_sub, *_ = _base_styles()
    data = [[Paragraph(title, st_title)], [Paragraph(subtitle, st_sub)]]
    t = Table(data, colWidths=[180 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_PRIMARY),
        ("BACKGROUND", (0, 1), (-1, 1), C_PRIMARY_D),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0, C_PRIMARY),
    ]))
    return t


def _section_title(text: str) -> Paragraph:
    *_, st_h, _, _ = _base_styles()
    return Paragraph(text, st_h)


def _kv_table(rows: List[Tuple[str, str]], col1_w: float = 120 * mm, col2_w: float = 60 * mm) -> Table:
    font, font_bold, *_ = _base_styles()
    data = [[
        Paragraph("<b>Показатель</b>", ParagraphStyle("th1", fontName=font_bold, fontSize=10, textColor=colors.white)),
        Paragraph("<b>Значение</b>", ParagraphStyle("th2", fontName=font_bold, fontSize=10, textColor=colors.white))
    ]]

    for k, v in rows:
        data.append([
            Paragraph(k, ParagraphStyle("c1", fontName=font, fontSize=10, textColor=C_TEXT)),
            Paragraph(v, ParagraphStyle("c2", fontName=font_bold, fontSize=10, textColor=C_TEXT, alignment=TA_LEFT))
        ])

    t = Table(data, colWidths=[col1_w, col2_w])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY_D),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.6, C_GRID),
        ("BOX", (0, 0), (-1, -1), 0.9, C_GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6)
    ]))
    for i in range(1, len(data)):
        if i % 2 == 0:
            t.setStyle(TableStyle([("BACKGROUND", (0, i), (-1, i), C_BG)]))
    return t


def _simple_table(headers: List[str], rows: List[List[str]], col_widths: List[float]) -> Table:
    font, font_bold, *_ = _base_styles()
    data = [[Paragraph(f"<b>{h}</b>", ParagraphStyle("th", fontName=font_bold, fontSize=9.7, textColor=colors.white))
             for h in headers]]
    for r in rows:
        data.append([Paragraph(str(x), ParagraphStyle("td", fontName=font, fontSize=9.4, textColor=C_TEXT))
                    for x in r])

    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY_D),
        ("GRID", (0, 0), (-1, -1), 0.5, C_GRID),
        ("BOX", (0, 0), (-1, -1), 0.9, C_GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4)
    ]))
    for i in range(1, len(data)):
        if i % 2 == 0:
            t.setStyle(TableStyle([("BACKGROUND", (0, i), (-1, i), C_BG)]))
    return t


def _flow_int(flow: Dict[str, Any], key: str) -> int:
    return int(flow.get(key, 0) or 0)


def _sum_items(items: Any) -> int:
    if not items:
        return 0
    s = 0
    for x in items:
        if isinstance(x, dict):
            s += int(x.get("count", 0) or 0)
    return s


def _as_ddmmyyyy_from_iso(date_iso: str) -> str:
    try:
        return datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return date_iso


# ─────────────────────────────────────────────────────────────
# FULL Daily PDF (from daily answers dict)
# ─────────────────────────────────────────────────────────────
def _build_full_daily_story(
    location_title: str,
    date_ddmmyyyy: str,
    daily: Dict[str, Any],
    month_flow: Optional[Dict[str, Any]] = None,
    year_flow: Optional[Dict[str, Any]] = None
) -> List[Any]:
    month_flow = month_flow or {}
    year_flow = year_flow or {}
    font, font_bold, st_title, st_sub, st_h, st_p, st_note = _base_styles()

    story: List[Any] = []
    story.append(_header_table(f"Движение поголовья — {location_title}", f"Дата: {date_ddmmyyyy}"))
    story.append(Spacer(1, 8))

    # ───── Поголовье (факт на утро): ИТОГО = фуражные + весь молодняк (вкл. нетели)
    fc = int(daily.get("forage_cows", 0) or 0)
    milking = int(daily.get("milking_cows", 0) or 0)

    h03 = int(daily.get("heifers_0_3", 0) or 0)
    h36 = int(daily.get("heifers_3_6", 0) or 0)
    h612 = int(daily.get("heifers_6_12", 0) or 0)
    h1218 = int(daily.get("heifers_12_18", 0) or 0)
    h18p = int(daily.get("heifers_18_plus", 0) or 0)
    neteli = int(daily.get("neteli_total", 0) or 0)
    b03 = int(daily.get("bulls_0_3", 0) or 0)

    young_total = h03 + h36 + h612 + h1218 + h18p + neteli + b03
    total_cattle_calc = fc + young_total

    preg = int(daily.get("pregnant_cows", 0) or 0)
    preg_pct = _pct(preg, fc, 1)

    story.append(_section_title("Поголовье (факт на утро)"))
    story.append(_kv_table([
        ("Всего КРС (фуражные + весь молодняк, включая нетелей)", f"{_fmt_int(total_cattle_calc)} гол"),
        ("Фуражные коровы", _fmt_int(fc)),
        ("Дойные коровы", _fmt_int(milking)),
        ("Молодняк всего (включая нетелей)", _fmt_int(young_total)),
        ("— Нетели", _fmt_int(neteli)),
        ("— Тёлки 0–3 мес", _fmt_int(h03)),
        ("— Тёлки 3–6 мес", _fmt_int(h36)),
        ("— Тёлки 6–12 мес", _fmt_int(h612)),
        ("— Тёлки 12–18 мес", _fmt_int(h1218)),
        ("— Тёлки старше 18 мес", _fmt_int(h18p)),
        ("— Бычки 0–3 мес", _fmt_int(b03)),
        ("Стельные коровы", f"{_fmt_int(preg)} (стельность {preg_pct} %)")
    ]))
    story.append(Spacer(1, 8))

    # ───── Состояние стада
    hosp = int(daily.get("hospital", 0) or 0)
    mast = int(daily.get("mastitis", 0) or 0)
    cull = int(daily.get("cull", 0) or 0)
    story.append(_section_title("Состояние стада"))
    story.append(_kv_table([
        ("Госпиталь", _fmt_int(hosp)),
        ("Мастит", _fmt_int(mast)),
        ("Брак (на выбытие)", _fmt_int(cull))
    ]))
    story.append(Spacer(1, 8))

    # ───── Поголовье по подразделениям + итоги молодняка
    chemo = {
        "Нетели": int(daily.get("sub_chemo_neteli", 0) or 0),
        "Тёлки 0–3 мес": int(daily.get("sub_chemo_h_0_3", 0) or 0),
        "Тёлки 3–6 мес": int(daily.get("sub_chemo_h_3_6", 0) or 0),
        "Тёлки 6–12 мес": int(daily.get("sub_chemo_h_6_12", 0) or 0),
        "Тёлки старше 12 мес": int(daily.get("sub_chemo_h_gt_12", 0) or 0),
        "Бычки 0–3 мес": int(daily.get("sub_chemo_b_0_3", 0) or 0),
    }
    chemo_total = sum(chemo.values())

    site = {
        "Нетели": int(daily.get("sub_site_neteli", 0) or 0),
        "Тёлки 6–12 мес": int(daily.get("sub_site_h_6_12", 0) or 0),
        "Тёлки старше 12 мес": int(daily.get("sub_site_h_gt_12", 0) or 0),
    }
    site_total = sum(site.values())

    story.append(_section_title("Поголовье по подразделениям (молодняк)"))
    story.append(_kv_table([
        ("Чемодурово — итого молодняк", f"{_fmt_int(chemo_total)}"),
        ("Нетельная площадка — итого молодняк", f"{_fmt_int(site_total)}")
    ]))
    story.append(Spacer(1, 6))

    story.append(Paragraph("<b>Чемодурово</b>", st_p))
    story.append(_kv_table([(k, _fmt_int(v)) for k, v in chemo.items()], col1_w=120*mm, col2_w=60*mm))
    story.append(Spacer(1, 6))

    story.append(Paragraph("<b>Нетельная площадка</b>", st_p))
    story.append(_kv_table([(k, _fmt_int(v)) for k, v in site.items()], col1_w=120*mm, col2_w=60*mm))
    story.append(Spacer(1, 8))

    # ───── Движение (сутки)
    launch = int(daily.get("launch", 0) or 0)

    calv_c = int(daily.get("calv_cows", 0) or 0)
    calv_n = int(daily.get("calv_neteli", 0) or 0)
    calv_total = calv_c + calv_n

    heif_c = int(daily.get("calves_h_cows", 0) or 0)
    bull_c = int(daily.get("calves_b_cows", 0) or 0)
    heif_n = int(daily.get("calves_h_neteli", 0) or 0)
    bull_n = int(daily.get("calves_b_neteli", 0) or 0)

    heif_total = heif_c + heif_n
    bull_total = bull_c + bull_n

    still = int(daily.get("stillborn_day", 0) or 0)
    abort = int(daily.get("abort_day", 0) or 0)

    calves_live = heif_total + bull_total
    calves_all = calves_live + still
    still_pct_day = _pct(still, calv_total, 1)

    story.append(_section_title("Движение стада за сутки"))
    story.append(_kv_table([
        ("Запуск", _fmt_int(launch)),
        ("Отёлы всего (коровы + нетели)", f"{_fmt_int(calv_total)} (коровы {_fmt_int(calv_c)}, нетели {_fmt_int(calv_n)})"),
        ("Приплод (живой)", f"{_fmt_int(calves_live)} (тёлки {_fmt_int(heif_total)}, бычки {_fmt_int(bull_total)})"),
        ("Мертворождённые", f"{_fmt_int(still)} ({still_pct_day} % к отёлу)"),
        ("Приплод всего (живой + мертворождённые)", _fmt_int(calves_all)),
        ("Аборты", _fmt_int(abort))
    ]))
    story.append(Spacer(1, 8))

    # ───── Падёж / Реализация (сутки)
    dc = int(daily.get("death_cows", 0) or 0)
    d03 = int(daily.get("death_calves_0_3", 0) or 0)
    d3p = int(daily.get("death_young_over_3", 0) or 0)
    death_total = dc + d03 + d3p

    sc = int(daily.get("sale_cows", 0) or 0)
    sn = int(daily.get("sale_neteli", 0) or 0)
    sh = int(daily.get("sale_heifers", 0) or 0)
    sb = int(daily.get("sale_bulls", 0) or 0)
    sale_total = sc + sn + sh + sb

    story.append(_section_title("Падёж и реализация за сутки"))
    story.append(_kv_table([
        ("Падёж — коровы", _fmt_int(dc)),
        ("Падёж — телята 0–3 мес", _fmt_int(d03)),
        ("Падёж — молодняк >3 мес", _fmt_int(d3p)),
        ("Падёж всего", _fmt_int(death_total)),
        ("Реализация — коровы", _fmt_int(sc)),
        ("Реализация — нетели", _fmt_int(sn)),
        ("Реализация — тёлки", _fmt_int(sh)),
        ("Реализация — бычки", _fmt_int(sb)),
        ("Реализация всего", _fmt_int(sale_total))
    ]))
    story.append(Spacer(1, 8))

    # ───── Переводы / поступления / племпродажа (сутки)
    tr_out = daily.get("transfers_out") or []
    tr_in = daily.get("transfers_in") or []
    breeding = daily.get("breeding_sales") or []

    if tr_out or tr_in:
        story.append(_section_title("Переводы и поступления за сутки"))
        if tr_out:
            rows = []
            for x in tr_out:
                if not isinstance(x, dict):
                    continue
                rows.append([str(x.get("unit", "")), str(x.get("group", "")), _fmt_int(x.get("count", 0))])
            story.append(Paragraph("<b>Переводы (исходящие)</b>", st_p))
            story.append(_simple_table(["Куда", "Группа", "Кол-во"], rows, [60*mm, 110*mm, 25*mm]))
            story.append(Spacer(1, 6))
        if tr_in:
            rows = []
            for x in tr_in:
                if not isinstance(x, dict):
                    continue
                rows.append([str(x.get("unit", "")), str(x.get("group", "")), _fmt_int(x.get("count", 0))])
            story.append(Paragraph("<b>Поступления (входящие)</b>", st_p))
            story.append(_simple_table(["Откуда", "Группа", "Кол-во"], rows, [60*mm, 110*mm, 25*mm]))
            story.append(Spacer(1, 6))

    if breeding:
        story.append(_section_title("Племпродажа за сутки"))
        rows = []
        for x in breeding:
            if not isinstance(x, dict):
                continue
            rows.append([
                str(x.get("group", "")),
                _fmt_int(x.get("count", 0)),
                str(x.get("to", "")),
                str(x.get("comment", "")) if str(x.get("comment", "")).strip() else "—"
            ])
        story.append(_simple_table(["Группа", "Кол-во", "Куда", "Комментарий"], rows, [55*mm, 20*mm, 60*mm, 45*mm]))
        story.append(Spacer(1, 6))

    # ───── Итоги МЕСЯЦ / ГОД
    def _flow_block(flow: Dict[str, Any]) -> Table:
        calv = _flow_int(flow, "calv_cows") + _flow_int(flow, "calv_neteli")
        heif = _flow_int(flow, "calves_h_cows") + _flow_int(flow, "calves_h_neteli")
        bull = _flow_int(flow, "calves_b_cows") + _flow_int(flow, "calves_b_neteli")
        still_f = _flow_int(flow, "stillborn_day")
        abort_f = _flow_int(flow, "abort_day")
        calves_live_f = heif + bull
        calves_all_f = calves_live_f + still_f

        death_cows_f = _flow_int(flow, "death_cows")
        death_0_3_f = _flow_int(flow, "death_calves_0_3")
        death_gt3_f = _flow_int(flow, "death_young_over_3")
        death_f = death_cows_f + death_0_3_f + death_gt3_f

        sale_cows_f = _flow_int(flow, "sale_cows")
        sale_neteli_f = _flow_int(flow, "sale_neteli")
        sale_heifers_f = _flow_int(flow, "sale_heifers")
        sale_bulls_f = _flow_int(flow, "sale_bulls")
        sale_f = sale_cows_f + sale_neteli_f + sale_heifers_f + sale_bulls_f

        tr_out_total = _sum_items(flow.get("transfers_out") or [])
        tr_in_total = _sum_items(flow.get("transfers_in") or [])
        bs_total = _sum_items(flow.get("breeding_sales") or [])

        still_pct = _pct(still_f, calv, 1)
        heif_pct_live = _pct(heif, calves_live_f, 1)

        return _kv_table([
            ("Отёлы всего", f"{_fmt_int(calv)} (коровы {_fmt_int(_flow_int(flow,'calv_cows'))}, нетели {_fmt_int(_flow_int(flow,'calv_neteli'))})"),
            ("Приплод (живой)", f"{_fmt_int(calves_live_f)} (тёлки {_fmt_int(heif)}, бычки {_fmt_int(bull)})"),
            ("Выход тёлок (от живого приплода)", f"{heif_pct_live} %"),
            ("Мертворождённые", f"{_fmt_int(still_f)} ({still_pct} % к отёлу)"),
            ("Приплод всего (живой + мертворождённые)", _fmt_int(calves_all_f)),
            ("Аборты", _fmt_int(abort_f)),
            ("Падёж всего", _fmt_int(death_f)),
            ("— коровы", _fmt_int(death_cows_f)),
            ("— телята 0–3 мес", _fmt_int(death_0_3_f)),
            ("— молодняк >3 мес", _fmt_int(death_gt3_f)),
            ("Реализация всего", _fmt_int(sale_f)),
            ("— коровы", _fmt_int(sale_cows_f)),
            ("— нетели", _fmt_int(sale_neteli_f)),
            ("— тёлки", _fmt_int(sale_heifers_f)),
            ("— бычки", _fmt_int(sale_bulls_f)),
            ("Переводы исходящие (всего)", _fmt_int(tr_out_total)),
            ("Поступления входящие (всего)", _fmt_int(tr_in_total)),
            ("Племпродажа (всего)", _fmt_int(bs_total))
        ])

    story.append(_section_title("Итоги с начала месяца"))
    story.append(_flow_block(month_flow))
    story.append(Spacer(1, 8))

    story.append(_section_title("Итоги с начала года"))
    story.append(_flow_block(year_flow))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Сформировано автоматически ботом «Сводка».", st_note))
    return story


# ─────────────────────────────────────────────────────────────
# Fallback: build from text/HTML
# ─────────────────────────────────────────────────────────────
def _build_pdf_from_text(title: str, text_html: str) -> bytes:
    font, font_bold, st_title, st_sub, st_h, st_p, st_note = _base_styles()
    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=title,
        author="Бот «Сводка»",
    )

    plain = _strip_html(text_html)
    lines = [x.rstrip() for x in plain.split("\n")]

    story: List[Any] = []
    story.append(_header_table(title, ""))
    story.append(Spacer(1, 8))

    cur_block: List[Tuple[str, str]] = []
    cur_header: Optional[str] = None

    def flush_block():
        nonlocal cur_block, cur_header
        if cur_header:
            story.append(_section_title(cur_header))
        if cur_block:
            story.append(_kv_table(cur_block))
            story.append(Spacer(1, 6))
        cur_block = []
        cur_header = None

    for line in lines:
        if not line.strip():
            flush_block()
            continue

        if line.strip().endswith(":") and len(line.strip()) <= 60:
            flush_block()
            cur_header = line.strip().rstrip(":")
            continue

        if line.lstrip().startswith("•"):
            item = line.lstrip()[1:].strip()
            if "—" in item:
                k, v = item.split("—", 1)
                cur_block.append((k.strip(), v.strip()))
            elif ":" in item:
                k, v = item.split(":", 1)
                cur_block.append((k.strip(), v.strip()))
            else:
                cur_block.append((item, ""))
            continue

        if ":" in line:
            k, v = line.split(":", 1)
            cur_block.append((k.strip(), v.strip()))
        else:
            cur_block.append((line.strip(), ""))

    flush_block()
    story.append(Spacer(1, 6))
    story.append(Paragraph("Сформировано автоматически ботом «Сводка».", st_note))

    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────
def build_herd_daily_pdf_bytes(location_title: str, date_ddmmyyyy: str, *args) -> bytes:
    """
    Поддерживает:
    1) build_herd_daily_pdf_bytes(title, date, report_text_html:str)  [fallback]
    2) build_herd_daily_pdf_bytes(title, date, daily_dict, month_flow, year_flow) [ПОЛНЫЙ, красивый PDF]
    """
    title = f"Движение поголовья — {location_title}"

    # 1) HTML/text
    if len(args) == 1 and isinstance(args[0], str):
        return _build_pdf_from_text(f"{title} за {date_ddmmyyyy}", args[0])

    daily = args[0] if len(args) >= 1 and isinstance(args[0], dict) else {}
    month_flow = args[1] if len(args) >= 2 and isinstance(args[1], dict) else {}
    year_flow = args[2] if len(args) >= 3 and isinstance(args[2], dict) else {}

    # если есть ключи поголовья — делаем полный отчёт
    if any(k in daily for k in ("forage_cows", "heifers_0_3", "neteli_total", "milking_cows", "sub_chemo_neteli", "sub_site_neteli")):
        buf = BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
            title=f"{title} за {date_ddmmyyyy}", author="Бот «Сводка»"
        )
        story = _build_full_daily_story(location_title, date_ddmmyyyy, daily, month_flow, year_flow)
        doc.build(story)
        return buf.getvalue()

    # fallback: короткий режим
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"{title} за {date_ddmmyyyy}", author="Бот «Сводка»"
    )

    calv_d = _flow_int(daily, "calv_cows") + _flow_int(daily, "calv_neteli")
    heifers_d = _flow_int(daily, "calves_h_cows") + _flow_int(daily, "calves_h_neteli")
    bulls_d = _flow_int(daily, "calves_b_cows") + _flow_int(daily, "calves_b_neteli")
    still_d = _flow_int(daily, "stillborn_day")

    calves_live = heifers_d + bulls_d
    calves_all = calves_live + still_d
    still_pct_day = _pct(still_d, calv_d, 1)

    death_d = _flow_int(daily, "death_cows") + _flow_int(daily, "death_calves_0_3") + _flow_int(daily, "death_young_over_3")
    sale_d = _flow_int(daily, "sale_cows") + _flow_int(daily, "sale_neteli") + _flow_int(daily, "sale_heifers") + _flow_int(daily, "sale_bulls")

    m_calv = _flow_int(month_flow, "calv_cows") + _flow_int(month_flow, "calv_neteli")
    m_still = _flow_int(month_flow, "stillborn_day")
    m_still_pct = _pct(m_still, m_calv, 1)

    y_calv = _flow_int(year_flow, "calv_cows") + _flow_int(year_flow, "calv_neteli")
    y_still = _flow_int(year_flow, "stillborn_day")
    y_still_pct = _pct(y_still, y_calv, 1)

    font, font_bold, st_title, st_sub, st_h, st_p, st_note = _base_styles()
    story: List[Any] = []
    story.append(_header_table(title, f"Дата: {date_ddmmyyyy}"))
    story.append(Spacer(1, 8))

    story.append(_section_title("Кратко (сутки)"))
    story.append(_kv_table([
        ("Отёлы", _fmt_int(calv_d)),
        ("Приплод (живой)", f"{_fmt_int(calves_live)} (тёлки {_fmt_int(heifers_d)}, бычки {_fmt_int(bulls_d)})"),
        ("Мертворождённые", f"{_fmt_int(still_d)} ({still_pct_day} % к отёлу)"),
        ("Приплод всего (живой + мертворождённые)", _fmt_int(calves_all)),
        ("Падёж", _fmt_int(death_d)),
        ("Реализация", _fmt_int(sale_d))
    ]))
    story.append(Spacer(1, 8))

    story.append(_section_title("Итоги с начала месяца"))
    story.append(_kv_table([
        ("Отёлы", _fmt_int(m_calv)),
        ("Мертворождённые", f"{_fmt_int(m_still)} ({m_still_pct} % к отёлу)"),
        ("Падёж", _fmt_int(_flow_int(month_flow, "death_cows") + _flow_int(month_flow, "death_calves_0_3") + _flow_int(month_flow, "death_young_over_3"))),
        ("Реализация", _fmt_int(_flow_int(month_flow, "sale_cows") + _flow_int(month_flow, "sale_neteli") + _flow_int(month_flow, "sale_heifers") + _flow_int(month_flow, "sale_bulls")))
    ]))
    story.append(Spacer(1, 8))

    story.append(_section_title("Итоги с начала года"))
    story.append(_kv_table([
        ("Отёлы", _fmt_int(y_calv)),
        ("Мертворождённые", f"{_fmt_int(y_still)} ({y_still_pct} % к отёлу)"),
        ("Падёж", _fmt_int(_flow_int(year_flow, "death_cows") + _flow_int(year_flow, "death_calves_0_3") + _flow_int(year_flow, "death_young_over_3"))),
        ("Реализация", _fmt_int(_flow_int(year_flow, "sale_cows") + _flow_int(year_flow, "sale_neteli") + _flow_int(year_flow, "sale_heifers") + _flow_int(year_flow, "sale_bulls")))
    ]))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Сформировано автоматически ботом «Сводка».", st_note))

    doc.build(story)
    return buf.getvalue()


def build_herd_monthly_pdf_bytes(location_title: str, month_label: str, month_flow: Dict[str, Any], *args) -> bytes:
    """
    Месячный PDF:
    - Итоги (агрегаты)
    - Детализация по дням (если передали month_reports:list)
      rows = даты, cols = показатели (одна таблица на месяц)
    """
    month_reports = args[0] if len(args) >= 1 and isinstance(args[0], list) else None

    def g(k: str) -> int:
        return int(month_flow.get(k, 0) or 0)

    calv = g("calv_cows") + g("calv_neteli")
    heifers = g("calves_h_cows") + g("calves_h_neteli")
    bulls = g("calves_b_cows") + g("calves_b_neteli")
    still = g("stillborn_day")
    abort = g("abort_day")

    calves_live = heifers + bulls
    calves_all = calves_live + still

    still_pct = _pct(still, calv, 1)
    heif_pct_live = _pct(heifers, calves_live, 1)

    death_cows = g("death_cows")
    death_0_3 = g("death_calves_0_3")
    death_gt3 = g("death_young_over_3")
    death = death_cows + death_0_3 + death_gt3

    sale_cows = g("sale_cows")
    sale_neteli = g("sale_neteli")
    sale_heifers = g("sale_heifers")
    sale_bulls = g("sale_bulls")
    sale = sale_cows + sale_neteli + sale_heifers + sale_bulls

    transfers_out = month_flow.get("transfers_out") or []
    transfers_in = month_flow.get("transfers_in") or []
    tr_out_total = _sum_items(transfers_out)
    tr_in_total = _sum_items(transfers_in)

    breeding = month_flow.get("breeding_sales") or []
    bs_total = _sum_items(breeding)

    title = f"Движение поголовья — {location_title}"
    subtitle = f"Период: {month_label}"

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4) if month_reports else A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"{title} за месяц {month_label}",
        author="Бот «Сводка»",
    )
    font, font_bold, st_title, st_sub, st_h, st_p, st_note = _base_styles()

    story: List[Any] = []
    story.append(_header_table(title, subtitle))
    story.append(Spacer(1, 8))

    story.append(_section_title("Итоги движения (месяц)"))
    story.append(_kv_table([
        ("Отёлы (коровы + нетели)", f"{_fmt_int(calv)} (коровы {_fmt_int(g('calv_cows'))}, нетели {_fmt_int(g('calv_neteli'))})"),
        ("Приплод (живой)", f"{_fmt_int(calves_live)} (тёлки {_fmt_int(heifers)}, бычки {_fmt_int(bulls)})"),
        ("Выход тёлок (от живого приплода)", f"{heif_pct_live} %"),
        ("Мертворождённые", f"{_fmt_int(still)} ({still_pct} % к отёлу)"),
        ("Приплод всего (живой + мертворождённые)", _fmt_int(calves_all)),
        ("Аборты", _fmt_int(abort)),
        ("Падёж (всего)", _fmt_int(death)),
        ("— коровы", _fmt_int(death_cows)),
        ("— телята 0–3 мес", _fmt_int(death_0_3)),
        ("— молодняк >3 мес", _fmt_int(death_gt3)),
        ("Реализация (всего)", _fmt_int(sale)),
        ("— коровы", _fmt_int(sale_cows)),
        ("— нетели", _fmt_int(sale_neteli)),
        ("— тёлки", _fmt_int(sale_heifers)),
        ("— бычки", _fmt_int(sale_bulls)),
        ("Переводы исходящие (всего)", _fmt_int(tr_out_total)),
        ("Поступления входящие (всего)", _fmt_int(tr_in_total)),
        ("Племпродажа (всего)", _fmt_int(bs_total))
    ]))
    story.append(Spacer(1, 8))

    # Детализация по дням (ОДНА таблица)
    if month_reports:
        story.append(PageBreak())
        story.append(_header_table("Детализация по дням", subtitle))
        story.append(Spacer(1, 8))
        story.append(_section_title("Движение по дням (строки = даты, столбцы = показатели)"))

        det_rows: List[List[str]] = []
        sums = {
            "calv": 0, "heif": 0, "bull": 0, "still": 0, "abort": 0,
            "death_cows": 0, "death_0_3": 0, "death_gt3": 0,
            "sale_cows": 0,
        }

        for r in month_reports:
            d_iso = str(r.get("report_date", ""))
            d = r.get("data") or {}
            dd = _as_ddmmyyyy_from_iso(d_iso)

            calv_d = int(d.get("calv_cows", 0) or 0) + int(d.get("calv_neteli", 0) or 0)
            heif_d = int(d.get("calves_h_cows", 0) or 0) + int(d.get("calves_h_neteli", 0) or 0)
            bull_d = int(d.get("calves_b_cows", 0) or 0) + int(d.get("calves_b_neteli", 0) or 0)
            still_d = int(d.get("stillborn_day", 0) or 0)
            abort_d = int(d.get("abort_day", 0) or 0)

            calves_live_d = heif_d + bull_d
            still_pct_d = _pct(still_d, calv_d, 1)

            death_cows_d = int(d.get("death_cows", 0) or 0)
            death_0_3_d = int(d.get("death_calves_0_3", 0) or 0)
            death_gt3_d = int(d.get("death_young_over_3", 0) or 0)

            sale_cows_d = int(d.get("sale_cows", 0) or 0)

            det_rows.append([
                dd,
                _fmt_int(calv_d),
                f"{_fmt_int(heif_d)}/{_fmt_int(bull_d)}",
                _fmt_int(still_d),
                f"{still_pct_d}%",
                _fmt_int(calves_live_d),
                _fmt_int(abort_d),
                _fmt_int(death_cows_d),
                _fmt_int(death_0_3_d),
                _fmt_int(death_gt3_d),
                _fmt_int(sale_cows_d)
            ])

            sums["calv"] += calv_d
            sums["heif"] += heif_d
            sums["bull"] += bull_d
            sums["still"] += still_d
            sums["abort"] += abort_d
            sums["death_cows"] += death_cows_d
            sums["death_0_3"] += death_0_3_d
            sums["death_gt3"] += death_gt3_d
            sums["sale_cows"] += sale_cows_d

        total_still_pct = _pct(sums["still"], sums["calv"], 1)
        total_live = sums["heif"] + sums["bull"]
        det_rows.append([
            "<b>Итого</b>",
            _fmt_int(sums["calv"]),
            f"{_fmt_int(sums['heif'])}/{_fmt_int(sums['bull'])}",
            _fmt_int(sums["still"]),
            f"{total_still_pct}%",
            _fmt_int(total_live),
            _fmt_int(sums["abort"]),
            _fmt_int(sums["death_cows"]),
            _fmt_int(sums["death_0_3"]),
            _fmt_int(sums["death_gt3"]),
            _fmt_int(sums["sale_cows"])
        ])

        story.append(_simple_table(
            ["Дата", "Отёлы", "Тёлки/Бычки", "Мертвор", "% мертв.", "Живой приплод", "Аборты",
             "Падёж кор.", "Падёж 0–3", "Падёж >3", "Реализация коров"],
            det_rows,
            [23*mm, 16*mm, 26*mm, 16*mm, 16*mm, 24*mm, 14*mm, 14*mm, 14*mm, 14*mm, 38*mm]
        ))
        story.append(Spacer(1, 8))

    story.append(Paragraph("Сформировано автоматически ботом «Сводка».", st_note))
    doc.build(story)
    return buf.getvalue()


def build_herd_yearly_pdf_bytes(
    location_title: str,
    year_label: str,
    date_from_iso: str,
    date_to_iso: str,
    year_reports: List[Dict[str, Any]],
) -> bytes:
    """
    Годовой PDF: одна таблица по дням (строки = даты), но колонки режутся на страницы,
    чтобы вместить ВСЕ показатели движения поголовья.
    """
    title = f"Движение поголовья — {location_title}"
    font, font_bold, st_title, st_sub, st_h, st_p, st_note = _base_styles()

    def ddmmyyyy(iso: str) -> str:
        try:
            return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")
        except Exception:
            return iso

    def g(d: Dict[str, Any], k: str) -> int:
        try:
            return int(d.get(k, 0) or 0)
        except Exception:
            return 0

    # карта данных по дате
    rep_map: Dict[str, Dict[str, Any]] = {}
    for r in (year_reports or []):
        iso = str(r.get("report_date") or "").strip()
        if iso:
            rep_map[iso] = r.get("data") or {}

    d0 = datetime.strptime(date_from_iso, "%Y-%m-%d").date()
    d1 = datetime.strptime(date_to_iso, "%Y-%m-%d").date()

    # список дней
    day_list: List[str] = []
    cur = d0
    while cur <= d1:
        day_list.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)

    # вычисление всех метрик на день
    def calc_row(d: Dict[str, Any]) -> Dict[str, int]:
        calv_c = g(d, "calv_cows")
        calv_n = g(d, "calv_neteli")
        calv = calv_c + calv_n

        heif = g(d, "calves_h_cows") + g(d, "calves_h_neteli")
        bull = g(d, "calves_b_cows") + g(d, "calves_b_neteli")
        calves_live = heif + bull

        still = g(d, "stillborn_day")
        abort = g(d, "abort_day")

        death_cows = g(d, "death_cows")
        death_0_3 = g(d, "death_calves_0_3")
        death_gt3 = g(d, "death_young_over_3")
        death_total = death_cows + death_0_3 + death_gt3

        sale_cows = g(d, "sale_cows")
        sale_neteli = g(d, "sale_neteli")
        sale_heif = g(d, "sale_heifers")
        sale_bulls = g(d, "sale_bulls")
        sale_total = sale_cows + sale_neteli + sale_heif + sale_bulls

        tr_out = _sum_items(d.get("transfers_out") or [])
        tr_in = _sum_items(d.get("transfers_in") or [])
        breeding = _sum_items(d.get("breeding_sales") or [])

        launch = g(d, "launch")

        return {
            "launch": launch,
            "calv": calv,
            "calv_cows": calv_c,
            "calv_neteli": calv_n,
            "heif": heif,
            "bull": bull,
            "calves_live": calves_live,
            "still": still,
            "abort": abort,
            "death_total": death_total,
            "death_cows": death_cows,
            "death_0_3": death_0_3,
            "death_gt3": death_gt3,
            "sale_total": sale_total,
            "sale_cows": sale_cows,
            "sale_neteli": sale_neteli,
            "sale_heif": sale_heif,
            "sale_bulls": sale_bulls,
            "tr_out": tr_out,
            "tr_in": tr_in,
            "breeding": breeding,
        }

    # колонки (ключ, заголовок HTML с переносом)
    COLS = [
        ("launch", "Запуск"),
        ("calv", "Отёлы<br/>всего"),
        ("calv_cows", "Отёлы<br/>коровы"),
        ("calv_neteli", "Отёлы<br/>нетели"),
        ("heif", "Приплод<br/>тёлки"),
        ("bull", "Приплод<br/>бычки"),
        ("calves_live", "Приплод<br/>живой"),
        ("still", "Мертвор<br/>всего"),
        ("abort", "Аборты"),
        ("death_total", "Падёж<br/>всего"),
        ("death_cows", "Падёж<br/>коровы"),
        ("death_0_3", "Падёж<br/>0–3"),
        ("death_gt3", "Падёж<br/>>3"),
        ("sale_total", "Реализация<br/>всего"),
        ("sale_cows", "Реализация<br/>коровы"),
        ("sale_neteli", "Реализация<br/>нетели"),
        ("sale_heif", "Реализация<br/>тёлки"),
        ("sale_bulls", "Реализация<br/>бычки"),
        ("tr_out", "Переводы<br/>исх."),
        ("tr_in", "Поступл.<br/>вх."),
        ("breeding", "Племпрод.<br/>всего"),
    ]

    # собираем строки + итоги
    rows_by_day: List[Tuple[str, Dict[str, int]]] = []
    totals: Dict[str, int] = {k: 0 for (k, _) in COLS}

    for iso in day_list:
        d = rep_map.get(iso, {}) or {}
        calc = calc_row(d)
        rows_by_day.append((ddmmyyyy(iso), calc))
        for k in totals.keys():
            totals[k] += int(calc.get(k, 0) or 0)

    # PDF
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=title,
        author="Бот «Сводка»",
    )

    story: List[Any] = []
    story.append(_header_table(title, f"{year_label} | Период: {ddmmyyyy(date_from_iso)} – {ddmmyyyy(date_to_iso)}"))
    story.append(Spacer(1, 8))
    story.append(_section_title("Движение поголовья по дням (все показатели)"))

    def chunks(seq, n):
        for i in range(0, len(seq), n):
            yield seq[i:i+n]

    # сколько колонок на страницу (кроме даты)
    max_cols = 9

    th = ParagraphStyle("thX", fontName=font_bold, fontSize=8.2, leading=9.2, textColor=colors.white, alignment=TA_CENTER)
    td = ParagraphStyle("tdX", fontName=font, fontSize=8.0, leading=9.2, textColor=C_TEXT, alignment=TA_CENTER)
    tot = ParagraphStyle("totX", fontName=font_bold, fontSize=8.2, leading=9.2, textColor=C_TEXT, alignment=TA_CENTER)

    for idx, chunk_cols in enumerate(chunks(COLS, max_cols)):
        if idx > 0:
            story.append(PageBreak())
            story.append(_header_table(title, f"{year_label} | продолжение (колонки {idx*max_cols+1}–{idx*max_cols+len(chunk_cols)})"))
            story.append(Spacer(1, 6))

        table_data = []
        table_data.append([Paragraph("<b>Дата</b>", th)] + [Paragraph(f"<b>{h}</b>", th) for (_, h) in chunk_cols])

        for d_str, calc in rows_by_day:
            row = [Paragraph(d_str, td)]
            for (k, _) in chunk_cols:
                row.append(Paragraph(_fmt_int(calc.get(k, 0)), td))
            table_data.append(row)

        # ИТОГО
        total_row = [Paragraph("<b>ИТОГО</b>", tot)]
        for (k, _) in chunk_cols:
            total_row.append(Paragraph(f"<b>{_fmt_int(totals.get(k, 0))}</b>", tot))
        table_data.append(total_row)

        # ширины
        total_w = 277 * mm
        w_date = 24 * mm
        w_each = (total_w - w_date) / max(1, len(chunk_cols))
        col_widths = [w_date] + [w_each] * len(chunk_cols)

        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY_D),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.45, C_GRID),
            ("BOX", (0, 0), (-1, -1), 0.9, C_GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))

        # зебра
        for r_i in range(1, len(table_data)-1):
            if r_i % 2 == 0:
                t.setStyle(TableStyle([("BACKGROUND", (0, r_i), (-1, r_i), C_BG)]))

        # ИТОГО подсветка
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, len(table_data)-1), (-1, len(table_data)-1), colors.HexColor("#EEF2FF")),
        ]))

        story.append(t)

    story.append(Spacer(1, 8))
    story.append(Paragraph("Сформировано автоматически ботом «Сводка».", st_note))

    doc.build(story)
    return buf.getvalue()
