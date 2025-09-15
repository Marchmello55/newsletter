import logging
from datetime import datetime, timedelta
from utils.constants import start_time, end_time


async def work_state_chack():
    now = datetime.now()
    current_time = now.time()
    if start_time <= current_time <= end_time:
        logging.info("Идет рабочий день")
        return True
    else:
        logging.info("Рабочий день окончен")
        return False



async def time_to_work():
    now = datetime.now()
    current_time = now.time()
    if current_time > end_time:
        # После 20:00 - ждем до 8:00 следующего дня
        tomorrow = now.date() + timedelta(days=1)
        logging.info("Рабочий день закончился")
        target_datetime = datetime.combine(tomorrow, start_time)
    else:
        # До 8:00 - ждем до 8:00 сегодня
        target_datetime = datetime.combine(now.date(), start_time)
        logging.info("Рабочий день еще не начался")
    return (target_datetime - now).total_seconds()
