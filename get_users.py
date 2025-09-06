from handlers import commands
from config_data.client import client
from config_data.config import Config, load_config


config: Config = load_config()


async def main():
    # Авторизуемся как пользователь
    await client.start(phone=config.tg_bot.phone)

    client.add_event_handler(commands.newsletter)
    client.add_event_handler(commands.stop_newsletter_command)
    client.add_event_handler(commands.newsletter_status_command)

    await client.run_until_disconnected()


if __name__ == '__main__':
    with client:
        client.loop.run_until_complete(main())