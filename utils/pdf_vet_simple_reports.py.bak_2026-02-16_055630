"""utils/pdf_vet_simple_reports.py

PDF-генерация для «простых» вет-отчётов (коровы, ортопедия) в стиле
«Движение поголовья» (reportlab: баннер + секции + таблицы).

Используется:
- handlers/vet/report_view.py
- handlers/vet/report_submit.py

Функции:
- build_vet_simple_daily_pdf_bytes(...)
- build_vet_simple_monthly_pdf_bytes(...)
"""

from __future__ import annotations

import re
from io import BytesIO
from datetime import datetime
from typing import Any, Dict, List, Tuple, Iterable, Optional, Set

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
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


def _kv_table(rows: List[Tuple[str, str]], col1_w: float = 150 * mm, col2_w: float = 36 * mm) -> Table:
    """Ключ-значение таблица.

    Требование: не дробить названия показателей на несколько строк.
    Делается за счёт:
    - неразрывных пробелов в названии
    - авто-уменьшения шрифта под ширину колонки
    """

    font, font_bold, *_ = _base_styles()

    # paddings соответствуют TableStyle ниже (LEFT/RIGHTPADDING = 8)
    pad_lr = 8
    avail_w = max(30.0, float(col1_w) - 2 * pad_lr)

    def _q_cell(s: str) -> Paragraph:
        raw = _strip_html_and_emoji(s)
        # NBSP, чтобы reportlab не переносил по пробелам
        nobr = raw.replace(" ", " ")

        base = 10.0
        try:
            w = pdfmetrics.stringWidth(raw, font, base)
        except Exception:
            w = 0.0

        size = base
        if w and w > avail_w:

            size = max(7.6, base * (avail_w / w))

        st = ParagraphStyle(
            "c1_fit",
            fontName=font,
            fontSize=size,
            leading=size + 2,
            textColor=C_TEXT,
            alignment=TA_LEFT,
        )
        # чтобы не дробить длинные слова
        st.splitLongWords = 0
        return Paragraph(nobr, st)

    def _v_cell(s: str) -> Paragraph:
        st = ParagraphStyle(
            "c2",
            fontName=font_bold,
            fontSize=10,
            leading=12,
            textColor=C_TEXT,
            alignment=TA_LEFT,
        )
        st.splitLongWords = 0
        return Paragraph(_strip_html_and_emoji(s), st)

    data = [
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
        data.append([_q_cell(k), _v_cell(v)])

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
    data = [[Paragraph(f"<b>{_strip_html_and_emoji(h)}</b>", ParagraphStyle("th", fontName=font_bold, fontSize=9.7, textColor=colors.white)) for h in headers]]
    for r in rows:
        data.append([Paragraph(_strip_html_and_emoji(str(x)), ParagraphStyle("td", fontName=font, fontSize=9.4, textColor=C_TEXT)) for x in r])

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


def _chunks(seq: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# ─────────────────────────────────────────────────────────────
# Daily PDF
# ─────────────────────────────────────────────────────────────
def build_vet_simple_daily_pdf_bytes(
    title: str,
    location: str,
    report_date_h: str,
    questions: List[str],
    keys: List[str],
    data: Dict[str, Any],
) -> bytes:
    """PDF за сутки (таблица показатель->значение)."""

    pdf_title = f"{title} — {location}"
    subtitle = f"Дата: {report_date_h} | Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"{pdf_title} за {report_date_h}",
        author="Бот «Сводка»",
    )

    rows = []
    for q, k in zip(questions, keys):
        rows.append((q, _fmt_int(data.get(k, 0))))

    story: List[Any] = []
    story.append(_header_table(pdf_title, subtitle))
    story.append(Spacer(1, 8))
    story.append(_section_title("Показатели (за день)"))
    story.append(_kv_table(rows))

    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────
# Monthly PDF
# ─────────────────────────────────────────────────────────────
def build_vet_simple_monthly_pdf_bytes(
    title: str,
    location: str,
    month_title: str,
    questions: List[str],
    keys: List[str],
    day_rows: List[Tuple[str, Dict[str, Any]]],
    avg_keys: Optional[Set[str]] = None,
) -> bytes:
    """PDF за месяц: итоги + динамика по дням (таблицы, страницы по чанкам ключей)."""

    avg_keys = set(avg_keys or set())

    pdf_title = f"{title} — {location}"
    subtitle = f"Период: {month_title} | Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"{pdf_title} за месяц {month_title}",
        author="Бот «Сводка»",
    )

    n = len(day_rows)

    # агрегаты
    sums: Dict[str, int] = {k: 0 for k in keys}
    for _d, payload in day_rows:
        for k in keys:
            try:
                sums[k] += int(payload.get(k, 0) or 0)
            except Exception:
                sums[k] += 0

    def agg_value(k: str) -> str:
        if k in avg_keys and n > 0:
            return _fmt_int(round(sums[k] / n))
        return _fmt_int(sums[k])

    summary_rows: List[Tuple[str, str]] = [("Кол-во дней с отчётом", _fmt_int(n))]
    for q, k in zip(questions, keys):
        mark = " (ср.)" if k in avg_keys else ""
        summary_rows.append((q.replace(":", "") + mark, agg_value(k)))

    story: List[Any] = []
    story.append(_header_table(pdf_title, subtitle))
    story.append(Spacer(1, 8))
    story.append(_section_title("Итоги (за месяц)"))

    # если показателей много — режем на 2 таблицы
    if len(summary_rows) <= 14:
        story.append(_kv_table(summary_rows, col1_w=140 * mm, col2_w=50 * mm))
    else:
        story.append(_kv_table(summary_rows[:14], col1_w=140 * mm, col2_w=50 * mm))
        story.append(Spacer(1, 6))
        story.append(_kv_table(summary_rows[14:], col1_w=140 * mm, col2_w=50 * mm))

    # динамика по дням
    story.append(PageBreak())

    max_cols = 6  # + дата
    for idx, chunk_keys in enumerate(_chunks(keys, max_cols)):
        chunk_q = [questions[keys.index(k)] if k in keys else k for k in chunk_keys]

        if idx > 0:
            story.append(PageBreak())

        story.append(_header_table("Динамика по дням", f"{pdf_title} | {month_title}"))
        story.append(Spacer(1, 8))

        story.append(_section_title("Показатели по дням"))

        headers = ["Дата"] + [re.sub(r":\s*$", "", q)[:18] for q in chunk_q]

        # ширины: под landscape(A4) полезная ширина ~ 270mm - 24mm = 246mm
        # оставим 30мм под дату
        total_w = 246 * mm
        w_date = 28 * mm
        w_each = (total_w - w_date) / max(1, len(chunk_keys))
        col_widths = [w_date] + [w_each] * len(chunk_keys)

        rows = []
        for d, payload in day_rows:
            row = [d]
            for k in chunk_keys:
                row.append(_fmt_int(payload.get(k, 0)))
            rows.append(row)

        story.append(_simple_table(headers=headers, rows=rows, col_widths=col_widths))

    doc.build(story)
    return buf.getvalue()
