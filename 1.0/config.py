from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession

API_TOKEN = '6890166616:AAGo4azOVNnAo1_X4RK8nJ7smJGWhTVy41g'
ADMIN_ID = '370028521'

session = AiohttpSession(timeout=60)

bot = Bot(token=API_TOKEN, session=session)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)