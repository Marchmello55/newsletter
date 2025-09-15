from config_data.client import client
import logging
from config_data.config import Config, load_config


# Кэшируем всю информацию о владельце
owner_info = None
config: Config = load_config()

trusted_users = set()


async def get_owner_id():
    """Получаем ID владельца"""
    global owner_info
    if owner_info is None:
        me = await client.get_me()
        owner_id = me.id
        # Добавляем владельца в доверенных пользователей
        trusted_users.add(owner_id)
        trusted_users.add(config.tg_bot.admin_id)
    return owner_info

async def is_owner(event):
    """Проверка, что отправитель - владелец или доверенный пользователь"""
    await get_owner_id()  # Убедимся, что owner_id инициализирован
    return event.sender_id in trusted_users

async def owner_filter(event):
    """Фильтр для владельца и доверенных пользователей"""
    await get_owner_id()  # Убедимся, что owner_id инициализирован
    is_privileged = event.sender_id in trusted_users

    if not is_privileged and str(event.message.text).startswith("/"):
        logging.info(f"🚫 Попытка доступа от {event.sender_id}")

    return is_privileged


def is_trusted_user(user_id: int):
    """Проверить, является ли пользователь доверенным"""
    return user_id in trusted_users