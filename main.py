import logging
import asyncio
from aiogram import Bot, Dispatcher, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import config
import aiosqlite
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)

API_TOKEN = config.token
admin_ids = config.admin_ids  # список администраторов
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

router = Router()

MAX_NAME_LENGTH = 255
MAX_PHONE_LENGTH = 20

class RegistrationStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone_number = State()

class AdminStates(StatesGroup):
    waiting_for_specialization = State()  # Ввод специализации админом
    waiting_for_subscription_specialist = State()  # Ожидание выбора специалиста для подписки

class DialogueStates(StatesGroup):
    waiting_for_user_message = State()
    waiting_for_specialist_response = State()
    waiting_for_specialist_message = State()
    waiting_for_user_response = State()

async def init_db():
    async with aiosqlite.connect('clinic.db') as conn:
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            registration_date DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS specialists (
            specialist_id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            specialization TEXT NOT NULL,
            full_name TEXT NOT NULL,
            phone_number TEXT NOT NULL
        )''')
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS dialogues (
            dialogue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            specialist_id INTEGER NOT NULL,
            last_message TEXT,
            last_message_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(specialist_id) REFERENCES specialists(specialist_id)
        )''')
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            subscription_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            specialist_id INTEGER NOT NULL,
            subscription_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            expiration_date DATETIME NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(specialist_id) REFERENCES specialists(specialist_id)
        )''')

        specialists = [
            (1234567890, "Кардиолог", "Доктор А", "+1234567890"),
            (1234567891, "Дерматолог", "Доктор Б", "+1234567891"),
            (1234567892, "Невролог", "Доктор В", "+1234567892"),
            (1234567893, "Педиатр", "Доктор Г", "+1234567893"),
            (1234567894, "Терапевт", "Доктор Д", "+1234567894")
        ]
        for specialist in specialists:
            await conn.execute('''
            INSERT OR IGNORE INTO specialists (telegram_id, specialization, full_name, phone_number)
            VALUES (?, ?, ?, ?)
            ''', specialist)

        await conn.commit()

async def add_sample_subscriptions():
    async with aiosqlite.connect('clinic.db') as conn:
        user_id = 1  # Примерный ID пользователя
        specialist_ids = [1, 2]  # Примерные ID специалистов
        for specialist_id in specialist_ids:
            expiration_date = datetime.now() + timedelta(days=30)
            await conn.execute('''
            INSERT OR IGNORE INTO subscriptions (user_id, specialist_id, expiration_date)
            VALUES (?, ?, ?)
            ''', (user_id, specialist_id, expiration_date))
        await conn.commit()

@router.message(Command('start'))
async def send_welcome(message: types.Message):
    buttons = [
        [InlineKeyboardButton(text="Регистрация", callback_data="register_user")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Добро пожаловать! Пожалуйста, зарегистрируйтесь:", reply_markup=markup)

@router.callback_query(lambda c: c.data == 'register_user')
async def register_user(query: types.CallbackQuery, state: FSMContext):
    await state.set_state(RegistrationStates.waiting_for_full_name)
    await query.message.edit_text("Введите ваше ФИО:")

@router.message(RegistrationStates.waiting_for_full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    full_name = message.text
    if len(full_name) > MAX_NAME_LENGTH:
        await message.answer(f"ФИО слишком длинное, максимальная длина {MAX_NAME_LENGTH} символов. Попробуйте еще раз.")
        return
    await state.update_data(full_name=full_name)
    await message.delete()
    await message.answer("Введите ваш номер телефона:")
    await state.set_state(RegistrationStates.waiting_for_phone_number)

@router.message(RegistrationStates.waiting_for_phone_number)
async def process_phone_number(message: types.Message, state: FSMContext):
    phone_number = message.text
    if len(phone_number) > MAX_PHONE_LENGTH:
        await message.answer(f"Номер телефона слишком длинный, максимальная длина {MAX_PHONE_LENGTH} символов. Попробуйте еще раз.")
        return
    await state.update_data(phone_number=phone_number)
    user_data = await state.get_data()
    telegram_id = message.from_user.id

    async with aiosqlite.connect('clinic.db') as conn:
        cursor = await conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
        existing_user = await cursor.fetchone()
        if not existing_user:
            await conn.execute('''
            INSERT INTO users (telegram_id, full_name, phone_number)
            VALUES (?, ?, ?)
            ''', (telegram_id, user_data['full_name'], user_data['phone_number']))
            await conn.commit()
        else:
            await conn.execute('''
            UPDATE users SET full_name = ?, phone_number = ? WHERE telegram_id = ?
            ''', (user_data['full_name'], user_data['phone_number'], telegram_id))
            await conn.commit()

    try:
        await notify_admins_about_registration(message, user_data)
        await message.answer("Ваша заявка была отправлена администратору на рассмотрение.")
    except Exception as e:
        logging.error(f"Error notifying admins: {e}")
        await message.answer("Произошла ошибка при отправке заявки администратору.")
    await state.clear()



async def notify_admins_about_registration(message: types.Message, user_data: dict):
    full_name = user_data['full_name']
    phone_number = user_data['phone_number']
    telegram_id = message.from_user.id

    for admin_id in admin_ids:
        buttons = [
            [InlineKeyboardButton(text="Добавить клиента", callback_data=f"add_client_{telegram_id}")],
            [InlineKeyboardButton(text="Добавить специалиста", callback_data=f"add_specialist_{telegram_id}")]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        try:
            await bot.send_message(admin_id, f"Новая заявка на регистрацию:\nФИО: {full_name}\nТелефон: {phone_number}", reply_markup=markup)
        except Exception as e:
            logging.error(f"Failed to send message to admin {admin_id}: {e}")


@router.callback_query(lambda c: c.data.startswith('add_client_'))
async def add_client(query: types.CallbackQuery):
    telegram_id = int(query.data.split('_')[2])
    async with aiosqlite.connect('clinic.db') as conn:
        cursor = await conn.execute('SELECT full_name, phone_number FROM users WHERE telegram_id = ?', (telegram_id,))
        user_data = await cursor.fetchone()
        if user_data:
            full_name, phone_number = user_data
            await register_user_in_db(telegram_id, full_name, phone_number, is_specialist=False)
            await bot.send_message(telegram_id, "Ваша заявка одобрена! Вы добавлены как клиент.")
            await query.message.edit_text("Пользователь добавлен как клиент.")
            await send_main_menu_to_user(telegram_id)  # Отправка главного меню пользователю

            # Добавляем кнопку для добавления подписок после регистрации пользователя
            buttons = [
                [InlineKeyboardButton(text="Добавить подписку", callback_data=f"add_subscription_{telegram_id}")]
            ]
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)
            for admin_id in admin_ids:
                await bot.send_message(admin_id, "Вы можете добавить подписку для нового пользователя:", reply_markup=markup)


@router.callback_query(lambda c: c.data.startswith('add_specialist_'))
async def add_specialist(query: types.CallbackQuery, state: FSMContext):
    telegram_id = int(query.data.split('_')[2])
    async with aiosqlite.connect('clinic.db') as conn:
        cursor = await conn.execute('SELECT full_name, phone_number FROM users WHERE telegram_id = ?', (telegram_id,))
        user_data = await cursor.fetchone()
        if user_data:
            full_name, phone_number = user_data
            await state.update_data(telegram_id=telegram_id, full_name=full_name, phone_number=phone_number)
            await state.set_state(AdminStates.waiting_for_specialization)
            await query.message.edit_text("Введите специализацию для нового специалиста:")

@router.message(AdminStates.waiting_for_specialization)
async def process_specialization(message: types.Message, state: FSMContext):
    specialization = message.text
    user_data = await state.get_data()
    telegram_id = user_data['telegram_id']
    full_name = user_data['full_name']
    phone_number = user_data['phone_number']
    await register_user_in_db(telegram_id, full_name, phone_number, is_specialist=True, specialization=specialization)
    await bot.send_message(telegram_id, f"Ваша заявка одобрена! Вы добавлены как специалист со специализацией {specialization}.")
    await message.answer("Специалист успешно добавлен.")
    await state.clear()


async def register_user_in_db(telegram_id: int, full_name: str, phone_number: str, is_specialist: bool, specialization: str = None):
    async with aiosqlite.connect('clinic.db') as conn:
        if is_specialist:
            cursor = await conn.execute('SELECT * FROM specialists WHERE telegram_id = ?', (telegram_id,))
            existing_specialist = await cursor.fetchone()
            if not existing_specialist:
                await conn.execute('''
                INSERT INTO specialists (telegram_id, full_name, phone_number, specialization)
                VALUES (?, ?, ?, ?)
                ''', (telegram_id, full_name, phone_number, specialization))
            else:
                await conn.execute('''
                UPDATE specialists SET full_name = ?, phone_number = ?, specialization = ? WHERE telegram_id = ?
                ''', (full_name, phone_number, specialization, telegram_id))
        else:
            cursor = await conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
            existing_user = await cursor.fetchone()
            if not existing_user:
                await conn.execute('''
                INSERT INTO users (telegram_id, full_name, phone_number)
                VALUES (?, ?, ?)
                ''', (telegram_id, full_name, phone_number))
            else:
                await conn.execute('''
                UPDATE users SET full_name = ?, phone_number = ? WHERE telegram_id = ?
                ''', (full_name, phone_number, telegram_id))
        await conn.commit()


@router.callback_query(lambda c: c.data.startswith('add_subscription_'))
async def select_user_for_subscription(query: types.CallbackQuery, state: FSMContext):
    telegram_id = int(query.data.split('_')[2])
    async with aiosqlite.connect('clinic.db') as conn:
        cursor = await conn.execute('SELECT user_id FROM users WHERE telegram_id = ?', (telegram_id,))
        user = await cursor.fetchone()
        if user:
            user_id = user[0]
            await state.update_data(user_id=user_id)
            specialists_cursor = await conn.execute('SELECT specialist_id, specialization FROM specialists')
            specialists = await specialists_cursor.fetchall()
            buttons = [[InlineKeyboardButton(text=s[1], callback_data=f"select_specialist_{s[0]}")] for s in specialists]
            buttons.append([InlineKeyboardButton(text="Отмена", callback_data="cancel_subscription")])
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)
            await query.message.edit_text("Выберите специалиста для подписки:", reply_markup=markup)
            await state.set_state(AdminStates.waiting_for_subscription_specialist)
        else:
            await query.message.edit_text("Пользователь не найден.")

@router.callback_query(lambda c: c.data.startswith('select_specialist_'))
async def add_subscription_to_user(query: types.CallbackQuery, state: FSMContext):
    specialist_id = int(query.data.split('_')[2])
    user_data = await state.get_data()
    user_id = user_data['user_id']
    expiration_date = datetime.now() + timedelta(days=30)
    async with aiosqlite.connect('clinic.db') as conn:
        await conn.execute('''
        INSERT INTO subscriptions (user_id, specialist_id, expiration_date)
        VALUES (?, ?, ?)
        ''', (user_id, specialist_id, expiration_date))
        await conn.commit()
        await query.message.edit_text("Подписка успешно добавлена.")
        cursor = await conn.execute('SELECT telegram_id FROM users WHERE user_id = ?', (user_id,))
        user = await cursor.fetchone()
        if user:
            await bot.send_message(user[0], "Ваша подписка на специалиста была обновлена и будет действовать 1 месяц.")
    await state.clear()

@router.callback_query(lambda c: c.data == 'cancel_subscription')
async def cancel_subscription(query: types.CallbackQuery, state: FSMContext):
    await query.message.edit_text("Операция добавления подписки отменена.")
    await state.clear()

@router.callback_query(lambda c: c.data == 'contact_specialist')
async def contact_specialist(query: types.CallbackQuery):
    telegram_id = query.from_user.id
    async with aiosqlite.connect('clinic.db') as conn:
        user_cursor = await conn.execute('SELECT user_id FROM users WHERE telegram_id = ?', (telegram_id,))
        user = await user_cursor.fetchone()
        if user:
            user_id = user[0]
            subscriptions_cursor = await conn.execute('SELECT sp.specialist_id, sp.specialization FROM subscriptions s JOIN specialists sp ON s.specialist_id = sp.specialist_id WHERE s.user_id = ?', (user_id,))
            subscriptions = await subscriptions_cursor.fetchall()
            if subscriptions:
                buttons = [[InlineKeyboardButton(text=sub[1], callback_data=f"specialist_{sub[0]}")] for sub in subscriptions]
                buttons.append([InlineKeyboardButton(text="Назад в главное меню", callback_data="main_menu")])
                markup = InlineKeyboardMarkup(inline_keyboard=buttons)
                await query.message.edit_text("Выберите специалиста:", reply_markup=markup)
            else:
                await query.message.edit_text("У вас нет доступных подписок. Обратитесь к администратору.")
        else:
            await query.message.edit_text("Вы не зарегистрированы. Пожалуйста, зарегистрируйтесь сначала.")
    await query.answer()

@router.callback_query(lambda c: c.data == 'view_schedule')
async def view_schedule(query: types.CallbackQuery):
    schedule_text = "Часы работы специалистов: Пн-Пт 9:00 - 18:00, Сб-Вс 10:00 - 16:00."
    buttons = [
        [InlineKeyboardButton(text="Назад в главное меню", callback_data="main_menu")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await query.message.edit_text(schedule_text, reply_markup=markup)
    await query.answer()

@router.callback_query(lambda c: c.data == 'view_subscriptions')
async def view_subscriptions(query: types.CallbackQuery):
    telegram_id = query.from_user.id
    async with aiosqlite.connect('clinic.db') as conn:
        user_cursor = await conn.execute('SELECT user_id FROM users WHERE telegram_id = ?', (telegram_id,))
        user = await user_cursor.fetchone()
        if user:
            user_id = user[0]
            subscriptions_cursor = await conn.execute('SELECT sp.full_name, sp.specialization, s.subscription_date, s.expiration_date FROM subscriptions s JOIN specialists sp ON s.specialist_id = sp.specialist_id WHERE s.user_id = ?', (user_id,))
            subscriptions = await subscriptions_cursor.fetchall()
            if subscriptions:
                subscriptions_text = "Ваши текущие подписки:\n"
                for sub in subscriptions:
                    subscription_date = datetime.strptime(sub[2], "%Y-%m-%d %H:%M:%S")
                    expiration_date = datetime.strptime(sub[3], "%Y-%m-%d %H:%M:%S")
                    subscriptions_text += f"{sub[0]} ({sub[1]}) - до {expiration_date.strftime('%Y-%m-%d')}\n"
            else:
                subscriptions_text = "У вас нет текущих подписок."
            buttons = [
                [InlineKeyboardButton(text="Назад в главное меню", callback_data="main_menu")]
            ]
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)
            await query.message.edit_text(subscriptions_text, reply_markup=markup)
        else:
            await query.message.edit_text("Вы не зарегистрированы.")
    await query.answer()


@router.callback_query(lambda c: c.data == 'main_menu')
async def main_menu(query: types.CallbackQuery):
    telegram_id = query.from_user.id
    await query.message.delete()
    await send_main_menu_to_user(telegram_id)
    await query.answer()

async def send_main_menu_to_user(telegram_id: int):
    buttons = [
        [InlineKeyboardButton(text="Обратиться к специалисту", callback_data="contact_specialist")],
        [InlineKeyboardButton(text="Получить информацию о часах работы", callback_data="view_schedule")],
        [InlineKeyboardButton(text="Получить информацию о текущих подписках", callback_data="view_subscriptions")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await bot.send_message(telegram_id, "Главное меню. Пожалуйста, выберите действие:", reply_markup=markup)


@router.callback_query(lambda c: c.data.startswith('specialist_'))
async def handle_specialist_selection(query: types.CallbackQuery, state: FSMContext):
    specialist_id = int(query.data.split('_')[1])
    telegram_id = query.from_user.id

    async with aiosqlite.connect('clinic.db') as conn:
        user_cursor = await conn.execute('SELECT user_id FROM users WHERE telegram_id = ?', (telegram_id,))
        user = await user_cursor.fetchone()

        if user:
            user_id = user[0]
            await state.update_data(user_id=user_id, specialist_id=specialist_id, reply_user_id=telegram_id)
            await state.set_state(DialogueStates.waiting_for_user_message)
            await query.message.edit_text("Введите ваше сообщение для специалиста:")
        else:
            await query.message.edit_text("Пользователь не найден.")
    await query.answer()

@router.message(DialogueStates.waiting_for_user_message)
async def forward_message_to_specialist(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    specialist_id = user_data['specialist_id']
    user_id = user_data['user_id']
    logging.info(f"Forwarding message to specialist: {specialist_id} from user: {user_id}")
    async with aiosqlite.connect('clinic.db') as conn:
        cursor = await conn.execute('SELECT telegram_id FROM specialists WHERE specialist_id = ?', (specialist_id,))
        specialist = await cursor.fetchone()
    if specialist:
        specialist_telegram_id = specialist[0]
        msg_text = f"Сообщение от пользователя {user_id}:\n{message.text}"
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ответить", callback_data=f"reply_to_user_{user_id}")],
            [InlineKeyboardButton(text="Завершить диалог", callback_data="end_dialogue")]
        ])
        await bot.send_message(specialist_telegram_id, msg_text, reply_markup=markup)
        await message.answer("Ваше сообщение было отправлено специалисту.")
        # Сохранение ID пользователя для последующих сообщений
        await state.update_data(last_user_message_id=user_id, reply_specialist_id=specialist_telegram_id)
        # Переключение состояния для ответа специалиста
        await state.set_state(DialogueStates.waiting_for_specialist_response)
    else:
        await message.answer("Произошла ошибка. Специалист не найден.")


@router.callback_query(lambda c: c.data.startswith('reply_to_user_'))
async def reply_to_user(query: types.CallbackQuery, state: FSMContext):
    user_id = int(query.data.split('_')[3])  # Правильный индекс для user_id
    logging.info(f"Specialist is replying to user: {user_id}")
    await state.update_data(reply_user_id=user_id)
    await state.set_state(DialogueStates.waiting_for_specialist_message)
    await query.message.edit_text("Введите ваше сообщение для пользователя:")

@router.message(DialogueStates.waiting_for_specialist_message)
async def forward_message_to_user(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    reply_user_id = user_data['reply_user_id']
    logging.info(f"Forwarding message to user: {reply_user_id} from specialist: {message.from_user.id}")
    async with aiosqlite.connect('clinic.db') as conn:
        cursor = await conn.execute('SELECT telegram_id FROM users WHERE user_id = ?', (reply_user_id,))
        user = await cursor.fetchone()
    if user:
        user_telegram_id = user[0]
        msg_text = f"Сообщение от специалиста {message.from_user.id}:\n{message.text}"
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ответить", callback_data=f"reply_to_specialist_{message.from_user.id}")],
            [InlineKeyboardButton(text="Завершить диалог", callback_data="end_dialogue")]
        ])
        await bot.send_message(user_telegram_id, msg_text, reply_markup=markup)
        await message.answer("Ваше сообщение было отправлено пользователю.")
        # Сохранение ID специалиста для последующих сообщений
        await state.update_data(last_specialist_message_id=message.from_user.id)
        # Переключение состояния для ответа пользователя
        await state.set_state(DialogueStates.waiting_for_user_response)
    else:
        await message.answer("Произошла ошибка. Пользователь не найден.")

@router.callback_query(lambda c: c.data.startswith('reply_to_specialist_'))
async def reply_to_specialist(query: types.CallbackQuery, state: FSMContext):
    # Правильный индекс для specialist_id
    specialist_id = int(query.data.split('_')[3])
    logging.info(f"User is replying to specialist: {specialist_id}")
    await state.update_data(reply_specialist_id=specialist_id)
    await state.set_state(DialogueStates.waiting_for_user_message)
    await query.message.edit_text("Введите ваше сообщение для специалиста:")


from aiogram.exceptions import TelegramBadRequest

@router.callback_query(lambda c: c.data == "end_dialogue")
async def end_dialogue(query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    user_id = query.from_user.id

    # Определяем, кто завершает диалог (пользователь или специалист)
    opposite_user_id = user_data.get("reply_user_id")
    opposite_specialist_id = user_data.get("reply_specialist_id")
    print(opposite_specialist_id)
    print(opposite_user_id)

    try:
        if opposite_user_id:
            await bot.send_message(opposite_specialist_id, "Диалог завершен другой стороной.")
        elif opposite_specialist_id:
            await bot.send_message(opposite_user_id, "Диалог завершен другой стороной.")
    except TelegramBadRequest as e:
        logging.error(f"Failed to send message: {e}")

    logging.info(f"Dialogue ended for user: {user_id}")
    await state.clear()

    # Отправляем сообщение завершившей стороне
    await query.message.edit_text("Диалог завершен.", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Назад в главное меню", callback_data="main_menu")]]
    ))
    await query.answer()




async def main():
    await init_db()
    await add_sample_subscriptions()  # Добавление подписок для примера
    dp.include_router(router)
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
