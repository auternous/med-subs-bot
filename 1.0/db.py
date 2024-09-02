import aiosqlite
import logging

async def init_db():
    async with aiosqlite.connect('bot.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS doctors (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            fio TEXT,
                            phone TEXT,
                            specialization TEXT,
                            approved BOOLEAN DEFAULT FALSE,
                            user_id INTEGER)''')
        await db.commit()

async def add_doctor(fio, phone, user_id):
    async with aiosqlite.connect('bot.db') as db:
        cursor = await db.execute('INSERT INTO doctors (fio, phone, user_id) VALUES (?, ?, ?)',
                                  (fio, phone, user_id))
        doctor_id = cursor.lastrowid
        await db.commit()
    return doctor_id

async def get_doctor_by_user_id(user_id):
    async with aiosqlite.connect('bot.db') as db:
        async with db.execute('SELECT * FROM doctors WHERE id = ?', (user_id,)) as cursor:
            doctor = await cursor.fetchone()
            return doctor




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

