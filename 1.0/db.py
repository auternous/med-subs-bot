import sqlite3

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            specialization TEXT,
            is_approved BOOLEAN DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            doctor_id INTEGER,
            referral_code TEXT,
            referral_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user INTEGER,
            to_user INTEGER,
            message TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def add_admin(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO admins (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

# Вызов инициализации базы данных
init_db()

def add_doctor(user_id, specialization):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO doctors (user_id, specialization) VALUES (?, ?)', (user_id, specialization))
    conn.commit()
    conn.close()

def generate_referral_link(doctor_id):
    # Генерация ссылки (упрощенная версия)
    referral_code = f'ref-{doctor_id}'
    return f'https://t.me/YOUR_BOT?start={referral_code}'

def get_doctor_by_referral(referral_code):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM doctors WHERE id = ?', (referral_code.split('-')[1],))
    doctor = cursor.fetchone()
    conn.close()
    return doctor[0] if doctor else None

def add_patient(user_id, doctor_id, referral_code):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO patients (user_id, doctor_id, referral_code) VALUES (?, ?, ?)', (user_id, doctor_id, referral_code))
    conn.commit()
    conn.close()

def approve_doctor(doctor_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE doctors SET is_approved = 1 WHERE id = ?', (doctor_id,))
    conn.commit()
    conn.close()

def add_specialization_to_doctor(doctor_id, specialization):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE doctors SET specialization = ? WHERE id = ?', (specialization, doctor_id))
    conn.commit()
    conn.close()
