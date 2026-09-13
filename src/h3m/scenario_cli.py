"""Portable CLI for compiling a user-authored scenario specification."""
import argparse
import json
from pathlib import Path

from h3m.service import MapService


def walkthrough(report):
    spec=report['specification']
    parts=['# '+spec['name'],'',spec['description'],'',
           ('Новая игра; фиксированная охрана и награды на 80–200%.' if spec.get('balance_profile')=='fixed'
            else 'Новая игра; рекомендуемая сложность 100%.')
           + ' Сначала прочитайте указатель у пляжа и посетите хижину мага.',
           'Все пристани находятся на юге островов. Не снимайте шляпу адмирала.',
           'После задания войдите в северную ограждённую площадку, к указателю завершения.',
           'Путевые знаки передаются автоматически; не продавайте их.','', '## Этапы','']
    by_id={c['id']:c for c in spec['chapters']}
    for i,c in enumerate(report['chapters'],1):
        design=by_id[c['id']]
        parts.extend([f'### {i:02}. {c["title"]}'+(' (необязательно)' if c['optional'] else ''),'',
                      design['text'],'',design['challenge']['text'],
                      'Предыдущие этапы: '+(', '.join(by_id[k]['title'] for k in design['requires']) or 'старт'), ''])
    parts.extend(['## Проверки','',f'Максимальный морской переход: {report["pacing"]["max_steps"]} клеток.',
                  'Проверены сюжетные зависимости, припасы, береговые подходы и прохождение без необязательных наград.',
                  'Модель предполагает победы без потерь. Сложность боёв, длительность и работа в движке требуют игрового теста.',''])
    return '\n'.join(parts)


def main():
    parser=argparse.ArgumentParser(description='Compile a custom HotA story adventure from JSON')
    parser.add_argument('spec',type=Path)
    parser.add_argument('--workspace',type=Path,default=Path.cwd())
    parser.add_argument('--game-dir',type=Path)
    args=parser.parse_args()
    service=MapService(args.workspace,args.game_dir)
    result=service.generate_scenario(json.loads(args.spec.read_text(encoding='utf-8-sig')))
    print(json.dumps({k:v for k,v in result.items() if k!='report'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
