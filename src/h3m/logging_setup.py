"""Единая настройка логирования для всех скриптов проекта.

Каждый прогон пишет одновременно в консоль и в собственный файл
``logs/<timestamp>_<имя скрипта>.log``. Отдельный файл на прогон, а не общий
растущий лог, выбран сознательно: при разборе бинарного формата важно уметь
сказать «вот этот конкретный запуск дал вот такой результат» и сравнить его с
соседним, а не выкусывать нужный кусок из общей простыни.

В файл пишется уровень DEBUG со смещениями и именами полей, в консоль — INFO.
Разбор бинарника генерирует очень много подробностей, которые в консоли только
мешают, но при расследовании расхождения оказываются единственной зацепкой.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = PROJECT_ROOT / "logs"

_CONSOLE_FORMAT = "%(levelname)-7s %(message)s"
_FILE_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"


def setup_logging(
    script_name: str,
    *,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
) -> Path:
    """Настроить корневой логгер и вернуть путь к файлу лога этого прогона.

    Вызывать один раз на входе в скрипт. Повторный вызов заменяет обработчики,
    чтобы не получить дублирующиеся строки.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    log_path = LOGS_DIR / f"{stamp}_{script_name}.log"

    root = logging.getLogger()
    root.setLevel(min(console_level, file_level))
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(file_level)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
    root.addHandler(console_handler)

    logging.getLogger(__name__).debug("Лог прогона: %s", log_path)
    return log_path
