import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # Импортируем планировщик
from db import remove_expired_doctor_relations
from config import bot, dp, storage
from db import init_db
import doctor
import admin
import patient

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(remove_expired_doctor_relations, 'interval', hours=1)  # Проверка раз в час
    scheduler.start()
    dp.include_router(doctor.router)
    dp.include_router(admin.router)
    dp.include_router(patient.router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен.")
