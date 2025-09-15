import enum


from sqlalchemy import String, Integer
from sqlalchemy.orm import DeclarativeBase, declared_attr, mapped_column, Mapped
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from typing import Annotated

uniq_str_an = Annotated[str, mapped_column(unique=True)]

# Создаем асинхронный движок
engine = create_async_engine("sqlite+aiosqlite:///database/db.sqlite3", echo=False)
# Настраиваем фабрику сессий
async_session = async_sessionmaker(engine, expire_on_commit=False)


# Базовый класс для всех моделей
class Base(AsyncAttrs, DeclarativeBase):
    __abstract__ = True

    @declared_attr.directive
    def __tablename__(cls) -> str:
        return cls.__name__.lower() + 's'

async def create_tables():
    """Создает все таблицы в базе данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def connection(method):
    async def wrapper(*args, **kwargs):
        async with async_session() as session:
            try:
                # Явно не открываем транзакции, так как они уже есть в контексте
                return await method(*args, session=session, **kwargs)
            except Exception as e:
                await session.rollback()  # Откатываем сессию при ошибке
                raise e  # Поднимаем исключение дальше
            finally:
                await session.close()  # Закрываем сессию

    return wrapper
