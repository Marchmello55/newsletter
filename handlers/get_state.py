from utils.general import *
from telethon import events
import logging

from filter.filter import owner_filter
from config_data.client import client



@client.on(events.NewMessage(pattern='/newsletter_status', func=owner_filter))
async def newsletter_status_command(event):
    """Обработчик команды статуса рассылки"""
    try:
        if not is_valid_message_event(event):
            return
        logging.info("newsletter_status_command")
        status = get_newsletter_status()
        await event.reply(status)
        users = await rq.get_user_to_report_newsletter
        text =await create_text_file(users)
        await client.send_file(event.message.chat_id, text)
        users = await rq.get_user_to_report_wait_action
        text = await create_text_file(users)
        await client.send_file(event.message.chat_id, text)
    except Exception as e:
        logging.error(f"Ошибка в newsletter_status_command: {e}")
