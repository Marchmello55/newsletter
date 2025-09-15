from sqlalchemy import Integer
from sqlalchemy.orm import mapped_column, Mapped

from database.base import Base, engine


class Newsletter(Base):
    tg_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[int]
    cause: Mapped[str|None]

class WaitAnswer(Base):
    tg_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[int]
    answer: Mapped[str|None]

async def async_main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

