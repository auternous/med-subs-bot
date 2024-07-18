import aiosqlite


async def init_db():
    async with aiosqlite.connect('clinic.db') as conn:
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            subscription BOOLEAN DEFAULT TRUE,
            subscription_date DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS doctors (
            doctor_id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            specialization TEXT NOT NULL,
            full_name TEXT NOT NULL,
            phone_number TEXT NOT NULL
        )''')
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS dialogues (
            dialogue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            last_message TEXT,
            last_message_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(doctor_id) REFERENCES doctors(doctor_id)
        )''')
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            subscription_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            subscription_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(doctor_id) REFERENCES doctors(doctor_id)
        )''')
        await conn.commit()
