"""
Клавиатуры, доступные только администраторам.
"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# ────────────────────── Основное админ-меню ────────────────────
def get_admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Список задач по отделам/блокам")],
            [
                KeyboardButton(text="♻️ Регулярные задачи"),
                KeyboardButton(text="👥 Пользователи"),
            ],
            [
                KeyboardButton(text="🔄 Сменить руководителя"),
                KeyboardButton(text="🔎 Просмотреть отчёты"),
            ],
            [KeyboardButton(text="➕ Добавить регламент/протокол/инструкцию")],
            [
                KeyboardButton(text="✉️ СМС по меню"),
                KeyboardButton(text="✉️ СМС не по меню"),
            ],
            [
                KeyboardButton(text="⚖️ Назначить штраф"),
                KeyboardButton(text="🔍 Все штрафы"),
            ],
            [
                KeyboardButton(text="✅ Подтвердить штраф"),
                KeyboardButton(text="❌ Отменить штраф"),
            ],
            [
                KeyboardButton(text="📜 Сделать распоряжение"),
                KeyboardButton(text="📖 Сделать протокол"),
            ],
            [
                KeyboardButton(text="⚙️ Настройки"),
                KeyboardButton(text="⬅️ Выйти в главное меню"),
            ],
        ],
        resize_keyboard=True,
    )


# ─────────────────── Подменю «Управление пользователями» ───────
def get_user_management_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Список пользователей")],
            [
                KeyboardButton(text="👤 Добавить пользователя"),
                KeyboardButton(text="🗑 Удалить пользователя"),
            ],
            [KeyboardButton(text="🔄 Изменить роль")],
            [KeyboardButton(text="⬅️ Назад в админ меню")],
        ],
        resize_keyboard=True,
    )


# ─────────────────── Подменю «Регламенты / документы» ──────────
def get_reglament_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="👥 Оргструктура"),
                KeyboardButton(text="📑 Регламенты"),
            ],
            [
                KeyboardButton(text="📖 Инструкция"),
                KeyboardButton(text="📋 Протоколы"),
            ],
            [
                KeyboardButton(text="✔️ Чек-листы"),
                KeyboardButton(text="📚 Справочник"),
            ],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


# ─────────────────── Подменю «Справочники» ──────────
def get_reference_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚜 Справочник МТП")],
            [KeyboardButton(text="⬅️ Назад в документацию")],
        ],
        resize_keyboard=True,
    )


def get_mtp_reference_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="✍️ Заполнить справочник"),
                KeyboardButton(text="👀 Посмотреть справочник"),
            ],
            [KeyboardButton(text="⬅️ Назад в справочник")],
        ],
        resize_keyboard=True,
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


__all__ = [
    "get_admin_menu",
    "get_admin_keyboard",           # ← добавили
    "get_user_management_keyboard",
    "get_reglament_menu",
    "get_reference_menu",
    "get_mtp_reference_menu",
    "get_cancel_keyboard",
]


get_admin_keyboard = get_admin_menu
