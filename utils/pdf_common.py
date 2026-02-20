# utils/pdf_common.py — общий модуль PDF на fpdf2 (аккуратный, совместимый)
# -----------------------------------------------------------------------------
from __future__ import annotations

import os
import re
from typing import Optional, List, Any, Dict, Sequence

from fpdf import FPDF

try:
    # fpdf2 >= 2.7
    from fpdf.enums import WrapMode, MethodReturnValue, Align, XPos, YPos
except Exception:  # fallback for older fpdf2
    WrapMode = None
    MethodReturnValue = None
    Align = None
    XPos = None
    YPos = None


# ─────────────────────────────────────────────────────────────
# THEME (единый стиль для всех PDF)
# ─────────────────────────────────────────────────────────────
THEME_DEFAULT: Dict[str, Any] = {
    "primary": (33, 150, 243),
    "primary_dark": (25, 118, 210),
    "header_text": (255, 255, 255),
    "section_fill": (232, 245, 253),
    "table_header_fill": (33, 150, 243),
    "table_header_text": (255, 255, 255),
    "row_odd": (255, 255, 255),
    "row_even": (248, 250, 252),
    "border": (210, 214, 220),
    "text": (0, 0, 0),   # <-- FIX: было битое "t    "text"
    "muted": (70, 70, 70),
}


def _merge_theme(theme: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not theme:
        return dict(THEME_DEFAULT)
    t = dict(THEME_DEFAULT)
    t.update(theme)
    return t


# ─────────────────────────────────────────────────────────────
# ШРИФТЫ (Linux)
# ─────────────────────────────────────────────────────────────
_DEFAULT_FONT_REGULAR_CANDIDATES = [
    os.getenv("PDF_FONT_REGULAR", "").strip(),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
]

_DEFAULT_FONT_BOLD_CANDIDATES = [
    os.getenv("PDF_FONT_BOLD", "").strip(),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
]


def _first_existing(paths: List[str]) -> Optional[str]:
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


FONT_REGULAR_PATH = _first_existing(_DEFAULT_FONT_REGULAR_CANDIDATES)
FONT_BOLD_PATH = _first_existing(_DEFAULT_FONT_BOLD_CANDIDATES)
FONT_FAMILY = "DejaVu"


# ─────────────────────────────────────────────────────────────
# ТЕКСТ: безопасный вывод для PDF
# ─────────────────────────────────────────────────────────────
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


def safe_text(val: Any) -> str:
    if val is None:
        s = ""
    else:
        s = str(val)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = _EMOJI_RE.sub("", s)
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s


def pdf_safe(text: str) -> str:
    # совместимость со старыми модулями
    if text is None:
        return ""
    return str(text).replace("✅", "OK")


# ─────────────────────────────────────────────────────────────
# PDF: базовые настройки и байты
# ─────────────────────────────────────────────────────────────
def setup_pdf(pdf: FPDF):
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_margins(12, 12, 12)
    pdf.set_creator("aktuba_bot")
    pdf.set_title("Report")
    pdf.set_subject("Report")

    if FONT_REGULAR_PATH and FONT_BOLD_PATH:
        try:
            pdf.add_font(FONT_FAMILY, "", FONT_REGULAR_PATH, uni=True)
            pdf.add_font(FONT_FAMILY, "B", FONT_BOLD_PATH, uni=True)
        except Exception:
            # если add_font не поддерживается или файл не читается — остаёмся на Helvetica
            pass

    if FONT_REGULAR_PATH and FONT_BOLD_PATH:
        pdf.set_font(FONT_FAMILY, "", 10)
    else:
        pdf.set_font("Helvetica", "", 10)


def set_font(pdf: FPDF, bold: bool = False, size: int = 10):
    if FONT_REGULAR_PATH and FONT_BOLD_PATH:
        pdf.set_font(FONT_FAMILY, "B" if bold else "", size)
    else:
        pdf.set_font("Helvetica", "B" if bold else "", size)


def _pdf_bytes(pdf: FPDF) -> bytes:
    out = pdf.output(dest="S")
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return str(out).encode("latin1", errors="ignore")


def pdf_bytes(pdf: FPDF) -> bytes:
    return _pdf_bytes(pdf)


# алиас под импорт в некоторых модулях (у вас встречается pdf_byte)
def pdf_byte(pdf: FPDF) -> bytes:
    return _pdf_bytes(pdf)


def _wrapmode():
    if WrapMode is not None:
        return WrapMode.CHAR
    return None


def _align(a: str):
    if Align is None:
        return a
    try:
        return Align(a)
    except Exception:
        au = a.upper()
        return Align.L if au == "L" else Align.R if au == "R" else Align.C if au == "C" else Align.J


def _multi_cell(
    pdf: FPDF,
    w: float,
    h: float,
    txt: str,
    *,
    border: int = 0,
    align: str = "L",
    fill: bool = False,
    new_x=None,
    new_y=None,
    wrapmode=None,
    dry_run: bool = False,
    output=None,
):
    """
    Унифицированный multi_cell:
    - Для новых fpdf2 передаём new_x/new_y/wrapmode/dry_run/output.
    - Для старых fpdf2 — безопасно откатываемся на базовый вызов без этих параметров.
    """
    kwargs = {"border": border, "align": _align(align), "fill": fill}

    # ВАЖНО: передаём дополнительные kw только если они реально есть/нужны
    if wrapmode is not None and WrapMode is not None:
        kwargs["wrapmode"] = wrapmode
    if new_x is not None and XPos is not None:
        kwargs["new_x"] = new_x
    if new_y is not None and YPos is not None:
        kwargs["new_y"] = new_y
    if dry_run and MethodReturnValue is not None:
        kwargs["dry_run"] = True
        kwargs["output"] = output

    try:
        return pdf.multi_cell(w, h, txt, **kwargs)
    except TypeError:
        # старые версии: убираем неизвестные kwargs
        kwargs.pop("wrapmode", None)
        kwargs.pop("new_x", None)
        kwargs.pop("new_y", None)
        kwargs.pop("dry_run", None)
        kwargs.pop("output", None)
        return pdf.multi_cell(w, h, txt, **kwargs)


def _need_height(pdf: FPDF, w: float, line_h: float, text: str, align: str = "L") -> float:
    txt = safe_text(text)

    # Если нет MethodReturnValue или dry_run не поддерживается — оцениваем грубо
    if MethodReturnValue is None:
        return line_h * max(1, (len(txt) // 60) + 1)

    try:
        return float(
            _multi_cell(
                pdf,
                w,
                line_h,
                txt,
                border=0,
                align=align,
                fill=False,
                wrapmode=_wrapmode(),
                dry_run=True,
                output=MethodReturnValue.HEIGHT,
            )
        )
    except Exception:
        return line_h * max(1, (len(txt) // 60) + 1)


def _ensure_space(pdf: FPDF, h: float):
    if pdf.get_y() + h > (pdf.h - pdf.b_margin):
        pdf.add_page()


# ─────────────────────────────────────────────────────────────
# РЕНДЕР: безопасные многострочные строки
# ─────────────────────────────────────────────────────────────
def mc(pdf: FPDF, text: str, h: float = 5.6, align: str = "L"):
    pdf.set_x(pdf.l_margin)
    _multi_cell(
        pdf,
        0,
        h,
        safe_text(text),
        align=align,
        wrapmode=_wrapmode(),
    )


# ─────────────────────────────────────────────────────────────
# Заголовки / секции (цветные)
# ─────────────────────────────────────────────────────────────
def header_block(pdf: FPDF, title: str, subtitle: str = "", theme: Optional[Dict[str, Any]] = None):
    t = _merge_theme(theme)
    pdf.add_page()

    pdf.set_fill_color(*t["primary"])
    pdf.rect(0, 0, pdf.w, 22, style="F")

    pdf.set_text_color(*t["header_text"])
    set_font(pdf, bold=True, size=14)
    pdf.set_xy(pdf.l_margin, 6)
    pdf.cell(0, 8, safe_text(title), border=0)

    if subtitle:
        set_font(pdf, bold=False, size=10)
        pdf.set_xy(pdf.l_margin, 14)
        pdf.cell(0, 6, safe_text(subtitle), border=0)

    pdf.set_text_color(*t["text"])
    pdf.set_y(26)


def add_title(pdf: FPDF, *args):
    """
    Совместимость:
      - add_title(pdf, title, subtitle="")
      - add_title(pdf, font, theme, title, subtitle="")
    """
    if not args:
        return

    theme = None
    if len(args) >= 3 and isinstance(args[0], str) and isinstance(args[1], dict):
        theme = args[1]
        title = args[2]
        subtitle = args[3] if len(args) >= 4 else ""
    else:
        title = args[0]
        subtitle = args[1] if len(args) >= 2 else ""

    t = _merge_theme(theme)

    pdf.set_fill_color(*t["primary"])
    pdf.rect(0, 0, pdf.w, 22, style="F")

    pdf.set_text_color(*t["header_text"])
    set_font(pdf, bold=True, size=14)
    pdf.set_xy(pdf.l_margin, 6)
    pdf.cell(0, 8, safe_text(title), border=0)

    if subtitle:
        set_font(pdf, bold=False, size=10)
        pdf.set_xy(pdf.l_margin, 14)
        pdf.cell(0, 6, safe_text(subtitle), border=0)

    pdf.set_text_color(*t["text"])
    pdf.set_y(26)
    pdf.ln(2)

    setattr(pdf, "_kv_i", 0)


def section_title(pdf: FPDF, text: str, theme: Optional[Dict[str, Any]] = None):
    t = _merge_theme(theme)

    pdf.ln(2)
    _ensure_space(pdf, 10)

    y = pdf.get_y()
    pdf.set_fill_color(*t["section_fill"])
    pdf.rect(pdf.l_margin, y, pdf.w - pdf.l_margin - pdf.r_margin, 8, style="F")

    set_font(pdf, bold=True, size=11)
    pdf.set_text_color(*t["muted"])
    pdf.set_xy(pdf.l_margin + 2, y + 1.2)
    pdf.cell(0, 6, safe_text(text), border=0)

    pdf.set_text_color(*t["text"])
    pdf.set_y(y + 10)

    setattr(pdf, "_kv_i", 0)


def section(pdf: FPDF, *args):
    """
    Совместимость:
      - section(pdf, title)
      - section(pdf, font, theme, title)
    """
    if not args:
        return
    theme = None
    title = args[-1]
    if len(args) >= 3 and isinstance(args[0], str) and isinstance(args[1], dict):
        theme = args[1]
    section_title(pdf, title, theme=theme)


# ─────────────────────────────────────────────────────────────
# KV / Bullet в виде таблицы
# ─────────────────────────────────────────────────────────────
def kv(pdf: FPDF, *args):
    """
    Совместимость:
      - kv(pdf, label, value)
      - kv(pdf, font, label, value)
      - kv(pdf, font, theme, label, value)
    """
    if len(args) < 2:
        return

    theme = None
    if len(args) == 2:
        label, value = args[0], args[1]
    elif len(args) == 3:
        label, value = args[1], args[2]
    else:
        if isinstance(args[1], dict):
            theme = args[1]
        label, value = args[-2], args[-1]

    t = _merge_theme(theme)

    w_total = pdf.w - pdf.l_margin - pdf.r_margin
    w_label = w_total * 0.42
    w_value = w_total - w_label
    line_h = 5.6

    set_font(pdf, bold=True, size=10)
    h1 = _need_height(pdf, w_label - 2, line_h, str(label), align="L")
    set_font(pdf, bold=False, size=10)
    h2 = _need_height(pdf, w_value - 2, line_h, str(value), align="L")
    row_h = max(h1, h2, line_h)

    _ensure_space(pdf, row_h + 1)

    i = int(getattr(pdf, "_kv_i", 0))
    fill = t["row_even"] if (i % 2 == 0) else t["row_odd"]
    setattr(pdf, "_kv_i", i + 1)

    x0 = pdf.l_margin
    y0 = pdf.get_y()

    pdf.set_fill_color(*fill)
    pdf.rect(x0, y0, w_total, row_h, style="F")

    pdf.set_draw_color(*t["border"])
    pdf.rect(x0, y0, w_label, row_h)
    pdf.rect(x0 + w_label, y0, w_value, row_h)

    pdf.set_text_color(*t["text"])
    set_font(pdf, bold=True, size=10)
    pdf.set_xy(x0 + 1, y0 + 0.6)
    _multi_cell(
        pdf,
        w_label - 2,
        line_h,
        safe_text(label),
        border=0,
        align="L",
        fill=False,
        new_x=(XPos.RIGHT if XPos is not None else None),
        new_y=(YPos.TOP if YPos is not None else None),
        wrapmode=_wrapmode(),
    )

    set_font(pdf, bold=False, size=10)
    pdf.set_xy(x0 + w_label + 1, y0 + 0.6)
    _multi_cell(
        pdf,
        w_value - 2,
        line_h,
        safe_text(value),
        border=0,
        align="L",
        fill=False,
        new_x=(XPos.LMARGIN if XPos is not None else None),
        new_y=(YPos.NEXT if YPos is not None else None),
        wrapmode=_wrapmode(),
    )

    pdf.set_y(y0 + row_h)


def bullet(pdf: FPDF, text: str, theme: Optional[Dict[str, Any]] = None):
    t = _merge_theme(theme)

    w_total = pdf.w - pdf.l_margin - pdf.r_margin
    line_h = 5.6
    set_font(pdf, bold=False, size=10)
    row_h = max(_need_height(pdf, w_total - 2, line_h, f"• {text}", align="L"), line_h)

    _ensure_space(pdf, row_h + 1)

    i = int(getattr(pdf, "_kv_i", 0))
    fill = t["row_even"] if (i % 2 == 0) else t["row_odd"]
    setattr(pdf, "_kv_i", i + 1)

    x0 = pdf.l_margin
    y0 = pdf.get_y()

    pdf.set_fill_color(*fill)
    pdf.rect(x0, y0, w_total, row_h, style="F")

    pdf.set_draw_color(*t["border"])
    pdf.rect(x0, y0, w_total, row_h)

    pdf.set_text_color(*t["text"])
    pdf.set_xy(x0 + 1, y0 + 0.6)
    _multi_cell(
        pdf,
        w_total - 2,
        line_h,
        safe_text(f"• {text}"),
        border=0,
        align="L",
        fill=False,
        wrapmode=_wrapmode(),
    )

    pdf.set_y(y0 + row_h)


# ─────────────────────────────────────────────────────────────
# TABLE (цветная шапка + зебра + выравнивание)
# ─────────────────────────────────────────────────────────────
def _table_impl(
    pdf: FPDF,
    headers: List[str],
    rows: List[List[Any]],
    col_widths: Optional[List[float]] = None,
    aligns: Optional[Sequence[str]] = None,
    *,
    theme: Optional[Dict[str, Any]] = None,
    header_fill: bool = True,
):
    if not headers:
        return

    t = _merge_theme(theme)

    page_w = pdf.w - pdf.l_margin - pdf.r_margin
    n = len(headers)

    if not col_widths or len(col_widths) != n:
        col_widths = [page_w / n] * n
    if not aligns or len(aligns) != n:
        aligns = ["L"] * n

    head_h = 6.5
    _ensure_space(pdf, head_h + 2)

    y0 = pdf.get_y()
    x0 = pdf.l_margin

    if header_fill:
        pdf.set_fill_color(*t["table_header_fill"])
        pdf.rect(x0, y0, sum(col_widths), head_h, style="F")

    pdf.set_draw_color(*t["border"])

    x = x0
    for w in col_widths:
        pdf.rect(x, y0, w, head_h)
        x += w

    pdf.set_text_color(*t["table_header_text"])
    set_font(pdf, bold=True, size=10)
    x = x0
    for i, htxt in enumerate(headers):
        pdf.set_xy(x + 1, y0 + 0.8)
        _multi_cell(
            pdf,
            col_widths[i] - 2,
            5.0,
            safe_text(htxt),
            border=0,
            align="C",
            fill=False,
            new_x=(XPos.RIGHT if XPos is not None else None),
            new_y=(YPos.TOP if YPos is not None else None),
            wrapmode=_wrapmode(),
        )
        x += col_widths[i]

    pdf.set_y(y0 + head_h)
    pdf.set_text_color(*t["text"])

    set_font(pdf, bold=False, size=9)

    for r_i, r in enumerate(rows or []):
        r = list(r) + [""] * (n - len(r))
        r = r[:n]

        line_h = 5.2
        heights = []
        for i in range(n):
            heights.append(_need_height(pdf, col_widths[i] - 2, line_h, str(r[i]), align=aligns[i]))
        row_h = max(max(heights) if heights else line_h, line_h)
        _ensure_space(pdf, row_h + 1)

        y = pdf.get_y()

        fill = t["row_even"] if (r_i % 2 == 0) else t["row_odd"]
        pdf.set_fill_color(*fill)
        pdf.rect(x0, y, sum(col_widths), row_h, style="F")

        pdf.set_draw_color(*t["border"])
        x = x0
        for w in col_widths:
            pdf.rect(x, y, w, row_h)
            x += w

        x = x0
        for i in range(n):
            pdf.set_xy(x + 1, y + 0.6)
            _multi_cell(
                pdf,
                col_widths[i] - 2,
                line_h,
                safe_text(r[i]),
                border=0,
                align=aligns[i],
                fill=False,
                new_x=(XPos.RIGHT if XPos is not None else None),
                new_y=(YPos.TOP if YPos is not None else None),
                wrapmode=_wrapmode(),
            )
            x += col_widths[i]

        pdf.set_y(y + row_h)


def table(pdf: FPDF, *args, **kwargs):
    """
    Совместимость:
      - table(pdf, headers, rows, col_widths=...)
      - table(pdf, font, theme, headers=..., rows=..., widths=..., aligns=...)
    """
    theme = kwargs.get("theme")

    # поддержка table(pdf, font, theme, ...)
    if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], (dict, type(None))):
        if theme is None and isinstance(args[1], dict):
            theme = args[1]
        args = args[2:]

    headers = kwargs.get("headers")
    rows = kwargs.get("rows")

    if headers is None and len(args) >= 1 and isinstance(args[0], list):
        headers = args[0]
    if rows is None and len(args) >= 2 and isinstance(args[1], list):
        rows = args[1]

    col_widths = kwargs.get("col_widths")
    if col_widths is None:
        col_widths = kwargs.get("widths")

    aligns = kwargs.get("aligns") or kwargs.get("align") or kwargs.get("alignments")
    header_fill = kwargs.get("header_fill", True)

    return _table_impl(
        pdf,
        headers=headers or [],
        rows=rows or [],
        col_widths=col_widths,
        aligns=aligns,
        theme=theme,
        header_fill=header_fill,
    )


# ─────────────────────────────────────────────────────────────
# new_pdf (совместимость со старым API)
# ─────────────────────────────────────────────────────────────
def new_pdf(orientation: str = "P", unit: str = "mm", format: str = "A4"):
    pdf = FPDF(orientation=orientation, unit=unit, format=format)
    setup_pdf(pdf)
    pdf.add_page()

    font = FONT_FAMILY if (FONT_REGULAR_PATH and FONT_BOLD_PATH) else "Helvetica"
    theme = dict(THEME_DEFAULT)
    return pdf, font, theme


__all__ = [
    "THEME_DEFAULT",
    "setup_pdf",
    "set_font",
    "safe_text",
    "pdf_safe",
    "mc",
    "header_block",
    "add_title",
    "section_title",
    "section",
    "kv",
    "bullet",
    "table",
    "_pdf_bytes",
    "pdf_bytes",
    "pdf_byte",
    "new_pdf",
]
