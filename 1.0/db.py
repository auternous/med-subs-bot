import aiosqlite
import json
import logging
from aiogram import Bot

async def init_db():
    async with aiosqlite.connect('bot.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS doctors (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            fio TEXT,
                            phone TEXT,
                            specialization TEXT,
                            approved BOOLEAN DEFAULT FALSE,
                            user_id INTEGER,
                            subscribers TEXT)''')

        await db.execute('''CREATE TABLE IF NOT EXISTS patients (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT,
                            telegram_id INTEGER,
                            phone TEXT,
                            doctor_id INTEGER,
                            registration_date TEXT)''')
        
        await db.execute('''CREATE TABLE IF NOT EXISTS dialogues (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            patient_id INTEGER,
                            doctor_id INTEGER,
                            state TEXT DEFAULT 'active')''')  # active/completed

        await db.commit()


async def send_message_to_patient(telegram_id: int, message: str, bot: Bot):
    try:
        await bot.send_message(chat_id=telegram_id, text=message)
    except Exception as e:
        print(f"Failed to send message to patient {telegram_id}: {e}")


async def start_dialogue(patient_id, doctor_id):
    async with aiosqlite.connect('bot.db') as db:
        cursor = await db.execute('INSERT INTO dialogues (patient_id, doctor_id) VALUES (?, ?)',
                                  (patient_id, doctor_id))
        dialogue_id = cursor.lastrowid
        await db.commit()
    return dialogue_id

async def get_active_dialogue(patient_id, doctor_id):
    async with aiosqlite.connect('bot.db') as db:
        async with db.execute('SELECT * FROM dialogues WHERE patient_id = ? AND doctor_id = ? AND state = "active"',
                              (patient_id, doctor_id)) as cursor:
            dialogue = await cursor.fetchone()
    return dialogue

async def complete_dialogue(dialogue_id):
    async with aiosqlite.connect('bot.db') as db:
        await db.execute('UPDATE dialogues SET state = "completed" WHERE id = ?', (dialogue_id,))
        await db.commit()


async def add_subscriber_to_doctor(doctor_telegram_id, subscriber_id):
    async with aiosqlite.connect('bot.db') as db:
        async with db.execute('SELECT subscribers FROM doctors WHERE user_id = ?', (doctor_telegram_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                subscribers = json.loads(row[0])
            else:
                subscribers = []

            # Проверяем, что пациент еще не подписан
            if subscriber_id not in subscribers:
                subscribers.append(subscriber_id)

            await db.execute('UPDATE doctors SET subscribers = ? WHERE user_id = ?',
                             (json.dumps(subscribers), doctor_telegram_id))
            await db.commit()


# Получение подписчиков доктора
async def get_doctor_subscribers(doctor_id):
    async with aiosqlite.connect('bot.db') as db:
        async with db.execute('SELECT subscribers FROM doctors WHERE id = ?', (doctor_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                return json.loads(row[0])
            return []

# Добавление пациента
async def add_patient(name, telegram_id, phone, doctor_id, registration_date):
    async with aiosqlite.connect('bot.db') as db:
        await db.execute('INSERT INTO patients (name, telegram_id, phone, doctor_id, registration_date) VALUES (?, ?, ?, ?, ?)',
                         (name, telegram_id, phone, doctor_id, registration_date))  # doctor_id теперь будет содержать Telegram ID доктора
        await db.commit()


# Обновление данных пациента
async def update_patient_info(telegram_id, name=None, phone=None):
    async with aiosqlite.connect('bot.db') as db:
        updates = []
        params = []
        if name:
            updates.append('name = ?')
            params.append(name)
        if phone:
            updates.append('phone = ?')
            params.append(phone)
        
        params.append(telegram_id)
        query = f'UPDATE patients SET {", ".join(updates)} WHERE telegram_id = ?'
        await db.execute(query, params)
        await db.commit()

# Получение информации о пациенте по его Telegram ID
async def get_patient_by_telegram_id(telegram_id):
    async with aiosqlite.connect('bot.db') as db:
        async with db.execute('SELECT * FROM patients WHERE telegram_id = ?', (telegram_id,)) as cursor:
            return await cursor.fetchone()

# Функция для обновления количества подписчиков у доктора
async def update_doctor_subscribers(doctor_id, increment=True):
    async with aiosqlite.connect('bot.db') as db:
        if increment:
            await db.execute('UPDATE doctors SET subscribers = subscribers + 1 WHERE id = ?', (doctor_id,))
        else:
            await db.execute('UPDATE doctors SET subscribers = subscribers - 1 WHERE id = ?', (doctor_id,))
        await db.commit()

# Функция для получения информации о докторе по ID пользователя
async def get_doctor_by_user_id(user_id):
    async with aiosqlite.connect('bot.db') as db:
        async with db.execute('SELECT * FROM doctors WHERE id = ?', (user_id,)) as cursor:
            doctor = await cursor.fetchone()
            return doctor

async def add_doctor(fio, phone, user_id):
    async with aiosqlite.connect('bot.db') as db:
        cursor = await db.execute('INSERT INTO doctors (fio, phone, user_id) VALUES (?, ?, ?)',
                                  (fio, phone, user_id))
        doctor_id = cursor.lastrowid
        await db.commit()
    return doctor_id

async def update_doctor_specialization(doctor_id, specialization):
    async with aiosqlite.connect('bot.db') as db:
        logging.info(f"Executing SQL: UPDATE doctors SET specialization = '{specialization}', approved = TRUE WHERE id = {doctor_id}")
        await db.execute('UPDATE doctors SET specialization = ?, approved = TRUE WHERE id = ?',
                         (specialization, doctor_id))
        await db.commit()
        logging.info(f"Specialization for doctor ID {doctor_id} updated successfully.")

async def get_pending_doctors():
    async with aiosqlite.connect('bot.db') as db:
        async with db.execute('SELECT * FROM doctors WHERE approved = FALSE') as cursor:
            doctors = await cursor.fetchall()
    return doctors

async def get_doctor_for_link(user_id):
    async with aiosqlite.connect('bot.db') as db:
        async with db.execute('SELECT id FROM doctors WHERE user_id = ?', (user_id,)) as cursor:
            doctor = await cursor.fetchone()
            return doctor[0] if doctor else None

async def get_patient_by_id(telegram_id):
    async with aiosqlite.connect('bot.db') as db:
        async with db.execute('''
            SELECT patients.*, doctors.specialization, doctors.user_id
            FROM patients
            JOIN doctors ON patients.doctor_id = doctors.user_id  -- Связываем по Telegram ID доктора
            WHERE patients.telegram_id = ?
        ''', (telegram_id,)) as cursor:
            patient = await cursor.fetchone()
            return {
                'id': patient[0],
                'name': patient[1],
                'telegram_id': patient[2],
                'phone': patient[3],
                'doctor_id': patient[7],  # Теперь возвращаем telegram_id доктора
                'registration_date': patient[5],
                'specialization': patient[6]  # Специализация доктора
            } if patient else None


async def get_doctors_for_patient(telegram_id):
    async with aiosqlite.connect('bot.db') as db:
        async with db.execute('''
            SELECT doctors.user_id, doctors.fio, doctors.specialization 
            FROM doctors 
            JOIN patients ON doctors.user_id = patients.doctor_id 
            WHERE patients.telegram_id = ?
        ''', (telegram_id,)) as cursor:
            return await cursor.fetchall()


