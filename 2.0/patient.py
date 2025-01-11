# patient.py

from aiogram import Router, types
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from db import (
    get_invite_code, mark_invite_code_as_used,
    get_doctor_by_id,
    get_patient_by_telegram_id, add_patient, add_patient_doctor_relation,
    get_patient_id_by_telegram_id, get_doctors_for_patient,
    start_dialogue
)
from config import bot

router = Router()

# Главное меню (включим сюда "Профиль" и т. п.)
def generate_main_menu():
    buttons = [
        [InlineKeyboardButton(text="Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="Мои чаты", callback_data="my_chats")]  # <-- для чатов
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(CommandStart(deep_link=True))
async def patient_start(message: types.Message, state: FSMContext):
    """
    Обработчик /start c deep_link'ом вида: /start invite_{uuid}.
    Пациент переходит по ссылке, чтобы привязаться к врачу.
    """
    args = message.text.split()
    if len(args) < 2 or not args[1].startswith("invite_"):
        await message.answer("Неверная или просроченная ссылка.")
        return
    
    code = args[1].split("_", 1)[1]
    invite_code = await get_invite_code(code)
    if not invite_code or invite_code['used']:
        await message.answer("Ссылка недействительна или уже использована.")
        return

    doctor_id = invite_code['doctor_id']
    doctor = await get_doctor_by_id(doctor_id)
    if not doctor:
        await message.answer("Доктор не найден.")
        return

    # Помечаем код как использованный
    await mark_invite_code_as_used(code)

    # Если пациент уже есть, просто привязываем к врачу
    existing_patient = await get_patient_by_telegram_id(message.from_user.id)
    if existing_patient:
        patient_id = existing_patient['id']
        reg_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await add_patient_doctor_relation(patient_id, doctor_id, reg_date)
        
        # Создаём/активируем диалог, чтобы у пациента сразу появился чат
        await start_dialogue(patient_id, doctor_id)

        await message.answer("Теперь вы прикреплены к новому врачу.", reply_markup=generate_main_menu())
        return
    else:
        # Пациент ещё не зарегистрирован — отправляем на регистрацию
        await state.update_data(doctor_id=doctor_id)
        await message.answer("Введите ваше ФИО для регистрации:")
        await state.set_state("patient_waiting_name")

@router.message(StateFilter("patient_waiting_name"))
async def process_patient_name(message: types.Message, state: FSMContext):
    """
    Пользователь ввёл своё ФИО. Просим подтвердить.
    """
    await state.update_data(name=message.text)
    await message.answer(
        f"Вы указали ФИО: {message.text}\nПодтвердить (да/нет)?"
    )
    await state.set_state("patient_confirm")

@router.message(StateFilter("patient_confirm"))
async def process_patient_confirm(message: types.Message, state: FSMContext):
    """
    Подтверждение регистрационных данных пациента.
    """
    if message.text.lower() == "да":
        data = await state.get_data()
        name = data['name']
        doctor_id = data['doctor_id']
        telegram_id = message.from_user.id
        reg_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Создаём запись о пациенте
        await add_patient(name, telegram_id, reg_date)

        # 2. Привязываем пациента к врачу
        patient_id = await get_patient_id_by_telegram_id(telegram_id)
        await add_patient_doctor_relation(patient_id, doctor_id, reg_date)

        # 3. Создаём/активируем диалог, чтобы у пациента сразу появился чат
        await start_dialogue(patient_id, doctor_id)

        # 4. Сообщаем об успешной регистрации
        await message.answer("Регистрация завершена.", reply_markup=generate_main_menu())
        await state.clear()
    else:
        # Если пользователь ответил "нет", даём возможность ввести ФИО заново
        await message.answer("Введите ваше ФИО ещё раз:")
        await state.set_state("patient_waiting_name")

# Профиль пациента
@router.callback_query(lambda c: c.data == "profile")
async def show_profile(callback_query: types.CallbackQuery):
    """
    Показывает профиль пациента: имя и список прикреплённых врачей с датой истечения.
    """
    patient = await get_patient_by_telegram_id(callback_query.from_user.id)
    if not patient:
        await callback_query.message.edit_text("Ошибка: вы не зарегистрированы как пациент.")
        return

    text = f"Имя: {patient['name']}\n"
    patient_id = patient['id']
    doctors = await get_doctors_for_patient(patient_id)
    if doctors:
        text += "\nПрикреплённые врачи:\n"
        for doc in doctors:
            spec = doc['specialization'] or "не указана"
            text += f"• {doc['fio']} ({spec}) до {doc['expiry_date']}\n"
    else:
        text += "\nУ вас нет прикреплённых врачей."

    await callback_query.message.edit_text(text, reply_markup=generate_main_menu())
    await callback_query.answer()
