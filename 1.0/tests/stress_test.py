# test_stress.py

import pytest
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Update, Message
from aiogram.fsm.storage.memory import MemoryStorage
from unittest.mock import AsyncMock

# Import your routers
from doctor import router as doctor_router
from patient import router as patient_router
from admin import router as admin_router

# Mock your bot's token
TEST_BOT_TOKEN = "7232213621:AAHVeQRw9zxE1UVfC5qolMVy0gt3qmJkXX8"

@pytest.mark.asyncio
async def test_bot_under_load():
    # Create a mock bot
    bot = Bot(token=TEST_BOT_TOKEN)
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.get_me = AsyncMock(return_value=AsyncMock(username='test_bot'))

    # Create a Dispatcher and include your routers
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(doctor_router)
    dp.include_router(patient_router)
    dp.include_router(admin_router)

    # Number of simulated users
    num_users = 100

    async def simulate_user(user_id):
        # Simulate a /start command from the user
        message = Message(
            message_id=1,
            date=None,
            chat=AsyncMock(id=user_id, type="private"),
            text="/start",
            from_user=AsyncMock(id=user_id, is_bot=False, first_name=f"User{user_id}"),
        )

        update = Update(update_id=user_id, message=message)

        # Process the update
        await dp.feed_update(bot, update)

    # Create tasks for all users
    tasks = [simulate_user(user_id) for user_id in range(1, num_users + 1)]

    # Run all tasks concurrently
    await asyncio.gather(*tasks)

    # Check that bot methods were called expected number of times
    assert bot.send_message.call_count >= num_users
