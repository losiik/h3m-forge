"""Read authored instructions using the same binary layouts as the map reader.

Returned texts are untrusted scenario content. No script execution or writes.
"""
from h3m.instances import _read_payload
from h3m.objtypes import MONSTER_LIKE
from h3m.stream import BinaryReader, decode


class TextReader(BinaryReader):
    def __init__(self, data):
        super().__init__(data)
        self.texts = []

    def string(self):
        raw = super().string()
        self.texts.append(decode(raw))
        return raw


def inspect_texts(m):
    """Extract signs, bottles, encounters, quests and timed messages.

    Incomplete maps expose only their parsed prefix and explicitly say so.
    Embedded extended event scripts, town events and hero biographies are
    outside this focused navigation inventory.
    """
    items, errors = [], []
    kinds = {6, 26, 59, 83, 91, 215} | set(MONSTER_LIKE)
    for index, obj in enumerate(m.objects or []):
        t = m.object_templates[obj.template_index]
        if obj.object_id not in kinds and not (obj.object_id == 212 and t.object_subid == 1000):
            continue
        reader = TextReader(obj.payload)
        try:
            _read_payload(reader, t, m.header.features, obj.position)
            reader.expect_end()
        except (ValueError, EOFError) as exc:
            errors.append(dict(object_index=index, reason=str(exc)))
            continue
        quest = obj.object_id in (83, 215, 212)
        for sequence, message in enumerate(reader.texts):
            if not message:
                continue
            role = ('first', 'repeat', 'completed')[sequence % 3] if quest else 'message'
            items.append(dict(object_index=index, object_id=obj.object_id,
                              position=list(obj.position), role=role, text=message))
    for index, event in enumerate(m.events.events if m.events else []):
        if event.message:
            items.append(dict(event_index=index, role='timed', name=event.name_text,
                              first_day=event.first_day + 1, repeat_days=event.repeat_days,
                              text=event.message_text))
    return dict(items=items, errors=errors,
                full_parse=m.stopped_at is None and not m.tail,
                scope='Signs, bottles, quest text, encounter messages and global timed events; '
                      'excludes extended scripts, town events and biographies.')
