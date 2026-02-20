from __future__ import annotations

"""PDF: суточная «Сводка МТП».

Файл добавлен для унификации:
  - отправка PDF сразу после сдачи отчёта МТП
  - включение отчёта МТП в ежедневный PDF-пакет (jobs/daily_report_deadline.py)
"""

from datetime import datetime
from typing import Any, Dict, List

from utils.pdf_common import add_title, new_pdf, section, kv, table, pdf_bytes, safe_text


def _iv(d: Dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(d.get(key) if d.get(key) is not None else default)
    except Exception:
        return default


def _sv(d: Dict[str, Any], key: str, default: str = "—") -> str:
    v = d.get(key)
    s = safe_text(v)
    return s if s else default


def _fmt_int(x: int) -> str:
    return f"{int(x):,}".replace(",", " ")


def build_mtp_daily_pdf_bytes(location_title: str, report_date_ddmmyyyy: str, data: Dict[str, Any]) -> bytes:
    """Вернёт PDF-байты суточной сводки МТП."""
    pdf, font, theme = new_pdf(orientation="P")

    subtitle = f"Дата: {report_date_ddmmyyyy} | Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    add_title(pdf, font, theme, f"Сводка МТП — {location_title}", subtitle)

    section(pdf, font, theme, "Персонал")
    kv(pdf, font, theme, "Смена", _sv(data, "shift"))
    kv(pdf, font, theme, "Трактористов: факт / штат", f"{_fmt_int(_iv(data,'drivers_fact'))} / {_fmt_int(_iv(data,'drivers_staff'))}")
    kv(pdf, font, theme, "Не вышли", _fmt_int(_iv(data, "drivers_absent")))
    if _sv(data, "drivers_absent_reason", "").strip() and _iv(data, "drivers_absent") > 0:
        kv(pdf, font, theme, "Причины невыхода", _sv(data, "drivers_absent_reason"))
    kv(pdf, font, theme, "Механики в смене", _fmt_int(_iv(data, "mech_count")))
    kv(pdf, font, theme, "Ответственный/диспетчер", _sv(data, "responsible_fio"))

    section(pdf, font, theme, "Техника в работе")
    headers = ["Позиция", "Кол-во"]
    widths = [140, 40]
    aligns = ["L", "C"]
    rows: List[List[str]] = [
        ["Тракторы", _fmt_int(_iv(data, "tech_tractors"))],
        ["Погрузчики/телескопы", _fmt_int(_iv(data, "tech_loaders"))],
        ["Кормораздатчики/смесители", _fmt_int(_iv(data, "tech_mixers"))],
        ["Техника по навозу/скрепера", _fmt_int(_iv(data, "tech_manure"))],
        ["Автотранспорт", _fmt_int(_iv(data, "tech_transport"))],
        ["Простой техники", _fmt_int(_iv(data, "tech_downtime"))],
    ]
    table(pdf, font, theme, headers=headers, rows=rows, widths=widths, aligns=aligns)
    if _sv(data, "tech_downtime_list", "").strip() and _iv(data, "tech_downtime") > 0:
        kv(pdf, font, theme, "Перечень простоев", _sv(data, "tech_downtime_list"))

    section(pdf, font, theme, "Заявки и ремонты")
    kv(pdf, font, theme, "Заявок поступило", _fmt_int(_iv(data, "tickets_in")))
    kv(pdf, font, theme, "Закрыто", _fmt_int(_iv(data, "tickets_closed")))
    kv(pdf, font, theme, "В работе/перенос", _fmt_int(_iv(data, "tickets_pending")))
    kv(pdf, font, theme, "Критические поломки", "да" if bool(data.get("critical_breakdowns")) else "нет")
    if bool(data.get("critical_breakdowns")) and _sv(data, "critical_list", "").strip():
        kv(pdf, font, theme, "Список критических", _sv(data, "critical_list"))

    section(pdf, font, theme, "Запчасти и сервис")
    kv(pdf, font, theme, "Запчасти израсходовано (₽)", _fmt_int(_iv(data, "parts_spent_rub")))
    kv(pdf, font, theme, "Запчасти заказано/в пути (₽)", _fmt_int(_iv(data, "parts_ordered_rub")))
    kv(pdf, font, theme, "Дефицит критических позиций", "да" if bool(data.get("parts_deficit")) else "нет")
    if bool(data.get("parts_deficit")) and _sv(data, "parts_deficit_list", "").strip():
        kv(pdf, font, theme, "Что в дефиците", _sv(data, "parts_deficit_list"))
    kv(pdf, font, theme, "Внешний сервис", "да" if bool(data.get("external_service")) else "нет")
    if bool(data.get("external_service")) and _sv(data, "external_service_details", "").strip():
        kv(pdf, font, theme, "Внешний сервис (детали)", _sv(data, "external_service_details"))

    section(pdf, font, theme, "ГСМ")
    diesel_morning = _iv(data, "diesel_morning")
    diesel_income = _iv(data, "diesel_income")
    diesel_spent = _iv(data, "diesel_spent")
    diesel_fact_end = _iv(data, "diesel_fact_end")
    diesel_calc_end = max(0, diesel_morning + diesel_income - diesel_spent)
    diff = diesel_fact_end - diesel_calc_end
    diff_s = f" ({'+' if diff > 0 else ''}{_fmt_int(diff)} л)" if abs(diff) >= 50 else ""
    kv(pdf, font, theme, "ДТ: остаток на утро (л)", _fmt_int(diesel_morning))
    kv(pdf, font, theme, "ДТ: приход (л)", _fmt_int(diesel_income))
    kv(pdf, font, theme, "ДТ: расход (л)", _fmt_int(diesel_spent))
    kv(pdf, font, theme, "ДТ: расчетный остаток (л)", _fmt_int(diesel_calc_end))
    kv(pdf, font, theme, "ДТ: фактический остаток (л)", _fmt_int(diesel_fact_end) + diff_s)
    kv(pdf, font, theme, "Масло/смазки: расход (л)", _fmt_int(_iv(data, "oil_spent_l")))
    kv(pdf, font, theme, "Есть перерасход/слив/подозрение", "да" if bool(data.get("fuel_issue")) else "нет")
    if bool(data.get("fuel_issue")) and _sv(data, "fuel_issue_comment", "").strip():
        kv(pdf, font, theme, "Комментарий по ГСМ", _sv(data, "fuel_issue_comment"))

    section(pdf, font, theme, "Работы")
    kv(pdf, font, theme, "Кормораздача выполнена", "да" if bool(data.get("feed_done")) else "нет")
    if bool(data.get("feed_done")) and _sv(data, "feed_runs", "").strip():
        kv(pdf, font, theme, "Кормораздача (рейсы)", _sv(data, "feed_runs"))
    kv(pdf, font, theme, "Навозоудаление выполнено", "да" if bool(data.get("manure_done")) else "нет")
    if bool(data.get("manure_done")) and _sv(data, "manure_runs", "").strip():
        kv(pdf, font, theme, "Навозоудаление (рейсы)", _sv(data, "manure_runs"))
    kv(pdf, font, theme, "Погрузочно-разгрузочные", _sv(data, "loading_ops"))
    kv(pdf, font, theme, "Прочие работы", _sv(data, "other_work"))

    section(pdf, font, theme, "Комментарий")
    kv(pdf, font, theme, "Проблемы", _sv(data, "problems"))
    kv(pdf, font, theme, "План на завтра", _sv(data, "plan"))

    return pdf_bytes(pdf)


__all__ = ["build_mtp_daily_pdf_bytes"]
