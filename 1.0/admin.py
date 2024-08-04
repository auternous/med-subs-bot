import logging
from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters.state import StateFilter

from config import bot, ADMIN_ID
from db import update_doctor_specialization, get_pending_doctors, get_doctor_by_id

router = Router()

class AdminActions(StatesGroup):
    waiting_for_specialization = State()

@router.message(lambda message: message.text.lower() in ["да", "нет"])
async def admin_confirmation(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    logging.info("Admin confirmation received: %s", message.text)

    if message.text.lower() == "да":
        pending_doctors = await get_pending_doctors()
        logging.info("Pending doctors: %s", pending_doctors)
        
        if not pending_doctors:
            await message.answer("Нет заявок на рассмотрение.")
            return

        doctor = pending_doctors[0]
        await state.update_data(doctor_id=doctor[0])
        await state.set_state(AdminActions.waiting_for_specialization)
        await message.answer(f"Введите специализацию для доктора {doctor[1]} {doctor[2]} (ID: {doctor[0]}):")
    else:
        await message.answer("Заявка отклонена.")

@router.message(StateFilter(AdminActions.waiting_for_specialization))
async def set_specialization(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    logging.info("State data: %s", state_data)

    doctor_id = state_data["doctor_id"]
    await update_doctor_specialization(doctor_id, message.text)
    doctor = await get_doctor_by_id(doctor_id)
    logging.info("Doctor info: %s", doctor)

    await message.answer(f"Доктор {doctor[1]} {doctor[2]} успешно добавлен с специализацией: {doctor[4]}.")
    await state.clear()
