import logging
from aiogram import Bot, Dispatcher, executor, types
from config import TOKEN
from db import init_db
from admin import register_admin_handlers
from doctor import register_doctor_handlers
from patient import register_patient_handlers

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Регистрация хэндлеров
register_admin_handlers(dp)
register_doctor_handlers(dp)
register_patient_handlers(dp)

if __name__ == '__main__':
    init_db()
    executor.start_polling(dp, skip_updates=True)
