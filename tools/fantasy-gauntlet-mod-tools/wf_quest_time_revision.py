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
    tower = table.get("700099")
    if tower is None:
        return {}
    if not isinstance(tower, dict):
        raise ValueError("Deep Abyss quest payload is not an OrderedMap")
    floors = {key: row for key, row in tower.items()
              if key.isdigit() and 1 <= int(key) <= 98}
    if not floors:
        raise ValueError("Deep Abyss has no finite floors")
    canonical = json.dumps(floors, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":")).encode("utf-8")
    return {ABYSS_REVISION_KEY: hashlib.sha256(canonical).hexdigest()}


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
                expected = quest_time_revisions({RUSH_QUEST_MEMBER: archive.read(RUSH_QUEST_MEMBER)})[ABYSS_REVISION_KEY]
                if marker != expected:
                    raise ValueError('Deep Abyss tower changed but its published time revision is stale')
                return {'tower_version': patch['version'], 'marker_version': latest['version'], 'revision': marker}
    raise ValueError('No effective Rush quest table found in the active patch chain')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Read-only Deep Abyss personal/global time revision gate')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    print(json.dumps(validate_current_chain(parser.parse_args().root), ensure_ascii=False))
