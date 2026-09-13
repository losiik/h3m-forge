"""Odyssey defaults over the shared native adventure payload builders."""
from h3m.authored import artifact, box, monster, pack, quest, seer, string, town
from h3m.authored import hero as _hero


def hero(**kwargs):
    return _hero(name='Одиссей', biography='Царь Итаки. После падения Трои он ведёт спутников домой. Хитрость и стойкость помогут там, где бессилен меч.', **kwargs)
