from aiogram import Router, types
from aiogram import F
from aiogram.types import InputFile, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.filters import CommandStart
from aiogram.exceptions import TelegramNetworkError
from config import bot, ADMIN_ID
from db import (
    add_doctor,
    get_doctor_by_user_id,
    get_doctor_for_link,
    get_doctor_by_id,
    update_doctor_specialization,
    get_active_dialogue,
    complete_dialogue,
    create_invite_code,
    send_message_to_patient,
    get_patient_id_by_telegram_id
)
import qrcode  # For generating QR codes
import io  # For handling image data in memory
import logging

router = Router()

# States for doctor registration and admin actions
class DoctorRegistration(StatesGroup):
    waiting_for_name = State()
    confirmation = State()

class AdminActions(StatesGroup):
    waiting_for_specialization = State()

class DialogueState(StatesGroup):
    waiting_for_message = State()
    waiting_for_reply = State()


# Command to start doctor registration
@router.message(Command("reg"))
async def cmd_register(message: types.Message, state: FSMContext):
    await state.clear()  # Clear any previous state
    await state.set_state(DoctorRegistration.waiting_for_name)
    await message.answer("Введите ваше ФИО:")

# Process doctor's name
@router.message(StateFilter(DoctorRegistration.waiting_for_name))
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    user_data = await state.get_data()
    await message.answer(
        f"Анкета доктора:\nИмя: {user_data['fio']}\n\nПодтвердите отправку анкеты (да/нет)?"
    )
    await state.set_state(DoctorRegistration.confirmation)

# Confirm registration
@router.message(StateFilter(DoctorRegistration.confirmation))
async def process_confirmation(message: types.Message, state: FSMContext):
    try:
        if message.text.lower() == 'да':
            user_data = await state.get_data()
            user_id = message.from_user.id
            doctor_id = await add_doctor(user_data['fio'], user_id)
            await message.answer("Анкета отправлена на рассмотрение.")
            await state.clear()

            # Notify admin with approval options
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Одобрить", callback_data=f"approve_{doctor_id}"),
                    InlineKeyboardButton(text="Отклонить", callback_data=f"reject_{doctor_id}")
                ]
            ])
            await bot.send_message(
                ADMIN_ID,
                f"Новая заявка на регистрацию доктора:\nИмя: {user_data['fio']}",
                reply_markup=keyboard
            )
        else:
            await message.answer("Регистрация отменена. Начните сначала с команды /reg.")
            await state.clear()
    except TelegramNetworkError:
        await message.answer("Произошла ошибка сети. Пожалуйста, попробуйте позже.")

# Handle admin's approval of doctor registration
@router.callback_query(F.data.startswith("approve_"))
async def approve_doctor(callback_query: types.CallbackQuery, state: FSMContext):
    doctor_id = int(callback_query.data.split("_")[1])

    await state.update_data(doctor_id=doctor_id)
    await callback_query.message.answer("Введите специализацию доктора:")
    await state.set_state(AdminActions.waiting_for_specialization)
    await callback_query.answer()

# Set doctor's specialization
@router.message(StateFilter(AdminActions.waiting_for_specialization))
async def set_specialization(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    doctor_id = state_data.get("doctor_id")

    if doctor_id is None:
        await message.answer("Ошибка: не удалось получить ID доктора.")
        return

    # Сохраняем введённую специализацию во временные данные состояния
    await state.update_data(specialization=message.text)

    # Запрашиваем подтверждение специализации
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Подтвердить", callback_data="confirm_specialization"),
            InlineKeyboardButton(text="Отмена", callback_data="cancel_specialization")
        ]
    ])
    await message.answer(f"Вы ввели специализацию: {message.text}. Подтвердите или отмените ввод.", reply_markup=keyboard)


# Обработчик подтверждения специализации
@router.callback_query(lambda c: c.data == "confirm_specialization")
async def confirm_specialization(callback_query: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    doctor_id = state_data.get("doctor_id")
    specialization = state_data.get("specialization")

    # Устанавливаем специализацию и статус "approved" для доктора
    await update_doctor_specialization(doctor_id, specialization)
    await callback_query.message.edit_text(f"Специализация успешно установлена для доктора: {specialization}.")
    
    # Получаем данные врача и уведомляем его
    doctor = await get_doctor_by_id(doctor_id)
    if doctor:
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="Создать ссылку")]],
            resize_keyboard=True
        )
        await bot.send_message(
            doctor['user_id'],
            "Теперь вы можете создать ссылку для приглашения пациентов.",
            reply_markup=keyboard
        )

    await state.clear()
    await callback_query.answer()


# Обработчик отмены специализации
@router.callback_query(lambda c: c.data == "cancel_specialization")
async def cancel_specialization(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text("Отмена ввода специализации. Пожалуйста, введите специализацию снова.")
    await state.set_state(AdminActions.waiting_for_specialization)  # Возвращаемся к этапу ввода специализации
    await callback_query.answer()

# Handler for creating an invite link when the doctor clicks "Создать ссылку"
@router.message(F.text == "Создать ссылку")
async def handle_create_link(message: types.Message):
    doctor_id = await get_doctor_for_link(message.from_user.id)
    if doctor_id is None:
        await message.answer("Произошла ошибка. Попробуйте позже.")
        return

    # Generate a unique code and save it to the database
    code = await create_invite_code(doctor_id)

    # Generate a unique link using the code
    bot_info = await bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start=invite_{code}"

    # Generate a QR code for the link
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(invite_link)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')

    # Save the QR code image in memory
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    # Send the QR code and link to the doctor
    await bot.send_photo(
        chat_id=message.from_user.id,
        photo=BufferedInputFile(file=img_byte_arr.read(), filename="qrcode.png"),
        caption=f"Ваша уникальная ссылка для приглашения пациента (одноразовая):\n{invite_link}"
    )

# Handle doctor's rejection of registration
@router.callback_query(F.data.startswith("reject_"))
async def reject_doctor(callback_query: types.CallbackQuery):
    doctor_id = int(callback_query.data.split("_")[1])

    # Get doctor's data
    doctor = await get_doctor_by_id(doctor_id)

    if doctor:
        # Send notification to the doctor about the rejection
        await bot.send_message(
            doctor['user_id'],
            "К сожалению, ваша заявка на регистрацию была отклонена."
        )

    await callback_query.message.answer("Регистрация доктора отклонена.")
    await callback_query.answer()

# Handle messages from patients to doctors
@router.callback_query(F.data.startswith("reply_to_patient_"))
async def reply_to_patient(callback_query: types.CallbackQuery, state: FSMContext):
    # Извлекаем Telegram ID пациента из callback_data
    data = callback_query.data.split("_")
    patient_telegram_id = int(data[3])

    # Сохраняем Telegram ID пациента в состоянии
    await state.update_data(patient_telegram_id=patient_telegram_id)

    # Запрашиваем сообщение от доктора
    await callback_query.message.answer("Введите ваше сообщение для пациента:")
    await state.set_state(DialogueState.waiting_for_reply)
    await callback_query.answer()


@router.message(StateFilter(DialogueState.waiting_for_reply))
async def process_doctor_reply(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    patient_telegram_id = state_data.get("patient_telegram_id")

    if patient_telegram_id is None:
        await message.answer("Ошибка: не удалось получить Telegram ID пациента.")
        return

    # Получаем patient_id для проверки диалога
    patient_id = await get_patient_id_by_telegram_id(patient_telegram_id)

    # Проверяем, что диалог активен
    dialogue = await get_active_dialogue(patient_id, message.from_user.id)
    if not dialogue or dialogue['state'] == "completed":
        await message.answer("Диалог завершён. Вы не можете отправить сообщение.")
        await state.clear()
        return

    # Формируем кнопки для пациента
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ответить", callback_data=f"reply_to_doctor_{message.from_user.id}")],
        [InlineKeyboardButton(text="Завершить диалог", callback_data=f"patient_end_dialogue_{message.from_user.id}")]
    ])

    # Отправляем сообщение пациенту, используя его Telegram ID
    await bot.send_message(patient_telegram_id, f"Ответ от доктора: {message.text}", reply_markup=markup)
    await message.answer("Ваше сообщение отправлено пациенту.")

    # Очищаем состояние
    await state.clear()

# Handler for unexpected messages from the doctor
@router.message(F.text & ~F.text.startswith('/'), StateFilter(None))
async def handle_unexpected_message(message: types.Message):
    await message.answer("Чтобы ответить пациенту, пожалуйста, используйте кнопку 'Ответить' под его сообщением.")

# Handle ending dialogue by the doctor
@router.callback_query(F.data.startswith("doctor_end_dialogue_"))
async def end_dialogue_doctor(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data.split("_")
    patient_telegram_id = int(data[3])
    doctor_telegram_id = callback_query.from_user.id
    patient_id = await get_patient_id_by_telegram_id(patient_telegram_id)

    # Получаем активный диалог
    dialogue = await get_active_dialogue(patient_id, doctor_telegram_id)

    if not dialogue:
        await callback_query.message.answer("Ошибка: диалог не найден.")
        return

    # Завершаем диалог
    await complete_dialogue(dialogue['id'])

    # Очищаем состояние
    await state.clear()

    # Уведомляем обе стороны
    await bot.send_message(patient_telegram_id, "Доктор завершил диалог.", reply_markup=generate_main_menu())
    await callback_query.message.answer("Вы завершили диалог с пациентом.")
    await callback_query.answer()


# Function to generate the main menu for patients (used when ending dialogue)
def generate_main_menu():
    buttons = [
        [InlineKeyboardButton(text="Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="Расписание", callback_data="schedule")],
        [InlineKeyboardButton(text="Написать доктору", callback_data="contact_doctor")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(F.text == "Мои чаты")
async def show_chats(message: types.Message):
    doctor_id = await get_doctor_by_user_id(message.from_user.id)
    if not doctor_id:
        await message.answer("Вы не зарегистрированы как врач.")
        return

    dialogues = await get_active_dialogue(doctor_id=doctor_id['id'])
    if not dialogues:
        await message.answer("У вас нет активных чатов.")
        return

    buttons = [
        [InlineKeyboardButton(text=f"Чат с {dialogue['patient_name']}", callback_data=f"open_chat_{dialogue['id']}")]
        for dialogue in dialogues
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Ваши активные чаты:", reply_markup=markup)


@router.callback_query(F.data.startswith("open_chat_"))
async def open_chat(callback_query: types.CallbackQuery, state: FSMContext):
    dialogue_id = int(callback_query.data.split("_")[2])
    await state.update_data(current_dialogue_id=dialogue_id)
    await callback_query.message.edit_text(f"Вы в чате. Можете писать сообщения.")
    await callback_query.answer()


async def send_notification_to_doctor(doctor_id, patient_name, message, dialogue_id):
    buttons = [
        [InlineKeyboardButton(text="Перейти в чат", callback_data=f"open_chat_{dialogue_id}")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await bot.send_message(doctor_id, f"Новое сообщение от {patient_name}: {message}", reply_markup=markup)


@router.message(F.text == "Выйти в список чатов")
async def back_to_chat_list(message: types.Message, state: FSMContext):
    await state.clear()
    await show_chats(message)
