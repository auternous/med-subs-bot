from aiogram import Router, types
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.exceptions import TelegramNetworkError
from config import bot, dp, ADMIN_ID
from db import (add_doctor, get_doctor_by_user_id, get_doctor_for_link, 
                update_doctor_specialization, get_active_dialogue, 
                complete_dialogue, send_message_to_patient)

router = Router()

class DoctorRegistration(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    confirmation = State()

class AdminActions(StatesGroup):
    waiting_for_specialization = State()

class DialogueState(StatesGroup):
    waiting_for_message = State()  # Ожидание сообщения пациента
    waiting_for_reply = State() 

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


# Сообщение от пациента доктору по нажатию на кнопку
@router.callback_query(F.data.startswith("reply_to_patient_"))
async def reply_to_patient(callback_query: types.CallbackQuery, state: FSMContext):
    # Извлечение patient_id из callback_data
    data = callback_query.data.split("_")
    patient_id = int(data[3])

    # Сохранение patient_id в состоянии
    await state.update_data(patient_id=patient_id)

    # Сообщение доктору с просьбой ввести сообщение для пациента
    await callback_query.message.edit_text("Введите ваше сообщение для пациента:")
    await state.set_state(DialogueState.waiting_for_reply)  # Переход в состояние ожидания сообщения
    await callback_query.answer()


@router.message(StateFilter(DialogueState.waiting_for_reply))
async def process_doctor_reply(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    patient_id = state_data.get("patient_id")

    # Проверяем, активен ли диалог
    dialogue = await get_active_dialogue(patient_id, message.from_user.id)
    if not dialogue or dialogue[2] == "completed":  # Проверяем, завершён ли диалог
        await message.answer("Диалог завершён. Вы не можете отправить сообщение.")
        return

    # Отправляем сообщение пациенту
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ответить", callback_data=f"reply_to_doctor_{message.from_user.id}")],
        [InlineKeyboardButton(text="Завершить диалог", callback_data=f"end_dialogue_{message.from_user.id}")]
    ])

    await bot.send_message(patient_id, f"Ответ от доктора: {message.text}", reply_markup=markup)
    await message.answer("Ваше сообщение отправлено пациенту.")



# Главное меню пациента
def generate_main_menu():
    buttons = [
        [InlineKeyboardButton(text="Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="Расписание", callback_data="schedule")],
        [InlineKeyboardButton(text="Написать доктору", callback_data="contact_doctor")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# Завершение диалога доктором
@router.callback_query(F.data.startswith("end_dialogue_"))
async def end_dialogue_doctor(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data.split("_")
    patient_id = int(data[2])
    doctor_id = callback_query.from_user.id

    # Получаем активный диалог
    dialogue = await get_active_dialogue(patient_id, doctor_id)
    
    if not dialogue:
        await callback_query.message.answer("Ошибка: диалог не найден.")
        return

    # Завершаем диалог
    await complete_dialogue(dialogue[0])

    # Очищаем состояние FSM для доктора
    await state.clear()

    # Уведомляем обе стороны
    await bot.send_message(patient_id, "Доктор завершил диалог.", reply_markup=generate_main_menu())
    await callback_query.message.answer("Вы завершили диалог с пациентом.", reply_markup=None)

    # Очищаем состояние FSM для пациента (если используется FSM для пациента)
    await state.clear()
    await callback_query.answer()
