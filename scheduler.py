import os
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import TZ, REPORTS_DIR
from database import get_objects, get_daily_summary
from utils import today_str
from services.reports import generate_daily_report


async def daily_rollover():
    today = today_str()
    os.makedirs(REPORTS_DIR, exist_ok=True)

    objects = await get_objects()
    for obj in objects:
        summary = await get_daily_summary(obj["id"], today)
        try:
            filepath = await generate_daily_report(obj["id"], obj["name"], today)
            print(f"[{datetime.now(TZ)}] Дневной отчет сохранен: {filepath}")
        except Exception as e:
            print(f"[{datetime.now(TZ)}] Ошибка генерации отчета для {obj['name']}: {e}")

    print(f"[{datetime.now(TZ)}] Ежедневный расчет остатков завершен")


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(
        daily_rollover,
        trigger="cron",
        hour=0,
        minute=0,
        id="daily_rollover",
        replace_existing=True,
    )
    return scheduler
