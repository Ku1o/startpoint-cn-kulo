"""Publish an event-specific time-record revision with the actual quest payload."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import wf_quest_lib as q

RUSH_QUEST_LOGICAL = "master/quest/event/rush_event_quest.orderedmap"
_digest = hashlib.sha1((RUSH_QUEST_LOGICAL + q.SALT).encode()).hexdigest()
RUSH_QUEST_MEMBER = f"production/upload/{_digest[:2]}/{_digest[2:]}"
ABYSS_REVISION_KEY = "rush:700099"


def quest_time_revisions(payloads: dict[str, bytes]) -> dict[str, str]:
    """Ignore official quests, other modes, and the separate endless quest."""
    payload = payloads.get(RUSH_QUEST_MEMBER)
    if payload is None:
        return {}
    table = q.parse_node(payload)
    if not isinstance(table, dict):
        raise ValueError("Rush quest payload is not an OrderedMap")
    result = {}
    for event_id, last_floor in (("700099", 98), ("700100", 30)):
        tower = table.get(event_id)
        if tower is None:
            continue
        if not isinstance(tower, dict):
            raise ValueError(f"Deep Abyss {event_id} quest payload is not an OrderedMap")
        floors = {key: row for key, row in tower.items()
                  if key.isdigit() and 1 <= int(key) <= last_floor}
        if not floors:
            raise ValueError(f"Deep Abyss {event_id} has no finite floors")
        canonical = json.dumps(floors, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8")
        result[f"rush:{event_id}"] = hashlib.sha256(canonical).hexdigest()
    return result


def validate_current_chain(root: Path) -> dict:
    """Check the winning tower bytes against the marker the server actually resolves.

    A later metadata-only correction is allowed; an unmarked newer tower is not.
    """
    manifest = json.loads((root / 'assets/asset-patch/manifest.json').read_text(encoding='utf-8-sig'))
    patches = sorted((p for p in manifest['patches'] if p.get('enabled') and p.get('type') == 'patch'),
                     key=lambda p: tuple(map(int, p['version'].split('.'))), reverse=True)
    markers = [p for p in patches if ABYSS_REVISION_KEY in p.get('quest_time_revisions', {})]
    if not markers:
        raise ValueError('Deep Abyss has no published time revision')
    latest = markers[0]
    marker = latest['quest_time_revisions'][ABYSS_REVISION_KEY]
    if any(p['quest_time_revisions'][ABYSS_REVISION_KEY] != marker
           for p in markers if p['version'] == latest['version']):
        raise ValueError('Conflicting Deep Abyss time revisions')
    for patch in patches:
        names = patch.get('chain') or patch.get('archives') or [patch.get('archive')]
        for name in reversed(names):
            if not isinstance(name, str):
                continue
            with zipfile.ZipFile(root / 'assets/asset-patch/active' / name) as archive:
                if RUSH_QUEST_MEMBER not in archive.namelist():
                    continue
                expected = quest_time_revisions({RUSH_QUEST_MEMBER: archive.read(RUSH_QUEST_MEMBER)})
                modes = {}
                for event_key, fingerprint in expected.items():
                    candidates = [p for p in patches if event_key in p.get('quest_time_revisions', {})]
                    if not candidates:
                        raise ValueError(f'{event_key} has no published time revision')
                    head = candidates[0]
                    actual = head['quest_time_revisions'][event_key]
                    if any(p['quest_time_revisions'][event_key] != actual
                           for p in candidates if p['version'] == head['version']):
                        raise ValueError(f'Conflicting time revisions for {event_key}')
                    if actual != fingerprint:
                        validate_description_revision(root, patches, head, event_key, actual,
                                                      archive.read(RUSH_QUEST_MEMBER), fingerprint)
                    modes[event_key] = {'marker_version': head['version'], 'revision': actual}
                if ABYSS_REVISION_KEY not in modes:
                    raise ValueError('Effective quest table dropped the normal Deep Abyss tower')
                return {'tower_version': patch['version'], 'marker_version': latest['version'],
                        'revision': marker, 'modes': modes}
    raise ValueError('No effective Rush quest table found in the active patch chain')


def validate_description_revision(root, patches, head, event_key, actual, current, fingerprint):
    """An audited subtitle repair can keep records, but never hide combat-column edits.

    Reference bytes must come from an earlier immutable archive, with the original
    record digest. The explicit proof also binds the exact outgoing content digest.
    Condition-carrier equivalence is separately checked by the repair publisher.
    """
    proof = head.get('quest_description_revisions', {}).get(event_key, {})
    if proof.get('content_revision') != fingerprint or proof.get('record_revision') != actual:
        raise ValueError(f'{event_key} tower changed but its published time revision is stale')
    reference = next((p for p in patches if p.get('id') == proof.get('reference_patch')), None)
    if (reference is None or tuple(map(int, reference['version'].split('.'))) >=
            tuple(map(int, head['version'].split('.')))):
        raise ValueError('Description revision requires an earlier reference patch')
    names = reference.get('chain') or reference.get('archives') or [reference.get('archive')]
    event = event_key.split(':')[1]
    for name in reversed(names):
        with zipfile.ZipFile(root / 'assets/asset-patch/active' / name) as source:
            if RUSH_QUEST_MEMBER not in source.namelist():
                continue
            raw = source.read(RUSH_QUEST_MEMBER)
            if quest_time_revisions({RUSH_QUEST_MEMBER: raw}).get(event_key) != actual:
                raise ValueError('Description reference does not match preserved record revision')
            before, after = q.parse_node(raw)[event], q.parse_node(current)[event]
            if set(before) != set(after):
                raise ValueError('Description correction changed quest IDs')
            import csv, io
            def columns(row):
                return list(csv.reader(io.StringIO(row.decode() if isinstance(row, bytes) else row)))[0]
            for key in before:
                if before[key] == after[key]:
                    continue
                a, b = columns(before[key]), columns(after[key])
                if not key.isdigit() or int(key) == 99 or len(a) < 4 or a[:3]+a[4:] != b[:3]+b[4:]:
                    raise ValueError('Description correction changed combat columns or endless')
            return
    raise ValueError('Description reference has no quest table')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Read-only Deep Abyss personal/global time revision gate')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    print(json.dumps(validate_current_chain(parser.parse_args().root), ensure_ascii=False))
