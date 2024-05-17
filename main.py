
import logging
import asyncio
from aiogram import Bot, Dispatcher, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import config
import db
import aiosqlite

logging.basicConfig(level=logging.INFO)

API_TOKEN = config.token
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

router = Router()

class RegistrationStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone_number = State()
    waiting_for_specialization = State()  # Для врачей

class DialogueStates(StatesGroup):
    waiting_for_user_message = State()
    waiting_for_doctor_response = State()

@router.message(Command('start'))
async def send_welcome(message: types.Message):
    buttons = [
        [InlineKeyboardButton(text="Регистрация пациента", callback_data="register_patient")],
        [InlineKeyboardButton(text="Регистрация врача", callback_data="register_doctor")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Добро пожаловать! Пожалуйста, выберите действие:", reply_markup=markup)

@router.callback_query(lambda c: c.data == 'register_patient')
async def register_patient(query: types.CallbackQuery, state: FSMContext):
    await state.set_state(RegistrationStates.waiting_for_full_name)
    await query.message.answer("Введите ваше ФИО:")

@router.callback_query(lambda c: c.data == 'register_doctor')
async def register_doctor(query: types.CallbackQuery, state: FSMContext):
    await state.set_state(RegistrationStates.waiting_for_full_name)
    await state.update_data(is_doctor=True)
    await query.message.answer("Введите ФИО врача:")

@router.message(RegistrationStates.waiting_for_full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("Введите ваш номер телефона:")
    await state.set_state(RegistrationStates.waiting_for_phone_number)

@router.message(RegistrationStates.waiting_for_phone_number)
async def process_phone_number(message: types.Message, state: FSMContext):
    await state.update_data(phone_number=message.text)
    data = await state.get_data()
    if data.get("is_doctor"):
        await message.answer("Введите вашу специализацию:")
        await state.set_state(RegistrationStates.waiting_for_specialization)
    else:
        await complete_registration(message, state)

@router.message(RegistrationStates.waiting_for_specialization)
async def process_specialization(message: types.Message, state: FSMContext):
    await state.update_data(specialization=message.text)
    await complete_registration(message, state)

async def complete_registration(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    full_name = user_data['full_name']
    phone_number = user_data['phone_number']
    telegram_id = message.from_user.id
    is_doctor = user_data.get('is_doctor', False)
    
    async with aiosqlite.connect('clinic.db') as conn:
        if is_doctor:
            specialization = user_data['specialization']
            cursor = await conn.execute('SELECT * FROM doctors WHERE telegram_id = ?', (telegram_id,))
            existing_doctor = await cursor.fetchone()
            if existing_doctor:
                await message.answer("Этот врач уже зарегистрирован!")
            else:
                await conn.execute('''
                INSERT INTO doctors (telegram_id, full_name, phone_number, specialization)
                VALUES (?, ?, ?, ?)
                ''', (telegram_id, full_name, phone_number, specialization))
                await conn.commit()
                await message.answer("Регистрация врача завершена!")
        else:
            cursor = await conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
            existing_user = await cursor.fetchone()
            if existing_user:
                await message.answer("Вы уже зарегистрированы!")
            else:
                await conn.execute('''
                INSERT INTO users (telegram_id, full_name, phone_number, subscription)
                VALUES (?, ?, ?, TRUE)
                ''', (telegram_id, full_name, phone_number))
                await conn.commit()
                await message.answer("Регистрация пациента завершена!")
    await state.clear()
    await show_profile(message, telegram_id, is_doctor)

async def show_profile(message: types.Message, telegram_id: int, is_doctor: bool):
    async with aiosqlite.connect('clinic.db') as conn:
        if is_doctor:
            cursor = await conn.execute('SELECT full_name, phone_number, specialization FROM doctors WHERE telegram_id = ?', (telegram_id,))
            doctor = await cursor.fetchone()
            if doctor:
                profile_text = f"Ваш профиль:\nФИО: {doctor[0]}\nТелефон: {doctor[1]}\nСпециализация: {doctor[2]}"
        else:
            cursor = await conn.execute('SELECT full_name, phone_number FROM users WHERE telegram_id = ?', (telegram_id,))
            user = await cursor.fetchone()
            if user:
                profile_text = f"Ваш профиль:\nФИО: {user[0]}\nТелефон: {user[1]}"
    
    buttons = []
    if not is_doctor:
        buttons.append([InlineKeyboardButton(text="Показать врачей", callback_data="show_doctors")])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(profile_text, reply_markup=markup)

@router.callback_query(lambda c: c.data == 'show_doctors')
async def send_doctors_list(query: types.CallbackQuery):
    async with aiosqlite.connect('clinic.db') as conn:
        doctors = await conn.execute_fetchall('SELECT specialization, doctor_id FROM doctors')
        if not doctors:
            await query.message.answer("На данный момент нет зарегистрированных врачей.")
            return
        buttons = [InlineKeyboardButton(text=doc[0], callback_data=f"doctor_{doc[1]}") for doc in doctors]
        markup = InlineKeyboardMarkup(inline_keyboard=[buttons])
        await query.message.answer("Выберите врача по специализации из списка:", reply_markup=markup)

@router.callback_query(lambda c: c.data.startswith('doctor_'))
async def handle_doctor_selection(query: types.CallbackQuery, state: FSMContext):
    doctor_id = query.data.split('_')[1]
    await state.update_data(doctor_id=doctor_id, user_id=query.from_user.id)
    
    async with aiosqlite.connect('clinic.db') as conn:
        cursor = await conn.execute('SELECT full_name, specialization, phone_number FROM doctors WHERE doctor_id = ?', (doctor_id,))
        doctor = await cursor.fetchone()
        
    if doctor:
        response_text = f"Информация о враче:\nИмя: {doctor[0]}\nСпециализация: {doctor[1]}\nТелефон: {doctor[2]}"
        buttons = [
            InlineKeyboardButton(text="Написать", callback_data=f"write_{doctor_id}"),
            InlineKeyboardButton(text="Отмена", callback_data="cancel")
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=[buttons])
        await query.message.answer(response_text, reply_markup=markup)
    else:
        await query.message.answer("Извините, не удалось найти информацию о данном враче.")
    
    await query.answer()

@router.callback_query(lambda c: c.data.startswith('write_'))
async def start_dialogue(query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    doctor_id = user_data['doctor_id']
    user_id = user_data['user_id']
    
    await state.set_state(DialogueStates.waiting_for_user_message)
    await query.message.answer("Введите ваше сообщение для врача:")

@router.message(DialogueStates.waiting_for_user_message)
async def forward_message_to_doctor(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    doctor_id = user_data['doctor_id']
    user_id = message.from_user.id
    async with aiosqlite.connect('clinic.db') as conn:
        cursor = await conn.execute('SELECT telegram_id FROM doctors WHERE doctor_id = ?', (doctor_id,))
        doctor = await cursor.fetchone()
    if doctor:
        doctor_telegram_id = doctor[0]
        msg_text = f"Сообщение от пользователя {user_id} (ID доктора: {doctor_id}):\n{message.text}"
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ответить", callback_data=f"reply_{user_id}")],
            [InlineKeyboardButton(text="Завершить диалог", callback_data="end_dialogue")]
        ])
        await bot.send_message(doctor_telegram_id, msg_text, reply_markup=markup)
        await message.answer("Ваше сообщение было отправлено врачу.")
    else:
        await message.answer("Произошла ошибка. Врач не найден.")

@router.callback_query(lambda c: c.data.startswith('reply_'))
async def reply_to_user(query: types.CallbackQuery, state: FSMContext):
    user_id = query.data.split('_')[1]
    await state.update_data(reply_user_id=user_id)
    await state.set_state(DialogueStates.waiting_for_doctor_response)
    await query.message.answer("Введите ваше сообщение для пользователя:")

@router.message(DialogueStates.waiting_for_doctor_response)
async def forward_message_to_user(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    reply_user_id = user_data['reply_user_id']
    doctor_id = message.from_user.id
    async with aiosqlite.connect('clinic.db') as conn:
        cursor = await conn.execute('SELECT telegram_id FROM users WHERE telegram_id = ?', (reply_user_id,))
        user = await cursor.fetchone()
    if user:
        user_telegram_id = user[0]
        msg_text = f"Сообщение от врача {doctor_id}:\n{message.text}"
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ответить", callback_data=f"reply_{doctor_id}")],
            [InlineKeyboardButton(text="Завершить диалог", callback_data="end_dialogue")]
        ])
        await bot.send_message(user_telegram_id, msg_text, reply_markup=markup)
        await message.answer("Ваше сообщение было отправлено пользователю.")
    else:
        await message.answer("Произошла ошибка. Пользователь не найден.")

@router.callback_query(lambda c: c.data == "end_dialogue")
async def end_dialogue(query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await query.message.answer("Диалог завершен.")
    await query.answer()

async def main():
    await db.init_db()
    dp.include_router(router)
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
