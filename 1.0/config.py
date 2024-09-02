from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession

API_TOKEN = '7232213621:AAHVeQRw9zxE1UVfC5qolMVy0gt3qmJkXX8'
ADMIN_ID = '370028521'

session = AiohttpSession(timeout=60)

bot = Bot(token=API_TOKEN, session=session)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)