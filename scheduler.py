from apscheduler.schedulers.asyncio import AsyncIOScheduler
from handlers.milk_summary import send_daily_group_milk_summary
from jobs.daily_report_deadline import send_daily_deadline_and_pdfs

def setup_scheduler(bot):
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    scheduler.add_job(
        send_daily_group_milk_summary,
        trigger="cron",
        hour=15,
        minute=0,
        args=[bot],
        id="milk_summary_to_group_1500",
        replace_existing=True,
    )

    # 16:00 — контроль несданных сводок + пакет PDF за сутки всем пользователям
    scheduler.add_job(
        send_daily_deadline_and_pdfs,
        trigger="cron",
        hour=16,
        minute=0,
        args=[bot],
        id="daily_deadline_1600",
        replace_existing=True,
    )

    scheduler.start()
    return scheduler
