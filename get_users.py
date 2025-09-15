from handlers import stop_newsletter, get_users, start_newsletter, custom_newsletter, get_state, reset
from config_data.client import client
from config_data.config import Config, load_config
from database.base import create_tables

import asyncio

config: Config = load_config()


async def main():
    await create_tables()
    # Авторизуемся как пользователь
    await client.start(phone=config.tg_bot.phone)
    client.add_event_handler(start_newsletter.newsletter)
    client.add_event_handler(custom_newsletter.custom_newsletter)
    client.add_event_handler(stop_newsletter.stop_newsletter_command)
    client.add_event_handler(get_state.newsletter_status_command)
    client.add_event_handler(get_users.get_users_command)

    asyncio.create_task(reset.reset_state())
    await client.run_until_disconnected()


if __name__ == '__main__':
    with client:
        client.loop.run_until_complete(main())