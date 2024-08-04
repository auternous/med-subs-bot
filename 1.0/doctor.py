from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.filters.state import StateFilter

from config import bot, dp, ADMIN_ID
from db import add_doctor

router = Router()

class DoctorRegistration(StatesGroup):
    waiting_for_name = State()
    waiting_for_surname = State()
    waiting_for_phone = State()
    confirmation = State()

@router.message(Command("reg"))
async def cmd_register(message: types.Message, state: FSMContext):
    await state.set_state(DoctorRegistration.waiting_for_name)
    await message.answer("Введите имя доктора:")

@router.message(StateFilter(DoctorRegistration.waiting_for_name))
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(DoctorRegistration.waiting_for_surname)
    await message.answer("Введите фамилию доктора:")

@router.message(StateFilter(DoctorRegistration.waiting_for_surname))
async def process_surname(message: types.Message, state: FSMContext):
    await state.update_data(surname=message.text)
    await state.set_state(DoctorRegistration.waiting_for_phone)
    await message.answer("Введите номер телефона доктора:")

@router.message(StateFilter(DoctorRegistration.waiting_for_phone))
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    user_data = await state.get_data()
    await message.answer(
        f"Анкета доктора:\nИмя: {user_data['name']}\nФамилия: {user_data['surname']}\nТелефон: {user_data['phone']}\n\nПодтвердите отправку анкеты (да/нет)?")
    await state.set_state(DoctorRegistration.confirmation)

@router.message(StateFilter(DoctorRegistration.confirmation))
async def process_confirmation(message: types.Message, state: FSMContext):
    if message.text.lower() == 'да':
        user_data = await state.get_data()
        await add_doctor(user_data['name'], user_data['surname'], user_data['phone'])
        await message.answer("Анкета отправлена на рассмотрение.")
        await state.clear()
        await bot.send_message(ADMIN_ID, f"Новая заявка на регистрацию:\nИмя: {user_data['name']}\nФамилия: {user_data['surname']}\nТелефон: {user_data['phone']}\n\nДобавить доктора (да/нет)?")
    else:
        await message.answer("Регистрация отменена. Начните сначала с команды /reg.")
        await state.clear()
