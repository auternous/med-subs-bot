import logging
from aiogram import Bot, Dispatcher, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
import sqlite3
import os
import config

# Настройка логирования
logging.basicConfig(level=logging.INFO)
print(config.token)
# Установка токена бота
API_TOKEN = config.token  # Убедитесь, что переменная содержит токен вашего бота
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('clinic.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        phone_number TEXT NOT NULL,
        subscription BOOLEAN DEFAULT TRUE,
        purchase_date DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS doctors (
        doctor_id INTEGER PRIMARY KEY AUTOINCREMENT,
        specialization TEXT NOT NULL,
        full_name TEXT NOT NULL,
        phone_number TEXT NOT NULL
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS dialogs (
        dialog_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(user_id),
        doctor_id INTEGER REFERENCES doctors(doctor_id),
        start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        end_time DATETIME,
        status TEXT DEFAULT 'active'
    )
    ''')
    
    conn.commit()
    conn.close()

# Состояния для управления процессом регистрации
class RegistrationStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone_number = State()

# Обработчик команды /start
@router.message(Command(commands='start'))
async def send_welcome(message: types.Message):
    await message.answer("Добро пожаловать! Чтобы зарегистрироваться, введите /register.")

# Обработчик команды /register для запуска процесса регистрации
@router.message(Command(commands='register'))
async def register_user(message: types.Message, state: FSMContext):
    await message.answer("Введите ваше ФИО:")
    await state.set_state(RegistrationStates.waiting_for_full_name)

# Обработчик ввода ФИО
@router.message(RegistrationStates.waiting_for_full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("Введите ваш номер телефона:")
    await state.set_state(RegistrationStates.waiting_for_phone_number)

# Обработчик ввода номера телефона
@router.message(RegistrationStates.waiting_for_phone_number)
async def process_phone_number(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    full_name = user_data['full_name']
    phone_number = message.text
    telegram_id = message.from_user.id
    
    # Добавляем пользователя в базу данных
    conn = sqlite3.connect('clinic.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR IGNORE INTO users (telegram_id, full_name, phone_number, subscription, purchase_date)
    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (telegram_id, full_name, phone_number, True))
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer("Регистрация завершена!")

# Команда /choose_doctor для выбора врача
@router.message(Command(commands='choose_doctor'))
async def choose_doctor(message: types.Message):
    conn = sqlite3.connect('clinic.db')
    cursor = conn.cursor()
    cursor.execute('SELECT doctor_id, specialization, full_name FROM doctors')
    doctors = cursor.fetchall()
    
    if not doctors:
        await message.answer("Нет доступных врачей. Пожалуйста, добавьте врачей в базу данных.")
        return
    
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    for doctor in doctors:
        keyboard.add(KeyboardButton(f"ID: {doctor[0]}, {doctor[1]}, {doctor[2]}"))
    
    await message.answer("Выберите врача:", reply_markup=keyboard)
    conn.close()

# Инициализация базы данных перед запуском бота
init_db()

# Основная функция запуска
if __name__ == "__main__":
    dp.run_polling(bot, skip_updates=True)
