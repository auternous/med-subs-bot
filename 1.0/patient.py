from aiogram import types
from aiogram.dispatcher.filters import Command

from config import dp, bot
from db import link_patient_to_doctor

@dp.message_handler(Command("start"))
async def start_command(message: types.Message):
    await message.answer("Привет! Для регистрации перейдите по реферальной ссылке вашего доктора.")

@dp.message_handler(Command("referral"))
async def referral_command(message: types.Message):
    doctor_id = int(message.get_args())
    link_patient_to_doctor(message.from_user.id, doctor_id)
    await message.answer("Вы успешно зарегистрированы. Теперь вы можете общаться с вашим доктором.")
