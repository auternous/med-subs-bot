from aiogram import Router, types, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db import (get_doctor_by_user_id, add_patient, add_subscriber_to_doctor, 
                get_patient_by_id, get_doctors_for_patient, start_dialogue, 
                get_active_dialogue, complete_dialogue)
from datetime import datetime
from config import bot


router = Router()

# Состояния для регистрации пациента и диалога
class PatientRegistration(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    confirmation = State()

class DialogueState(StatesGroup):
    waiting_for_message = State()  # Ожидание сообщения пациента
    waiting_for_reply = State() 

# Главное меню пациента
def generate_main_menu():
    buttons = [
        [InlineKeyboardButton(text="Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="Расписание", callback_data="schedule")],
        [InlineKeyboardButton(text="Написать доктору", callback_data="contact_doctor")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Регистрация пациента
@router.message(CommandStart(deep_link=True))
async def patient_start(message: types.Message, state: FSMContext):
    args = message.text.split()[1] if len(message.text.split()) > 1 else None
    if not args or not args.startswith("doctor_"):
        await message.answer("Неверная ссылка.")
        return

    doctor_id = args.split("_")[1] 
    doctor = await get_doctor_by_user_id(int(doctor_id))
    if not doctor:
        await message.answer("Доктор не найден.")
        return
    
    # Сохраняем Telegram ID доктора
    doctor_telegram_id = doctor[5]  # Telegram ID доктора
    await state.update_data(doctor_telegram_id=doctor_telegram_id)
    await state.set_state(PatientRegistration.waiting_for_name)
    await message.answer("Введите ваше ФИО:")

@router.message(StateFilter(PatientRegistration.waiting_for_name))
async def process_patient_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(PatientRegistration.waiting_for_phone)
    await message.answer("Введите ваш номер телефона:")

@router.message(StateFilter(PatientRegistration.waiting_for_phone))
async def process_patient_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("Подтвердите ваши данные (да/нет).")
    await state.set_state(PatientRegistration.confirmation)

@router.message(StateFilter(PatientRegistration.confirmation))
async def process_patient_confirmation(message: types.Message, state: FSMContext):
    if message.text.lower() == 'да':
        user_data = await state.get_data()
        doctor_telegram_id = user_data['doctor_telegram_id']
        await add_patient(
            name=user_data['name'],
            phone=user_data['phone'],
            telegram_id=message.from_user.id,
            doctor_id=doctor_telegram_id,
            registration_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        await add_subscriber_to_doctor(doctor_telegram_id, message.from_user.id)
        await message.answer("Регистрация завершена.", reply_markup=generate_main_menu())
        await state.clear()
    else:
        await state.set_state(PatientRegistration.waiting_for_name)
        await message.answer("Введите ваше ФИО:")

# Показать профиль пациента
@router.callback_query(lambda c: c.data == "profile")
async def show_profile(callback_query: types.CallbackQuery):
    patient = await get_patient_by_id(callback_query.from_user.id)
    if not patient:
        await callback_query.message.edit_text("Ошибка: не удалось получить данные профиля.")
        return

    registration_date_str = patient['registration_date']
    registration_date = datetime.strptime(registration_date_str, "%Y-%m-%d %H:%M:%S")
    days_left = 5 - (datetime.now() - registration_date).days

    profile_info = (
        f"Имя: {patient['name']}\n"
        f"Ваш доктор: {patient['specialization']}\n"  # Используем специализацию
        f"Подписка заканчивается через: {days_left} дней"
    )

    await callback_query.message.edit_text(profile_info, reply_markup=generate_main_menu())
    await callback_query.answer()

# Показать расписание
@router.callback_query(lambda c: c.data == "schedule")
async def show_schedule(callback_query: types.CallbackQuery):
    schedule_info = "График работы:\nПонедельник - Пятница: 9:00 - 18:00\nСуббота: 10:00 - 15:00\nВоскресенье: выходной"
    await callback_query.message.edit_text(schedule_info, reply_markup=generate_main_menu())
    await callback_query.answer()

# Показать список врачей, к которым пациент может обратиться
@router.callback_query(lambda c: c.data == "contact_doctor")
async def show_doctors_list(callback_query: types.CallbackQuery):
    patient_id = callback_query.from_user.id
    doctors = await get_doctors_for_patient(patient_id)

    if not doctors:
        await callback_query.message.edit_text("У вас нет закрепленных врачей.")
        return

    buttons = [
        [InlineKeyboardButton(text=f"{doctor[1]} ({doctor[2]})", callback_data=f"doctor_{doctor[0]}")]
        for doctor in doctors
    ]
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="back_to_menu")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback_query.message.edit_text("Выберите доктора:", reply_markup=markup)
    await callback_query.answer()

# Обработка кнопки "Назад" для возврата в главное меню
@router.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text("Главное меню:", reply_markup=generate_main_menu())
    await callback_query.answer()

@router.callback_query(lambda c: c.data.startswith("doctor_"))
async def start_dialogue_with_doctor(callback_query: types.CallbackQuery, state: FSMContext):
    doctor_telegram_id = int(callback_query.data.split("_")[1])
    patient_id = callback_query.from_user.id

    dialogue = await get_active_dialogue(patient_id, doctor_telegram_id)
    if dialogue:
        await callback_query.message.edit_text("У вас уже есть активный диалог с этим доктором.")
    else:
        await start_dialogue(patient_id, doctor_telegram_id)
        # Сохраняем doctor_telegram_id и patient_id в состоянии
        await state.update_data(doctor_telegram_id=doctor_telegram_id, patient_id=patient_id)
        await state.set_state(DialogueState.waiting_for_message)
        await callback_query.message.edit_text("Напишите ваше сообщение для доктора.")
    await callback_query.answer()


@router.message(StateFilter(DialogueState.waiting_for_message))
async def send_message_to_doctor(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    doctor_id = state_data.get("doctor_telegram_id")
    patient_id = message.from_user.id

    # Проверяем, активен ли диалог
    dialogue = await get_active_dialogue(patient_id, doctor_id)
    if not dialogue or dialogue[2] == "completed":  # Проверяем, завершён ли диалог
        await message.answer("Диалог завершён. Вы не можете отправить сообщение.")
        return

    # Отправка сообщения доктору
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ответить", callback_data=f"reply_to_patient_{patient_id}")],
        [InlineKeyboardButton(text="Завершить диалог", callback_data=f"end_dialogue_{patient_id}")]
    ])

    await bot.send_message(doctor_id, f"Сообщение от пациента {message.from_user.full_name}: {message.text}", reply_markup=markup)
    await message.answer("Сообщение отправлено доктору.")


@router.callback_query(F.data.startswith("reply_to_doctor_"))
async def reply_to_doctor(callback_query: types.CallbackQuery, state: FSMContext):
    # Извлечение doctor_id из callback_data
    data = callback_query.data.split("_")
    doctor_id = int(data[3])

    # Сохранение doctor_id в состоянии
    await state.update_data(doctor_telegram_id=doctor_id)

    # Сообщение пациенту с просьбой ввести сообщение для доктора
    await callback_query.message.edit_text("Введите ваше сообщение для доктора:")
    await state.set_state(DialogueState.waiting_for_message)  # Переход в состояние ожидания сообщения
    await callback_query.answer()


