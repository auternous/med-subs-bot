from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from db import add_patient, get_doctor_by_referral

class PatientStates(StatesGroup):
    awaiting_referral_code = State()

async def start_patient_registration(message: types.Message):
    await message.reply("Привет, пациент! Отправь код реферала.")
    await PatientStates.awaiting_referral_code.set()

async def add_referral_code(message: types.Message, state: FSMContext):
    referral_code = message.text
    doctor_id = get_doctor_by_referral(referral_code)
    if doctor_id:
        add_patient(message.from_user.id, doctor_id, referral_code)
        await state.finish()
        await message.reply("Вы успешно прикреплены к врачу. Теперь вы можете отправлять сообщения.")
    else:
        await message.reply("Неверный код реферала. Попробуйте снова.")

def register_patient_handlers(dp: Dispatcher):
    dp.register_message_handler(start_patient_registration, commands="start_patient", state="*")
    dp.register_message_handler(add_referral_code, state=PatientStates.awaiting_referral_code)
