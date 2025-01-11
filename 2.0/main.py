# main.py

import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import dp, bot
from db import init_db, remove_expired_doctor_relations
import admin
import doctor
import patient
import chat

logging.basicConfig(level=logging.INFO)

async def main():
    # Инициализация БД
    await init_db()

    # Планировщик для удаления просроченных связей
    scheduler = AsyncIOScheduler()
    scheduler.add_job(remove_expired_doctor_relations, 'interval', hours=1)
    scheduler.start()

    # Подключаем все роутеры
    dp.include_router(admin.router)
    dp.include_router(doctor.router)
    dp.include_router(patient.router)
    dp.include_router(chat.router)

    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен.")
