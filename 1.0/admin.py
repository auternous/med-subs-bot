import logging
from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import StateFilter
from aiogram.fsm.state import StatesGroup, State
from config import bot, ADMIN_ID
from db import update_doctor_specialization, get_doctor_by_user_id

router = Router()

class AdminActions(StatesGroup):
    waiting_for_specialization = State()

def create_doctor_keyboard():
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Создать ссылку")]
        ],
        resize_keyboard=True
    )
    return keyboard


@router.callback_query(lambda c: c.data and c.data.startswith('approve_'))
async def approve_doctor(callback_query: types.CallbackQuery, state: FSMContext):
    logging.info(f"Received callback_data: {callback_query.data}")
    
    try:
        doctor_id = int(callback_query.data.split("_")[1])
        logging.info(f"Processing approval for doctor ID: {doctor_id}")
        
        await state.update_data(doctor_id=doctor_id)
        doctor = await get_doctor_by_user_id(doctor_id)
        
        # Используем числовые индексы для доступа к полям кортежа
        await callback_query.message.answer(f"Введите специализацию для доктора {doctor[1]}:")
        await state.set_state(AdminActions.waiting_for_specialization)
    except (ValueError, IndexError) as e:
        logging.error(f"Error processing callback_data: {e}")
        await callback_query.message.answer("Произошла ошибка при обработке данных. Попробуйте еще раз.")
    
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('approve_'))
async def approve_doctor(callback_query: types.CallbackQuery, state: FSMContext):
    logging.info(f"Received callback_data: {callback_query.data}")
    
    try:
        doctor_id = int(callback_query.data.split("_")[1])
        logging.info(f"Processing approval for doctor ID: {doctor_id}")
        
        await state.update_data(doctor_id=doctor_id)
        doctor = await get_doctor_by_user_id(doctor_id)
        
        # Используем числовые индексы для доступа к элементам кортежа
        await update_doctor_specialization(doctor_id, message.text)
        await callback_query.message.answer(f"Доктор {doctor[1]} успешно добавлен с специализацией: {message.text}.")
        
        # Отправка уведомления доктору
        await bot.send_message(doctor[5], f"Ваша заявка одобрена! Ваша специализация: {message.text}.")
        
        await state.clear()
    except (ValueError, IndexError) as e:
        logging.error(f"Error processing callback_data: {e}")
        await callback_query.message.answer("Произошла ошибка при обработке данных. Попробуйте еще раз.")
    
    await callback_query.answer()

@router.callback_query(lambda c: c.data and c.data.startswith('reject_'))
async def reject_doctor(callback_query: types.CallbackQuery):
    logging.info(f"Received callback_data: {callback_query.data}")
    
    try:
        doctor_id = int(callback_query.data.split("_")[1])
        doctor = await get_doctor_by_user_id(doctor_id)
        await callback_query.message.answer(f"Заявка доктора {doctor[1]} отклонена.")
        
        # Отправка уведомления доктору
        await bot.send_message(doctor[5], "К сожалению, ваша заявка была отклонена.")
    except (ValueError, IndexError) as e:
        logging.error(f"Error processing callback_data: {e}")
        await callback_query.message.answer("Произошла ошибка при обработке данных. Попробуйте еще раз.")
    
    await callback_query.answer()


@router.message(StateFilter(AdminActions.waiting_for_specialization))
async def set_specialization(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    doctor_id = state_data.get("doctor_id")
    
    if doctor_id is None:
        await message.answer("Ошибка: не удалось получить ID доктора.")
        return

    logging.info(f"Updating specialization for doctor ID: {doctor_id} to {message.text}")
    
    await update_doctor_specialization(doctor_id, message.text)
    
    logging.info(f"Specialization updated for doctor ID: {doctor_id}")
    
    doctor = await get_doctor_by_user_id(doctor_id)
    logging.info(f"Doctor data after update: {doctor}")
    
    # Отправляем сообщение доктору с клавиатурой для создания ссылки
    await bot.send_message(doctor[5], f"Ваш запрос был одобрен! Ваша специализация: {doctor[3]}.",
                           reply_markup=create_doctor_keyboard())
    
    await message.answer(f"Доктор {doctor[1]} успешно добавлен с специализацией: {doctor[3]}.")
    await state.clear()
