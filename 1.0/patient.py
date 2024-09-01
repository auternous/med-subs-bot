from aiogram import Router, types
from aiogram.filters import CommandStart, Text
from aiogram.fsm.context import FSMContext
from config import bot
from db import get_doctor_by_id

router = Router()

@router.message(CommandStart(deep_link=True))
async def patient_start(message: types.Message, state: FSMContext):
    args = message.text.split()[1] if len(message.text.split()) > 1 else None

    if not args or not args.startswith("doctor_"):
        await message.answer("Неверная ссылка. Пожалуйста, получите правильную ссылку от вашего доктора.")
        return
    
    doctor_id = args.split("_")[1] 
    
    # Получаем информацию о докторе
    doctor = await get_doctor_by_id(int(doctor_id))
    
    if not doctor:
        await message.answer("Доктор не найден. Пожалуйста, проверьте ссылку.")
        return
    
    # Отправляем информацию о докторе пациенту
    doctor_info = f"Вам добавлен доктор:\nФИО: {doctor[1]}\nСпециализация: {doctor[3]}"
    await message.answer(doctor_info)

    # Сохранение состояния пациента, если требуется
    await state.update_data(doctor_id=doctor_id)
    await state.clear()


