from utils.general import *
from telethon import events
import logging

from filter.filter import owner_filter
from config_data.client import client
from utils.sqlite3_to_exel import create_excel_from_objects

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')



@client.on(events.NewMessage(pattern='/stop_newsletter', func=owner_filter))
async def stop_newsletter_command(event):
    """Обработчик команды остановки рассылки"""
    try:
        if not is_valid_message_event(event):
            return
        logging.info("stop_newsletter_command")
        global newsletter_state

        if not newsletter_state['is_running']:
            await event.reply("❌ Рассылка не запущена")
            return

        newsletter_state['is_running'] = False
        newsletter_state['is_waiting_for_work_hours'] = False  # ← Прерываем ожидание

        await event.reply("🛑 Рассылка остановлена. Текущий статус:\n" + get_newsletter_status())
        users = await rq.get_user_to_report_newsletter()
        text = create_excel_from_objects(users)
        await rq.delete_base()
        await client.send_file(event.message.chat_id, text)
        os.remove(text)

    except Exception as e:
        logging.error(f"Ошибка в stop_newsletter_command: {e}")
