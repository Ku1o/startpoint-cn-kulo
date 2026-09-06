"""Publish an event-specific time-record revision with the actual quest payload."""
from __future__ import annotations

import hashlib
import json

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
