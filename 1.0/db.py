# db.py

import aiosqlite
import json
import logging
from aiogram import Bot
import uuid  # For generating unique invite codes
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from config import DAYS_OF_SUBS

# Function to get a database connection as an async context manager
@asynccontextmanager
async def get_db_connection():
    async with aiosqlite.connect('bot.db') as conn:
        conn.row_factory = aiosqlite.Row  # Access columns by name
        yield conn

# Initialize the database
async def init_db():
    async with get_db_connection() as db:
        # Create table for doctors
        await db.execute('''
            CREATE TABLE IF NOT EXISTS doctors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fio TEXT,
                specialization TEXT,
                approved BOOLEAN DEFAULT FALSE,
                user_id INTEGER,
                subscribers TEXT
            )
        ''')

        # Create table for patients
        await db.execute('''
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                telegram_id INTEGER UNIQUE,
                registration_date TEXT
            )
        ''')

        # Create table for dialogues
        await db.execute('''
            CREATE TABLE IF NOT EXISTS dialogues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER,
                doctor_id INTEGER,
                state TEXT DEFAULT 'active'  -- 'active' or 'completed'
            )
        ''')

        # Create table for invite codes
        await db.execute('''
            CREATE TABLE IF NOT EXISTS invite_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                doctor_id INTEGER,
                used BOOLEAN DEFAULT FALSE
            )
        ''')

        # Create table for patient-doctor relations
        await db.execute('''
            CREATE TABLE IF NOT EXISTS patient_doctor_relations (
                patient_id INTEGER,
                doctor_id INTEGER,
                registration_date TEXT,
                expiry_date TEXT,
                PRIMARY KEY (patient_id, doctor_id),
                FOREIGN KEY (patient_id) REFERENCES patients(id),
                FOREIGN KEY (doctor_id) REFERENCES doctors(id)
            )
        ''')

        await db.commit()

# Function to create a unique invite code
async def create_invite_code(doctor_id):
    code = str(uuid.uuid4())
    async with get_db_connection() as db:
        await db.execute(
            'INSERT INTO invite_codes (code, doctor_id, used) VALUES (?, ?, ?)',
            (code, doctor_id, False)
        )
        await db.commit()
    return code

# Function to get an invite code from the database
async def get_invite_code(code):
    async with get_db_connection() as db:
        async with db.execute('SELECT * FROM invite_codes WHERE code = ?', (code,)) as cursor:
            invite_code = await cursor.fetchone()
    return invite_code  # Returns a Row or None if not found

# Function to mark an invite code as used
async def mark_invite_code_as_used(code):
    async with get_db_connection() as db:
        await db.execute('UPDATE invite_codes SET used = TRUE WHERE code = ?', (code,))
        await db.commit()

# Function to add a new doctor to the database
async def add_doctor(fio, user_id):
    async with get_db_connection() as db:
        cursor = await db.execute(
            'INSERT INTO doctors (fio, user_id) VALUES (?, ?)',
            (fio, user_id)
        )
        doctor_id = cursor.lastrowid
        await db.commit()
    return doctor_id

# Function to update doctor's specialization and approve them
async def update_doctor_specialization(doctor_id, specialization):
    async with get_db_connection() as db:
        await db.execute(
            'UPDATE doctors SET specialization = ?, approved = TRUE WHERE id = ?',
            (specialization, doctor_id)
        )
        await db.commit()

# Function to get a doctor by their user_id
async def get_doctor_by_user_id(user_id):
    async with get_db_connection() as db:
        async with db.execute('SELECT * FROM doctors WHERE user_id = ?', (user_id,)) as cursor:
            doctor = await cursor.fetchone()
    return doctor  # Returns a Row or None if not found

# Function to get doctor by their id
async def get_doctor_by_id(doctor_id):
    async with get_db_connection() as db:
        async with db.execute('SELECT * FROM doctors WHERE id = ?', (doctor_id,)) as cursor:
            doctor = await cursor.fetchone()
    return doctor  # Returns a Row or None if not found

# Function to get doctor's ID for link generation
async def get_doctor_for_link(user_id):
    async with get_db_connection() as db:
        async with db.execute('SELECT id FROM doctors WHERE user_id = ?', (user_id,)) as cursor:
            doctor = await cursor.fetchone()
            return doctor['id'] if doctor else None

# Function to add a new patient to the database
async def add_patient(name, telegram_id, registration_date):
    async with get_db_connection() as db:
        await db.execute(
            'INSERT INTO patients (name, telegram_id, registration_date) VALUES (?, ?, ?)',
            (name, telegram_id, registration_date)
        )
        await db.commit()

# Function to get patient by telegram_id
async def get_patient_by_telegram_id(telegram_id):
    async with get_db_connection() as db:
        async with db.execute('SELECT * FROM patients WHERE telegram_id = ?', (telegram_id,)) as cursor:
            patient = await cursor.fetchone()
    return patient  # Returns a Row or None if not found

# Function to get patient id by telegram_id
async def get_patient_id_by_telegram_id(telegram_id):
    patient = await get_patient_by_telegram_id(telegram_id)
    return patient['id'] if patient else None

# Function to add patient-doctor relation
async def add_patient_doctor_relation(patient_id, doctor_id, registration_date):
    async with get_db_connection() as db:
        await db.execute(
            'INSERT OR IGNORE INTO patient_doctor_relations (patient_id, doctor_id, registration_date) VALUES (?, ?, ?)',
            (patient_id, doctor_id, registration_date)
        )
        await db.commit()

# Function to get doctors associated with a patient
async def get_doctors_for_patient(patient_id):
    async with get_db_connection() as db:
        async with db.execute('''
            SELECT doctors.user_id, doctors.fio, doctors.specialization, patient_doctor_relations.expiry_date
            FROM doctors
            JOIN patient_doctor_relations ON doctors.id = patient_doctor_relations.doctor_id
            WHERE patient_doctor_relations.patient_id = ? AND patient_doctor_relations.expiry_date > ?
        ''', (patient_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))) as cursor:
            return await cursor.fetchall()

# Functions related to dialogues
async def start_dialogue(patient_id, doctor_id):
    async with get_db_connection() as db:
        cursor = await db.execute(
            'INSERT INTO dialogues (patient_id, doctor_id) VALUES (?, ?)',
            (patient_id, doctor_id)
        )
        dialogue_id = cursor.lastrowid
        await db.commit()
    return dialogue_id

async def get_active_dialogue(patient_id, doctor_id):
    async with get_db_connection() as db:
        async with db.execute('''
            SELECT * FROM dialogues 
            WHERE patient_id = ? AND doctor_id = ? AND state = "active"
        ''', (patient_id, doctor_id)) as cursor:
            dialogue = await cursor.fetchone()
    return dialogue  # Returns a Row or None if not found

async def complete_dialogue(dialogue_id):
    async with get_db_connection() as db:
        await db.execute(
            'UPDATE dialogues SET state = "completed" WHERE id = ?',
            (dialogue_id,)
        )
        await db.commit()

# Function to get the count of doctors
async def get_doctor_count():
    async with get_db_connection() as db:
        async with db.execute('SELECT COUNT(*) as count FROM doctors') as cursor:
            result = await cursor.fetchone()
            return result['count'] if result else 0

# Function to get the count of patients
async def get_patient_count():
    async with get_db_connection() as db:
        async with db.execute('SELECT COUNT(*) as count FROM patients') as cursor:
            result = await cursor.fetchone()
            return result['count'] if result else 0

# Function to get a list of doctors (optional)
async def get_doctor_list():
    async with get_db_connection() as db:
        async with db.execute('SELECT fio, specialization FROM doctors') as cursor:
            doctors = await cursor.fetchall()
        return doctors  # List of Row objects

async def send_message_to_patient(telegram_id: int, message: str, bot: Bot):
    try:
        await bot.send_message(chat_id=telegram_id, text=message)
    except Exception as e:
        logging.error(f"Failed to send message to patient {telegram_id}: {e}")

async def get_patient_by_telegram_id(telegram_id):
    async with get_db_connection() as db:
        async with db.execute('SELECT * FROM patients WHERE telegram_id = ?', (telegram_id,)) as cursor:
            patient = await cursor.fetchone()
    return patient  # Returns a Row or None if not found


# Функция для добавления новой связи между пациентом и врачом с установкой expiry_date
async def add_patient_doctor_relation(patient_id, doctor_id, registration_date):
    # Добавляем 5 дней к дате регистрации для установки срока истечения
    expiry_date = (datetime.strptime(registration_date, "%Y-%m-%d %H:%M:%S") + timedelta(days=DAYS_OF_SUBS)).strftime("%Y-%m-%d %H:%M:%S")
    async with get_db_connection() as db:
        await db.execute(
            'INSERT OR REPLACE INTO patient_doctor_relations (patient_id, doctor_id, registration_date, expiry_date) VALUES (?, ?, ?, ?)',
            (patient_id, doctor_id, registration_date, expiry_date)
        )
        await db.commit()

# Функция для проверки просроченных связей и их удаления
async def remove_expired_doctor_relations():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with get_db_connection() as db:
        await db.execute(
            'DELETE FROM patient_doctor_relations WHERE expiry_date < ?',
            (current_time,)
        )
        await db.commit()

# Функция для получения оставшегося времени до окончания прикрепления врача
async def get_doctor_expiry_time(patient_id, doctor_id):
    async with get_db_connection() as db:
        async with db.execute(
            'SELECT expiry_date FROM patient_doctor_relations WHERE patient_id = ? AND doctor_id = ?', 
            (patient_id, doctor_id)
        ) as cursor:
            result = await cursor.fetchone()
            return result['expiry_date'] if result else None
        

async def get_all_doctors():
    async with get_db_connection() as db:
        async with db.execute('SELECT fio, specialization, approved FROM doctors') as cursor:
            doctors = await cursor.fetchall()
        return doctors  # Список словарей с данными о врачах

# Function to get all active dialogues for a doctor
async def get_active_dialogues_for_doctor(doctor_id):
    async with get_db_connection() as db:
        async with db.execute('''
            SELECT d.id AS dialogue_id, p.name AS patient_name, p.telegram_id AS patient_telegram_id
            FROM dialogues d
            JOIN patients p ON d.patient_id = p.id
            WHERE d.doctor_id = ? AND d.state = "active"
        ''', (doctor_id,)) as cursor:
            dialogues = await cursor.fetchall()
    return dialogues  # Returns a list of Row objects

# Function to get all active dialogues for a patient
async def get_active_dialogues_for_patient(patient_id):
    async with get_db_connection() as db:
        async with db.execute('''
            SELECT d.id AS dialogue_id, doctors.fio AS doctor_name, doctors.user_id AS doctor_telegram_id
            FROM dialogues d
            JOIN doctors ON d.doctor_id = doctors.id
            WHERE d.patient_id = ? AND d.state = "active"
        ''', (patient_id,)) as cursor:
            dialogues = await cursor.fetchall()
    return dialogues  # Returns a list of Row objects

# Function to mark a dialogue as active or completed
async def update_dialogue_state(dialogue_id, new_state):
    async with get_db_connection() as db:
        await db.execute(
            'UPDATE dialogues SET state = ? WHERE id = ?',
            (new_state, dialogue_id)
        )
        await db.commit()

# Function to check if a specific dialogue exists between a doctor and patient
async def check_dialogue_exists(patient_id, doctor_id):
    async with get_db_connection() as db:
        async with db.execute('''
            SELECT * FROM dialogues
            WHERE patient_id = ? AND doctor_id = ? AND state = "active"
        ''', (patient_id, doctor_id)) as cursor:
            dialogue = await cursor.fetchone()
    return dialogue  # Returns a Row object or None
