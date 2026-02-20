from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from keyboards.reports_inline import (
    get_reports_menu,
    get_submit_keyboard,
    get_view_keyboard,
    get_milk_summary_submit_keyboard,
    get_milk_summary_keyboard,
    get_department_reports_keyboard,
    get_farms_keyboard,
    farm_title_by_code,
)
from keyboards import get_main_menu

router = Router()


# =========================
# SAFE EDIT HELPERS
# =========================
async def _safe_edit_text(
    callback: types.CallbackQuery,
    text: str,
    reply_markup=None,
    parse_mode: str | None = None,
):
    """
    TelegramBadRequest: message is not modified — возникает при повторном нажатии,
    когда текст и клавиатура не меняются. Это нормально — просто игнорируем.
    """
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            # чтобы Telegram не показывал "часики" — отвечаем на callback
            try:
                await callback.answer()
            except Exception:
                pass
            return
        raise


async def _safe_edit_reply_markup(callback: types.CallbackQuery, reply_markup=None):
    try:
        await callback.message.edit_reply_markup(reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            try:
                await callback.answer()
            except Exception:
                pass
            return
        raise


# =========================
# Главное меню отчетов
# =========================
@router.message(F.text == "📄 Отчеты")
async def reports_menu(message: types.Message, state: FSMContext):
    await message.answer("Выберите действие:", reply_markup=get_reports_menu())


@router.callback_query(F.data == "back_main_menu")
async def back_main(callback: types.CallbackQuery, state: FSMContext):
    # Inline-сообщение чистим, а главное меню показываем обычной Reply-клавиатурой
    try:
        await _safe_edit_reply_markup(callback, reply_markup=None)
    except Exception:
        pass

    await callback.message.answer(
        "Главное меню:",
        reply_markup=get_main_menu(callback.from_user.id),
    )
    await callback.answer()


# =========================
# Меню: Сдать / Посмотреть
# =========================
@router.callback_query(F.data == "report_submit")
async def show_submit(callback: types.CallbackQuery, state: FSMContext):
    await _safe_edit_text(
        callback,
        "Выберите раздел для сдачи отчёта:",
        reply_markup=get_submit_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "report_view")
async def show_view(callback: types.CallbackQuery, state: FSMContext):
    await _safe_edit_text(
        callback,
        "Выберите раздел для просмотра отчётов:",
        reply_markup=get_view_keyboard(),
    )
    await callback.answer()


# =========================
# Просмотр сводки по молоку
# =========================
@router.callback_query(F.data == "milk_summary")
async def milk_summary(callback: types.CallbackQuery, state: FSMContext):
    await _safe_edit_text(
        callback,
        "Выберите локацию сводки по молоку:",
        reply_markup=get_milk_summary_keyboard(include_soyuz_agro=True),
    )
    await callback.answer()


@router.callback_query(F.data == "milk_summary_back")
async def milk_back(callback: types.CallbackQuery, state: FSMContext):
    await _safe_edit_text(
        callback,
        "Выберите отчёт для просмотра:",
        reply_markup=get_view_keyboard(),
    )
    await callback.answer()


# =========================
# Сдача сводки по молоку
# =========================
@router.callback_query(F.data == "milk_summary_submit")
async def milk_summary_submit(callback: types.CallbackQuery, state: FSMContext):
    await _safe_edit_text(
        callback,
        "Выберите локацию для сдачи сводки по молоку:",
        reply_markup=get_milk_summary_submit_keyboard(include_soyuz_agro=True),
    )
    await callback.answer()


@router.callback_query(F.data == "milk_submit_back")
async def milk_submit_back(callback: types.CallbackQuery, state: FSMContext):
    await _safe_edit_text(
        callback,
        "Выберите раздел для сдачи отчёта:",
        reply_markup=get_submit_keyboard(),
    )
    await callback.answer()


# =========================
# Доп. пункт (если используете отдельно ООО Союз-Агро)
# =========================
@router.callback_query(F.data == "soyuz_agro")
async def soyuz_agro(callback: types.CallbackQuery):
    await callback.message.answer("Здесь будет отдельный отчёт по ООО «Союз-Агро».")
    await callback.answer()


# =========================
# Вложенное меню отделов: Сдать
# =========================
@router.callback_query(F.data.startswith("submit_"))
async def show_submit_department(callback: types.CallbackQuery, state: FSMContext):
    dept_code = callback.data.replace("submit_", "")
    # как в «Сводке по молоку»: сначала выбираем ферму, потом — конкретный отчёт
    await state.update_data(submit_dept=dept_code)
    await _safe_edit_text(
        callback,
        f"Выберите ферму для сдачи отчёта ({get_department_title(dept_code)}):",
        reply_markup=get_farms_keyboard("submit", dept_code),
    )
    await callback.answer()


# =========================
# Вложенное меню отделов: Посмотреть
# =========================
@router.callback_query(F.data.startswith("view_"))
async def show_view_department(callback: types.CallbackQuery, state: FSMContext):
    dept_code = callback.data.replace("view_", "")
    # как в «Сводке по молоку»: сначала выбираем ферму, потом — конкретный отчёт
    await state.update_data(view_dept=dept_code)
    await _safe_edit_text(
        callback,
        f"Выберите ферму для просмотра отчётов ({get_department_title(dept_code)}):",
        reply_markup=get_farms_keyboard("view", dept_code),
    )
    await callback.answer()


# =========================
# Выбор фермы: Сдать / Посмотреть
# =========================
@router.callback_query(F.data.startswith("farm_submit_"))
async def pick_farm_for_submit(callback: types.CallbackQuery, state: FSMContext):
    # farm_submit_{dept}_{farm}
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer()
        return
    dept_code = parts[2]
    farm_code = parts[3]
    farm_title = farm_title_by_code(farm_code)

    await state.update_data(submit_farm_code=farm_code, submit_farm_title=farm_title, submit_dept=dept_code)
    await _safe_edit_text(
        callback,
        f"{farm_title}\nВыберите отчёт для сдачи ({get_department_title(dept_code)}):",
        reply_markup=get_department_reports_keyboard(dept_code, submit=True),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("farm_view_"))
async def pick_farm_for_view(callback: types.CallbackQuery, state: FSMContext):
    # farm_view_{dept}_{farm}
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer()
        return
    dept_code = parts[2]
    farm_code = parts[3]
    farm_title = farm_title_by_code(farm_code)

    await state.update_data(view_farm_code=farm_code, view_farm_title=farm_title, view_dept=dept_code)
    await _safe_edit_text(
        callback,
        f"{farm_title}\nВыберите отчёт для просмотра ({get_department_title(dept_code)}):",
        reply_markup=get_department_reports_keyboard(dept_code, submit=False),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("submit_back_farms_"))
async def submit_back_farms(callback: types.CallbackQuery, state: FSMContext):
    dept_code = callback.data.replace("submit_back_farms_", "")
    await _safe_edit_text(
        callback,
        f"Выберите ферму для сдачи отчёта ({get_department_title(dept_code)}):",
        reply_markup=get_farms_keyboard("submit", dept_code),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("view_back_farms_"))
async def view_back_farms(callback: types.CallbackQuery, state: FSMContext):
    dept_code = callback.data.replace("view_back_farms_", "")
    await _safe_edit_text(
        callback,
        f"Выберите ферму для просмотра отчётов ({get_department_title(dept_code)}):",
        reply_markup=get_farms_keyboard("view", dept_code),
    )
    await callback.answer()


# =========================
# Заглушки выбора конкретного отчёта
# Здесь вы подключаете FSM/логику сдачи и просмотра
# =========================
@router.callback_query(F.data.startswith("report_submit_"))
async def submit_report(callback: types.CallbackQuery, state: FSMContext):
    report_code = callback.data.replace("report_submit_", "")
    await callback.message.answer(f"Логика сдачи отчёта: {report_code}")
    await callback.answer()


@router.callback_query(F.data.startswith("report_view_"))
async def view_report(callback: types.CallbackQuery, state: FSMContext):
    report_code = callback.data.replace("report_view_", "")
    await callback.message.answer(f"Логика просмотра отчёта: {report_code}")
    await callback.answer()


@router.callback_query(F.data == "submit_back_departments")
async def submit_back_departments(callback: types.CallbackQuery, state: FSMContext):
    await _safe_edit_text(
        callback,
        "Выберите отдел для сдачи отчёта:",
        reply_markup=get_submit_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "view_back_departments")
async def view_back_departments(callback: types.CallbackQuery, state: FSMContext):
    await _safe_edit_text(
        callback,
        "Выберите отдел для просмотра отчётов:",
        reply_markup=get_view_keyboard(),
    )
    await callback.answer()


# =========================
# HELPERS
# =========================
def get_department_title(code: str) -> str:
    mapping = {
        "prod": "Производство",
        "vet": "Ветеринария",
        "eng": "Инженерная служба",
        "adm": "АХО",
        "acc": "Бухгалтерия, учет",
        "saf": "ОТ и ПБ",
    }
    return mapping.get(code, code)
