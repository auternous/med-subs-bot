# patient.py

from aiogram import Router, types, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db import (
    get_doctor_by_user_id,
    add_patient,
    add_patient_doctor_relation,
    get_patient_by_telegram_id,         # Используйте эту функцию
    get_patient_id_by_telegram_id,
    get_doctors_for_patient,
    get_doctor_by_id,
    start_dialogue,
    get_active_dialogue,
    complete_dialogue,
    get_invite_code,
    mark_invite_code_as_used,
    get_doctor_expiry_time
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

    # Save the doctor's ID in state
    await state.update_data(doctor_id=doctor_id)

    # Check if patient is already registered
    existing_patient = await get_patient_by_telegram_id(message.from_user.id)
    if existing_patient:
        patient_id = existing_patient['id']
        # Patient is already registered
        # Associate the patient with the new doctor
        await add_patient_doctor_relation(
            patient_id=patient_id,
            doctor_id=doctor_id,
            registration_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        await message.answer("Вы были успешно добавлены к новому врачу.", reply_markup=generate_main_menu())
        await state.clear()
    else:
        # Patient is not registered, proceed with registration
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
        doctor_id = user_data['doctor_id']
        patient_telegram_id = message.from_user.id

        # Добавляем пациента в таблицу patients
        await add_patient(
            name=user_data['name'],
            telegram_id=patient_telegram_id,
            registration_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        # Получаем patient_id для связи
        patient_id = await get_patient_id_by_telegram_id(patient_telegram_id)

        # Устанавливаем связь между пациентом и врачом
        await add_patient_doctor_relation(
            patient_id=patient_id,
            doctor_id=doctor_id,
            registration_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        await message.answer("Регистрация завершена.", reply_markup=generate_main_menu())
        await state.clear()
    else:
        # Если пациент ответил "нет", просим его снова ввести данные
        await message.answer("Пожалуйста, введите ваше ФИО снова для регистрации.")
        await state.set_state(PatientRegistration.waiting_for_name)



@router.callback_query(lambda c: c.data == "profile")
async def show_profile(callback_query: types.CallbackQuery):
    patient = await get_patient_by_telegram_id(callback_query.from_user.id)
    if not patient:
        await callback_query.message.edit_text("Ошибка: не удалось получить данные профиля.")
        return

    profile_info = f"Имя: {patient['name']}\n"

    # Список врачей пациента с временем до окончания прикрепления
    patient_id = patient['id']
    doctors = await get_doctors_for_patient(patient_id)
    if doctors:
        doctor_list = ""
        for doctor in doctors:
            specialization = doctor['specialization'] or "Специализация не указана"
            expiry_date = doctor['expiry_date']
            time_remaining = get_time_remaining(expiry_date) if expiry_date else "неизвестно"
            doctor_list += f"{doctor['fio']} ({specialization}) - осталось: {time_remaining}\n"
        profile_info += f"Ваши врачи:\n{doctor_list}"
    else:
        profile_info += "У вас нет закрепленных врачей."

    await callback_query.message.edit_text(profile_info, reply_markup=generate_main_menu())
    await callback_query.answer()



@router.callback_query(lambda c: c.data == "schedule")
async def show_schedule(callback_query: types.CallbackQuery):
    schedule_info = "График работы:\nПонедельник - Пятница: 9:00 - 18:00\nСуббота: 10:00 - 15:00\nВоскресенье: выходной"
    await callback_query.message.edit_text(schedule_info, reply_markup=generate_main_menu())
    await callback_query.answer()

@router.callback_query(lambda c: c.data == "contact_doctor")
async def contact_doctor(callback_query: types.CallbackQuery):
    patient_telegram_id = callback_query.from_user.id
    patient_id = await get_patient_id_by_telegram_id(patient_telegram_id)
    if not patient_id:
        await callback_query.message.edit_text("Ошибка: не удалось получить данные пациента.")
        return

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
    patient_telegram_id = callback_query.from_user.id
    patient_id = await get_patient_id_by_telegram_id(patient_telegram_id)

    if not patient_id:
        await callback_query.message.edit_text("Ошибка: не удалось получить данные пациента.")
        return

    dialogue = await get_active_dialogue(patient_id, doctor_telegram_id)
    if dialogue:
        await callback_query.message.edit_text("У вас уже есть активный диалог с этим доктором.")
    else:
        await start_dialogue(patient_id, doctor_telegram_id)
        
        # Сохраняем данные в состоянии
        await state.update_data(doctor_telegram_id=doctor_telegram_id, patient_id=patient_id)
        await state.set_state(DialogueState.waiting_for_message)

        # Кнопка для отмены
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data="cancel_dialogue")]
        ])
        
        await callback_query.message.edit_text("Напишите ваше сообщение для доктора или нажмите 'Отмена', если передумали.", reply_markup=markup)
    await callback_query.answer()

from db import complete_dialogue  # Убедитесь, что функция complete_dialogue импортирована

# Обработчик для отмены диалога с врачом
@router.callback_query(lambda c: c.data == "cancel_dialogue")
async def cancel_dialogue(callback_query: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    doctor_telegram_id = state_data.get("doctor_telegram_id")
    patient_telegram_id = callback_query.from_user.id

    # Получаем patient_id для проверки диалога
    patient_id = await get_patient_id_by_telegram_id(patient_telegram_id)

    # Проверяем, есть ли активный диалог с этим врачом
    dialogue = await get_active_dialogue(patient_id, doctor_telegram_id)
    if dialogue:
        # Завершаем активный диалог, чтобы он не считался активным
        await complete_dialogue(dialogue['id'])

    # Очищаем состояние и возвращаемся в главное меню
    await state.clear()
    await callback_query.message.edit_text("Вы отменили диалог. Возвращаемся в главное меню.", reply_markup=generate_main_menu())
    await callback_query.answer()

# Send message to doctor
@router.message(StateFilter(DialogueState.waiting_for_message))
async def send_message_to_doctor(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    doctor_id = state_data.get("doctor_telegram_id")
    patient_telegram_id = message.from_user.id  # Это Telegram ID пациента

    if doctor_id is None:
        await message.answer("Ошибка: не удалось получить ID доктора.")
        return

    # Проверяем активный диалог
    patient_id = await get_patient_id_by_telegram_id(patient_telegram_id)
    dialogue = await get_active_dialogue(patient_id, doctor_id)
    if not dialogue or dialogue['state'] == "completed":
        await message.answer("Диалог завершён. Вы не можете отправить сообщение.")
        await state.clear()
        return

    # Формируем кнопки с использованием Telegram ID пациента
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ответить", callback_data=f"reply_to_patient_{patient_telegram_id}")],
        [InlineKeyboardButton(text="Завершить диалог", callback_data=f"doctor_end_dialogue_{patient_telegram_id}")]
    ])

    await bot.send_message(
        doctor_id,
        f"Сообщение от пациента: {message.text}",
        reply_markup=markup
    )
    await message.answer("Сообщение отправлено доктору.")

    # Очищаем состояние
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
    doctor_telegram_id = int(data[3])
    patient_telegram_id = callback_query.from_user.id
    patient_id = await get_patient_id_by_telegram_id(patient_telegram_id)

    # Получаем активный диалог
    dialogue = await get_active_dialogue(patient_id, doctor_telegram_id)

    if not dialogue:
        await callback_query.message.edit_text("Ошибка: диалог не найден.")
        return

    # Завершаем диалог
    await complete_dialogue(dialogue['id'])

    # Очищаем состояние
    await state.clear()

    # Уведомляем обе стороны
    await bot.send_message(doctor_telegram_id, "Пациент завершил диалог.")
    await callback_query.message.edit_text("Вы завершили диалог с доктором.", reply_markup=generate_main_menu())
    await callback_query.answer()


# Handler for unexpected messages from the patient
@router.message(F.text & ~F.text.startswith('/'), StateFilter(None))
async def handle_unexpected_message(message: types.Message):
    await message.answer("Чтобы написать доктору, пожалуйста, используйте кнопку 'Написать доктору' в меню.")


def get_time_remaining(expiry_date):
    expiry = datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S")
    time_remaining = expiry - datetime.now()
    days = time_remaining.days
    hours, remainder = divmod(time_remaining.seconds, 3600)
    return f"{days} дней, {hours} часов"


@router.callback_query(lambda c: c.data == "contact_doctor")
async def contact_doctor(callback_query: types.CallbackQuery):
    patient_telegram_id = callback_query.from_user.id
    patient_id = await get_patient_id_by_telegram_id(patient_telegram_id)
    if not patient_id:
        await callback_query.message.edit_text("Ошибка: не удалось получить данные пациента.")
        return

    doctors = await get_doctors_for_patient(patient_id)

    if not doctors:
        await callback_query.message.edit_text("У вас нет закрепленных врачей.")
        return

    buttons = [
        [InlineKeyboardButton(text=f"{doctor['fio']} ({doctor['specialization']})", callback_data=f"chat_with_{doctor['user_id']}")]
        for doctor in doctors
    ]
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="back_to_menu")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback_query.message.edit_text("Выберите доктора для связи:", reply_markup=markup)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("chat_with_"))
async def start_chat_with_doctor(callback_query: types.CallbackQuery, state: FSMContext):
    doctor_telegram_id = int(callback_query.data.split("_")[2])
    patient_telegram_id = callback_query.from_user.id
    patient_id = await get_patient_id_by_telegram_id(patient_telegram_id)

    if not patient_id:
        await callback_query.message.edit_text("Ошибка: не удалось получить данные пациента.")
        return

    # Проверяем активный диалог
    dialogue = await get_active_dialogue(patient_id, doctor_telegram_id)
    if not dialogue:
        await start_dialogue(patient_id, doctor_telegram_id)

    # Сохраняем данные диалога
    await state.update_data(current_doctor_id=doctor_telegram_id)
    await callback_query.message.edit_text("Вы в чате с доктором. Напишите сообщение.")
    await callback_query.answer()

