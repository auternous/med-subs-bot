from aiogram import Router, types
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db import get_doctor_by_user_id, add_patient, add_subscriber_to_doctor, get_patient_by_id
from datetime import datetime

router = Router()

# Определяем состояния для регистрации пациента
class PatientRegistration(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    confirmation = State()

@router.message(CommandStart(deep_link=True))
async def patient_start(message: types.Message, state: FSMContext):
    args = message.text.split()[1] if len(message.text.split()) > 1 else None

    if not args or not args.startswith("doctor_"):
        await message.answer("Неверная ссылка. Пожалуйста, получите правильную ссылку от вашего доктора.")
        return
    
    doctor_id = args.split("_")[1] 
    
    # Получаем информацию о докторе
    doctor = await get_doctor_by_user_id(int(doctor_id))
    
    if not doctor:
        await message.answer("Доктор не найден. Пожалуйста, проверьте ссылку.")
        return
    
    # Сохраняем doctor_id в состоянии
    await state.update_data(doctor_id=doctor_id)
    
    # Переход к вводу ФИО пациента
    await state.set_state(PatientRegistration.waiting_for_name)
    await message.answer("Пожалуйста, введите ваше ФИО:")

@router.message(StateFilter(PatientRegistration.waiting_for_name))
async def process_patient_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(PatientRegistration.waiting_for_phone)
    await message.answer("Пожалуйста, введите ваш номер телефона:")

@router.message(StateFilter(PatientRegistration.waiting_for_phone))
async def process_patient_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    user_data = await state.get_data()
    
    # Подтверждение данных пациента
    await message.answer(
        f"Проверьте ваши данные:\nФИО: {user_data['name']}\nТелефон: {user_data['phone']}\n\nЕсли все верно, напишите 'да', чтобы подтвердить, или 'нет', чтобы ввести заново.")
    await state.set_state(PatientRegistration.confirmation)

@router.message(StateFilter(PatientRegistration.confirmation))
async def process_patient_confirmation(message: types.Message, state: FSMContext):
    if message.text.lower() == 'да':
        user_data = await state.get_data()
        
        # Добавляем пациента в базу данных
        await add_patient(
            name=user_data['name'],
            phone=user_data['phone'],
            telegram_id=message.from_user.id,
            doctor_id=user_data['doctor_id'],
            registration_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        # Добавляем подписчика к доктору
        await add_subscriber_to_doctor(user_data['doctor_id'], message.from_user.id)

        # Инлайн-кнопки после завершения регистрации
        buttons = [
            [InlineKeyboardButton(text="Профиль", callback_data="profile")],
            [InlineKeyboardButton(text="Расписание", callback_data="schedule")],
            [InlineKeyboardButton(text="Написать доктору", callback_data="contact_doctor")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        await message.answer("Регистрация завершена. Добро пожаловать!", reply_markup=keyboard)
        await state.clear()
    else:
        # Повторный ввод данных
        await state.set_state(PatientRegistration.waiting_for_name)
        await message.answer("Введите ваше ФИО:")

# Обработка кнопки "Профиль"
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
        f"Ваш доктор: {patient['specialization']}\n"
        f"Подписка заканчивается через: {days_left} дней"
    )

    # Изменяем текст существующего сообщения
    await callback_query.message.edit_text(profile_info, reply_markup=callback_query.message.reply_markup)
    await callback_query.answer()


# Обработка кнопки "Расписание"
@router.callback_query(lambda c: c.data == "schedule")
async def show_schedule(callback_query: types.CallbackQuery):
    schedule_info = "График работы:\nПонедельник - Пятница: 9:00 - 18:00\nСуббота: 10:00 - 15:00\nВоскресенье: выходной"

    # Изменяем текст существующего сообщения
    await callback_query.message.edit_text(schedule_info, reply_markup=callback_query.message.reply_markup)
    await callback_query.answer()


# Обработка кнопки "Написать доктору"
@router.callback_query(lambda c: c.data == "contact_doctor")
async def contact_doctor(callback_query: types.CallbackQuery):
    await callback_query.message.answer("Специалисты")
    await callback_query.answer()
