# admin.py

import logging
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from config import bot, ADMIN_ID
from db import get_doctor_count, get_patient_count, get_doctor_list, get_all_doctors  
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

router = Router()

def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

def generate_admin_menu():
    buttons = [
        [InlineKeyboardButton(text="Показать статистику", callback_data="show_stats")],
        [InlineKeyboardButton(text="Список врачей", callback_data="list_doctors")]  # Кнопка для списка врачей
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для доступа к панели администратора.")
        return
    await message.answer("Панель администратора:", reply_markup=generate_admin_menu())

@router.callback_query(lambda c: c.data == "show_stats")
async def show_stats_callback(callback_query: types.CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    doctor_count = await get_doctor_count()
    patient_count = await get_patient_count()

    stats_message = (
        f"Статистика пользователей:\n"
        f"Количество зарегистрированных врачей: {doctor_count}\n"
        f"Количество зарегистрированных пациентов: {patient_count}"
    )

    await callback_query.message.edit_text(stats_message, reply_markup=generate_admin_menu())
    await callback_query.answer()

# Дополнительная функция для списка врачей (опционально)
@router.callback_query(lambda c: c.data == "list_doctors")
async def list_doctors_callback(callback_query: types.CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    doctors = await get_doctor_list()

    if not doctors:
        await callback_query.message.edit_text("Нет зарегистрированных врачей.", reply_markup=generate_admin_menu())
        await callback_query.answer()
        return

    doctors_info = "Список зарегистрированных врачей:\n"
    for doctor in doctors:
        doctors_info += f"Имя: {doctor['fio']}, Специализация: {doctor['specialization']}\n"

    await callback_query.message.edit_text(doctors_info, reply_markup=generate_admin_menu())
    await callback_query.answer()

@router.callback_query(lambda c: c.data == "list_doctors")
async def list_doctors_callback(callback_query: types.CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    doctors = await get_all_doctors()  # Получаем список всех врачей из базы данных

    if not doctors:
        await callback_query.message.edit_text("Нет зарегистрированных врачей.", reply_markup=generate_admin_menu())
        await callback_query.answer()
        return

    # Формируем список врачей для отображения
    doctors_info = "Список зарегистрированных врачей:\n"
    for doctor in doctors:
        status = "Одобрен" if doctor['approved'] else "Не одобрен"
        specialization = doctor['specialization'] or "Специализация не указана"
        doctors_info += f"Имя: {doctor['fio']}, Специализация: {specialization}, Статус: {status}\n"

    await callback_query.message.edit_text(doctors_info, reply_markup=generate_admin_menu())
    await callback_query.answer()