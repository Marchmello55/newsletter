from utils.general import *
import os
import asyncio
import random
from datetime import datetime
from telethon import events
import logging

from filter.filter import owner_filter
from config_data.client import client
from utils import working_state as ws
from utils.sqlite3_to_exel import create_excel_from_objects

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')



@client.on(events.NewMessage(pattern='/custom_newsletter', func=owner_filter))
async def custom_newsletter(event):
    """Обработчик команды /custom_newsletter с пользовательским сообщением"""
    global newsletter_state

    try:
        if not is_valid_message_event(event):
            return
        logging.info("custom_newsletter")
        if newsletter_state['is_running']:
            await event.reply("❌ Рассылка уже запущена. Используйте /newsletter_status для статуса")
            return

        # Запрашиваем пользовательское сообщение
        await event.reply(
            "📝 Команда пользовательской рассылки\n\n"
            "Отправьте текст сообщения для рассылки:"
        )

        # Ждем текст сообщения от пользователя
        message_response = await wait_for_user_response(event.chat_id, timeout=120)

        if not message_response:
            await event.reply("⏰ Время ожидания текста истекло. Попробуйте снова.")
            return

        message_text = message_response.text.strip()
        if not message_text:
            await event.reply("❌ Текст сообщения не может быть пустым.")
            return

        # Запрашиваем файл с ID пользователей
        await event.reply(
            "✅ Текст получен! Теперь отправьте мне текстовый файл (.txt) с ID пользователей.\n"
            "Каждый ID должен быть на отдельной строке."
        )

        # Ждем файл от пользователя
        file_response = await wait_for_user_response(event.chat_id, timeout=120)

        if not file_response:
            await event.reply("⏰ Время ожидания файла истекло. Попробуйте снова.")
            return

        # Скачиваем файл
        file_path = await download_file(event, file_response)
        if not file_path:
            return

        # Парсим ID пользователей
        user_ids = await parse_user_ids_from_file(file_path)
        if not user_ids:
            await event.reply("❌ Не удалось извлечь ID из файла или файл пуст.")
            try:
                os.remove(file_path)
            except:
                pass
            return
        os.remove(file_path)

        valid_users,  existing_ids = await validate_user_ids(user_ids)

        # Формируем детальное сообщение
        messages = []

        if existing_ids:
            messages.append(f"📋 Уже в БД: {len(existing_ids)}")

        if valid_users:
            messages.append(f"✅ Новых валидных: {len(valid_users)}")

        # Отправляем сводку
        if messages:
            summary = "📊 Результаты проверки:\n" + "\n".join(messages)
            await event.reply(summary)
        else:
            await event.reply("❌ Не найдено ни одного пользователя.")

        # Проверяем есть ли пользователи для рассылки
        if not valid_users:
            if existing_ids:
                await event.reply("ℹ️ Новых пользователей нет, но есть существующие в БД.")
            else:
                await event.reply("❌ Нет пользователей для рассылки.")
            return

        # Используем только валидных пользователей
        user_ids = valid_users
        await rq.add_users(user_ids)

        message_variations = [message_text]

        # Инициализируем состояние рассылки
        newsletter_state.update({
            'is_running': True,
            'total_users': len(user_ids),
            'sent_count': 0,
            'failed_count': 0,
            'current_batch': 0,
            'start_time': datetime.now(),
            'end_time': None,
            'message_type': 'custom',
            'message_variations': message_variations,
            'user_ids': user_ids,
            'current_index': 0
        })

        # ПРОВЕРЯЕМ рабочее время ПОСЛЕ инициализации
        if not await ws.work_state_chack():
            await event.reply(
                f"✅ Пользовательская рассылка запланирована!\n"
                f"• 👥 Пользователей: {len(user_ids)}\n"
                f"• 📝 Сообщений: {len(message_variations)} вариантов\n"
                f"• ⏱️ Перерывы: 15 минут между пачками\n"
                f"• ⚡ Сообщения: 3-5 секунд между отправками\n\n"
                f"Используйте /newsletter_status для отслеживания прогресса"
            )
            await event.reply("⏸️ Сейчас вне рабочего времени (8:00-20:00). Запуск отложен.")
            # Запускаем рассылку в фоне - она сама будет ждать
            asyncio.create_task(run_custom_newsletter(event))
        else:
            await event.reply(
                f"✅ Пользовательская рассылка запущена!\n"
                f"• 👥 Пользователей: {len(user_ids)}\n"
                f"• 📝 Сообщений: {len(message_variations)} вариантов\n"
                f"• ⏱️ Перерывы: 15 минут между пачками\n"
                f"• ⚡ Сообщения: 3-5 секунд между отправками\n\n"
                f"Используйте /newsletter_status для отслеживания прогресса"
            )
            # Запускаем рассылку в фоне
            asyncio.create_task(run_custom_newsletter(event))

        # Удаляем временный файл
        try:
            os.remove(file_path)
        except:
            pass

    except Exception as e:
        logging.error(f"Ошибка в custom_newsletter команде: {e}")
        if is_valid_message_event(event):
            await event.reply(f"❌ Произошла ошибка: {e}")


async def run_custom_newsletter(event):
    """Основная функция пользовательской рассылки с проверкой времени"""
    global newsletter_state

    try:
        # Ожидаем рабочее время перед началом
        if not await ws.work_state_chack():
            await event.reply("⏸️ Вне рабочего периода (8:00-20:00). Ожидаем...")
            await asyncio.sleep(await ws.time_to_work())
            # После ожидания проверяем, не была ли рассылка остановлена
            if not newsletter_state['is_running']:
                await event.reply("✅ Рассылка была остановлена во время ожидания.")
                return
            await event.reply("✅ Рабочее время наступило! Начинаем рассылку.")

        while newsletter_state['is_running'] and newsletter_state['current_index'] < len(newsletter_state['user_ids']):
            # Проверяем рабочее время перед каждой пачкой
            if not await ws.work_state_chack():
                await event.reply("⏸️ Текущее время вне рабочего периода. Ожидаем...")
                await asyncio.sleep(await ws.time_to_work())
                # После ожидания проверяем, не была ли рассылка остановлена
                if not newsletter_state['is_running']:
                    await event.reply("✅ Рассылка была остановлена во время ожидания.")
                    return
                await event.reply("✅ Рабочее время наступило! Продолжаем рассылку.")
                continue

            # Определяем размер текущей пачки (рандомно 3-6 сообщений)
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
            await event.reply(f"📦 Пачка #{newsletter_state['current_batch']}: {batch_size} сообщений")


            batch_results = await send_custom_messages_batch(user_ids_batch, client)

            logging.info(f"✅ Пачка #{newsletter_state['current_batch']} завершена: "
                         f"{batch_results['success']} успешно, {batch_results['failed']} неудачно")
            await event.reply(f"✅ Пачка #{newsletter_state['current_batch']} завершена: "
                              f"{batch_results['success']} успешно, {batch_results['failed']} неудачно")

            # Если еще есть пользователи - делаем перерыв 15 минут
            if newsletter_state['current_index'] < len(newsletter_state['user_ids']):
                users = await rq.get_user_to_report_newsletter()
                text = create_excel_from_objects(users)
                await client.send_file(event.message.chat_id, text)
                os.remove(text)
                if len(batch_results['success'])!=0:
                    logging.info("⏸️ Перерыв 15 минут до следующей пачки...")
                    await event.reply("⏸️ Перерыв 15 минут до следующей пачки...")

                    # Ждем 15 минут, но с проверкой каждую минуту, не остановлена ли рассылка
                    for _ in range(15):
                        await asyncio.sleep(60)
                        if not newsletter_state['is_running']:
                            await event.reply("✅ Рассылка остановлена во время перерыва.")
                            return
                else:
                    logging.info("В пачке не было успешной отправки поэтому отправка пачки начинается сейчас")
                    await event.reply("В пачке не было успешной отправки поэтому отправка пачки начинается сейчас")

    except Exception as e:
        logging.error(f"❌ Ошибка в run_custom_newsletter: {e}")
        await event.reply(f"❌ Ошибка в run_custom_newsletter: {e}")
    finally:
        # Завершение рассылки
        newsletter_state['is_running'] = False
        newsletter_state['end_time'] = datetime.now()
        newsletter_state['is_waiting_for_work_hours'] = False
        logging.info("✅ Пользовательская рассылка завершена")
        status = (
            f"✅ Пользовательская рассылка завершена\n"
            f"• 📨 Отправлено: {newsletter_state['sent_count']}/{newsletter_state['total_users']}\n"
            f"• ❌ Неудачно: {newsletter_state['failed_count']}\n"
            )
        users = await rq.get_user_to_report_newsletter()
        text = create_excel_from_objects(users)
        await client.send_file(event.message.chat_id, text)
        os.remove(text)
        await event.reply(status)



async def wait_for_user_response(chat_id, timeout=60):
    """Ожидает ответа от пользователя"""
    try:
        # Создаем future для ожидания
        response_future = asyncio.Future()
        waiting_for_response[chat_id] = response_future

        # Ждем ответа с таймаутом
        response = await asyncio.wait_for(response_future, timeout=timeout)
        return response

    except asyncio.TimeoutError:
        return None
    finally:
        # Убираем из ожидания
        if chat_id in waiting_for_response:
            del waiting_for_response[chat_id]