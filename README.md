# ЖК Актюба — Telegram бот (V2)

Версия V2 включает улучшенную регистрацию сотрудников:
- сбор ФИО + телефона (через кнопку Contact)
- выбор **Отдел → Блок → Должность** по оргструктуре
- заявка уходит администраторам, подтверждение/отклонение **через inline-кнопки**
- администратор может **изменить отдел/блок/должность** перед подтверждением

## 1) Установка

```bash
# Ubuntu
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

## 2) Настройка

1) Скопируйте шаблон окружения:

```bash
cp .env.example .env
```

2) Заполните `.env`:
- `API_TOKEN` — токен вашего бота
- `ADMIN_IDS` — Telegram ID админов через запятую
- (опционально) `OPENAI_API_KEY`
- (опционально) `GOOGLE_CREDENTIALS_PATH`

> Если используете Google Sheets/Drive — положите service account JSON-файл в `utils/credentials.json`
> либо укажите путь через `GOOGLE_CREDENTIALS_PATH`.

## 3) Запуск

```bash
source venv/bin/activate
python bot.py
```

## 4) Структура

- `handlers/registration_v2.py` — регистрация V2 (пользователь + админ подтверждение)
- `db.py` — база данных SQLite (создание схемы при старте)
- `tasks/` — модуль задач (создание, просмотр, подтверждение выполнения)

## 5) Важные заметки

- База данных создаётся автоматически в файле `bot.db` в корне проекта.
- Не храните боевые ключи Google/токены в репозитории. Используйте `.env`.
