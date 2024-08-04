from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

API_TOKEN = '6890166616:AAGo4azOVNnAo1_X4RK8nJ7smJGWhTVy41g'
ADMIN_ID = '370028521'

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)