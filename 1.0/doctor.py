from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from db import add_doctor, generate_referral_link

class DoctorStates(StatesGroup):
    awaiting_specialization = State()

async def start_doctor_registration(message: types.Message):
    await message.reply("Привет, доктор! Отправь свою специализацию.")
    await DoctorStates.awaiting_specialization.set()

async def add_specialization(message: types.Message, state: FSMContext):
    specialization = message.text
    add_doctor(message.from_user.id, specialization)
    await state.finish()
    await message.reply(f"Специализация {specialization} добавлена. Генерирую ссылку...")
    referral_link = generate_referral_link(message.from_user.id)
    await message.reply(f"Вот ваша реферальная ссылка: {referral_link}")

def register_doctor_handlers(dp: Dispatcher):
    dp.register_message_handler(start_doctor_registration, commands="start_doctor", state="*")
    dp.register_message_handler(add_specialization, state=DoctorStates.awaiting_specialization)
