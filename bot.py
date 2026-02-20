import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties

from config import BOT_TOKEN
from db import db, init_db
from handlers import routers as handler_routers
from tasks import routers as task_routers
from scheduler import setup_scheduler


# ───────────────────  Логирование  ────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ───────────────────  Системные хуки  ──────────────────
async def on_startup() -> None:
    """Действия при запуске бота"""
    logger.info("Starting database initialization…")
    if asyncio.iscoroutinefunction(init_db):
        await init_db()
    else:
        init_db()
    logger.info("Database initialized")


async def on_shutdown(bot: Bot, dispatcher: Dispatcher) -> None:
    """Действия при остановке бота"""
    logger.info("Shutting down…")

    # Останавливаем планировщик, если запущен
    try:
        scheduler = dispatcher.workflow_data.get("scheduler")
        if scheduler:
            scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")
    except Exception as e:
        logger.warning("Scheduler stop warning: %s", e)

    # Закрываем БД (если есть close)
    try:
        if hasattr(db, "close") and callable(db.close):
            if asyncio.iscoroutinefunction(db.close):
                await db.close()
            else:
                db.close()
            logger.info("Database connection closed")
    except Exception as e:
        logger.warning("DB close warning: %s", e)

    # Закрываем сессию бота
    try:
        if bot.session and not bot.session.closed:
            await bot.session.close()
            logger.info("Bot session closed")
    except Exception as e:
        logger.warning("Bot session close warning: %s", e)


# ───────────────────  Точка входа  ─────────────────────
async def main() -> None:
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Регистрируем хуки старта / остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # ── Роутеры из handlers ────────────────────────────
    for r in handler_routers:
        dp.include_router(r)

    # ── Роутеры из пакета tasks ─────────────────────────
    for r in task_routers:
        dp.include_router(r)

    # ── Планировщик ─────────────────────────────────────
    scheduler = setup_scheduler(bot)
    dp.workflow_data["scheduler"] = scheduler

    # ── Запуск поллинга ─────────────────────────────────
    try:
        await dp.start_polling(bot)
    except Exception as exc:
        logger.exception("Polling failed: %s", exc)
    finally:
        # страховка, если поллинг упал до вызова shutdown
        try:
            if bot.session and not bot.session.closed:
                await bot.session.close()
        except Exception:
            pass


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
