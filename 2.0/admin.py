# admin.py

import logging
from aiogram import Router, types
from aiogram.filters import Command
from config import bot, ADMIN_ID
from db import (
    get_doctor_count, get_patient_count,
    get_all_doctors
)
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

def generate_admin_menu():
    buttons = [
        [InlineKeyboardButton(text="Показать статистику", callback_data="show_stats")],
        [InlineKeyboardButton(text="Список врачей", callback_data="list_doctors")]
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

@router.callback_query(lambda c: c.data == "list_doctors")
async def list_doctors_callback(callback_query: types.CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    doctors = await get_all_doctors()
    if not doctors:
        await callback_query.message.edit_text("Нет зарегистрированных врачей.", reply_markup=generate_admin_menu())
        await callback_query.answer()
        return

    text = "Список зарегистрированных врачей:\n"
    for doc in doctors:
        status = "Одобрен" if doc['approved'] else "Не одобрен"
        spec = doc['specialization'] or "специализация не указана"
        text += f"{doc['fio']} ({spec}) — {status}\n"

    await callback_query.message.edit_text(text, reply_markup=generate_admin_menu())
    await callback_query.answer()
