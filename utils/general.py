import os
import asyncio
import random
from datetime import datetime

from telethon import events
from telethon.tl.types import PeerUser, MessageMediaDocument
import logging
from telethon.errors import (
    FloodWaitError,
    UserIsBlockedError,
    PeerIdInvalidError,
    ChannelPrivateError,
    InputUserDeactivatedError,
    UserDeactivatedError,
    BotMethodInvalidError,
    ChatWriteForbiddenError,
    PeerFloodError,
    UserPrivacyRestrictedError,
    PhoneNumberBannedError,
    AuthKeyUnregisteredError,
    SessionPasswordNeededError
)
from filter.filter import owner_filter
from config_data.client import client
from utils.random_get_message import random_message, TypeMessage
from database import requests as rq


# Глобальные переменные для отслеживания состояния рассылки
newsletter_state = {
    'is_running': False,
    'is_waiting_for_work_hours': False,
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


# Кэш сущностей пользователей
user_entity_cache = {}


@client.on(events.NewMessage(func=owner_filter))
async def handle_user_responses(event):
    """Обработчик ответов пользователей"""
    if not is_valid_message_event(event):
        return
    chat_id = event.chat_id
    if chat_id in waiting_for_response:
        # Завершаем future с ответом пользователя
        waiting_for_response[chat_id].set_result(event.message)


@client.on(events.NewMessage())
async def get_answer(event):
    """Обработчик ответов пользователей"""
    try:
        if not is_valid_message_event(event):
            return
        # Проверяем, что пользователь существует в базе
        user_exists = await rq.check_user(event.sender_id)
        if not user_exists:
            return

        # Обновляем ответ пользователя
        await rq.update_answer(event.sender_id, event.message.text)
        logging.info("get_answer")

        # Отправляем ответ
        message_text = await random_message(TypeMessage.question)
        await event.reply(message_text)

    except Exception as e:
        logging.error(f"Unhandled exception on get_answer: {e}")


def is_valid_message_event(event):
    """Проверяет, что это валидное событие сообщения"""
    return (hasattr(event, 'message') and
            hasattr(event.message, 'text') and
            isinstance(event, events.NewMessage.Event))


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
                line = line.replace("\n", " ")
                user_id = line.split(" ")
                for i in user_id:
                    if i.isdigit():
                        user_ids.append(i)

        logging.info(f"Parsed {len(user_ids)} user IDs from file")
        return user_ids

    except Exception as e:
        logging.error(f"Error parsing user IDs: {e}")
        return []


async def validate_user_ids(user_ids):
    """Оптимизированная версия без GetUsersRequest"""
    logging.info(f"Начало проверки {len(user_ids)} пользователей")


    user_ids = list(set(user_ids))
    logging.info(f"Уникальных для проверки: {len(user_ids)}")

    existing_ids, to_check = await rq.check_users_exist_batch(user_ids)
    logging.info(f"Пропускаем {len(existing_ids)} уже существующих в БД")

    if not to_check:
        return [], existing_ids


    logging.info(f"Валидных: {len(to_check)}, Есть в базе {len(existing_ids)}")
    return to_check, existing_ids



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


async def send_message_to_user(user_id, message_text, client):
    """Отправляет сообщение пользователю по ID с кэшированием сущностей"""
    try:
        # Проверяем валидность ID
        user_id_str = str(user_id).strip()
        if not user_id_str.isdigit() or int(user_id_str) <= 0:
            logging.error(f"❌ Неверный формат ID пользователя: {user_id}")
            await rq.update_state_users(int(user_id), 2, cause="Неверный формат ID")
            return False

        user_id_int = int(user_id_str)

        # Проверяем кэш
        if user_id_int in user_entity_cache:
            user_entity = user_entity_cache[user_id_int]
        else:
            # Пытаемся получить сущность пользователя
            try:
                user_entity = await client.get_entity(PeerUser(user_id_int))
                user_entity_cache[user_id_int] = user_entity

                # Проверяем тип аккаунта
                if hasattr(user_entity, 'bot') and user_entity.bot:
                    logging.error(f"❌ Пользователь {user_id_int} является ботом")
                    await rq.update_state_users(user_id_int, 2, cause="Аккаунт является ботом")
                    return False

                if hasattr(user_entity, 'deleted') and user_entity.deleted:
                    logging.error(f"❌ Аккаунт пользователя {user_id_int} удален")
                    await rq.update_state_users(user_id_int, 2, cause="Аккаунт удален")
                    return False

            except (ValueError, PeerIdInvalidError):
                logging.error(f"❌ Неверный ID пользователя {user_id_int}")
                await rq.update_state_users(user_id_int, 2, cause="Неверный ID пользователя")
                return False
            except Exception as e:
                logging.error(f"❌ Ошибка при получении сущности пользователя {user_id_int}: {e}")
                await rq.update_state_users(user_id_int, 2, cause=f"Ошибка получения сущности: {str(e)}")
                return False

        # Отправляем сообщение
        await rq.add_respondent_users(user_id_int)
        await rq.update_state_users(user_id_int, 1)
        await client.send_message(entity=user_entity, message=message_text)
        logging.info(f"✅ Сообщение отправлено пользователю {user_id_int}")
        return True

    except FloodWaitError as e:
        logging.error(f"⏳ FloodWait для пользователя {user_id_int}: {e.seconds} сек")
        await asyncio.sleep(e.seconds)
        await rq.update_state_users(user_id_int, 2, cause=f"FloodWait: {e.seconds} сек")
        return False

    except UserIsBlockedError:
        logging.error(f"❌ Пользователь {user_id_int} заблокировал бота")
        await rq.update_state_users(user_id_int, 2, cause="Пользователь заблокировал бота")
        return False

    except PeerIdInvalidError:
        logging.error(f"❌ Невалидный Peer ID пользователя {user_id_int}")
        await rq.update_state_users(user_id_int, 2, cause="Невалидный Peer ID")
        return False

    except ChannelPrivateError:
        logging.error(f"❌ Приватный канал для пользователя {user_id_int}")
        await rq.update_state_users(user_id_int, 2, cause="Приватный канал")
        return False

    except InputUserDeactivatedError:
        logging.error(f"❌ Аккаунт пользователя {user_id_int} деактивирован/удален")
        await rq.update_state_users(user_id_int, 2, cause="Аккаунт деактивирован или удален")
        return False

    except UserDeactivatedError:
        logging.error(f"❌ Аккаунт пользователя {user_id_int} деактивирован")
        await rq.update_state_users(user_id_int, 2, cause="Аккаунт деактивирован")
        return False

    except BotMethodInvalidError:
        logging.error(f"❌ Пользователь {user_id_int} является ботом")
        await rq.update_state_users(user_id_int, 2, cause="Аккаунт является ботом")
        return False

    except ChatWriteForbiddenError:
        logging.error(f"❌ Нет прав на отправку сообщения пользователю {user_id_int}")
        await rq.update_state_users(user_id_int, 2, cause="Нет прав на отправку сообщений")
        return False

    except PeerFloodError:
        logging.error(f"❌ Flood protection для пользователя {user_id_int}")
        await rq.update_state_users(user_id_int, 2, cause="Flood protection (ограничение отправки)")
        return False

    except UserPrivacyRestrictedError:
        logging.error(f"❌ Пользователь {user_id_int} ограничил получение сообщений")
        await rq.update_state_users(user_id_int, 2, cause="Ограничение приватности пользователя")
        return False

    except PhoneNumberBannedError:
        logging.error(f"❌ Номер телефона забанен для пользователя {user_id_int}")
        await rq.update_state_users(user_id_int, 2, cause="Номер телефона забанен")
        return False

    except AuthKeyUnregisteredError:
        logging.error(f"❌ Сессия не зарегистрирована для пользователя {user_id_int}")
        await rq.update_state_users(user_id_int, 2, cause="Сессия не зарегистрирована")
        return False

    except SessionPasswordNeededError:
        logging.error(f"❌ Требуется пароль сессии для пользователя {user_id_int}")
        await rq.update_state_users(user_id_int, 2, cause="Требуется пароль сессии")
        return False

    except TimeoutError:
        logging.error(f"❌ Таймаут при отправке пользователю {user_id_int}")
        await rq.update_state_users(user_id_int, 2, cause="Таймаут соединения")
        return False

    except ConnectionError:
        logging.error(f"❌ Ошибка соединения для пользователя {user_id_int}")
        await rq.update_state_users(user_id_int, 2, cause="Ошибка соединения")
        return False

    except Exception as e:
        # Ловим другие специфичные ошибки Telegram
        error_msg = str(e).lower()
        if "premium" in error_msg or "premium" in error_msg:
            logging.error(f"❌ Пользователь {user_id_int} требует Telegram Premium")
            await rq.update_state_users(user_id_int, 2, cause="Требуется Telegram Premium для отправки")
        elif "bot" in error_msg:
            logging.error(f"❌ Пользователь {user_id_int} является ботом")
            await rq.update_state_users(user_id_int, 2, cause="Аккаунт является ботом")
        elif "deleted" in error_msg or "deactivated" in error_msg:
            logging.error(f"❌ Аккаунт пользователя {user_id_int} удален/деактивирован")
            await rq.update_state_users(user_id_int, 2, cause="Аккаунт удален или деактивирован")
        elif "privacy" in error_msg or "restricted" in error_msg:
            logging.error(f"❌ Ограничения приватности у пользователя {user_id_int}")
            await rq.update_state_users(user_id_int, 2, cause="Ограничения приватности пользователя")
        else:
            logging.error(f"❌ Неизвестная ошибка при отправке пользователю {user_id_int}: {e}")
            await rq.update_state_users(user_id_int, 2, cause=f"Неизвестная ошибка: {str(e)}")
        return False


async def create_text_file(text_content):
    with open('text', 'w', encoding='utf-8') as file:
        file.write(text_content)

    logging.info("Файл 'text.txt' успешно создан!")

async def get_text(filename='text.txt'):
    """Читает всё содержимое файла в одну строку"""
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            content = file.read()
        if len(content)!=0:return content
        else:return None
    except FileNotFoundError:
        print(f"Файл {filename} не найден")
        return None
    except Exception as e:
        print(f"Ошибка при чтении файла: {e}")
        return None


def save_list_to_txt(data_list, filename: str = "users.txt", mode='w'):
    """
    Сохраняет список в текстовый файл

    Args:
        data_list: список для сохранения
        filename: имя файла (например, 'users.txt')
        mode: режим записи ('w' - перезапись, 'a' - добавление)
    """
    try:
        with open(filename, mode, encoding='utf-8') as file:
            for item in data_list:
                file.write(str(item) + '\n')
        return filename
    except Exception as e:
        return False