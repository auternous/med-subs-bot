import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import bot, dp, storage
from db import init_db
import doctor
import admin
import patient

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    dp.include_router(doctor.router)
    dp.include_router(admin.router)
    dp.include_router(patient.router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
