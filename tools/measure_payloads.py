"""Измерить настоящую длину начинки объектов, не доверяя своему разбору.

Приём: заголовок объекта опознаётся надёжно — три координаты, номер шаблона в
границах таблицы и пять нулевых байт. Значит, после каждого объекта можно
**искать**, где начинается следующий, вместо того чтобы вычислять это по своей
раскладке. Разница между найденным и вычисленным и есть ошибка, причём
приписанная конкретному типу объекта.

Так снимается главная ловушка прошлых попыток: раньше я мерил длину структуры,
до которой разбор уже не доходил корректно, и получал уверенные, но бессмысленные
числа.

Проверка честности приёма: у всех проблемных HotA-карт ноль глобальных событий
и хвост из 124 нулей, поэтому блок объектов обязан кончаться ровно за 128 байт
до конца файла. Если после прохода по всем объектам мы попали в эту точку —
измерение верно.

Запуск:
    python tools/measure_payloads.py
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict

from h3m import instances, paths
from h3m.container import read_map_bytes
from h3m.header import read_header
from h3m.logging_setup import setup_logging
from h3m.mapfile import parse
from h3m.objtypes import Obj
from h3m.stream import BinaryReader

log = logging.getLogger("measure_payloads")

MAX_SCAN = 96
"""Насколько далеко искать следующий заголовок. Больше — дороже и опаснее."""

FILE_TAIL = 128
"""Ноль событий (4 байта) плюс 124 нуля в конце файла."""


def type_name(object_id: int) -> str:
    try:
        return Obj(object_id).name
    except ValueError:
        return f"id={object_id}"


def looks_like_header(data: bytes, pos: int, size: int, levels: int, templates: int) -> bool:
    """Похоже ли на заголовок объекта.

    Якорь спрайта может выходить за край карты — тело объекта остаётся внутри,
    и игра это допускает. Поэтому запас в восемь клеток, а не строгие границы.
    """
    if pos + 12 > len(data):
        return False
    x, y, z = data[pos], data[pos + 1], data[pos + 2]
    if x >= size + 8 or y >= size + 8 or z >= levels:
        return False
    if int.from_bytes(data[pos + 3 : pos + 7], "little") >= templates:
        return False
    return data[pos + 7 : pos + 12] == b"\x00" * 5


LOOKAHEAD = 3
"""Сколько объектов пройти вперёд, проверяя кандидата на роль заголовка.

Без этой проверки измерение обманывается на нулях: внутри начинки города
лежат восемнадцать нулевых байт от масок заклинаний, и любая позиция там
выглядит корректным заголовком — координаты (0,0,0), нулевой номер шаблона,
пять нулей. Требование пройти дальше отсекает такие совпадения: настоящая
цепочка объектов продолжается, ложная обрывается на первом же шаге.
"""


def _chain_ok(
    data: bytes,
    pos: int,
    size: int,
    levels: int,
    templates: list,
    features,
    depth: int,
) -> bool:
    """Удаётся ли пройти ``depth`` объектов подряд, начиная с заголовка в ``pos``."""
    for _ in range(depth):
        if not looks_like_header(data, pos, size, levels, len(templates)):
            return False
        template_index = int.from_bytes(data[pos + 3 : pos + 7], "little")
        probe = BinaryReader(data)
        probe.pos = pos + 12
        try:
            instances._read_payload(  # noqa: SLF001 — диагностический доступ
                probe, templates[template_index], features, (0, 0, 0)
            )
        except Exception:  # noqa: BLE001
            return False
        pos = probe.pos
    return True


def _find_next_header(
    data: bytes,
    start: int,
    size: int,
    levels: int,
    templates: list,
    features,
    computed: int | None,
) -> int | None:
    """Смещение настоящего следующего заголовка от ``start``.

    Поиск идёт **от вычисленной позиции в обе стороны**, а не от начала
    начинки. Это снимает смещение измерения: при поиске слева направо ложное
    раннее совпадение возможно, а позднее нет, поэтому отрицательные
    расхождения систематически преувеличивались. Здесь же кандидаты
    перебираются по удалённости от нашей оценки, и обе стороны равноправны.
    """
    # Если наша позиция сама выглядит заголовком — верим ей и не ищем.
    #
    # Без этого проверка на три объекта вперёд распространяет ошибку назад:
    # когда настоящая поломка случится через пару объектов, цепочка оборвётся
    # и виноватым окажется предыдущий, ни в чём не повинный объект. Так у
    # декоративных объектов без начинки получались расхождения в 64 и 88 байт.
    if computed is not None and looks_like_header(
        data, start + computed, size, levels, len(templates)
    ):
        return computed

    candidates: list[int]
    if computed is None:
        candidates = list(range(MAX_SCAN))
    else:
        candidates = [computed]
        for step in range(1, MAX_SCAN):
            candidates.append(computed + step)
            if computed - step >= 0:
                candidates.append(computed - step)

    for offset in candidates:
        if 0 <= offset < len(data) - start and _chain_ok(
            data, start + offset, size, levels, templates, features, LOOKAHEAD
        ):
            return offset
    return None


def measure(path, first_error: list) -> tuple[dict[int, Counter[int]], bool]:
    """Пройти по объектам карты, измеряя длину каждой начинки.

    Возвращает распределение разниц по типам и признак того, что проход
    закончился ровно там, где должен. В ``first_error`` кладётся первое
    расхождение — оно и есть настоящая причина, всё остальное последствия.
    """
    data = read_map_bytes(path)
    parsed = parse(data)
    if parsed.object_templates is None:
        return {}, False

    size, levels = parsed.header.size, parsed.header.levels
    features = parsed.header.features
    templates = parsed.object_templates
    target_end = len(data) - FILE_TAIL

    reader = BinaryReader(data)
    read_header(reader)
    reader.pos = parsed.total_size - len(parsed.tail)
    count = reader.u32()

    deltas: dict[int, Counter[int]] = defaultdict(Counter)

    for index in range(count):
        reader.pos += 3 + 4  # координаты и номер шаблона
        template_index = int.from_bytes(data[reader.pos - 4 : reader.pos], "little")
        reader.pos += 5  # нулевые байты
        if template_index >= len(templates):
            return deltas, False

        template = templates[template_index]
        start = reader.pos

        # Сколько насчитала бы наша раскладка.
        probe = BinaryReader(data)
        probe.pos = start
        try:
            instances._read_payload(  # noqa: SLF001 — диагностический доступ
                probe, template, features, (0, 0, 0)
            )
            computed = probe.pos - start
        except Exception:  # noqa: BLE001
            computed = None

        # Где на самом деле начинается следующий объект.
        if index + 1 == count:
            actual = target_end - start
        else:
            actual = _find_next_header(
                data, start, size, levels, templates, features, computed
            )
            if actual is None:
                return deltas, False

        if computed is not None:
            deltas[template.object_id][actual - computed] += 1
            if actual != computed and first_error[0] is None:
                first_error[0] = (
                    template.object_id,
                    template.object_subid,
                    actual - computed,
                    index,
                )

        reader.pos = start + actual

    return deltas, reader.pos == target_end


def main() -> None:
    log_path = setup_logging("measure_payloads")

    totals: dict[int, Counter[int]] = defaultdict(Counter)
    culprits: Counter[tuple[str, int, int]] = Counter()
    exact = inexact = 0

    for map_path in paths.iter_maps():
        parsed = parse(read_map_bytes(map_path))
        if parsed.header.format.name != "HOTA" or parsed.object_templates is None:
            continue
        if parsed.objects is not None:
            continue

        first_error: list = [None]
        deltas, landed = measure(map_path, first_error)
        exact += landed
        inexact += not landed

        # Статистику берём только с карт, где проход завершился ровно в
        # расчётной точке. Если измеритель где-то сбился, все его измерения
        # после сбоя — мусор, и они забивают отчёт ложными расхождениями:
        # именно так монстры дважды попадали в подозреваемые, хотя разбирались
        # верно.
        if landed:
            for object_id, counter in deltas.items():
                totals[object_id].update(counter)
        if first_error[0]:
            object_id, subid, delta, index = first_error[0]
            culprits[(type_name(object_id), subid, delta)] += 1

    log.info("Карт измерено: %d, из них дошли ровно до конца: %d", exact + inexact, exact)
    log.info("")
    log.info("=== Типы, где наша длина расходится с настоящей ===")

    for object_id, counter in sorted(
        totals.items(), key=lambda item: -sum(v for k, v in item[1].items() if k)
    ):
        wrong = {delta: n for delta, n in counter.items() if delta}
        if not wrong:
            continue
        right = counter.get(0, 0)
        log.info(
            "  %-22s верно %5d, ошибок %5d, не хватает байт: %s",
            type_name(object_id),
            right,
            sum(wrong.values()),
            dict(sorted(wrong.items(), key=lambda kv: -kv[1])[:4]),
        )

    log.info("")
    log.info("=== Первая ошибка в карте (это и есть причины) ===")
    for (name, subid, delta), count in culprits.most_common(15):
        log.info(
            "  %-24s subid=%-4d не хватает %+4d байт — на %d картах",
            name, subid, delta, count,
        )

    log.info("")
    log.info("Подробный лог: %s", log_path)


if __name__ == "__main__":
    main()
