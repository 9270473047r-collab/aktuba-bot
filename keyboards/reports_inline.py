from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- Основные отделы и их коды ---
ORG_DEPARTMENTS = [
    ("Производство", "prod"),
    ("Ветеринария", "vet"),
    ("Инженерная служба", "eng"),
    ("АХО", "adm"),
    ("Бухгалтерия", "acc"),
    ("ОТ и ПБ", "saf"),
]

# --- Фермы (как в «Сводке по молоку») ---
FARMS = [
    ("ЖК «Актюба»", "aktuba"),
    ("Карамалы", "karamaly"),
    ("Шереметьево", "sheremetyovo"),
    ("Бирючевка", "biryuchevka"),
]


def farm_title_by_code(code: str) -> str:
    for title, c in FARMS:
        if c == code:
            return title
    return code

# --- Спец.отчёты (в начале меню просмотра) ---
# Важно: отдельную кнопку «ООО «Союз-Агро»» из просмотра убрали.
# ООО остаётся только внутри выбора локации «Сводки по молоку».
SPECIAL_REPORTS = [
    ("🍼 Сводка по молоку", "milk_summary"),
]


# --- Главное меню ---
def get_reports_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Сдать отчет", callback_data="report_submit")],
            [InlineKeyboardButton(text="📊 Посмотреть отчеты", callback_data="report_view")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main_menu")],
        ]
    )


# --- Клавиатура для выбора отдела (Сдать отчет) ---
def get_submit_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="🍼 Сводка по молоку", callback_data="milk_summary_submit")],
    ]
    kb += [
        [InlineKeyboardButton(text=name, callback_data=f"submit_{code}")]
        for name, code in ORG_DEPARTMENTS
    ]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# --- Клавиатура для выбора локации сдачи "Сводки по молоку" ---
def get_milk_summary_submit_keyboard(
    include_soyuz_agro: bool = False,
    allowed_location_codes: list[str] | None = None,
) -> InlineKeyboardMarkup:
    options = [
        ("ЖК «Актюба»", "milk_submit_aktuba"),
        ("Карамалы", "milk_submit_karamaly"),
        ("Шереметьево", "milk_submit_sheremetyovo"),
        ("Бирючевка", "milk_submit_biryuchevka"),
    ]

    if allowed_location_codes is not None:
        allowed_cb = {f"milk_submit_{code}" for code in allowed_location_codes}
        options = [(name, cb) for name, cb in options if cb in allowed_cb]

    kb = [[InlineKeyboardButton(text=name, callback_data=cb)] for name, cb in options]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="milk_submit_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# --- Клавиатура для выбора отдела (Посмотреть отчеты) + спец.отчёты ---
def get_view_keyboard() -> InlineKeyboardMarkup:
    # Сначала спец. отчёты
    kb = [[InlineKeyboardButton(text=name, callback_data=cb)] for name, cb in SPECIAL_REPORTS]

    # Затем отделы
    kb += [
        [InlineKeyboardButton(text=name, callback_data=f"view_{code}")]
        for name, code in ORG_DEPARTMENTS
    ]

    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# --- Клавиатура выбора фермы для отчётов служб ---
def get_farms_keyboard(
    action: str,
    dept_code: str,
    allowed_farm_codes: list[str] | None = None,
) -> InlineKeyboardMarkup:
    """action: 'submit' или 'view'"""
    farms = FARMS
    if allowed_farm_codes is not None:
        allowed = set(allowed_farm_codes)
        farms = [(title, code) for title, code in FARMS if code in allowed]

    kb = [[InlineKeyboardButton(text=title, callback_data=f"farm_{action}_{dept_code}_{code}")]
          for title, code in farms]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{action}_back_departments")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# --- Клавиатура выбора конкретного отчёта внутри отдела ---
def get_department_reports_keyboard(dept_code: str, submit: bool = True) -> InlineKeyboardMarkup:
    """
    Вложенное меню для выбора отчёта по отделу.

    Особые названия:
    - Производство (Отчет 1) -> 🔄 Движение поголовья
    - Ветеринария -> 3 отчёта с уникальными названиями
    """
    action = "submit" if submit else "view"

    if dept_code == "vet":
        reports = [
            ("🩺 Заболеваемость 0–3 мес", f"{dept_code}_report1_{action}"),
            ("🐄 Заболеваемость коров", f"{dept_code}_report2_{action}"),
            ("🦶 Ортопедия", f"{dept_code}_report3_{action}"),
        ]
    elif dept_code == "prod":
        reports = [
            ("🔄 Движение поголовья", f"{dept_code}_report1_{action}"),
            ("Отчет 2", f"{dept_code}_report2_{action}"),
            ("Отчет 3", f"{dept_code}_report3_{action}"),
        ]
    elif dept_code == "eng":
        reports = [
            ("🚜 Сводка МТП", f"{dept_code}_report1_{action}"),
            ("Отчет 2", f"{dept_code}_report2_{action}"),
            ("Отчет 3", f"{dept_code}_report3_{action}"),
        ]
    else:
        reports = [
            ("🔄 Движение поголовья", f"{dept_code}_report1_{action}"),
            ("Отчет 2", f"{dept_code}_report2_{action}"),
            ("Отчет 3", f"{dept_code}_report3_{action}"),
        ]

    kb = [[InlineKeyboardButton(text=title, callback_data=cb)] for title, cb in reports]

    # Назад: возвращаемся к выбору фермы в рамках текущей службы
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{action}_back_farms_{dept_code}")])

    return InlineKeyboardMarkup(inline_keyboard=kb)


# --- Клавиатура для сводки по молоку (просмотр по локациям) ---
def get_milk_summary_keyboard(
    include_soyuz_agro: bool = False,
    allowed_location_codes: list[str] | None = None,
) -> InlineKeyboardMarkup:
    options = [
        ("ЖК «Актюба»", "milk_aktuba"),
        ("Карамалы", "milk_karamaly"),
        ("Шереметьево", "milk_sheremetyovo"),
        ("Бирючевка", "milk_biryuchevka"),
    ]
    if include_soyuz_agro:
        options.append(("🏢 ООО «Союз-Агро»", "milk_soyuz_agro"))

    if allowed_location_codes is not None:
        allowed_cb = {f"milk_{code}" for code in allowed_location_codes}
        if include_soyuz_agro:
            allowed_cb.add("milk_soyuz_agro")
        options = [(name, cb) for name, cb in options if cb in allowed_cb]

    kb = [[InlineKeyboardButton(text=name, callback_data=cb)] for name, cb in options]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="milk_summary_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)
