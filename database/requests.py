import logging

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.base import async_session, connection
from database.models import Newsletter, WaitAnswer

import asyncio



@connection
async def add_users(codes_list: list[str], session):
    """
    Массовое добавление пользователей (опционально, для оптимизации)
    """
    logging.info(f"add: {len(codes_list)} users")
    await session.execute(delete(Newsletter))
    await session.flush()
    new_users = [Newsletter(tg_id=user, state=0) for user in codes_list]
    session.add_all(new_users)
    await session.commit()
    logging.info(f"Successfully replaced all users. New count: {len(codes_list)}")

@connection
async def get_users_to_newsletter(session):
    """
    получение пользователей для рассылки
    """
    logging.info("get_users_to_newsletter")
    users = await session.scalars(select(Newsletter).where(Newsletter.state == 0))
    return [i.tg_id for i in users]


@connection
async def get_users_success(session):
    """
    получение пользователей с успешной отправкой
    """
    logging.info("get_users_success")
    users = await session.scalars(select(Newsletter).where(Newsletter.state == 1))
    return [i.tg_id for i in users]


@connection
async def get_users_fail(session):
    """
    получение пользователей с безуспешной отправкой
    """
    logging.info("get_users_success")
    users = await session.scalars(select(Newsletter).where(Newsletter.state == 2))
    return [i.tg_id for i in users]


@connection
async def get_users(session):
    """
    Получаем всех пользователей
    """
    logging.info("get_users")
    users = await session.scalars(select(Newsletter))
    return [i.tg_id for i in users]


@connection
async def update_state_users(tg_id: int, state: int, session, cause: str = None):
    """
    Обновляем состояние пользователя
    """
    logging.info("update_state_users")
    await session.execute(update(Newsletter).where(Newsletter.tg_id == tg_id).values(state=state, cause=cause))
    await session.commit()


@connection
async def delete_base(session):
    """
    Удаление бд
    """
    logging.info("delete_base")
    await session.execute((delete(Newsletter)))
    await session.commit()

"""WaitAnswer"""


@connection
async def add_respondent_users(tg_id: int, session):
    """
    добавление пользователей в лист ожидания
    """
    logging.info("add_respondent_users")

    # Используем .first() или проверяем наличие записей
    user = await session.scalar(select(WaitAnswer).where(WaitAnswer.tg_id == tg_id))

    if user is None:  # Проверяем на None, а не на пустую коллекцию
        new_user = WaitAnswer(tg_id=tg_id, state=0)
        session.add(new_user)
        await session.commit()
        logging.info(f"Пользователь {tg_id} добавлен в WaitAnswer")
        return True
    else:
        logging.info(f"Пользователь {tg_id} уже существует")
        return False


@connection
async def check_user(tg_id: int, session):
    logging.info("check_user")
    user = await session.scalar(select(WaitAnswer).where(WaitAnswer.tg_id==tg_id).where(WaitAnswer.state==0))
    if user: return True
    else: return False


@connection
async def update_answer(tg_id: int, answer: str, session):
    logging.info("update_answer")
    user = await session.scalar(select(WaitAnswer).where(WaitAnswer.tg_id==tg_id))
    user.state = 1
    user.answer=answer
    await session.commit()

"""Для отчета"""


@connection
async def get_user_to_report_newsletter(session=None):
    """Получает пользователей для отчета по рассылкам"""
    logging.info("Запрос пользователей для отчета по рассылкам")

    result = await session.scalars(
        select(Newsletter).where(Newsletter.state != 0)
    )
    users = result.all()  # Получаем список объектов

    return [i for i in users]


@connection
async def get_user_to_report_wait_action(session=None):
    """Получает пользователей для отчета по ожидающим ответам"""
    logging.info("Запрос пользователей для отчета по ожидающим ответам")

    result = await session.scalars(
        select(WaitAnswer).where(WaitAnswer.state != 0)
    )
    users = result.all()  # Получаем список объектов
    return [i for i in users]


@connection
async def check_users_exist_batch(user_ids: list[int], session):

    if not user_ids:
        return [], []

    # Делаем запрос для всех ID сразу
    stmt = select(WaitAnswer.tg_id).where(WaitAnswer.tg_id.in_(user_ids))
    result = await session.execute(stmt)
    existing_ids = {row[0] for row in result.all()}

    existing_list = [uid for uid in user_ids if uid in existing_ids]
    missing_list = [uid for uid in user_ids if uid not in existing_ids]

    return existing_list, missing_list