from aiogram import Router, types
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, StateFilter
from aiogram.exceptions import TelegramNetworkError
from config import bot, dp, ADMIN_ID
from db import add_doctor, get_doctor_by_user_id, get_doctor_for_link

router = Router()

class DoctorRegistration(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    confirmation = State()

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


@router.message(F.text == "Создать ссылку")
async def generate_link(message: types.Message, state: FSMContext):
    bot_info = await bot.get_me()
    doctor_id = await get_doctor_for_link(message.from_user.id)  # Получаем ID доктора по его user_id
    if doctor_id is None:
        await message.answer("Произошла ошибка. Попробуйте позже.")
        await message.answer(f"Ваша уникальная ссылка для приглашения пациентов:\n{doctor_id}")
        return

    # Генерация уникальной ссылки с deep linking
    invite_link = f"https://t.me/{bot_info.username}?start=doctor_{doctor_id}"
    await message.answer(f"Ваша уникальная ссылка для приглашения пациентов:\n{invite_link}")