# client.py
from telethon import TelegramClient
from config_data.config import Config, load_config

config: Config = load_config()

# Используем данные пользователя, а не бота
api_id = config.tg_bot.api_id  # ваш api_id из my.telegram.org
api_hash = config.tg_bot.api_hash  # ваш api_hash
phone_number = config.tg_bot.phone  # нужно добавить номер телефона в конфиг

# Создаем клиент без бот-токена
client = TelegramClient('userbot_session', api_id, api_hash)