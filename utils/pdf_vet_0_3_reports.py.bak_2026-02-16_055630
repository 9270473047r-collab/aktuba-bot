"""utils/pdf_vet_0_3_reports.py

PDF-генерация для ветеринарии (молодняк 0–3 мес.).

Оформление приведено к стилю «Движение поголовья» (utils/pdf_herd_movement_reports.py):
- reportlab
- баннер в шапке
- секции и таблицы с чередованием строк

Сигнатуры функций сохранены:
- build_vet_0_3_daily_pdf_bytes(location_title, date_ddmmyyyy, data)
- build_vet_0_3_monthly_pdf_bytes(location_title, month_title, day_rows)
"""

from __future__ import annotations

import re
from io import BytesIO
from datetime import datetime
from typing import Any, Dict, List, Tuple

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib import colors


# ─────────────────────────────────────────────────────────────
# Theme (как в herd_movement)
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
def _register_fonts() -> Tuple[str, str]:
    """Возвращает (regular, bold)."""
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


def _fmt_pct(x: Any, digits: int = 2) -> str:
    try:
        v = float(x or 0)
    except Exception:
        v = 0.0
    return f"{v:.{digits}f}".replace(".", ",")


_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "]+",
    flags=re.UNICODE,
)


def _strip_html_and_emoji(s: str) -> str:
    s = s or ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</p\s*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = _EMOJI_RE.sub("", s)
    return s.strip()


def _base_styles():
    font, font_bold = _register_fonts()
    styles = getSampleStyleSheet()

    st_title = ParagraphStyle(
        "TitleX",
        parent=styles["Title"],
        fontName=font_bold,
        fontSize=14.5,
        leading=18,
        alignment=TA_CENTER,
        textColor=colors.white,
    )
    st_sub = ParagraphStyle(
        "SubX",
        parent=styles["Normal"],
        fontName=font,
        fontSize=10,
        leading=13,
        alignment=TA_CENTER,
        textColor=colors.white,
    )
    st_h = ParagraphStyle(
        "Hx",
        parent=styles["Heading2"],
        fontName=font_bold,
        fontSize=12.2,
        leading=15,
        textColor=C_TEXT,
        spaceBefore=10,
        spaceAfter=6,
    )
    st_p = ParagraphStyle(
        "Px",
        parent=styles["Normal"],
        fontName=font,
        fontSize=10.5,
        leading=13.5,
        textColor=C_TEXT,
    )
    st_note = ParagraphStyle(
        "Nx",
        parent=styles["Normal"],
        fontName=font,
        fontSize=9,
        leading=12,
        textColor=C_MUTED,
    )
    return font, font_bold, st_title, st_sub, st_h, st_p, st_note


def _header_table(title: str, subtitle: str) -> Table:
    _, _, st_title, st_sub, *_ = _base_styles()
    data = [[Paragraph(title, st_title)], [Paragraph(subtitle, st_sub)]]
    t = Table(data, colWidths=[180 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), C_PRIMARY),
                ("BACKGROUND", (0, 1), (-1, 1), C_PRIMARY_D),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BOX", (0, 0), (-1, -1), 0, C_PRIMARY),
            ]
        )
    )
    return t


def _section_title(text: str) -> Paragraph:
    *_, st_h, _, _ = _base_styles()
    return Paragraph(text, st_h)


def _kv_table(rows: List[Tuple[str, str]], col1_w: float = 120 * mm, col2_w: float = 60 * mm) -> Table:
    font, font_bold, *_ = _base_styles()
    data: List[List[Any]] = [
        [
            Paragraph(
                "<b>Показатель</b>",
                ParagraphStyle("th1", fontName=font_bold, fontSize=10, textColor=colors.white),
            ),
            Paragraph(
                "<b>Значение</b>",
                ParagraphStyle("th2", fontName=font_bold, fontSize=10, textColor=colors.white),
            ),
        ]
    ]

    for k, v in rows:
        data.append(
            [
                Paragraph(k, ParagraphStyle("c1", fontName=font, fontSize=10, textColor=C_TEXT)),
                Paragraph(
                    v,
                    ParagraphStyle(
                        "c2", fontName=font_bold, fontSize=10, textColor=C_TEXT, alignment=TA_LEFT
                    ),
                ),
            ]
        )

    t = Table(data, colWidths=[col1_w, col2_w])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY_D),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.6, C_GRID),
                ("BOX", (0, 0), (-1, -1), 0.9, C_GRID),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    for i in range(1, len(data)):
        if i % 2 == 0:
            t.setStyle(TableStyle([("BACKGROUND", (0, i), (-1, i), C_BG)]))
    return t


def _simple_table(headers: List[str], rows: List[List[str]], col_widths: List[float]) -> Table:
    font, font_bold, *_ = _base_styles()

    data: List[List[Any]] = [
        [
            Paragraph(
                f"<b>{h}</b>",
                ParagraphStyle("th", fontName=font_bold, fontSize=9.7, textColor=colors.white),
            )
            for h in headers
        ]
    ]

    for r in rows:
        data.append(
            [
                Paragraph(str(x), ParagraphStyle("td", fontName=font, fontSize=9.4, textColor=C_TEXT))
                for x in r
            ]
        )

    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY_D),
                ("GRID", (0, 0), (-1, -1), 0.5, C_GRID),
                ("BOX", (0, 0), (-1, -1), 0.9, C_GRID),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    for i in range(1, len(data)):
        if i % 2 == 0:
            t.setStyle(TableStyle([("BACKGROUND", (0, i), (-1, i), C_BG)]))
    return t


def _val_cnt_pct(d: Dict[str, Any], cnt_key: str, pct_key: str) -> str:
    cnt = int(d.get(cnt_key, 0) or 0)
    pct = d.get(pct_key, 0) or 0
    return f"{_fmt_int(cnt)} ({_fmt_pct(pct, 2)}%)"


def _cases_rows(cases: List[Dict[str, Any]], typ: str) -> List[List[str]]:
    out: List[List[str]] = []
    for c in cases or []:
        if not isinstance(c, dict):
            continue
        age = str(c.get("age_days", ""))
        diag = str(c.get("diagnosis", ""))
        out.append([typ, age, diag])
    return out


# ─────────────────────────────────────────────────────────────
# Daily PDF
# ─────────────────────────────────────────────────────────────

def build_vet_0_3_daily_pdf_bytes(location_title: str, date_ddmmyyyy: str, data: Dict[str, Any]) -> bytes:
    """PDF за сутки по вет. молодняку 0–3 мес."""

    title = f"Ветеринария 0–3 мес — {location_title}"
    subtitle = f"Дата: {date_ddmmyyyy} | Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"{title} за {date_ddmmyyyy}",
        author="Бот «Сводка»",
    )

    *_, st_p, st_note = _base_styles()

    story: List[Any] = []
    story.append(_header_table(title, subtitle))
    story.append(Spacer(1, 8))

    # --- Сводка
    story.append(_section_title("Сводные показатели"))
    story.append(
        _kv_table(
            [
                ("Поголовье 0–3 мес", f"{_fmt_int(data.get('total_0_3', 0))} гол"),
                ("Поступило за сутки", f"{_fmt_int(data.get('received', 0))} гол"),
                ("Переведено в 3+ мес", f"{_fmt_int(data.get('moved_3_plus', 0))} гол"),
                ("Для реализации", f"{_fmt_int(data.get('to_sell', 0))} гол"),
                ("Выпойка (итого)", f"{_fmt_int(data.get('feed_total_l', 0))} л"),
                ("Выпойка (средняя, л/гол)", _fmt_pct(data.get('feed_avg_lph', 0), 2)),
                ("Падёж", _val_cnt_pct(data, 'dead_count', 'dead_pct')),
                ("Санубой", _val_cnt_pct(data, 'san_count', 'san_pct')),
                ("Потери всего", _val_cnt_pct(data, 'loss_total', 'loss_total_pct')),
            ]
        )
    )
    story.append(Spacer(1, 6))

    # --- Выпойка детализация
    story.append(_section_title("Выпойка (детализация)"))
    story.append(
        _simple_table(
            headers=["Показатель", "Гол", "Литры"],
            rows=[
                ["Утро", _fmt_int(data.get('feed_morn_heads', 0)), _fmt_int(data.get('feed_morn_l', 0))],
                ["Вечер", _fmt_int(data.get('feed_even_heads', 0)), _fmt_int(data.get('feed_even_l', 0))],
            ],
            col_widths=[70 * mm, 35 * mm, 55 * mm],
        )
    )
    story.append(Spacer(1, 6))

    # --- Заболеваемость
    story.append(_section_title("Заболеваемость 0–3 мес (за сутки)"))

    disease_rows: List[Tuple[str, str]] = [
        ("Диарея (инъекции)", _val_cnt_pct(data, "diarr_inj", "diarr_inj_pct")),
        ("Тяжёлая диарея (дегидратация)", _val_cnt_pct(data, "diarr_severe", "diarr_severe_pct")),
        ("Рецидивы диареи", _val_cnt_pct(data, "diarr_relapse", "diarr_relapse_pct")),
        ("Диспепсия 0–14 дн", _val_cnt_pct(data, "dyspepsia_0_14", "dyspepsia_0_14_pct")),
        ("ЖКТ 15+ дн", _val_cnt_pct(data, "gkt_15_plus", "gkt_15_plus_pct")),
        ("Диарея (браслеты/перорально)", _val_cnt_pct(data, "diarr_bracelets", "diarr_bracelets_pct")),
        ("Пневмония (всего)", _val_cnt_pct(data, "pneumonia", "pneumonia_pct")),
        ("Пневмония (инъекции)", _val_cnt_pct(data, "pneumonia_inj", "pneumonia_inj_pct")),
        ("Пневмония повторно", _val_cnt_pct(data, "pneumonia_repeat", "pneumonia_repeat_pct")),
        ("Омфалиты/патологии", _val_cnt_pct(data, "omphalitis", "omphalitis_pct")),
        ("Травмы/переломы/хромота", _val_cnt_pct(data, "injuries", "injuries_pct")),
    ]

    story.append(_kv_table(disease_rows))

    other = str(data.get("other_diseases", "") or "").strip()
    if other:
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<b>Прочие заболевания:</b> { _strip_html_and_emoji(other) }", st_p))

    # --- Статус лечения
    story.append(_section_title("Статус лечения"))
    story.append(
        _kv_table(
            [
                ("Тяжёлые (риск падежа)", _val_cnt_pct(data, "risk_death", "risk_death_pct")),
                ("На лечении всего", _val_cnt_pct(data, "on_treatment", "on_treatment_pct")),
                ("Новые случаи (за сутки)", _val_cnt_pct(data, "new_cases", "new_cases_pct")),
                ("Выздоровело/снято", _fmt_int(data.get("recovered", 0))),
            ]
        )
    )

    # --- Список случаев
    dead_cases = data.get("dead_cases") or []
    san_cases = data.get("san_cases") or []

    case_rows = _cases_rows(dead_cases, "Падёж") + _cases_rows(san_cases, "Санубой")
    if case_rows:
        story.append(_section_title("Падёж / санубой — список случаев"))
        story.append(
            _simple_table(
                headers=["Тип", "Возраст, дн", "Диагноз"],
                rows=case_rows,
                col_widths=[30 * mm, 25 * mm, 115 * mm],
            )
        )

    # --- Замечания
    notes = str(data.get("notes", "") or "").strip()
    if notes:
        story.append(_section_title("Замечания"))
        story.append(Paragraph(_strip_html_and_emoji(notes).replace("\n", "<br/>"), st_p))

    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "Источник данных: отчёт, заполненный в Telegram-боте. PDF сформирован автоматически.",
            st_note,
        )
    )

    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────
# Monthly PDF
# ─────────────────────────────────────────────────────────────

def build_vet_0_3_monthly_pdf_bytes(
    location_title: str,
    month_title: str,
    day_rows: List[Tuple[str, Dict[str, Any]]],
) -> bytes:
    """PDF за месяц по вет. молодняку 0–3.

    Параметры:
      - month_title: строка вида "01.2026" или "01.2026" (как передаёт handlers/vet/report_view.py)
      - day_rows: [("DD.MM", data_dict), ...]
    """

    title = f"Ветеринария 0–3 мес — {location_title}"
    subtitle = f"Период: {month_title} | Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"

    # агрегаты
    n_days = len(day_rows)
    if n_days == 0:
        # пустой PDF (но валидный)
        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
        *_, st_p, st_note = _base_styles()
        story = [
            _header_table(title, subtitle),
            Spacer(1, 10),
            Paragraph("Нет данных за выбранный месяц.", st_p),
            Spacer(1, 6),
            Paragraph("PDF сформирован автоматически.", st_note),
        ]
        doc.build(story)
        return buf.getvalue()

    def s(key: str) -> int:
        total = 0
        for _d, payload in day_rows:
            try:
                total += int((payload or {}).get(key, 0) or 0)
            except Exception:
                pass
        return total

    def avg(key: str) -> float:
        return (s(key) / n_days) if n_days else 0.0

    avg_total = avg("total_0_3")
    sum_received = s("received")
    sum_moved = s("moved_3_plus")
    sum_sell = s("to_sell")

    sum_feed = s("feed_total_l")
    avg_feed = sum_feed / n_days

    sum_dead = s("dead_count")
    sum_san = s("san_count")
    sum_loss = s("loss_total")

    sum_new = s("new_cases")
    sum_rec = s("recovered")

    sum_diarr = s("diarr_inj")
    sum_pneu = s("pneumonia")

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"{title} за месяц {month_title}",
        author="Бот «Сводка»",
    )

    *_, st_p, st_note = _base_styles()

    story: List[Any] = []
    story.append(_header_table(title, subtitle))
    story.append(Spacer(1, 8))

    story.append(_section_title("Итоги (месяц)"))
    story.append(
        _kv_table(
            [
                ("Дней с отчётами", _fmt_int(n_days)),
                ("Поголовье 0–3 (среднее)", _fmt_pct(avg_total, 1) + " гол"),
                ("Поступило (сумма)", _fmt_int(sum_received)),
                ("Переведено 3+ (сумма)", _fmt_int(sum_moved)),
                ("Для реализации (сумма)", _fmt_int(sum_sell)),
                ("Выпойка (сумма)", _fmt_int(sum_feed) + " л"),
                ("Выпойка (среднее/день)", _fmt_pct(avg_feed, 1) + " л"),
                ("Падёж (сумма)", _fmt_int(sum_dead)),
                ("Санубой (сумма)", _fmt_int(sum_san)),
                ("Потери всего (сумма)", _fmt_int(sum_loss)),
                ("Новые случаи (сумма)", _fmt_int(sum_new)),
                ("Выздоровело (сумма)", _fmt_int(sum_rec)),
                ("Диарея (инъекции) — всего", _fmt_int(sum_diarr)),
                ("Пневмония — всего", _fmt_int(sum_pneu)),
            ]
        )
    )

    story.append(PageBreak())
    story.append(_header_table("Динамика по дням", subtitle))
    story.append(Spacer(1, 8))

    # таблица 1: основные метрики
    story.append(_section_title("Основные показатели (по дням)"))
    rows1: List[List[str]] = []
    for d, payload in day_rows:
        p = payload or {}
        rows1.append(
            [
                d,
                _fmt_int(p.get("total_0_3", 0)),
                _fmt_int(p.get("received", 0)),
                _fmt_int(p.get("moved_3_plus", 0)),
                _fmt_int(p.get("feed_total_l", 0)),
                _fmt_int(p.get("dead_count", 0)),
                _fmt_int(p.get("san_count", 0)),
                _fmt_int(p.get("loss_total", 0)),
                _fmt_int(p.get("on_treatment", 0)),
                _fmt_int(p.get("risk_death", 0)),
            ]
        )

    story.append(
        _simple_table(
            headers=[
                "Дата",
                "Погол",
                "Поступ",
                "Перевод 3+",
                "Выпойка, л",
                "Падёж",
                "Сан",
                "Потери",
                "Лечение",
                "Риск",
            ],
            rows=rows1,
            col_widths=[18 * mm, 18 * mm, 18 * mm, 22 * mm, 22 * mm, 16 * mm, 16 * mm, 16 * mm, 18 * mm, 18 * mm],
        )
    )

    story.append(Spacer(1, 8))

    # таблица 2: болезни
    story.append(_section_title("Заболеваемость (по дням)"))
    rows2: List[List[str]] = []
    for d, payload in day_rows:
        p = payload or {}
        rows2.append(
            [
                d,
                _fmt_int(p.get("diarr_inj", 0)),
                _fmt_int(p.get("diarr_severe", 0)),
                _fmt_int(p.get("dyspepsia_0_14", 0)),
                _fmt_int(p.get("gkt_15_plus", 0)),
                _fmt_int(p.get("pneumonia", 0)),
                _fmt_int(p.get("omphalitis", 0)),
                _fmt_int(p.get("injuries", 0)),
            ]
        )

    story.append(
        _simple_table(
            headers=["Дата", "Диар.инъ", "Диар.тяж", "Диспеп", "ЖКТ 15+", "Пневм", "Омф", "Травмы"],
            rows=rows2,
            col_widths=[18 * mm, 20 * mm, 20 * mm, 20 * mm, 20 * mm, 18 * mm, 18 * mm, 18 * mm],
        )
    )

    story.append(Spacer(1, 6))
    story.append(Paragraph("PDF сформирован автоматически на основе данных из БД бота.", st_note))

    doc.build(story)
    return buf.getvalue()
