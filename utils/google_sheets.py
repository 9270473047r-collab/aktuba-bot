# utils/google_sheets.py
# Полная версия: поддержка трёх вет-отчётов («0-3», «коровы», «ортопедия»)
# и обобщённая запись показателей в нужный лист Google Sheets.

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List

import gspread
from google.oauth2.service_account import Credentials

# ──────────────────────────── настройки ───────────────────────────
CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CREDENTIALS_PATH",
    os.path.join(os.path.dirname(__file__), "credentials.json"),
)
GSHEET_ID        = "1f82g_nSTQsL91T0VdK0-GUvRxXBPw6ZtFoc-28qmS0M"   # ID таблицы
MAX_ROW          = 999                                              # ищем дату в A2:A999

# метаданные трёх листов: порядок пользовательских колонок
_SHEET_META: Dict[str, List[str]] = {
    # лист 0-3 — «Молодняк 0-3»
    "0-3":  ["C", "E", "H", "K", "N", "Q", "T"],
    # лист 0-31 — «Заболевания коров»
    "0-31": ["C", "D", "F", "I", "L", "O", "R", "U", "X", "AA"],
    # лист 0-32 — «Ортопедия»
    "0-32": ["E", "H", "K", "N", "Q", "T", "W", "Z", "AC"],
}

# ────────────────────────── авторизация ───────────────────────────
_scopes  = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
_creds:   Credentials | None      = None
_client:  gspread.Client | None   = None
_ws_cache: Dict[str, gspread.Worksheet] = {}


def _get_ws(sheet_name: str) -> gspread.Worksheet:
    """Возвращает (кешированный) Worksheet по имени листа."""
    global _creds, _client, _ws_cache
    if sheet_name in _ws_cache:
        return _ws_cache[sheet_name]

    if _creds is None:
        _creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=_scopes)
    if _client is None:
        _client = gspread.authorize(_creds)

    ws = _client.open_by_key(GSHEET_ID).worksheet(sheet_name)
    _ws_cache[sheet_name] = ws
    return ws


# ───────────────────────── обобщённая запись ──────────────────────
def _write_row(sheet_name: str, date_obj: datetime, values: List[int]) -> None:
    """Находит date_obj в столбце A и пишет values в предопределённые колонки."""
    cols = _SHEET_META.get(sheet_name)
    if cols is None:
        raise ValueError(f"Неизвестный лист: {sheet_name}")

    if len(values) != len(cols):
        raise ValueError(f"Для листа {sheet_name} требуется {len(cols)} значений, "
                         f"получено {len(values)}.")

    ws = _get_ws(sheet_name)

    # A2:A... без заголовка
    a_col = ws.col_values(1)[1:MAX_ROW]
    try:
        row_idx = a_col.index(date_obj.strftime("%d.%m.%Y")) + 2
    except ValueError:
        raise ValueError("⛔️ Дата не найдена в столбце A.")

    requests = [
        {"range": f"{c}{row_idx}", "values": [[v]]}
        for c, v in zip(cols, values)
    ]
    ws.batch_update(requests, value_input_option="USER_ENTERED")


# ───────────────────── публичные обёртки для бота ─────────────────
def write_0_3_row(date_obj: datetime, values: List[int]) -> None:
    """Отчёт «Молодняк 0-3» (лист 0-3) — 7 показателей."""
    _write_row("0-3", date_obj, values)


def write_cows_row(date_obj: datetime, values: List[int]) -> None:
    """Отчёт «Заболевания коров» (лист 0-31) — 10 показателей."""
    _write_row("0-31", date_obj, values)


def write_ortho_row(date_obj: datetime, values: List[int]) -> None:
    """Отчёт «Ортопедия» (лист 0-32) — 9 показателей."""
    _write_row("0-32", date_obj, values)


# ────────────── обратная совместимость со старым кодом ────────────
def _ws():  # noqa: N802
    """Возвращает Worksheet листа 0-3 (оставлено для старого кода)."""
    return _get_ws("0-3")
