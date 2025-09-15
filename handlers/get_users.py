import os
import asyncio
from telethon import events
from telethon.tl.functions.channels import GetParticipantsRequest, JoinChannelRequest, GetFullChannelRequest
from telethon.tl.types import ChannelParticipantsSearch
from telethon.errors import ChannelPrivateError, UsernameNotOccupiedError, ChannelInvalidError, FloodWaitError
import re
import logging

from filter.filter import owner_filter
from config_data.client import client


@client.on(events.NewMessage(pattern='/get_users', func=owner_filter))
async def get_users_command(event):
    """Обработчик команды /get_users"""
    try:
        # Проверяем, что это сообщение
        if not hasattr(event, 'message') or not event.message:
            return
        logging.info("get_users_command")

        # Получаем текст сообщения
        message_text = event.message.message.strip()

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


async def process_channel(link, chat_id):
    """Основная функция обработки канала"""
    try:
        logging.info("process_channel")
        # Извлекаем username из ссылки
        channel_username = extract_channel_username(link)
        await client.send_message(chat_id, f"🔍 Обрабатываем канал: {channel_username}")

        # Пытаемся получить пользователей
        users, error = await get_channel_users(channel_username, chat_id)

        if users is not None:
            # Если доступ есть сразу
            await client.send_message(chat_id, f"✅ Найдено {len(users)} пользователей")
            filename = f'users.txt'
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
                await asyncio.sleep(10)

                # Пытаемся получить пользователей снова
                users, error = await get_channel_users(channel_username, chat_id)

                if users is not None:
                    await client.send_message(chat_id, f"✅ После присоединения найдено {len(users)} пользователей")
                    filename = f'users.txt'
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


async def get_channel_users(channel_username, chat_id):
    logging.info("get_channel_users")
    """Получает список ВСЕХ пользователей канала с помощью пагинации"""
    all_users = []  # Здесь будем хранить всех пользователей
    offset = 0
    limit = 200  # Максимальное количество за запрос (ограничение API)
    total_count = 0
    errors = 0
    max_errors = 3

    try:
        channel = await client.get_entity(channel_username)
        # Получаем общее количество участников для информации
        full_channel = await client(GetFullChannelRequest(channel))
        total_count = getattr(full_channel.full_chat, 'participants_count', 0)
        await client.send_message(chat_id, f"🔍 Всего участников в канале: {total_count}. Начинаю сбор...")

        # Запускаем цикл пагинации
        while True:
            try:
                participants = await client(GetParticipantsRequest(
                    channel=channel,
                    filter=ChannelParticipantsSearch(''),
                    offset=offset,
                    limit=limit,
                    hash=0
                ))

                if not participants or not participants.users:
                    break  # Больше пользователей нет, выходим из цикла

                # Добавляем полученных пользователей в общий список
                all_users.extend(participants.users)
                offset += len(participants.users)


                # Небольшая задержка, чтобы не нагружать сервера Telegram
                await asyncio.sleep(2)

            except FloodWaitError as e:
                # Если Telegram просит подождать
                wait_time = e.seconds
                await client.send_message(chat_id, f"⏳ Превышен лимит запросов. Жду {wait_time} секунд...")
                await asyncio.sleep(wait_time)
            except Exception as e:
                errors += 1
                logging.error(f"Ошибка при пагинации (offset {offset}): {e}")
                if errors >= max_errors:
                    await client.send_message(chat_id, f"❌ Слишком много ошибок. Прерываю сбор.")
                    break
                await asyncio.sleep(5)

        await client.send_message(chat_id, f"✅ Сбор завершен! Получено {len(all_users)} пользователей.")
        return all_users, None

    except ChannelPrivateError:
        return None, "🔒 Нет доступа к каналу. Бот/аккаунт должен быть администратором."
    except Exception as e:
        return None, f"❌ Критическая ошибка при получении пользователей: {e}"


async def save_users_to_file(users, filename):
    """Сохраняет ID пользователей в файл"""
    with open(filename, 'w', encoding='utf-8') as file:
        for user in users:
            file.write(f"{user.id}\n")
            """if user.username:
                file.write(f"{user.id} - @{user.username}\n")
            else:"""


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