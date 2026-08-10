"""Поиск установленной игры и доступ к её картам.

Реальные карты из поставки — основа проверки корректности всего проекта, но в
репозиторий они не попадают (чужие данные, см. .gitignore). Поэтому путь к игре
определяется на лету: переменной окружения ``H3_GAME_DIR`` либо перебором
типовых мест установки.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ENV_VAR = "H3_GAME_DIR"

#: Типовые места установки. Список намеренно короткий: если игра лежит
#: где-то ещё, правильный ответ — задать H3_GAME_DIR, а не растить перебор.
_CANDIDATES = (
    Path(r"C:\Games\Heroes of Might and Magic III Complete"),
    Path(r"C:\Program Files (x86)\Heroes of Might and Magic III Complete"),
    Path(r"C:\GOG Games\Heroes of Might and Magic 3 Complete"),
)

#: Файлы, по наличию которых каталог опознаётся как установка с HotA.
_HOTA_MARKERS = ("HotA.dll", "h3hota.exe")


class GameNotFoundError(RuntimeError):
    """Установка игры не найдена."""


def find_game_dir() -> Path:
    """Вернуть каталог установленной игры.

    :raises GameNotFoundError: если каталог не найден и переменная не задана.
    """
    env_value = os.environ.get(ENV_VAR)
    if env_value:
        path = Path(env_value)
        if not path.is_dir():
            raise GameNotFoundError(f"{ENV_VAR}={env_value!r} — каталога не существует")
        return path

    for candidate in _CANDIDATES:
        if candidate.is_dir():
            return candidate

    raise GameNotFoundError(
        "Установка Heroes III не найдена. Задайте путь переменной окружения "
        f"{ENV_VAR}, например:\n"
        rf'    set {ENV_VAR}=C:\Games\Heroes of Might and Magic III Complete'
    )


def has_hota(game_dir: Path | None = None) -> bool:
    """Установлен ли HotA в этом каталоге."""
    game_dir = game_dir or find_game_dir()
    return any((game_dir / marker).is_file() for marker in _HOTA_MARKERS)


def maps_dir(game_dir: Path | None = None) -> Path:
    """Каталог с картами игры."""
    game_dir = game_dir or find_game_dir()
    path = game_dir / "Maps"
    if not path.is_dir():
        raise GameNotFoundError(f"В {game_dir} нет подкаталога Maps")
    return path


def iter_maps(game_dir: Path | None = None) -> Iterator[Path]:
    """Все файлы карт из поставки, отсортированные по размеру.

    Сортировка по возрастанию размера не косметическая: при отладке парсера
    начинать надо с самых маленьких карт — в них меньше объектов и меньше
    шансов, что несколько разных ошибок наложатся друг на друга.
    """
    return iter(sorted(maps_dir(game_dir).glob("*.h3m"), key=lambda p: p.stat().st_size))


def out_dir() -> Path:
    """Каталог для сгенерированных карт (создаётся при обращении)."""
    path = PROJECT_ROOT / "out"
    path.mkdir(parents=True, exist_ok=True)
    return path


def reference_dir() -> Path:
    """Каталог для дампов и заметок по формату (создаётся при обращении)."""
    path = PROJECT_ROOT / "reference"
    path.mkdir(parents=True, exist_ok=True)
    return path
