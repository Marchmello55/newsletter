import os
from pathlib import Path


async def check_file(file_path, verbose=True):
    """
    Проверяет наличие файла и выводит подробную информацию

    Args:
        file_path (str): путь к файлу
        verbose (bool): вывод подробной информации

    Returns:
        bool: True если файл существует, иначе False
    """
    path = Path(file_path)

    if verbose:
        print(f"Проверка файла: {file_path}")
        print(f"Абсолютный путь: {path.absolute()}")

    if not path.exists():
        if verbose:
            print("❌ Файл не существует")
        return False

    if verbose:
        print("✅ Файл существует")
        print(f"Размер: {path.stat().st_size} байт")
        print(f"Последнее изменение: {path.stat().st_mtime}")

    return True
