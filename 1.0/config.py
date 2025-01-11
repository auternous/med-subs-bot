from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession

API_TOKEN = '7339481201:AAGeLezO4I94FrhA2FN3E6K1WLwqIFfZS8k'
ADMIN_ID = '370028521'
DAYS_OF_SUBS = 3

session = AiohttpSession(timeout=60)

bot = Bot(token=API_TOKEN, session=session)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)