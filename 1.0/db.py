import aiosqlite

async def init_db():
    async with aiosqlite.connect('bot.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS doctors (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT,
                            surname TEXT,
                            phone TEXT,
                            specialization TEXT,
                            approved BOOLEAN DEFAULT FALSE)''')
        await db.commit()

async def add_doctor(name, surname, phone):
    async with aiosqlite.connect('bot.db') as db:
        await db.execute('INSERT INTO doctors (name, surname, phone) VALUES (?, ?, ?)',
                         (name, surname, phone))
        await db.commit()

async def update_doctor_specialization(doctor_id, specialization):
    async with aiosqlite.connect('bot.db') as db:
        await db.execute('UPDATE doctors SET specialization = ?, approved = TRUE WHERE id = ?',
                         (specialization, doctor_id))
        await db.commit()

async def get_doctor_by_id(doctor_id):
    async with aiosqlite.connect('bot.db') as db:
        async with db.execute('SELECT * FROM doctors WHERE id = ?', (doctor_id,)) as cursor:
            doctor = await cursor.fetchone()
    return doctor

async def get_pending_doctors():
    async with aiosqlite.connect('bot.db') as db:
        async with db.execute('SELECT * FROM doctors WHERE approved = FALSE') as cursor:
            doctors = await cursor.fetchall()
    return doctors
