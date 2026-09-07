"""Build Odyssey gameplay revision 4; keep earlier map files intact."""
import argparse
import hashlib
import json
from pathlib import Path

from h3m import mapfile, paths
from h3m.world import Assets
from odyssey.compact import generate, ISLANDS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('out/Odyssey-Homecoming-Compact.h3m'))
    parser.add_argument('--seed', type=int, default=20260905)
    args = parser.parse_args()
    files = [f for f in paths.iter_maps() if not f.name.startswith('Odyssey-Homecoming')]
    assets = Assets.cached(files, paths.out_dir() / 'world-assets.json')
    result, report = generate(assets, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mapfile.save(args.output, result)
    report['file_sha256'] = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix('.report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    guide = ['# ' + report['name'], '',
        'HotA 1.8.0; 72×72, два уровня; один игрок. Рекомендуемая сложность 100%.',
        'Переработка 4. Прежняя версия пройдена пользователем за 20 минут. '
        'Длительность этой версии ещё не измерена; полный игровой прогон не выполнен.', '',
        'Начните новую игру: старые сохранения не подхватывают изменения карты. '
        'Первая задача — отбить троянский дозор восточнее лагеря; корабль у южного пляжа.', '',
        '## Что изменилось', '',
        '- Архипелаг вчетверо меньше по площади; задачи и припасы рядом с причалами.',
        '- Исправлена высадка: береговые флаги рассчитываются по воде вокруг клетки; проверены все 14 пристаней.',
        '- Шляпа адмирала надета со старта. Не снимайте её: она сохраняет движение при посадке и высадке.',
        '- Полифем, Кирка и Калипсо: заплатить мастеру или отбить припасы. Проходить оба варианта не нужно.',
        '- Дополнительные награды включают Точность, Лечение и ману; остальные дают войска и опыт.',
        '- Семь проливов открываются после победы над определённым отрядом. Сдавать трофей не нужно.',
        '- Всего 23 боевых столкновения: 14 отдельных отрядов, 3 охраняемых склада и 6 необязательных испытаний.',
        '- Девять разговоров и заданий сохраняют побег от Полифема, Эола, Кирку, Тиресия, Сциллу, Калипсо и Пенелопу.',
        '- Щит, Благословение, Ускорение и Замедление доступны со старта. Начальное войско меньше.',
        '- Подсказка появляется в первый день и при входе в 13 морских стоянок. На берегах есть указатели.',
        '- Не продавайте оставшиеся сюжетные предметы. Сберегите шесть копейщиков для Сциллы; запасные есть на её острове.', '',
        '## Маршрут (спойлеры)', '']
    for island in ISLANDS:
        guide.extend(['### ' + island.name, '', report['objectives'][island.key], ''])
    guide.extend(['## Проверка расстояний', '',
        f'Морские перегоны в одной модели: {report["pacing_previous"]["total_steps"]} → {report["pacing"]["total_steps"]} клеток; '
        f'самый длинный новый — {report["pacing"]["max_steps"]}. Это расстояния, не измерение ходов или времени.',
        f'От причала до южного подхода к действию: максимум {report["shore_access"]["max_steps"]} шагов по сторонам клеток.', ''])
    guide.extend(['## Ограничения проверки', '',
        'Автоматическая модель проверяет порядок открытия проходов и наличие припасов, '
        'предполагая победы без потерь. Она не оценивает сложность тактических боёв. '
        'Обычные артефакты ещё используются для части сюжетных знаков. '
        'Кораблекрушения и годы странствий переданы текстом; автоматического уничтожения всего экипажа нет.', ''])
    args.output.with_suffix('.md').write_text('\n'.join(guide), encoding='utf-8')
    print(f'{args.output.resolve()}\n{len(result.objects)} objects; '
          f'{report["total_battles"]} encounters; {len(report["quests"])} quests; '
          f'{report["kill_objective_gates"]} defeat-monster gates')


if __name__ == '__main__':
    main()
