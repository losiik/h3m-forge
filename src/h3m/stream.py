"""Чтение и запись бинарного потока с отслеживанием смещения.

Ключевое проектное решение здесь — **строки хранятся как байты, а не как str**.

Карты Heroes III не содержат указания кодировки: русская локализация пишет
cp1251, английская — cp1252, и отличить их по содержимому файла нельзя. Если
декодировать при чтении и кодировать при записи, любая ошибка в угадывании
кодировки испортит round-trip, и мы будем ловить расхождение байтов там, где
формат разобран правильно.

Поэтому байты остаются байтами, а декодирование — отдельная операция для
показа человеку. Round-trip от кодировки не зависит вообще.
"""

from __future__ import annotations

import struct
from typing import Final

#: Кодировка русской локализации. Используется только для показа текста,
#: на корректность чтения и записи не влияет.
DEFAULT_ENCODING: Final = "cp1251"


class TruncatedStreamError(EOFError):
    """Поток кончился раньше, чем ожидалось."""


class TrailingDataError(ValueError):
    """После разбора остались непрочитанные байты."""


def decode(raw: bytes, encoding: str = DEFAULT_ENCODING) -> str:
    """Декодировать строку карты для показа человеку."""
    return raw.decode(encoding, errors="replace")


class BinaryReader:
    """Последовательное чтение из bytes с контролем границ.

    Хранит текущее смещение, чтобы при расхождении можно было точно сказать,
    на каком байте всё пошло не так, — при отладке бинарного формата это
    главная диагностическая информация.
    """

    __slots__ = ("data", "pos")

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    # --- служебное ------------------------------------------------------

    def __len__(self) -> int:
        return len(self.data)

    @property
    def remaining(self) -> int:
        """Сколько байт осталось непрочитанными."""
        return len(self.data) - self.pos

    def at_end(self) -> bool:
        return self.pos >= len(self.data)

    def expect_end(self) -> None:
        """Убедиться, что поток прочитан ровно до конца.

        Второй по важности инвариант проекта после round-trip: если разбор
        закончился, а байты остались, значит где-то поехало смещение.
        """
        if self.remaining:
            raise TrailingDataError(
                f"после разбора осталось {self.remaining} непрочитанных байт "
                f"(позиция {self.pos} из {len(self.data)})"
            )

    def _take(self, count: int) -> bytes:
        end = self.pos + count
        if end > len(self.data):
            raise TruncatedStreamError(
                f"запрошено {count} байт по смещению {self.pos}, "
                f"а в потоке всего {len(self.data)}"
            )
        chunk = self.data[self.pos : end]
        self.pos = end
        return chunk

    # --- примитивы ------------------------------------------------------

    def u8(self) -> int:
        return self._take(1)[0]

    def i8(self) -> int:
        return struct.unpack("<b", self._take(1))[0]

    def u16(self) -> int:
        return struct.unpack("<H", self._take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self._take(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self._take(4))[0]

    def boolean(self) -> bool:
        """Флаг размером в байт.

        В файлах встречаются значения, отличные от 0 и 1, поэтому проверку не
        ужесточаем: наша задача — воспроизвести файл, а не судить его.
        Исходное значение при этом теряется, что для round-trip неприемлемо,
        поэтому для флагов, где это важно, читаем u8.
        """
        return self._take(1)[0] != 0

    def bytes_(self, count: int) -> bytes:
        return self._take(count)

    def skip(self, count: int) -> bytes:
        """Пропустить байты, вернув их — чтобы записать обратно без изменений."""
        return self._take(count)

    def string(self) -> bytes:
        """Строка: длина u32, затем сырые байты. Не декодируется."""
        length = self.u32()
        return self._take(length)


class BinaryWriter:
    """Сборка бинарного потока. Зеркало BinaryReader."""

    __slots__ = ("chunks", "size")

    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.size = 0

    def __len__(self) -> int:
        return self.size

    def getvalue(self) -> bytes:
        return b"".join(self.chunks)

    def _put(self, raw: bytes) -> None:
        self.chunks.append(raw)
        self.size += len(raw)

    # --- примитивы ------------------------------------------------------

    def u8(self, value: int) -> None:
        self._put(struct.pack("<B", value))

    def i8(self, value: int) -> None:
        self._put(struct.pack("<b", value))

    def u16(self, value: int) -> None:
        self._put(struct.pack("<H", value))

    def u32(self, value: int) -> None:
        self._put(struct.pack("<I", value))

    def i32(self, value: int) -> None:
        self._put(struct.pack("<i", value))

    def boolean(self, value: bool) -> None:
        self._put(b"\x01" if value else b"\x00")

    def bytes_(self, raw: bytes) -> None:
        self._put(raw)

    def string(self, raw: bytes) -> None:
        self.u32(len(raw))
        self._put(raw)
