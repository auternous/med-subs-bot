from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from db import approve_doctor, add_specialization_to_doctor

class AdminStates(StatesGroup):
    awaiting_doctor_id = State()
    awaiting_specialization = State()

async def start_admin_registration(message: types.Message):
    await message.reply("Привет, админ! Чтобы одобрить врача, введи его ID.")
    await AdminStates.awaiting_doctor_id.set()

async def get_doctor_id(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['doctor_id'] = int(message.text)
    await message.reply("Теперь отправь специализацию врача.")
    await AdminStates.awaiting_specialization.set()

async def add_specialization(message: types.Message, state: FSMContext):
    specialization = message.text
    async with state.proxy() as data:
        doctor_id = data['doctor_id']
        approve_doctor(doctor_id)
        add_specialization_to_doctor(doctor_id, specialization)
    await state.finish()
    await message.reply(f"Врач с ID {doctor_id} одобрен со специализацией {specialization}.")

def register_admin_handlers(dp: Dispatcher):
    dp.register_message_handler(start_admin_registration, commands="start_admin", state="*")
    dp.register_message_handler(get_doctor_id, state=AdminStates.awaiting_doctor_id)
    dp.register_message_handler(add_specialization, state=AdminStates.awaiting_specialization)
