# chat.py

from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import bot
from db import (
    get_active_dialogues_for_doctor,
    get_active_dialogues_for_patient,
    get_dialogue_participants,
    start_dialogue,
    save_message,
    get_messages,
    get_patient_by_telegram_id,
    get_doctor_by_user_id
)

router = Router()

class ChatStates(StatesGroup):
    in_dialogue = State()  # пользователь находится в конкретном чате

# Кнопка "Мои чаты" есть и у доктора, и у пациента
@router.callback_query(lambda c: c.data == "my_chats")
async def my_chats(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id

    # Определяем, кто это — доктор или пациент
    doctor = await get_doctor_by_user_id(user_id)
    if doctor:
        # Получаем диалоги врача
        dialogues = await get_active_dialogues_for_doctor(doctor['id'])
        if not dialogues:
            await callback_query.message.edit_text("У вас нет активных чатов.")
            return
        keyboard = []
        for d in dialogues:
            dialogue_id = d['dialogue_id']
            patient_name = d['patient_name']
            keyboard.append([
                InlineKeyboardButton(
                    text=f"Чат с {patient_name}",
                    callback_data=f"open_chat_{dialogue_id}"
                )
            ])
        await callback_query.message.edit_text("Ваши активные чаты:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback_query.answer()
        return

    # Если не доктор, то может быть пациент
    patient = await get_patient_by_telegram_id(user_id)
    if patient:
        dialogues = await get_active_dialogues_for_patient(patient['id'])
        if not dialogues:
            await callback_query.message.edit_text("У вас нет активных чатов.")
            return
        keyboard = []
        for d in dialogues:
            dialogue_id = d['dialogue_id']
            doctor_name = d['doctor_name']
            keyboard.append([
                InlineKeyboardButton(
                    text=f"Чат с {doctor_name}",
                    callback_data=f"open_chat_{dialogue_id}"
                )
            ])
        await callback_query.message.edit_text("Ваши активные чаты:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback_query.answer()
        return

    # Если ни пациент, ни доктор
    await callback_query.message.edit_text("Вы не зарегистрированы ни как доктор, ни как пациент.")
    await callback_query.answer()

# Открыть конкретный чат
@router.callback_query(F.data.startswith("open_chat_"))
async def open_chat(callback_query: types.CallbackQuery, state: FSMContext):
    dialogue_id = int(callback_query.data.split("_")[2])

    # Сохраняем в state
    await state.update_data(current_dialogue_id=dialogue_id)
    await state.set_state(ChatStates.in_dialogue)

    # Загружаем историю
    msgs = await get_messages(dialogue_id)
    if not msgs:
        history = "История сообщений пуста."
    else:
        history_lines = []
        user_id = callback_query.from_user.id
        for m in msgs:
            sender_prefix = "Вы" if m['sender_id'] == user_id else "Собеседник"
            history_lines.append(f"{sender_prefix}: {m['text']}")
        history = "\n".join(history_lines)

    text = f"История чата:\n{history}\n\nТеперь вы можете писать сообщения здесь."
    # Добавим кнопку "Назад" (вернуться к списку чатов)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад к списку чатов", callback_data="my_chats")]
    ])
    await callback_query.message.edit_text(text, reply_markup=markup)
    await callback_query.answer()

# Любое текстовое сообщение, когда мы в состоянии in_dialogue, уходит собеседнику
@router.message(ChatStates.in_dialogue)
async def process_chat_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    dialogue_id = data.get("current_dialogue_id")
    if not dialogue_id:
        await message.answer("Ошибка: не найден текущий диалог.")
        return

    # Сохраняем сообщение
    await save_message(dialogue_id, message.from_user.id, message.text)

    # Определяем собеседника
    participants = await get_dialogue_participants(dialogue_id)
    if not participants:
        await message.answer("Ошибка: диалог не найден в базе.")
        return

    if message.from_user.id == participants['patient_telegram_id']:
        counterpart_id = participants['doctor_telegram_id']
    else:
        counterpart_id = participants['patient_telegram_id']

    # Попробуем отправить собеседнику уведомление
    text_for_counterpart = f"Новое сообщение от {message.from_user.full_name}:\n{message.text}"
    # Кнопка "Перейти в чат"
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перейти в чат", callback_data=f"open_chat_{dialogue_id}")]
    ])
    await bot.send_message(chat_id=counterpart_id, text=text_for_counterpart, reply_markup=markup)

    # Сообщаем отправителю, что сообщение ушло
    await message.answer("Сообщение отправлено.")

