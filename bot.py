import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, REPORTS_DIR
from database import init_db
from handlers import registration, head_office, object_user
from scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    BOT_TOKEN = "6702099427:AAFzH_TnVZEqStL7EuFL9dI9iu5fVNJ3gOM"

    os.makedirs(REPORTS_DIR, exist_ok=True)

    await init_db()
    logger.info("База данных инициализирована")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(registration.router)
    dp.include_router(head_office.router)
    dp.include_router(object_user.router)

    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("Планировщик запущен")

    logger.info("Бот запущен и готов к работе")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
