# doctor.py

from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, StateFilter
from aiogram.exceptions import TelegramNetworkError
from config import bot, ADMIN_ID
from db import (
    add_doctor, get_doctor_by_id, get_doctor_by_user_id,
    update_doctor_specialization, create_invite_code, get_doctor_for_link
)
import qrcode
import io

router = Router()

# States
class DoctorRegistration(StatesGroup):
    waiting_for_name = State()
    confirmation = State()

class AdminActions(StatesGroup):
    waiting_for_specialization = State()


@router.message(Command("reg"))
async def cmd_register(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(DoctorRegistration.waiting_for_name)
    await message.answer("Введите ваше ФИО:")

@router.message(StateFilter(DoctorRegistration.waiting_for_name))
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await message.answer(
        f"Анкета доктора:\n"
        f"Имя: {message.text}\n"
        f"Подтвердить (да/нет)?"
    )
    await state.set_state(DoctorRegistration.confirmation)

@router.message(StateFilter(DoctorRegistration.confirmation))
async def process_confirmation(message: types.Message, state: FSMContext):
    try:
        if message.text.lower() == 'да':
            data = await state.get_data()
            doctor_id = await add_doctor(data['fio'], message.from_user.id)
            await message.answer("Анкета отправлена на рассмотрение.")
            await state.clear()

            # Уведомляем админа
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="Одобрить", callback_data=f"approve_{doctor_id}"),
                    InlineKeyboardButton(text="Отклонить", callback_data=f"reject_{doctor_id}")
                ]]
            )
            await bot.send_message(
                ADMIN_ID,
                f"Новая заявка на регистрацию доктора: {data['fio']}",
                reply_markup=keyboard
            )
        else:
            await message.answer("Регистрация отменена. Начните с /reg заново.")
            await state.clear()
    except TelegramNetworkError:
        await message.answer("Произошла сетевая ошибка. Попробуйте позже.")

# Админ нажимает "Одобрить"
@router.callback_query(F.data.startswith("approve_"))
async def approve_doctor(callback_query: types.CallbackQuery, state: FSMContext):
    doctor_id = int(callback_query.data.split("_")[1])
    await state.update_data(doctor_id=doctor_id)
    await callback_query.message.answer("Введите специализацию доктора:")
    await state.set_state(AdminActions.waiting_for_specialization)
    await callback_query.answer()

@router.message(StateFilter(AdminActions.waiting_for_specialization))
async def set_specialization(message: types.Message, state: FSMContext):
    data = await state.get_data()
    doctor_id = data.get("doctor_id")
    if not doctor_id:
        await message.answer("Ошибка: не найден ID доктора.")
        return
    # Подтверждение специализации
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Подтвердить", callback_data="confirm_specialization"),
            InlineKeyboardButton(text="Отмена", callback_data="cancel_specialization")
        ]
    ])
    await state.update_data(specialization=message.text)
    await message.answer(
        f"Вы ввели специализацию: {message.text}. Подтвердить или отменить?",
        reply_markup=keyboard
    )

@router.callback_query(lambda c: c.data == "confirm_specialization")
async def confirm_specialization(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    doctor_id = data.get("doctor_id")
    specialization = data.get("specialization")
    await update_doctor_specialization(doctor_id, specialization)
    await callback_query.message.edit_text(f"Специализация установлена: {specialization}")
    # Уведомляем доктора
    doctor = await get_doctor_by_id(doctor_id)
    if doctor:
        await bot.send_message(
            doctor['user_id'],
            "Вашу анкету одобрили! Теперь вы можете сгенерировать ссылку для пациентов.\n"
            "Введите в чат: Создать ссылку",
        )
    await state.clear()
    await callback_query.answer()

@router.callback_query(lambda c: c.data == "cancel_specialization")
async def cancel_specialization(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text("Отмена ввода специализации. Введите снова:")
    await state.set_state(AdminActions.waiting_for_specialization)
    await callback_query.answer()

# Админ "Отклонить"
@router.callback_query(F.data.startswith("reject_"))
async def reject_doctor(callback_query: types.CallbackQuery):
    doctor_id = int(callback_query.data.split("_")[1])
    doctor = await get_doctor_by_id(doctor_id)
    if doctor:
        await bot.send_message(
            doctor['user_id'],
            "К сожалению, ваша заявка отклонена."
        )
    await callback_query.message.answer("Регистрация доктора отклонена.")
    await callback_query.answer()

# Генерация одноразовой ссылки для пациента
@router.message(F.text == "Создать ссылку")
async def handle_create_link(message: types.Message):
    doctor_id = await get_doctor_for_link(message.from_user.id)
    if not doctor_id:
        await message.answer("Ошибка: вы не зарегистрированы как врач или вас ещё не одобрили.")
        return
    code = await create_invite_code(doctor_id)
    bot_info = await bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start=invite_{code}"

    # Генерируем QR
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(invite_link)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    await bot.send_photo(
        chat_id=message.from_user.id,
        photo=BufferedInputFile(buf.read(), "qrcode.png"),
        caption=f"Ваша одноразовая ссылка:\n{invite_link}"
    )
