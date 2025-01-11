# db.py

import aiosqlite
import uuid
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from config import DAYS_OF_SUBS

@asynccontextmanager
async def get_db_connection():
    async with aiosqlite.connect('bot.db') as conn:
        conn.row_factory = aiosqlite.Row
        yield conn

async def init_db():
    async with get_db_connection() as db:
        # 1. Таблица с докторами
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
        # 2. Таблица с пациентами
        await db.execute('''
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                telegram_id INTEGER UNIQUE,
                registration_date TEXT
            )
        ''')
        # 3. Таблица диалогов (связь пациент-врач)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS dialogues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER,
                doctor_id INTEGER,
                state TEXT DEFAULT 'active'
            )
        ''')
        # 4. Таблица invite-кодов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS invite_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                doctor_id INTEGER,
                used BOOLEAN DEFAULT FALSE
            )
        ''')
        # 5. Таблица для связей patient_doctor_relations (срок действия прикрепления)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS patient_doctor_relations (
                patient_id INTEGER,
                doctor_id INTEGER,
                registration_date TEXT,
                expiry_date TEXT,
                PRIMARY KEY (patient_id, doctor_id)
            )
        ''')
        # 6. **Новая** таблица для хранения истории сообщений
        await db.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dialogue_id INTEGER,
                sender_id INTEGER,
                text TEXT,
                created_at TEXT
            )
        ''')

        await db.commit()

# -------------------------------------------
# Функции по работе с докторами
# -------------------------------------------

async def add_doctor(fio, user_id):
    async with get_db_connection() as db:
        cursor = await db.execute(
            'INSERT INTO doctors (fio, user_id) VALUES (?, ?)',
            (fio, user_id)
        )
        doctor_id = cursor.lastrowid
        await db.commit()
    return doctor_id

async def get_doctor_by_id(doctor_id):
    async with get_db_connection() as db:
        async with db.execute('SELECT * FROM doctors WHERE id = ?', (doctor_id,)) as cursor:
            return await cursor.fetchone()

async def get_doctor_by_user_id(user_id):
    async with get_db_connection() as db:
        async with db.execute('SELECT * FROM doctors WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def update_doctor_specialization(doctor_id, specialization):
    async with get_db_connection() as db:
        await db.execute(
            'UPDATE doctors SET specialization = ?, approved = TRUE WHERE id = ?',
            (specialization, doctor_id)
        )
        await db.commit()

async def get_doctor_for_link(user_id):
    async with get_db_connection() as db:
        async with db.execute('SELECT id FROM doctors WHERE user_id = ?', (user_id,)) as cursor:
            doctor = await cursor.fetchone()
            return doctor['id'] if doctor else None

# -------------------------------------------
# Функции по работе с пациентами
# -------------------------------------------

async def add_patient(name, telegram_id, registration_date):
    async with get_db_connection() as db:
        await db.execute(
            'INSERT INTO patients (name, telegram_id, registration_date) VALUES (?, ?, ?)',
            (name, telegram_id, registration_date)
        )
        await db.commit()

async def get_patient_by_telegram_id(telegram_id):
    async with get_db_connection() as db:
        async with db.execute('SELECT * FROM patients WHERE telegram_id = ?', (telegram_id,)) as cursor:
            return await cursor.fetchone()

async def get_patient_id_by_telegram_id(telegram_id):
    patient = await get_patient_by_telegram_id(telegram_id)
    return patient['id'] if patient else None

# -------------------------------------------
# Invite-коды
# -------------------------------------------

async def create_invite_code(doctor_id):
    code = str(uuid.uuid4())
    async with get_db_connection() as db:
        await db.execute(
            'INSERT INTO invite_codes (code, doctor_id, used) VALUES (?, ?, 0)',
            (code, doctor_id)
        )
        await db.commit()
    return code

async def get_invite_code(code):
    async with get_db_connection() as db:
        async with db.execute('SELECT * FROM invite_codes WHERE code = ?', (code,)) as cursor:
            return await cursor.fetchone()

async def mark_invite_code_as_used(code):
    async with get_db_connection() as db:
        await db.execute('UPDATE invite_codes SET used = 1 WHERE code = ?', (code,))
        await db.commit()

# -------------------------------------------
# Связь пациент-врач (срок прикрепления)
# -------------------------------------------

async def add_patient_doctor_relation(patient_id, doctor_id, registration_date):
    expiry_date = (datetime.strptime(registration_date, "%Y-%m-%d %H:%M:%S") 
                   + timedelta(days=DAYS_OF_SUBS)).strftime("%Y-%m-%d %H:%M:%S")
    async with get_db_connection() as db:
        await db.execute('''
            INSERT OR REPLACE INTO patient_doctor_relations 
            (patient_id, doctor_id, registration_date, expiry_date)
            VALUES (?, ?, ?, ?)
        ''', (patient_id, doctor_id, registration_date, expiry_date))
        await db.commit()

async def remove_expired_doctor_relations():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with get_db_connection() as db:
        # Удаляем/или можно UPDATE state='completed' в таблице dialogues
        # но тут делаем DELETE, как в исходном коде
        await db.execute(
            'DELETE FROM patient_doctor_relations WHERE expiry_date < ?',
            (now_str,)
        )
        await db.commit()

# Получаем всех докторов, прикреплённых к пациенту и не истёкших
async def get_doctors_for_patient(patient_id):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    query = '''
        SELECT d.user_id, d.fio, d.specialization, pdr.expiry_date
        FROM doctors d
        JOIN patient_doctor_relations pdr ON d.id = pdr.doctor_id
        WHERE pdr.patient_id = ? AND pdr.expiry_date > ?
    '''
    async with get_db_connection() as db:
        async with db.execute(query, (patient_id, now_str)) as cursor:
            return await cursor.fetchall()

# -------------------------------------------
# Диалоги (dialogues) + сообщения (messages)
# -------------------------------------------

async def start_dialogue(patient_id, doctor_id):
    """
    Создаём запись в dialogues, если её ещё нет (активной).
    Возвращаем id диалога.
    """
    async with get_db_connection() as db:
        # Проверим, нет ли уже активного диалога
        existing = await db.execute('''
            SELECT id FROM dialogues
            WHERE patient_id=? AND doctor_id=? AND state='active'
        ''', (patient_id, doctor_id))
        row = await existing.fetchone()
        if row:
            return row['id']  # уже есть
        
        cursor = await db.execute(
            'INSERT INTO dialogues (patient_id, doctor_id) VALUES (?, ?)',
            (patient_id, doctor_id)
        )
        new_id = cursor.lastrowid
        await db.commit()
        return new_id

async def get_active_dialogues_for_patient(patient_id):
    """
    Возвращает список всех активных диалогов для пациента
    JOIN с таблицей doctors, чтобы узнать ФИО врача
    """
    query = '''
        SELECT dlg.id as dialogue_id,
               d.fio as doctor_name,
               d.user_id as doctor_telegram_id
        FROM dialogues dlg
        JOIN doctors d ON dlg.doctor_id = d.id
        WHERE dlg.patient_id=? AND dlg.state='active'
    '''
    async with get_db_connection() as db:
        async with db.execute(query, (patient_id,)) as cursor:
            return await cursor.fetchall()

async def get_active_dialogues_for_doctor(doctor_id):
    """
    Возвращает список всех активных диалогов для врача
    JOIN с таблицей patients, чтобы узнать имя пациента
    """
    query = '''
        SELECT dlg.id as dialogue_id,
               p.name as patient_name,
               p.telegram_id as patient_telegram_id
        FROM dialogues dlg
        JOIN patients p ON dlg.patient_id = p.id
        WHERE dlg.doctor_id=? AND dlg.state='active'
    '''
    async with get_db_connection() as db:
        async with db.execute(query, (doctor_id,)) as cursor:
            return await cursor.fetchall()

async def get_dialogue_participants(dialogue_id):
    """
    Возвращает словарь вида:
      {
        'patient_id': ...,
        'patient_telegram_id': ...,
        'doctor_id': ...,
        'doctor_telegram_id': ...
      }
    """
    query = '''
        SELECT dlg.id as dialogue_id, dlg.patient_id, dlg.doctor_id,
               p.telegram_id as patient_telegram_id,
               d.user_id as doctor_telegram_id
        FROM dialogues dlg
        JOIN patients p ON dlg.patient_id = p.id
        JOIN doctors d ON dlg.doctor_id = d.id
        WHERE dlg.id=?
    '''
    async with get_db_connection() as db:
        async with db.execute(query, (dialogue_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                'patient_id': row['patient_id'],
                'patient_telegram_id': row['patient_telegram_id'],
                'doctor_id': row['doctor_id'],
                'doctor_telegram_id': row['doctor_telegram_id']
            }

# -------------------------------------------
# Работа с сообщениями (messages)
# -------------------------------------------

async def save_message(dialogue_id, sender_id, text):
    async with get_db_connection() as db:
        await db.execute('''
            INSERT INTO messages (dialogue_id, sender_id, text, created_at)
            VALUES (?, ?, ?, ?)
        ''', (dialogue_id, sender_id, text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        await db.commit()

async def get_messages(dialogue_id):
    """
    Возвращаем все сообщения диалога (упорядоченные по времени).
    """
    query = '''
        SELECT * FROM messages
        WHERE dialogue_id=?
        ORDER BY id ASC
    '''
    async with get_db_connection() as db:
        async with db.execute(query, (dialogue_id,)) as cursor:
            return await cursor.fetchall()

# -------------------------------------------
# Прочие (статистика для админа)
# -------------------------------------------

async def get_doctor_count():
    async with get_db_connection() as db:
        async with db.execute('SELECT COUNT(*) as count FROM doctors') as cursor:
            row = await cursor.fetchone()
            return row['count'] if row else 0

async def get_patient_count():
    async with get_db_connection() as db:
        async with db.execute('SELECT COUNT(*) as count FROM patients') as cursor:
            row = await cursor.fetchone()
            return row['count'] if row else 0

async def get_doctor_list():
    async with get_db_connection() as db:
        async with db.execute('SELECT fio, specialization FROM doctors') as cursor:
            return await cursor.fetchall()

async def get_all_doctors():
    async with get_db_connection() as db:
        async with db.execute('SELECT fio, specialization, approved FROM doctors') as cursor:
            return await cursor.fetchall()
