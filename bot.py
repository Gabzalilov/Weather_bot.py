"основной код бота"
import asyncio
import logging
import sys
import os
from os import getenv
import aiohttp
import asyncpg
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

TOKEN = os.getenv("BOT_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Saint-Petersburg")

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")


WEATHER_URL = 'https://api.openweathermap.org/data/2.5/weather'


if not all([TOKEN, WEATHER_API_KEY, DB_USER, DB_PASSWORD, DB_NAME]):
    raise ValueError("Не заданы переменные окружения BOT_TOKEN или WEATHER_API_KEY")


dp = Dispatcher()

class Database:
    def __init__(self, pool:asyncpg.Pool):
        self.pool = pool
    async def create_table(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS subscribers(
                               user_id BIGINT PRIMARY KEY,
                               city TEXT,
                               created_at TIMESTAMP DEFAULT NOW()
                               )"""
            )
    async def add_subscribers(self, user_id: int, city: str = None):
        if city is None:
            city = DEFAULT_CITY
        async with self.pool.acquire() as conn:
            await conn.execute("""
                               INSERT INTO subscribers(user_id, city)
                               VALUES ($1, $2)
                               ON CONFLICT(user_id) DO UPDATE SET city = $2, created_at = NOW()
                               """, user_id, city)

    async def remove_subscrivers(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM subscribers WHERE user_id = $1", user_id)

    async def get_all_subscribers(self):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT user_id, city FROM subscribers")
            return [(row["user_id"], row["city"]) for row in rows]


@dp.message(CommandStart())
async def command_start_handler(message: Message):
    await message.answer(f"Привет, {html.bold(message.from_user.full_name)}!\n"
                        "Я бот погоды\n"
                        "/subscribe [город] – подписаться на ежедневную рассылку\n"
                        "/unsubscribe – отписаться\n"
                        "/weather город – погода сейчас"
                    )

@dp.message(Command("stop"))
async def stop_bot_handler(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Останавливаю бота")
        await dp.stop_polling()
    else:
        await message.answer("У вас нет прав для выполнения данной комманды")

async def get_weather(city: str) -> str:
    params = {
        'q': city,
        'appid': WEATHER_API_KEY,
        'units': 'metric',
        'lang': 'ru'
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(WEATHER_URL, params=params) as resp:
            if resp.status != 200:
                return 'Отстань'
            
            data = await resp.json()
            temp = data['main']['temp']
            feels_like = data['main']['feels_like']
            description = data['weather'][0]['description']
            city_name = data['name']
            humidity = data['main']['humidity']
            wind_speed = data['wind']['speed']

            return (f"Погода в {city_name}: \n"
                    f"Температура: {temp:.1f} (ощущается как {feels_like:.1f}) \n"
                    f"{description.capitalize()}\n"
                    f"Влажность:{humidity}%\n"
                    f"Ветер: {wind_speed} м/с")

@dp.message(Command('weather'))
async def weather_handler(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer('Напишите город после команда, например, /weather Москва')
        return
    city = args[1]
    weather_text = await get_weather(city)
    await message.answer(weather_text)



@dp.message()
async def echo_handler(message: Message):
    try:
        await message.send_copy(chat_id=message.chat.id)
    except TypeError:
        await message.answer('Nice Try')

async def main():
    session = aiohttp.ClientSession()

    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await dp.start_polling(bot, session=session)
    finally:
        await session.close()
        await bot.session.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
