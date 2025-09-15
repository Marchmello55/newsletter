import pandas as pd
from sqlalchemy import inspect
from datetime import datetime



def create_excel_from_objects(objects_list, filename=None, sheet_name="Data"):
    """
    Создает Excel файл из списка объектов SQLAlchemy

    Args:
        objects_list: список объектов ORM
        filename: имя файла (если None, генерируется автоматически)
        sheet_name: название листа в Excel

    Returns:
        str: путь к созданному файлу
    """
    if not objects_list:
        raise ValueError("Список объектов пуст")

    # Генерируем имя файла если не указано
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_name = objects_list[0].__class__.__name__.lower()
        filename = f"{model_name}_export_{timestamp}.xlsx"

    # Получаем названия колонок из первого объекта
    inspector = inspect(objects_list[0])
    columns = [column.key for column in inspector.mapper.column_attrs]

    # Собираем данные
    data = []
    for obj in objects_list:
        row = {}
        for column in columns:
            row[column] = getattr(obj, column, None)
        data.append(row)

    # Создаем DataFrame
    df = pd.DataFrame(data, columns=columns)

    # Сохраняем в Excel
    df.to_excel(filename, index=False, sheet_name=sheet_name, engine='openpyxl')

    return filename