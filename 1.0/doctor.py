from aiogram import Router, types
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, StateFilter
from aiogram.exceptions import TelegramNetworkError
from config import bot, dp, ADMIN_ID
from db import add_doctor, get_doctor_by_user_id, get_doctor_for_link, update_doctor_specialization

router = Router()

class DoctorRegistration(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    confirmation = State()

class AdminActions(StatesGroup):
    waiting_for_specialization = State()

@router.message(Command("reg"))
async def cmd_register(message: types.Message, state: FSMContext):
    await state.clear()  # Сбрасываем состояние перед установкой нового
    await state.set_state(DoctorRegistration.waiting_for_name)
    await message.answer("Введите ФИО доктора:")

@router.message(StateFilter(DoctorRegistration.waiting_for_name))
async def process_surname(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await state.set_state(DoctorRegistration.waiting_for_phone)
    await message.answer("Введите номер телефона доктора:")

@router.message(StateFilter(DoctorRegistration.waiting_for_phone))
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    user_data = await state.get_data()
    await message.answer(
        f"Анкета доктора:\nИмя: {user_data['fio']}\nТелефон: {user_data['phone']}\n\nПодтвердите отправку анкеты (да/нет)?")
    await state.set_state(DoctorRegistration.confirmation)

@router.message(StateFilter(DoctorRegistration.confirmation))
async def process_confirmation(message: types.Message, state: FSMContext):
    try:
        if message.text.lower() == 'да':
            user_data = await state.get_data()
            user_id = message.from_user.id
            doctor_id = await add_doctor(user_data['fio'], user_data['phone'], user_id)
            await message.answer("Анкета отправлена на рассмотрение.")
            await state.clear()

            # Отправляем сообщение админу с кнопками
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [
                    types.InlineKeyboardButton(text="Одобрить", callback_data=f"approve_{doctor_id}"),
                    types.InlineKeyboardButton(text="Отклонить", callback_data=f"reject_{doctor_id}")
                ]
            ])
            await bot.send_message(ADMIN_ID, f"Новая заявка на регистрацию:\nИмя: {user_data['fio']}\nТелефон: {user_data['phone']}", reply_markup=keyboard)
        else:
            await message.answer("Регистрация отменена. Начните сначала с команды /reg.")
            await state.clear()
    except TelegramNetworkError:
        await message.answer("Произошла ошибка сети. Пожалуйста, попробуйте позже.")

# Обработка callback query для одобрения доктора
@router.callback_query(F.data.startswith("approve_"))
async def approve_doctor(callback_query: types.CallbackQuery, state: FSMContext):
    doctor_id = int(callback_query.data.split("_")[1])
    
    await state.update_data(doctor_id=doctor_id)
    await callback_query.message.answer("Введите специализацию доктора:")
    await state.set_state(AdminActions.waiting_for_specialization)
    await callback_query.answer()

@router.message(StateFilter(AdminActions.waiting_for_specialization))
async def set_specialization(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    doctor_id = state_data.get("doctor_id")
    
    if doctor_id is None:
        await message.answer("Ошибка: не удалось получить ID доктора.")
        return

    await update_doctor_specialization(doctor_id, message.text)
    await message.answer(f"Специализация успешно установлена для доктора {message.text}.")
    
    # Добавляем инлайн-кнопку "Создать ссылку"
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="Создать ссылку", callback_data="create_link")
        ]
    ])
    
    await message.answer("Теперь вы можете создать ссылку для приглашения пациентов.", reply_markup=keyboard)
    await state.clear()

# Обработка создания ссылки через инлайн-кнопку
@router.callback_query(F.data == "create_link")
async def handle_create_link(callback_query: types.CallbackQuery):
    doctor_id = await get_doctor_for_link(callback_query.from_user.id)  # Получаем ID доктора по его user_id
    if doctor_id is None:
        await callback_query.message.answer("Произошла ошибка. Попробуйте позже.")
        return

    # Генерация уникальной ссылки с deep linking
    bot_info = await bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start=doctor_{doctor_id}"
    await callback_query.message.answer(f"Ваша уникальная ссылка для приглашения пациентов:\n{invite_link}")
    await callback_query.answer()
