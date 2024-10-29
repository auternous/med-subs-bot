from aiogram import Router, types, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db import (
    get_doctor_by_user_id,
    add_patient,
    add_subscriber_to_doctor,
    get_patient_by_id,
    get_doctors_for_patient,
    get_doctor_by_id,
    start_dialogue,
    get_active_dialogue,
    get_patient_by_telegram_id,
    complete_dialogue,
    get_invite_code,
    mark_invite_code_as_used
)
from datetime import datetime
from config import bot

router = Router()

# States for patient registration and dialogue
class PatientRegistration(StatesGroup):
    waiting_for_name = State()
    confirmation = State()

class DialogueState(StatesGroup):
    waiting_for_message = State()
    waiting_for_reply = State()

# Function to generate the main menu for patients
def generate_main_menu():
    buttons = [
        [InlineKeyboardButton(text="Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="Расписание", callback_data="schedule")],
        [InlineKeyboardButton(text="Написать доктору", callback_data="contact_doctor")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Patient starts registration using the unique invite link
@router.message(CommandStart(deep_link=True))
async def patient_start(message: types.Message, state: FSMContext):
    args = message.text.split()[1] if len(message.text.split()) > 1 else None
    if not args or not args.startswith("invite_"):
        await message.answer("Неверная или недействительная ссылка.")
        return

    code = args.split("_", 1)[1]

    # Get invite code from the database
    invite_code = await get_invite_code(code)
    if not invite_code:
        await message.answer("Неверная или недействительная ссылка.")
        return
    if invite_code['used']:
        await message.answer("Ссылка уже была использована.")
        return

    doctor_id = invite_code['doctor_id']
    doctor = await get_doctor_by_id(doctor_id)
    if not doctor:
        await message.answer("Доктор не найден.")
        return

    # Mark the invite code as used
    await mark_invite_code_as_used(code)

    # Save the doctor's Telegram ID
    doctor_telegram_id = doctor['user_id']
    await state.update_data(doctor_telegram_id=doctor_telegram_id)
    await state.set_state(PatientRegistration.waiting_for_name)
    await message.answer("Введите ваше ФИО:")

# Process patient's name
@router.message(StateFilter(PatientRegistration.waiting_for_name))
async def process_patient_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    user_data = await state.get_data()
    await message.answer(
        f"Анкета пациента:\nИмя: {user_data['name']}\n\nПодтвердите отправку анкеты (да/нет)?"
    )
    await state.set_state(PatientRegistration.confirmation)

# Confirm patient registration
@router.message(StateFilter(PatientRegistration.confirmation))
async def process_patient_confirmation(message: types.Message, state: FSMContext):
    if message.text.lower() == 'да':
        user_data = await state.get_data()
        doctor_telegram_id = user_data['doctor_telegram_id']
        patient_id = message.from_user.id

        # Check if patient with this telegram_id already exists
        existing_patient = await get_patient_by_telegram_id(patient_id)
        if existing_patient:
            await message.answer("Вы уже зарегистрированы в системе.")
            await state.clear()
            return

        await add_patient(
            name=user_data['name'],
            telegram_id=patient_id,
            doctor_id=doctor_telegram_id,
            registration_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        await add_subscriber_to_doctor(doctor_telegram_id, patient_id)
        await message.answer("Регистрация завершена.", reply_markup=generate_main_menu())
        await state.clear()
    else:
        await message.answer("Регистрация отменена.")
        await state.clear()

# Handle main menu actions
@router.callback_query(lambda c: c.data == "profile")
async def show_profile(callback_query: types.CallbackQuery):
    patient = await get_patient_by_id(callback_query.from_user.id)
    if not patient:
        await callback_query.message.edit_text("Ошибка: не удалось получить данные профиля.")
        return

    registration_date_str = patient['registration_date']
    registration_date = datetime.strptime(registration_date_str, "%Y-%m-%d %H:%M:%S")
    days_left = 5 - (datetime.now() - registration_date).days

    if days_left < 0:
        days_left = 0

    profile_info = (
        f"Имя: {patient['name']}\n"
        f"Ваш доктор: {patient['specialization']}\n"
        f"Подписка заканчивается через: {days_left} дней"
    )

    await callback_query.message.edit_text(profile_info, reply_markup=generate_main_menu())
    await callback_query.answer()

@router.callback_query(lambda c: c.data == "schedule")
async def show_schedule(callback_query: types.CallbackQuery):
    schedule_info = "График работы:\nПонедельник - Пятница: 9:00 - 18:00\nСуббота: 10:00 - 15:00\nВоскресенье: выходной"
    await callback_query.message.edit_text(schedule_info, reply_markup=generate_main_menu())
    await callback_query.answer()

@router.callback_query(lambda c: c.data == "contact_doctor")
async def contact_doctor(callback_query: types.CallbackQuery):
    patient_id = callback_query.from_user.id
    doctors = await get_doctors_for_patient(patient_id)

    if not doctors:
        await callback_query.message.edit_text("У вас нет закрепленных врачей.")
        return

    buttons = [
        [InlineKeyboardButton(text=f"{doctor['fio']} ({doctor['specialization']})", callback_data=f"doctor_{doctor['user_id']}")]
        for doctor in doctors
    ]
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="back_to_menu")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback_query.message.edit_text("Выберите доктора для связи:", reply_markup=markup)
    await callback_query.answer()

@router.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text("Главное меню:", reply_markup=generate_main_menu())
    await callback_query.answer()

# Start dialogue with doctor
@router.callback_query(lambda c: c.data.startswith("doctor_"))
async def start_dialogue_with_doctor(callback_query: types.CallbackQuery, state: FSMContext):
    doctor_telegram_id = int(callback_query.data.split("_")[1])
    patient_id = callback_query.from_user.id

    # Check patient's subscription validity
    patient = await get_patient_by_id(patient_id)
    if not patient:
        await callback_query.message.edit_text("Ошибка: не удалось получить данные пациента.")
        return

    registration_date_str = patient['registration_date']
    registration_date = datetime.strptime(registration_date_str, "%Y-%m-%d %H:%M:%S")
    days_since_registration = (datetime.now() - registration_date).days

    if days_since_registration > 5:
        await callback_query.message.edit_text("Ваша подписка истекла. Обратитесь к администратору для продления.")
        await callback_query.answer()
        return

    dialogue = await get_active_dialogue(patient_id, doctor_telegram_id)
    if dialogue:
        await callback_query.message.edit_text("У вас уже есть активный диалог с этим доктором.")
    else:
        await start_dialogue(patient_id, doctor_telegram_id)
        # Save doctor_telegram_id and patient_id in state
        await state.update_data(doctor_telegram_id=doctor_telegram_id, patient_id=patient_id)
        await state.set_state(DialogueState.waiting_for_message)
        await callback_query.message.edit_text("Напишите ваше сообщение для доктора.")
    await callback_query.answer()

# Send message to doctor
@router.message(StateFilter(DialogueState.waiting_for_message))
async def send_message_to_doctor(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    doctor_id = state_data.get("doctor_telegram_id")
    patient_id = message.from_user.id

    if doctor_id is None:
        await message.answer("Ошибка: не удалось получить ID доктора.")
        return

    # Check patient's subscription validity
    patient = await get_patient_by_id(patient_id)
    if not patient:
        await message.answer("Ошибка: не удалось получить данные пациента.")
        await state.clear()
        return

    registration_date_str = patient['registration_date']
    registration_date = datetime.strptime(registration_date_str, "%Y-%m-%d %H:%M:%S")
    days_since_registration = (datetime.now() - registration_date).days

    if days_since_registration > 5:
        await message.answer("Ваша подписка истекла. Обратитесь к администратору для продления.")
        await state.clear()
        return

    # Check if dialogue is active
    dialogue = await get_active_dialogue(patient_id, doctor_id)
    if not dialogue or dialogue['state'] == "completed":
        await message.answer("Диалог завершён. Вы не можете отправить сообщение.")
        await state.clear()
        return

    # Send message to doctor
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ответить", callback_data=f"reply_to_patient_{patient_id}")],
        [InlineKeyboardButton(text="Завершить диалог", callback_data=f"doctor_end_dialogue_{patient_id}")]
    ])

    await bot.send_message(
        doctor_id,
        f"Сообщение от пациента {message.from_user.full_name}: {message.text}",
        reply_markup=markup
    )
    await message.answer("Сообщение отправлено доктору.")

    # Clear state after sending message
    await state.clear()

# Handle doctor's reply to patient
@router.callback_query(F.data.startswith("reply_to_doctor_"))
async def reply_to_doctor(callback_query: types.CallbackQuery, state: FSMContext):
    # Extract doctor_id from callback_data
    data = callback_query.data.split("_")
    doctor_id = int(data[3])

    # Save doctor_id in state
    await state.update_data(doctor_telegram_id=doctor_id)

    # Send message to patient
    await callback_query.message.answer("Введите ваше сообщение для доктора:")
    await state.set_state(DialogueState.waiting_for_message)
    await callback_query.answer()

# Handle ending dialogue by the patient
@router.callback_query(F.data.startswith("patient_end_dialogue_"))
async def end_dialogue_patient(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data.split("_")
    doctor_id = int(data[3])
    patient_id = callback_query.from_user.id

    # Get active dialogue
    dialogue = await get_active_dialogue(patient_id, doctor_id)

    if not dialogue:
        await callback_query.message.edit_text("Ошибка: диалог не найден.")
        return

    # Complete the dialogue
    await complete_dialogue(dialogue['id'])  # dialogue['id'] is 'id'

    # Clear FSM state for the patient
    await state.clear()

    # Notify both parties
    await bot.send_message(doctor_id, "Пациент завершил диалог.")
    await callback_query.message.edit_text("Вы завершили диалог с доктором.", reply_markup=generate_main_menu())
    await callback_query.answer()

# Handler for unexpected messages from the patient
@router.message(F.text & ~F.text.startswith('/'), StateFilter(None))
async def handle_unexpected_message(message: types.Message):
    await message.answer("Чтобы написать доктору, пожалуйста, используйте кнопку 'Написать доктору' в меню.")
