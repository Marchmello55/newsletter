from dataclasses import dataclass
from environs import Env


@dataclass
class TgBot:
    bot_name: str
    api_id: int
    api_hash: str
    phone: str
    admin_id: str


@dataclass
class Config:
    tg_bot: TgBot


def load_config(path: str = None) -> Config:
    env = Env()
    env.read_env(path)
    return Config(tg_bot=TgBot(bot_name=env('BOT_NAME'),
                               api_id=env('API_ID'),
                               api_hash=env('API_HASH'),
                               phone=env('PHONE'),
                               admin_id=env('ADMINS')))
