"""Внешняя оболочка файла карты — gzip.

Важная оговорка про round-trip: сравнивать имеет смысл **распакованные**
данные, а не сам файл. Контейнер gzip хранит время создания, имя исходного
файла и зависит от уровня сжатия, поэтому побайтово повторить именно файл
нельзя, да и незачем — игра читает содержимое, а не оболочку.

Соответственно критерий корректности проекта формулируется так:
распакованный поток после разбора и сборки совпадает с распакованным
оригиналом байт в байт.
"""

from __future__ import annotations

import gzip
from pathlib import Path


def read_map_bytes(path: Path) -> bytes:
    """Прочитать и распаковать карту."""
    with gzip.open(path, "rb") as fh:
        return fh.read()


def write_map_bytes(path: Path, data: bytes, *, compresslevel: int = 9) -> None:
    """Упаковать и записать карту.

    ``mtime=0`` — чтобы одинаковое содержимое давало одинаковый файл и диффы
    между прогонами были осмысленными.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(path, "wb", compresslevel=compresslevel, mtime=0) as fh:
        fh.write(data)


def peek_version(path: Path) -> int:
    """Прочитать поле версии, не распаковывая карту целиком."""
    with gzip.open(path, "rb") as fh:
        return int.from_bytes(fh.read(4), "little")
