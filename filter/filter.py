from config_data.client import client
import logging


# Кэшируем всю информацию о владельце
owner_info = None


async def get_owner_info():
    """Получаем полную информацию о владельце"""
    global owner_info
    if owner_info is None:
        me = await client.get_me()
        owner_info = {
            'id': me.id,
            'username': me.username,
            'first_name': me.first_name,
            'last_name': me.last_name,
            'phone': me.phone
        }
    return owner_info


async def is_owner(event):
    """Проверка, что отправитель - владелец"""
    owner = await get_owner_info()
    return event.sender_id == owner['id']


async def owner_filter(event):
    """Фильтр с подробным логированием"""
    owner = await get_owner_info()
    is_owner = event.sender_id == owner['id']

    if not is_owner:
        logging.info(f"🚫 Попытка доступа от {event.sender_id} (не владелец)")

    return is_owner