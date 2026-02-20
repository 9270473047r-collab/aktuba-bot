import os
import json
import re
import asyncio
from datetime import datetime, date

from aiogram import Router, types, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from db import db  # ваш глобальный db (db.conn)

router = Router()

LOCATION_CODE = "aktuba"
LOCATION_TITLE = "ЖК «Актюба»"

DB_TABLE = "mtp_daily_reports"


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def fmt_int(x: float | int) -> str:
    return f"{int(round(x)):,}".replace(",", " ")


def parse_number(text: str) -> int:
    t = (text or "").strip().replace(" ", "").replace(",", ".")
    t = re.sub(r"[^0-9.]", "", t)
    if t == "":
        raise ValueError("Пустое значение")
    x = float(t)
    if x < 0:
        raise ValueError("Число не может быть отрицательным")
    return int(round(x))


def parse_rub(text: str) -> int:
    # допускаем "38 500", "38500", "38 500 ₽"
    return parse_number(text)


def parse_date_ddmmyyyy(text: str) -> str:
    t = (text or "").strip()
    if t.lower() in ("0", "сегодня", "today"):
        return datetime.now().strftime("%d.%m.%Y")
    dt = datetime.strptime(t, "%d.%m.%Y")
    return dt.strftime("%d.%m.%Y")


def iso_from_ddmmyyyy(date_str: str) -> str:
    return datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")


def parse_shift(text: str) -> str:
    t = (text or "").strip().lower()
    if t in ("день", "дневная", "day"):
        return "день"
    if t in ("ночь", "ночная", "night"):
        return "ночь"
    raise ValueError("Введите: день или ночь")


def parse_yes_no(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in ("да", "д", "yes", "y", "1", "+"):
        return True
    if t in ("нет", "н", "no", "n", "0", "-"):
        return False
    raise ValueError("Введите: да или нет")


def diesel_calc_end(morning: int, income: int, spent: int) -> int:
    return max(0, int(morning + income - spent))


def maybe_warn_diff(calc_end: int, fact_end: int) -> str:
    diff = fact_end - calc_end
    if abs(diff) >= 50:
        sign = "+" if diff > 0 else ""
        return f" (расхождение: {sign}{fmt_int(diff)} л)"
    return ""


# ─────────────────────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────────────────────
async def ensure_table():
    await db.conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT NOT NULL,
            report_date DATE NOT NULL,
            data_json TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(location, report_date)
        );
    """)
    await db.conn.commit()


async def upsert_report(location: str, report_date: str, data: dict, created_by: int):
    await ensure_table()
    await db.conn.execute(f"""
        INSERT INTO {DB_TABLE} (location, report_date, data_json, created_by)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(location, report_date) DO UPDATE SET
            data_json  = excluded.data_json,
            created_by = excluded.created_by,
            created_at = CURRENT_TIMESTAMP
    """, (location, report_date, json.dumps(data, ensure_ascii=False), created_by))
    await db.conn.commit()


async def get_latest_report(location: str):
    await ensure_table()
    cur = await db.conn.execute(f"""
        SELECT location, report_date, data_json, created_by, created_at
        FROM {DB_TABLE}
        WHERE location = ?
        ORDER BY report_date DESC, created_at DESC
        LIMIT 1
    """, (location,))
    row = await cur.fetchone()
    await cur.close()
    return dict(row) if row else None


# ─────────────────────────────────────────────────────────────
# FSM
# ─────────────────────────────────────────────────────────────
class MtpWizard(StatesGroup):
    active = State()


# ─────────────────────────────────────────────────────────────
# Steps (вопросы)
# ─────────────────────────────────────────────────────────────
# Пояснение по “ветвлениям”:
# часть вопросов задаём только если нужно (например, причины невыхода, список простоев и т.д.)
BASE_STEPS = [
    ("report_date", "Введите дату отчёта <b>ДД.ММ.ГГГГ</b> (или <b>0</b> = сегодня):", parse_date_ddmmyyyy, "пример: 31.12.2025"),
    ("shift", "Смена: <b>день</b> или <b>ночь</b>:", parse_shift, "введите: день/ночь"),

    # A. Персонал
    ("drivers_fact", "Работает трактористов (чел):", parse_number, "пример: 18"),
    ("drivers_staff", "По штату трактористов (чел):", parse_number, "пример: 22"),
    ("drivers_absent", "Не вышли на работу (чел):", parse_number, "если 0 — причин не спросим"),
    # drivers_absent_reason (условно)
    ("mech_count", "Механики в смене (чел):", parse_number, "пример: 2"),
    ("responsible_fio", "Диспетчер/ответственный (ФИО):", lambda x: x.strip(), "пример: Иванов А.А."),

    # B. Техника в работе
    ("tech_tractors", "Тракторов в работе (ед):", parse_number, "пример: 14"),
    ("tech_loaders", "Погрузчиков/телескопов в работе (ед):", parse_number, "пример: 3"),
    ("tech_mixers", "Кормораздатчиков/смесителей в работе (ед):", parse_number, "пример: 2"),
    ("tech_manure", "Техника по навозу/скрепера в работе (ед):", parse_number, "пример: 4"),
    ("tech_transport", "Автотранспорт (ГАЗ/КАМАЗ/прочее) в работе (ед):", parse_number, "пример: 2"),
    ("tech_downtime", "Простой техники (ед):", parse_number, "если >0 — спросим список"),

    # C. Заявки и ремонты
    ("tickets_in", "Заявок поступило (шт):", parse_number, "пример: 12"),
    ("tickets_closed", "Заявок закрыто (шт):", parse_number, "пример: 9"),
    ("tickets_pending", "Заявок в работе/перенос (шт):", parse_number, "пример: 3"),
    ("critical_breakdowns", "Поломки критические? (да/нет):", parse_yes_no, "пример: да"),

    # D. Запчасти и сервис
    ("parts_spent_rub", "Запчасти израсходовано за сутки (₽):", parse_rub, "пример: 38 500"),
    ("parts_ordered_rub", "Запчасти заказано/в пути (₽):", parse_rub, "пример: 120 000"),
    ("parts_deficit", "Критические позиции в дефиците? (да/нет):", parse_yes_no, "пример: да"),
    ("external_service", "Внешний сервис привлекали? (да/нет):", parse_yes_no, "пример: нет"),

    # E. ГСМ
    ("diesel_morning", "Остаток ДТ на утро (л):", parse_number, "пример: 2400"),
    ("diesel_income", "Приход ДТ (л):", parse_number, "пример: 0"),
    ("diesel_spent", "Расход ДТ (л):", parse_number, "пример: 680"),
    ("diesel_fact_end", "Остаток ДТ на конец суток (л):", parse_number, "сравним с расчетным"),
    ("oil_spent_l", "Масло/смазки: расход (л):", parse_number, "пример: 6"),
    ("fuel_issue", "Есть перерасход/слив/подозрение? (да/нет):", parse_yes_no, "пример: нет"),

    # F. Работы
    ("feed_done", "Кормораздача выполнена? (да/нет):", parse_yes_no, "пример: да"),
    # feed_runs (условно)
    ("manure_done", "Навозоудаление выполнено? (да/нет):", parse_yes_no, "пример: да"),
    # manure_runs (условно)
    ("loading_ops", "Погрузочно-разгрузочные работы (рейсы/часы/текст):", lambda x: x.strip(), "пример: 3 часа / 5 рейсов"),
    ("other_work", "Прочие работы (текст, можно 0):", lambda x: x.strip(), "пример: доставка воды — 2 рейса"),

    # G. Комментарий дня
    ("problems", "Основные проблемы дня (текст, можно 0):", lambda x: x.strip(), "кратко по сути"),
    ("plan", "План на завтра (текст, можно 0):", lambda x: x.strip(), "кратко по сути"),
]


# ─────────────────────────────────────────────────────────────
# Wizard engine with branching
# ─────────────────────────────────────────────────────────────
def next_key_sequence(answers: dict) -> list[tuple]:
    """
    Возвращает фактический список шагов с учётом ветвлений.
    """
    steps = []
    for item in BASE_STEPS:
        key = item[0]

        # ВЕТВЛЕНИЯ
        if key == "mech_count":
            # перед mechanics может быть вопрос по причинам невыхода
            pass

        steps.append(item)

        # после drivers_absent если > 0 — добавим причины
        if key == "drivers_absent":
            if int(answers.get("drivers_absent", 0) or 0) > 0:
                steps.append(("drivers_absent_reason",
                              "Причины невыхода (если несколько — через точку с запятой):",
                              lambda x: x.strip(),
                              "пример: болезнь — 1; без причины — 1"))

        # после tech_downtime если > 0 — добавим список простоев
        if key == "tech_downtime":
            if int(answers.get("tech_downtime", 0) or 0) > 0:
                steps.append(("tech_downtime_list",
                              "Перечень простоев: техника — причина — статус/срок (текст):",
                              lambda x: x.strip(),
                              "пример: МТЗ-82 — КПП — в ремонте до 02.01"))

        # после critical_breakdowns если да — список критических
        if key == "critical_breakdowns":
            if bool(answers.get("critical_breakdowns", False)) is True:
                steps.append(("critical_list",
                              "Критические поломки: техника — неисправность — статус — срок (текст):",
                              lambda x: x.strip(),
                              "пример: КАМАЗ-5511 — стартер — в работе до 12:00"))

        # после parts_deficit если да — что именно
        if key == "parts_deficit":
            if bool(answers.get("parts_deficit", False)) is True:
                steps.append(("parts_deficit_list",
                              "Что в дефиците и на какую технику (текст):",
                              lambda x: x.strip(),
                              "пример: подшипники КПП МТЗ-82"))

        # после external_service если да — детали
        if key == "external_service":
            if bool(answers.get("external_service", False)) is True:
                steps.append(("external_service_details",
                              "Внешний сервис: подрядчик — техника — сумма — статус (текст):",
                              lambda x: x.strip(),
                              "пример: ООО «Сервис» — КАМАЗ — 50 000 — в работе"))

        # после fuel_issue если да — комментарий
        if key == "fuel_issue":
            if bool(answers.get("fuel_issue", False)) is True:
                steps.append(("fuel_issue_comment",
                              "Комментарий по ГСМ (что именно):",
                              lambda x: x.strip(),
                              "кратко и конкретно"))

        # после feed_done если да — рейсы
        if key == "feed_done":
            if bool(answers.get("feed_done", False)) is True:
                steps.append(("feed_runs",
                              "Кормораздач, рейсов (шт):",
                              parse_number,
                              "пример: 6"))

        # после manure_done если да — рейсы/объём
        if key == "manure_done":
            if bool(answers.get("manure_done", False)) is True:
                steps.append(("manure_runs",
                              "Навоз/жижи: рейсов (шт):",
                              parse_number,
                              "пример: 18"))

    return steps


async def ask_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    answers = data.get("answers", {})
    seq = next_key_sequence(answers)
    idx = int(data.get("step_idx", 0))

    key, q, _, hint = seq[idx]
    await message.answer(
        f"🚜 <b>Сводка МТП за сутки — {LOCATION_TITLE}</b>\n"
        f"Шаг <b>{idx + 1}</b> из <b>{len(seq)}</b>\n\n"
        f"{q}\n<i>{hint}</i>\n\n"
        f"Для отмены: <b>отмена</b>",
        parse_mode="HTML"
    )


def build_report_text(d: dict) -> str:
    date_str = d.get("report_date", datetime.now().strftime("%d.%m.%Y"))
    shift = d.get("shift", "-")

    # A. Персонал
    df = int(d.get("drivers_fact", 0) or 0)
    ds = int(d.get("drivers_staff", 0) or 0)
    da = int(d.get("drivers_absent", 0) or 0)
    da_reason = d.get("drivers_absent_reason", "").strip()
    mech = int(d.get("mech_count", 0) or 0)
    resp = d.get("responsible_fio", "-").strip()

    absent_line = f"• Не вышли: <b>{fmt_int(da)}</b>"
    if da > 0 and da_reason:
        absent_line += f" ({da_reason})"

    # B. Техника
    t_tr = int(d.get("tech_tractors", 0) or 0)
    t_ld = int(d.get("tech_loaders", 0) or 0)
    t_mx = int(d.get("tech_mixers", 0) or 0)
    t_mn = int(d.get("tech_manure", 0) or 0)
    t_tp = int(d.get("tech_transport", 0) or 0)
    t_dt = int(d.get("tech_downtime", 0) or 0)
    t_dt_list = d.get("tech_downtime_list", "").strip()

    downtime_line = f"• Простой: <b>{fmt_int(t_dt)}</b> ед"
    if t_dt > 0 and t_dt_list:
        downtime_line += f" ({t_dt_list})"

    # C. Заявки
    ti = int(d.get("tickets_in", 0) or 0)
    tc = int(d.get("tickets_closed", 0) or 0)
    tp = int(d.get("tickets_pending", 0) or 0)
    crit = bool(d.get("critical_breakdowns", False))
    crit_list = d.get("critical_list", "").strip()

    crit_line = "• Критические поломки: <b>да</b>" if crit else "• Критические поломки: <b>нет</b>"
    if crit and crit_list:
        crit_line += f"\n— {crit_list}"

    # D. Запчасти/сервис
    p_spent = int(d.get("parts_spent_rub", 0) or 0)
    p_order = int(d.get("parts_ordered_rub", 0) or 0)
    p_def = bool(d.get("parts_deficit", False))
    p_def_list = d.get("parts_deficit_list", "").strip()
    ext = bool(d.get("external_service", False))
    ext_det = d.get("external_service_details", "").strip()

    def_line = "• Дефицит: <b>да</b>" if p_def else "• Дефицит: <b>нет</b>"
    if p_def and p_def_list:
        def_line += f" ({p_def_list})"

    ext_line = "• Внешний сервис: <b>да</b>" if ext else "• Внешний сервис: <b>нет</b>"
    if ext and ext_det:
        ext_line += f"\n— {ext_det}"

    # E. ГСМ
    dm = int(d.get("diesel_morning", 0) or 0)
    di = int(d.get("diesel_income", 0) or 0)
    dspt = int(d.get("diesel_spent", 0) or 0)
    de = int(d.get("diesel_fact_end", 0) or 0)
    de_calc = diesel_calc_end(dm, di, dspt)
    de_warn = maybe_warn_diff(de_calc, de)

    oil = int(d.get("oil_spent_l", 0) or 0)
    f_issue = bool(d.get("fuel_issue", False))
    f_issue_comment = d.get("fuel_issue_comment", "").strip()

    fuel_line = (
        f"• ДТ утро: <b>{fmt_int(dm)}</b> л | приход: <b>{fmt_int(di)}</b> л | "
        f"расход: <b>{fmt_int(dspt)}</b> л | остаток: <b>{fmt_int(de)}</b> л{de_warn}\n"
        f"• Расчётный остаток: <b>{fmt_int(de_calc)}</b> л\n"
        f"• Масло/смазки: <b>{fmt_int(oil)}</b> л\n"
    )
    if f_issue:
        fuel_line += f"• Замечания по ГСМ: <b>да</b> ({f_issue_comment})\n"
    else:
        fuel_line += f"• Замечания по ГСМ: <b>нет</b>\n"

    # F. Работы
    feed_done = bool(d.get("feed_done", False))
    feed_runs = d.get("feed_runs", None)
    manure_done = bool(d.get("manure_done", False))
    manure_runs = d.get("manure_runs", None)
    loading_ops = (d.get("loading_ops", "") or "0").strip()
    other_work = (d.get("other_work", "") or "0").strip()

    feed_line = "• Кормораздача: <b>выполнена</b>" if feed_done else "• Кормораздача: <b>не выполнена</b>"
    if feed_done and feed_runs is not None:
        feed_line += f", рейсы: <b>{fmt_int(int(feed_runs))}</b>"

    manure_line = "• Навозоудаление: <b>выполнено</b>" if manure_done else "• Навозоудаление: <b>не выполнено</b>"
    if manure_done and manure_runs is not None:
        manure_line += f", рейсы: <b>{fmt_int(int(manure_runs))}</b>"

    # G. Комментарии
    problems = (d.get("problems", "") or "0").strip()
    plan = (d.get("plan", "") or "0").strip()

    text = (
        f"🚜 <b>Сводка МТП за {date_str}</b> ({LOCATION_TITLE})\n\n"
        f"<b>Персонал</b>\n"
        f"• Смена: <b>{shift}</b>\n"
        f"• Трактористы: <b>{fmt_int(df)}/{fmt_int(ds)}</b> (факт/штат)\n"
        f"{absent_line}\n"
        f"• Механики: <b>{fmt_int(mech)}</b>, ответственный: <b>{resp}</b>\n\n"
        f"<b>Техника</b>\n"
        f"• Тракторы в работе: <b>{fmt_int(t_tr)}</b> ед\n"
        f"• Погрузчики: <b>{fmt_int(t_ld)}</b> ед\n"
        f"• Кормораздатчики/смесители: <b>{fmt_int(t_mx)}</b> ед\n"
        f"• Навоз: <b>{fmt_int(t_mn)}</b> ед\n"
        f"• Автотранспорт: <b>{fmt_int(t_tp)}</b> ед\n"
        f"{downtime_line}\n\n"
        f"<b>Заявки/ремонт</b>\n"
        f"• Поступило: <b>{fmt_int(ti)}</b>, закрыто: <b>{fmt_int(tc)}</b>, в работе: <b>{fmt_int(tp)}</b>\n"
        f"{crit_line}\n\n"
        f"<b>Запчасти/сервис</b>\n"
        f"• Расход запчастей: <b>{fmt_int(p_spent)}</b> ₽\n"
        f"• Заказано/в пути: <b>{fmt_int(p_order)}</b> ₽\n"
        f"{def_line}\n"
        f"{ext_line}\n\n"
        f"<b>ГСМ</b>\n"
        f"{fuel_line}\n"
        f"<b>Работы</b>\n"
        f"{feed_line}\n"
        f"{manure_line}\n"
        f"• Погрузочно-разгрузочные: <b>{loading_ops}</b>\n"
        f"• Прочее: <b>{other_work}</b>\n\n"
        f"<b>Комментарий</b>\n"
        f"• Проблемы: <b>{problems}</b>\n"
        f"• План: <b>{plan}</b>\n"
    )
    return text


# ─────────────────────────────────────────────────────────────
# SUBMIT / VIEW (callback из меню "Инженерная служба")
# eng_report1_submit / eng_report1_view
# ─────────────────────────────────────────────────────────────
@router.callback_query(F.data == "eng_report1_submit")
async def start_submit(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(MtpWizard.active)
    await state.update_data(step_idx=0, answers={})

    await callback.message.answer(
        "✅ Начинаем сдачу отчёта <b>«Сводка МТП»</b>.\n"
        "Бот будет задавать вопросы по одному.",
        parse_mode="HTML"
    )
    await ask_step(callback.message, state)
    await callback.answer()


@router.message(MtpWizard.active)
async def wizard_input(message: types.Message, state: FSMContext):
    txt = (message.text or "").strip()

    if txt.lower() in ("отмена", "cancel", "/cancel", "стоп"):
        await state.clear()
        await message.answer("⛔ Сдача отчёта отменена.")
        return

    data = await state.get_data()
    answers = data.get("answers", {})
    seq = next_key_sequence(answers)
    idx = int(data.get("step_idx", 0))

    key, _, parser, _ = seq[idx]

    try:
        value = parser(txt)
    except Exception as e:
        await message.answer(f"❗️Ошибка ввода: {e}\nПовторите ещё раз.")
        await ask_step(message, state)
        return

    answers[key] = value
    idx += 1

    # пересобираем seq (вдруг появились ветвления после ответа)
    seq2 = next_key_sequence(answers)

    if idx >= len(seq2):
        # сохранение
        if "report_date" not in answers:
            answers["report_date"] = datetime.now().strftime("%d.%m.%Y")

        report_date_iso = iso_from_ddmmyyyy(str(answers["report_date"]))

        await upsert_report(
            location=LOCATION_CODE,
            report_date=report_date_iso,
            data=answers,
            created_by=message.from_user.id
        )

        text = build_report_text(answers)
        await state.clear()
        await message.answer("✅ <b>Отчёт МТП сохранён.</b>\n\n" + text, parse_mode="HTML")
        return

    await state.update_data(step_idx=idx, answers=answers)
    await ask_step(message, state)


@router.callback_query(F.data == "eng_report1_view")
async def view_latest(callback: types.CallbackQuery):
    row = await get_latest_report(LOCATION_CODE)
    if not row:
        await callback.message.answer("❗️Отчётов «Сводка МТП» ещё нет.")
        await callback.answer()
        return

    d = json.loads(row["data_json"])
    text = build_report_text(d)

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

