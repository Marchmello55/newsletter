from sqlalchemy.util import await_only
from utils.general import *
import os
import asyncio
import random
from datetime import datetime
from telethon import events
from telethon.tl.types import InputPeerUser, MessageMediaDocument
from telethon.errors import PeerIdInvalidError, UserIsBlockedError
import logging

from filter.filter import owner_filter
from config_data.client import client
from utils.random_get_message import random_message, TypeMessage
from utils.sqlite3_to_exel import create_excel_from_objects
from utils import working_state as ws


async def reset_state():
    global newsletter_state
    logging.info("reset_state")

    users_to_newsletter = await rq.get_users_to_newsletter()
    if len(users_to_newsletter) == 0:
        logging.info("Нет пользователей для рассылки")
        return

    text = await get_text()
    if text:
        newsletter_state.update({
            'is_running': True,
            'total_users': len(await rq.get_users()),
            'sent_count': len(await rq.get_users_success()),
            'failed_count': len(await rq.get_users_fail()),
            'start_time': datetime.now(),
            'end_time': None,
            'message_type': "custom",
            'user_ids': users_to_newsletter,
            'current_index': 0,
            'current_batch': 0
        })
        asyncio.create_task(reset_custom_newsletter(client))
    else:
        newsletter_state.update({
            'is_running': True,
            'total_users': len(await rq.get_users()),
            'sent_count': len(await rq.get_users_success()),
            'failed_count': len(await rq.get_users_fail()),
            'start_time': datetime.now(),
            'end_time': None,
            'user_ids': users_to_newsletter,
            'current_index': 0,
            'current_batch': 0
        })
        asyncio.create_task(reset_newsletter(client))


async def reset_newsletter(client):
    """Основная функция рассылки с проверкой времени"""
    global newsletter_state

    try:
        # Ожидаем рабочее время перед началом
        if not await ws.work_state_chack():
            await client.send_message("me", "⏸️ Вне рабочего периода (8:00-20:00). Ожидаем...")
            await asyncio.sleep(await ws.time_to_work())
            if not newsletter_state['is_running']:
                await client.send_message("me", "✅ Рассылка была остановлена во время ожидания.")
                return
            await client.send_message("me", "✅ Рабочее время наступило! Начинаем рассылку.")

        while newsletter_state['is_running'] and newsletter_state['current_index'] < len(newsletter_state['user_ids']):
            # Проверяем рабочее время перед каждой пачкой
            if not await ws.work_state_chack():
                await client.send_message("me", "⏸️ Текущее время вне рабочего периода. Ожидаем...")
                await asyncio.sleep(await ws.time_to_work())
                if not newsletter_state['is_running']:
                    await client.send_message("me", "✅ Рассылка была остановлена во время ожидания.")
                    return
                await client.send_message("me", "✅ Рабочее время наступило! Продолжаем рассылку.")
                continue

            # Определяем размер текущей пачки
            batch_size = random.randint(5, 15)
            remaining_users = len(newsletter_state['user_ids']) - newsletter_state['current_index']
            batch_size = min(batch_size, remaining_users)

            # Берем пачку пользователей
            start_idx = newsletter_state['current_index']
            end_idx = start_idx + batch_size
            user_ids_batch = newsletter_state['user_ids'][start_idx:end_idx]

            newsletter_state['current_batch'] += 1

            # Отправляем пачку
            logging.info(f"📦 Пачка #{newsletter_state['current_batch']}: {batch_size} сообщений")
            await client.send_message("me", f"📦 Пачка #{newsletter_state['current_batch']}: {batch_size} сообщений")

            # Получаем пользователей для отчета
            users = await rq.get_user_to_report_newsletter()
            if users:
                try:
                    filename = create_excel_from_objects(users)
                    await client.send_file("me", filename)
                    os.remove(filename)  # Удаляем временный файл
                except Exception as e:
                    logging.error(f"Ошибка при создании Excel: {e}")
                    await client.send_message("me", f"❌ Ошибка создания отчета: {e}")

            # Отправляем сообщения
            batch_results = await send_messages_batch(user_ids_batch, newsletter_state['message_type'], client)

            logging.info(f"✅ Пачка #{newsletter_state['current_batch']} завершена: "
                         f"{batch_results['success']} успешно, {batch_results['failed']} неудачно")
            await client.send_message("me", f"✅ Пачка #{newsletter_state['current_batch']} завершена: "
                                            f"{batch_results['success']} успешно, {batch_results['failed']} неудачно")

            # Обновляем индекс
            newsletter_state['current_index'] = end_idx

            # Если еще есть пользователи - делаем перерыв
            if newsletter_state['current_index'] < len(newsletter_state['user_ids']):
                logging.info("⏸️ Перерыв 15 минут до следующей пачки...")
                await client.send_message("me", "⏸️ Перерыв 15 минут до следующей пачки...")

                # Ждем с проверкой остановки
                for _ in range(15):
                    await asyncio.sleep(60)
                    if not newsletter_state['is_running']:
                        await client.send_message("me", "✅ Рассылка остановлена во время перерыва.")
                        return

    except Exception as e:
        logging.error(f"❌ Ошибка в run_newsletter: {e}")
        await client.send_message("me", f"❌ Ошибка в run_newsletter: {e}")
    finally:
        # Завершение рассылки
        newsletter_state['is_running'] = False
        newsletter_state['end_time'] = datetime.now()
        logging.info("✅ Рассылка завершена")

        # Финальный отчет
        users = await rq.get_user_to_report_newsletter()
        if users:
            try:
                filename = create_excel_from_objects(users)
                await client.send_file("me", filename)
                os.remove(filename)
            except Exception as e:
                logging.error(f"Ошибка при создании финального отчета: {e}")
                await client.send_message("me", f"❌ Ошибка финального отчета: {e}")

        status = (
            f"✅ Рассылка завершена\n"
            f"• 📨 Отправлено: {newsletter_state['sent_count']}/{newsletter_state['total_users']}\n"
            f"• ❌ Неудачно: {newsletter_state['failed_count']}\n"
        )
        await client.send_message("me", status)


async def reset_custom_newsletter(client):
    """Основная функция пользовательской рассылки с проверкой времени"""
    global newsletter_state

    try:
        # Ожидаем рабочее время перед началом
        if not await ws.work_state_chack():
            await client.send_message("me", "⏸️ Вне рабочего периода (8:00-20:00). Ожидаем...")
            await asyncio.sleep(await ws.time_to_work())
            if not newsletter_state['is_running']:
                await client.send_message("me", "✅ Рассылка была остановлена во время ожидания.")
                return
            await client.send_message("me", "✅ Рабочее время наступило! Начинаем рассылку.")

        while newsletter_state['is_running'] and newsletter_state['current_index'] < len(newsletter_state['user_ids']):
            # Проверяем рабочее время
            if not await ws.work_state_chack():
                await client.send_message("me", "⏸️ Текущее время вне рабочего периода. Ожидаем...")
                await asyncio.sleep(await ws.time_to_work())
                if not newsletter_state['is_running']:
                    await client.send_message("me", "✅ Рассылка была остановлена во время ожидания.")
                    return
                await client.send_message("me", "✅ Рабочее время наступило! Продолжаем рассылку.")
                continue

            # Определяем размер пачки
            batch_size = random.randint(3, 6)
            remaining_users = len(newsletter_state['user_ids']) - newsletter_state['current_index']
            batch_size = min(batch_size, remaining_users)

            # Берем пачку пользователей
            start_idx = newsletter_state['current_index']
            end_idx = start_idx + batch_size
            user_ids_batch = newsletter_state['user_ids'][start_idx:end_idx]

            newsletter_state['current_batch'] += 1

            # Отправляем пачку
            logging.info(f"📦 Пачка #{newsletter_state['current_batch']}: {batch_size} сообщений")
            await client.send_message("me", f"📦 Пачка #{newsletter_state['current_batch']}: {batch_size} сообщений")

            # Отправляем кастомные сообщения
            batch_results = await send_custom_messages_batch(user_ids_batch, client)

            logging.info(f"✅ Пачка #{newsletter_state['current_batch']} завершена: "
                         f"{batch_results['success']} успешно, {batch_results['failed']} неудачно")
            await client.send_message("me", f"✅ Пачка #{newsletter_state['current_batch']} завершена: "
                                            f"{batch_results['success']} успешно, {batch_results['failed']} неудачно")

            # Обновляем индекс
            newsletter_state['current_index'] = end_idx

            # Перерыв если есть еще пользователи
            if newsletter_state['current_index'] < len(newsletter_state['user_ids']):
                if len(batch_results['success']) != 0:
                    logging.info("⏸️ Перерыв 15 минут до следующей пачки...")
                    await client.send_message("me", "⏸️ Перерыв 15 минут до следующей пачки...")

                    # Ждем 15 минут, но с проверкой каждую минуту, не остановлена ли рассылка
                    for _ in range(15):
                        await asyncio.sleep(60)
                        if not newsletter_state['is_running']:
                            await client.send_message("me", "✅ Рассылка остановлена во время перерыва.")
                            return
                else:
                    logging.info("В пачке не было успешной отправки поэтому отправка пачки начинается сейчас")
                    await client.send_message("me", "В пачке не было успешной отправки поэтому отправка пачки начинается сейчас")

    except Exception as e:
        logging.error(f"❌ Ошибка в run_custom_newsletter: {e}")
        await client.send_message("me", f"❌ Ошибка в run_custom_newsletter: {e}")

    finally:
        # Завершение рассылки
        newsletter_state['is_running'] = False
        newsletter_state['end_time'] = datetime.now()
        logging.info("✅ Пользовательская рассылка завершена")

        # Финальный отчет
        users = await rq.get_user_to_report_newsletter()
        if users:
            try:
                filename = create_excel_from_objects(users)
                await client.send_file("me", filename)
                os.remove(filename)
            except Exception as e:
                logging.error(f"Ошибка при создании финального отчета: {e}")
                await client.send_message("me", f"❌ Ошибка финального отчета: {e}")

        status = (
            f"✅ Пользовательская рассылка завершена\n"
            f"• 📨 Отправлено: {newsletter_state['sent_count']}/{newsletter_state['total_users']}\n"
            f"• ❌ Неудачно: {newsletter_state['failed_count']}\n"
        )
        await client.send_message("me", status)