import os
import asyncio
import random
from datetime import datetime
from telethon import events
from telethon.tl.functions.channels import GetParticipantsRequest, JoinChannelRequest, GetFullChannelRequest
from telethon.tl.types import ChannelParticipantsSearch, InputPeerUser, MessageMediaDocument
from telethon.errors import ChannelPrivateError, UsernameNotOccupiedError, ChannelInvalidError, FloodWaitError
from telethon.errors import PeerIdInvalidError, UserIsBlockedError
import re
import logging


from config_data.client import client
from utils.random_get_message import random_message, TypeMessage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Глобальные переменные для отслеживания состояния рассылки
newsletter_state = {
    'is_running': False,
    'total_users': 0,
    'sent_count': 0,
    'failed_count': 0,
    'current_batch': 0,
    'start_time': None,
    'end_time': None,
    'message_type': '',
    'user_ids': [],
    'current_index': 0
}

# Словарь для ожидаемых ответов от пользователей
waiting_for_response = {}


def is_valid_message_event(event):
    """Проверяет, что это валидное событие сообщения"""
    return (hasattr(event, 'message') and
            hasattr(event.message, 'text') and
            isinstance(event, events.NewMessage.Event))


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


@client.on(events.NewMessage())
async def handle_user_responses(event):
    """Обработчик ответов пользователей"""
    if not is_valid_message_event(event):
        return

    chat_id = event.chat_id
    if chat_id in waiting_for_response:
        # Завершаем future с ответом пользователя
        waiting_for_response[chat_id].set_result(event.message)


async def send_message_to_user(user_id, message_text, client):
    """Отправляет сообщение пользователю по ID"""
    try:
        user_entity = InputPeerUser(user_id=int(user_id), access_hash=0)
        await client.send_message(entity=user_entity, message=message_text)
        logging.info(f"✅ Сообщение отправлено пользователю {user_id}")
        return True
    except (PeerIdInvalidError, UserIsBlockedError, ValueError, Exception) as e:
        logging.error(f"❌ Ошибка при отправке пользователю {user_id}: {e}")
        return False


async def send_messages_batch(user_ids_batch, message_type, client):
    """Отправляет пачку сообщений с рандомными задержками"""
    batch_results = {'success': 0, 'failed': 0}

    for user_id in user_ids_batch:
        try:
            # Получаем рандомное сообщение
            message_text = await random_message(message_type)

            # Рандомная задержка между сообщениями 3-5 секунд
            delay = random.uniform(3, 5)
            await asyncio.sleep(delay)

            success = await send_message_to_user(user_id, message_text, client)

            if success:
                batch_results['success'] += 1
                newsletter_state['sent_count'] += 1
            else:
                batch_results['failed'] += 1
                newsletter_state['failed_count'] += 1

            newsletter_state['current_index'] += 1

        except Exception as e:
            logging.error(f"❌ Ошибка при отправке пользователю {user_id}: {e}")
            batch_results['failed'] += 1
            newsletter_state['failed_count'] += 1
            newsletter_state['current_index'] += 1

    return batch_results


async def run_newsletter():
    """Основная функция рассылки с циклами и перерывами"""
    global newsletter_state

    while newsletter_state['is_running'] and newsletter_state['current_index'] < len(newsletter_state['user_ids']):
        try:
            # Определяем размер текущей пачки (рандомно 5-15 сообщений)
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
            batch_results = await send_messages_batch(user_ids_batch, newsletter_state['message_type'], client)

            logging.info(f"✅ Пачка #{newsletter_state['current_batch']} завершена: "
                         f"{batch_results['success']} успешно, {batch_results['failed']} неудачно")

            # Если еще есть пользователи - делаем перерыв 15 минут
            if newsletter_state['current_index'] < len(newsletter_state['user_ids']):
                logging.info("⏸️ Перерыв 15 минут до следующей пачки...")
                await asyncio.sleep(15 * 60)

        except Exception as e:
            logging.error(f"❌ Ошибка в run_newsletter: {e}")
            await asyncio.sleep(60)

    # Завершение рассылки
    newsletter_state['is_running'] = False
    newsletter_state['end_time'] = datetime.now()
    logging.info("✅ Рассылка завершена")


def get_newsletter_status():
    """Возвращает статус текущей рассылки"""
    if not newsletter_state['is_running']:
        return "📭 Рассылка не запущена"

    elapsed = datetime.now() - newsletter_state['start_time']
    progress = (newsletter_state['current_index'] / newsletter_state['total_users'] * 100) if newsletter_state[
                                                                                                  'total_users'] > 0 else 0

    # Определяем тип рассылки
    if newsletter_state['message_type'] == 'custom':
        message_info = f"Пользовательская ({len(newsletter_state.get('message_variations', []))} вариантов)"
    else:
        message_info = "Автоматическая (вопросы)"

    status = (
        f"📊 Статус рассылки:\n"
        f"• 🏃‍♂️ Статус: {'Запущена' if newsletter_state['is_running'] else 'Завершена'}\n"
        f"• 📨 Отправлено: {newsletter_state['sent_count']}/{newsletter_state['total_users']}\n"
        f"• ❌ Неудачно: {newsletter_state['failed_count']}\n"
        f"• 📦 Пачек отправлено: {newsletter_state['current_batch']}\n"
        f"• 📝 Тип: {message_info}\n"
        f"• 📈 Прогресс: {progress:.1f}%\n"
        f"• ⏱️ Время работы: {elapsed}\n"
        f"• 🎯 Текущий индекс: {newsletter_state['current_index']}"
    )

    return status


@client.on(events.NewMessage(pattern='/newsletter_status'))
async def newsletter_status_command(event):
    """Обработчик команды статуса рассылки"""
    try:
        if not is_valid_message_event(event):
            return

        status = get_newsletter_status()
        await event.reply(status)
    except Exception as e:
        logging.error(f"Ошибка в newsletter_status_command: {e}")


@client.on(events.NewMessage(pattern='/stop_newsletter'))
async def stop_newsletter_command(event):
    """Обработчик команды остановки рассылки"""
    try:
        if not is_valid_message_event(event):
            return

        global newsletter_state

        if not newsletter_state['is_running']:
            await event.reply("❌ Рассылка не запущена")
            return

        newsletter_state['is_running'] = False
        await event.reply("🛑 Рассылка остановлена. Текущий статус:\n" + get_newsletter_status())

    except Exception as e:
        logging.error(f"Ошибка в stop_newsletter_command: {e}")


async def download_file(event, message):
    """Скачивает файл из сообщения"""
    try:
        if message.media and isinstance(message.media, MessageMediaDocument):
            os.makedirs("downloads", exist_ok=True)
            file_path = await client.download_media(message.media, "downloads/")
            logging.info(f"Файл скачан: {file_path}")
            return file_path
        else:
            await event.reply("❌ В сообщении нет файла для скачивания")
            return None
    except Exception as e:
        logging.error(f"Ошибка при скачивании файла: {e}")
        await event.reply(f"❌ Ошибка при скачивании файла: {e}")
        return None


async def parse_user_ids_from_file(file_path: str) -> list:
    """Парсит ID пользователей из файла"""
    user_ids = []

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                user_id = line.split(" ")
                for i in user_id:
                    if i and i.isdigit():
                        user_ids.append(i)

        logging.info(f"Parsed {len(user_ids)} user IDs from file")
        return user_ids

    except Exception as e:
        logging.error(f"Error parsing user IDs: {e}")
        return []


@client.on(events.NewMessage(pattern='/start_newsletter'))
async def newsletter(event):
    """Обработчик команды /newsletter"""
    global newsletter_state

    try:
        if not is_valid_message_event(event):
            return

        if newsletter_state['is_running']:
            await event.reply("❌ Рассылка уже запущена. Используйте /newsletter_status для статуса")
            return

        message_type = TypeMessage.question
        type_name = "вопросы"  # Добавлено определение переменной type_name

        # Запрашиваем файл
        await event.reply(
            "Теперь отправьте мне текстовый файл (.txt) с ID пользователей.\n"
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

        # Инициализируем состояние рассылки
        newsletter_state.update({
            'is_running': True,
            'total_users': len(user_ids),
            'sent_count': 0,
            'failed_count': 0,
            'current_batch': 0,
            'start_time': datetime.now(),
            'end_time': None,
            'message_type': message_type,
            'user_ids': user_ids,
            'current_index': 0
        })

        await event.reply(
            f"✅ Рассылка запущена!\n"
            f"• 👥 Пользователей: {len(user_ids)}\n"
            f"• 📝 Тип сообщений: {type_name}\n"
            f"• ⏱️ Перерывы: 15 минут между пачками\n"
            f"• ⚡ Сообщения: 3-5 секунд между отправками\n\n"
            f"Используйте /newsletter_status для отслеживания прогресса"
        )

        # Запускаем рассылку в фоне
        asyncio.create_task(run_newsletter())

        # Удаляем временный файл
        try:
            os.remove(file_path)
        except:
            pass

    except Exception as e:
        logging.error(f"Ошибка в newsletter команде: {e}")
        if is_valid_message_event(event):
            await event.reply(f"❌ Произошла ошибка: {e}")


@client.on(events.NewMessage(pattern='/custom_newsletter'))
async def custom_newsletter(event):
    """Обработчик команды /custom_newsletter с пользовательским сообщением"""
    global newsletter_state

    try:
        if not is_valid_message_event(event):
            return

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

        # Генерируем случайное количество сообщений (3-6)
        num_messages = random.randint(3, 6)
        message_variations = [message_text]

        # Добавляем небольшие вариации к сообщениям


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

        await event.reply(
            f"✅ Пользовательская рассылка запущена!\n"
            f"• 👥 Пользователей: {len(user_ids)}\n"
            f"• 📝 Сообщений: {num_messages} вариантов\n"
            f"• ⏱️ Перерывы: 15 минут между пачками\n"
            f"• ⚡ Сообщения: 3-5 секунд между отправками\n\n"
            f"Используйте /newsletter_status для отслеживания прогресса"
        )

        # Запускаем рассылку в фоне
        asyncio.create_task(run_custom_newsletter())

        # Удаляем временный файл
        try:
            os.remove(file_path)
        except:
            pass

    except Exception as e:
        logging.error(f"Ошибка в custom_newsletter команде: {e}")
        if is_valid_message_event(event):
            await event.reply(f"❌ Произошла ошибка: {e}")


async def run_custom_newsletter():
    """Основная функция пользовательской рассылки"""
    global newsletter_state

    while newsletter_state['is_running'] and newsletter_state['current_index'] < len(newsletter_state['user_ids']):
        try:
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
            batch_results = await send_custom_messages_batch(user_ids_batch, client)

            logging.info(f"✅ Пачка #{newsletter_state['current_batch']} завершена: "
                         f"{batch_results['success']} успешно, {batch_results['failed']} неудачно")

            # Если еще есть пользователи - делаем перерыв 15 минут
            if newsletter_state['current_index'] < len(newsletter_state['user_ids']):
                logging.info("⏸️ Перерыв 15 минут до следующей пачки...")
                await asyncio.sleep(15 * 60)

        except Exception as e:
            logging.error(f"❌ Ошибка в run_custom_newsletter: {e}")
            await asyncio.sleep(60)

    # Завершение рассылки
    newsletter_state['is_running'] = False
    newsletter_state['end_time'] = datetime.now()
    logging.info("✅ Пользовательская рассылка завершена")


async def send_custom_messages_batch(user_ids_batch, client):
    """Отправляет пачку пользовательских сообщений"""
    batch_results = {'success': 0, 'failed': 0}

    for user_id in user_ids_batch:
        try:
            # Выбираем случайное сообщение из вариаций
            message_text = random.choice(newsletter_state['message_variations'])

            # Рандомная задержка между сообщениями 3-5 секунд
            delay = random.uniform(3, 5)
            await asyncio.sleep(delay)

            success = await send_message_to_user(user_id, message_text, client)

            if success:
                batch_results['success'] += 1
                newsletter_state['sent_count'] += 1
            else:
                batch_results['failed'] += 1
                newsletter_state['failed_count'] += 1

            newsletter_state['current_index'] += 1

        except Exception as e:
            logging.error(f"❌ Ошибка при отправке пользователю {user_id}: {e}")
            batch_results['failed'] += 1
            newsletter_state['failed_count'] += 1
            newsletter_state['current_index'] += 1

    return batch_results


def extract_channel_username(link):
    """Извлекает username канала из ссылки"""
    patterns = [
        r't\.me/([a-zA-Z0-9_]+)',
        r'https?://t\.me/([a-zA-Z0-9_]+)',
        r'@([a-zA-Z0-9_]+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, link)
        if match:
            return match.group(1)

    if link.startswith('@'):
        return link[1:]
    return link


async def join_channel(channel_username):
    """Пытается присоединиться к каналу"""
    try:
        channel = await client.get_entity(channel_username)
        await client(JoinChannelRequest(channel))
        return True, f"✅ Успешно присоединились к каналу: {channel_username}"
    except ChannelPrivateError:
        return False, f"❌ Канал {channel_username} приватный. Необходимо ручное присоединение."
    except (UsernameNotOccupiedError, ChannelInvalidError):
        return False, f"❌ Канал {channel_username} не существует или недоступен."
    except FloodWaitError as e:
        return False, f"❌ Необходимо подождать {e.seconds} секунд перед повторной попыткой."
    except Exception as e:
        return False, f"❌ Ошибка при присоединении к каналу: {e}"


async def get_channel_users(channel_username, chat_id):
    """Получает список пользователей канала"""
    try:
        # Сначала получаем полную информацию о канале
        channel = await client.get_entity(channel_username)
        full_channel = await client(GetFullChannelRequest(channel))

        # Проверяем права доступа
        if not hasattr(full_channel, 'full_chat') or not hasattr(full_channel.full_chat, 'participants_count'):
            await client.send_message(chat_id, "❌ Нет прав для просмотра участников канала.")
            return None, "Недостаточно прав"

        # Получаем список участников
        participants = await client(GetParticipantsRequest(
            channel=channel,
            filter=ChannelParticipantsSearch(''),
            offset=0,
            limit=10000,
            hash=0
        ))

        return participants.users, None

    except ChannelPrivateError:
        return None, "🔒 Нет доступа к каналу."
    except Exception as e:
        return None, f"❌ Ошибка при получении пользователей: {e}"


async def save_users_to_file(users, filename):
    """Сохраняет ID пользователей в файл"""
    with open(filename, 'w', encoding='utf-8') as file:
        for user in users:
            if user.username:
                file.write(f"{user.id} - @{user.username}\n")
            else:
                file.write(f"{user.id}\n")


async def process_channel(link, chat_id):
    """Основная функция обработки канала"""
    try:
        # Извлекаем username из ссылки
        channel_username = extract_channel_username(link)
        await client.send_message(chat_id, f"🔍 Обрабатываем канал: {channel_username}")

        # Пытаемся получить пользователей
        users, error = await get_channel_users(channel_username, chat_id)

        if users is not None:
            # Если доступ есть сразу
            await client.send_message(chat_id, f"✅ Найдено {len(users)} пользователей")
            filename = f'{channel_username}_users.txt'
            await save_users_to_file(users, filename)

            # Отправляем файл пользователю
            await client.send_file(chat_id, filename, caption=f"📊 Данные пользователей канала {channel_username}")

            # Удаляем временный файл
            os.remove(filename)
            return True, "✅ Операция завершена успешно!"
        else:
            # Если доступа нет, пытаемся присоединиться
            await client.send_message(chat_id, "🔄 Пытаемся присоединиться к каналу...")
            joined, join_message = await join_channel(channel_username)
            await client.send_message(chat_id, join_message)

            if joined:
                # Ждем больше времени после присоединения
                await asyncio.sleep(10)  # Увеличиваем время ожидания

                # Пытаемся получить пользователей снова
                users, error = await get_channel_users(channel_username, chat_id)

                if users is not None:
                    await client.send_message(chat_id, f"✅ После присоединения найдено {len(users)} пользователей")
                    filename = f'{channel_username}_users.txt'
                    await save_users_to_file(users, filename)

                    # Отправляем файл пользователю
                    await client.send_file(chat_id, filename,
                                           caption=f"📊 Данные пользователей канала {channel_username}")

                    # Удаляем временный файл
                    os.remove(filename)
                    return True, "✅ Операция завершена успешно!"
                else:
                    # Проверяем, может ли бот видеть участников
                    try:
                        channel = await client.get_entity(channel_username)
                        full_channel = await client(GetFullChannelRequest(channel))

                        if hasattr(full_channel, 'full_chat') and hasattr(full_channel.full_chat, 'participants_count'):
                            count = full_channel.full_chat.participants_count
                            return False, f"❌ Бот присоединился, но не может получить список участников. Участников в канале: {count}. Возможно, нужны права администратора."
                        else:
                            return False, "❌ Бот присоединился, но не может получить информацию о канале. Возможно, нужны права администратора."
                    except:
                        return False, "❌ Не удалось получить данные даже после присоединения. Возможно, нужны права администратора."
            else:
                return False, "❌ Не удалось присоединиться к каналу"

    except Exception as e:
        return False, f"❌ Критическая ошибка: {e}"


@client.on(events.NewMessage(pattern='/get_users'))
async def get_users_command(event):
    """Обработчик команды /get_users"""
    try:
        # Проверяем, что это сообщение
        if not hasattr(event, 'message') or not event.message:
            return

        # Получаем текст сообщения
        message_text = event.message.text.strip()

        # Разделяем команду и аргументы
        parts = message_text.split(' ', 1)

        if len(parts) < 2:
            await event.reply("❌ Пожалуйста, укажите ссылку на канал после команды:\n`/get_users @channel_username`")
            return

        link = parts[1].strip()
        chat_id = event.message.chat_id

        await event.reply("⏳ Начинаю обработку канала...")

        # Запускаем обработку канала
        success, message = await process_channel(link, chat_id)

        await event.reply(message)
        await event.reply("\n" + "=" * 50 + "\n")

    except Exception as e:
        print(f"Ошибка в get_users_command: {e}")