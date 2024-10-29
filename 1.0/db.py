import aiosqlite
import json
import logging
from aiogram import Bot
import uuid  # For generating unique invite codes
from contextlib import asynccontextmanager

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
                doctor_id INTEGER,
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

# Function to get doctor's ID for link generation
async def get_doctor_for_link(user_id):
    async with get_db_connection() as db:
        async with db.execute('SELECT id FROM doctors WHERE user_id = ?', (user_id,)) as cursor:
            doctor = await cursor.fetchone()
            return doctor['id'] if doctor else None

# Function to add a new patient to the database
async def add_patient(name, telegram_id, doctor_id, registration_date):
    async with get_db_connection() as db:
        await db.execute(
            'INSERT INTO patients (name, telegram_id, doctor_id, registration_date) VALUES (?, ?, ?, ?)',
            (name, telegram_id, doctor_id, registration_date)
        )
        await db.commit()

# Function to add a subscriber to a doctor
async def add_subscriber_to_doctor(doctor_telegram_id, subscriber_id):
    async with get_db_connection() as db:
        async with db.execute('SELECT subscribers FROM doctors WHERE user_id = ?', (doctor_telegram_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row['subscribers']:
                subscribers = json.loads(row['subscribers'])
            else:
                subscribers = []

            # Check if subscriber is already in the list
            if subscriber_id not in subscribers:
                subscribers.append(subscriber_id)

            await db.execute(
                'UPDATE doctors SET subscribers = ? WHERE user_id = ?',
                (json.dumps(subscribers), doctor_telegram_id)
            )
            await db.commit()

# Function to get patient by telegram_id
async def get_patient_by_id(telegram_id):
    async with get_db_connection() as db:
        async with db.execute('''
            SELECT patients.*, doctors.specialization, doctors.user_id
            FROM patients
            JOIN doctors ON patients.doctor_id = doctors.user_id
            WHERE patients.telegram_id = ?
        ''', (telegram_id,)) as cursor:
            patient = await cursor.fetchone()
            if patient:
                return {
                    'id': patient['id'],
                    'name': patient['name'],
                    'telegram_id': patient['telegram_id'],
                    'doctor_id': patient['doctor_id'],
                    'registration_date': patient['registration_date'],
                    'specialization': patient['specialization'],  # from doctors table
                    'doctor_user_id': patient['user_id']  # from doctors table
                }
            else:
                return None

# Function to get doctors associated with a patient
async def get_doctors_for_patient(telegram_id):
    async with get_db_connection() as db:
        async with db.execute('''
            SELECT doctors.user_id, doctors.fio, doctors.specialization 
            FROM doctors 
            JOIN patients ON doctors.user_id = patients.doctor_id 
            WHERE patients.telegram_id = ?
        ''', (telegram_id,)) as cursor:
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

# Function to send a message to a patient (used in other parts of the code)
async def send_message_to_patient(telegram_id: int, message: str, bot: Bot):
    try:
        await bot.send_message(chat_id=telegram_id, text=message)
    except Exception as e:
        logging.error(f"Failed to send message to patient {telegram_id}: {e}")

# Function to get pending doctors (if needed)
async def get_pending_doctors():
    async with get_db_connection() as db:
        async with db.execute('SELECT * FROM doctors WHERE approved = FALSE') as cursor:
            doctors = await cursor.fetchall()
    return doctors

# Additional functions can be added below as needed...
async def get_doctor_by_id(doctor_id):
    async with get_db_connection() as db:
        async with db.execute('SELECT * FROM doctors WHERE id = ?', (doctor_id,)) as cursor:
            doctor = await cursor.fetchone()
    return doctor  # Returns a Row or None if not found

async def get_patient_by_telegram_id(telegram_id):
    async with get_db_connection() as db:
        async with db.execute('SELECT * FROM patients WHERE telegram_id = ?', (telegram_id,)) as cursor:
            patient = await cursor.fetchone()
    return patient  # Returns a Row or None if not found

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