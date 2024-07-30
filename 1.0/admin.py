from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from db import add_admin

class AdminStates(StatesGroup):
    awaiting_specialization = State()

async def start_admin_registration(message: types.Message):
    await message.reply("Привет, админ! Отправь свою специализацию.")
    await AdminStates.awaiting_specialization.set()

async def add_specialization(message: types.Message, state: FSMContext):
    specialization = message.text
    add_admin(message.from_user.id)
    await state.finish()
    await message.reply(f"Специализация {specialization} добавлена.")

def register_admin_handlers(dp: Dispatcher):
    dp.register_message_handler(start_admin_registration, commands="start_admin", state="*")
    dp.register_message_handler(add_specialization, state=AdminStates.awaiting_specialization)
