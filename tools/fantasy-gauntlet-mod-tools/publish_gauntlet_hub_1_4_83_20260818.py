#!/usr/bin/env python3
"""Publish a shared Fantasy/Deep-Abyss folder with a rank-130 entry gate.

The patch is intentionally client-data-only.  It moves Rush events 700098 and
700099 out of event_list and into one EventFolder, adds an exact Chinese unlock
message, and writes selectable_player_rank=130 to their Rush quests.  Fantasy
Gauntlet's Advent multiplayer quests are not touched, so lower-rank players can
still join rescue rooms opened by eligible hosts.  It also fixes Swim EX's
low-HP action skill to reduce thunder resistance instead of water resistance.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import shutil
import sys
import zipfile
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any

MOD_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOD_DIR))
import wf_mod_tool as core  # noqa: E402
import wf_quest_lib as quest  # noqa: E402
import wf_dsl  # noqa: E402


SOURCE_ROOT = Path(r"F:\codex\startpoint-cn-private-clean")
DEPLOY_ROOT = Path(r"F:\startpoint-cn-main")
BACKUP_ROOT = Path(r"F:\codex\local-deploy-backups")

BASE_VERSION = "1.4.82"
PATCH_VERSION = "1.4.83"
PATCH_ID = "gauntlet-hub-rank140-1.4.83"
ARCHIVE_NAME = "pinball-1.4.82-1.4.83-1-0818-gauntlet-hub-rank140.zip"

FOLDER_ID = "2"
FOLDER_STRING_ID = "mod_gauntlet_hub"
UNLOCK_ID = "mod_gauntlet_hub"
UNLOCK_CONDITION_ID = "condition_mod_gauntlet_hub"
UNLOCK_MESSAGE_ID = "system_lock_mod_gauntlet_hub"
UNLOCK_SHORT_MESSAGE_ID = "short_system_lock_mod_gauntlet_hub"
MIN_PLAYER_RANK = "130"
FANTASY_EVENT_ID = "700098"
DEEP_ABYSS_EVENT_ID = "700099"

EVENT_FOLDER_LOGICAL = "master/quest/event/event_folder.orderedmap"
EVENT_FOLDER_EVENTS_LOGICAL = "master/quest/event/event_folder_events.orderedmap"
EVENT_LIST_LOGICAL = "master/quest/event/event_list.orderedmap"
GAME_UNLOCK_LOGICAL = "master/game_system_unlock/game_system_unlock.orderedmap"
GAME_UNLOCK_CONDITION_LOGICAL = (
    "master/game_system_unlock/game_system_unlock_condition.orderedmap"
)
RUSH_QUEST_LOGICAL = "master/quest/event/rush_event_quest.orderedmap"
UI_STRING_LOGICAL = "master/string/ui_string.orderedmap"
SWIMEX_SKILL_LOGICALS = (
    "battle/action/skill/action/rare5/"
    "resistance_princess_ex$resistance_princess_ex_1.action.dsl.amf3.deflate",
    "battle/action/skill/action/rare5/"
    "resistance_princess_ex$resistance_princess_ex_2.action.dsl.amf3.deflate",
)

TABLE_LOGICALS = (
    EVENT_FOLDER_LOGICAL,
    EVENT_FOLDER_EVENTS_LOGICAL,
    EVENT_LIST_LOGICAL,
    GAME_UNLOCK_LOGICAL,
    GAME_UNLOCK_CONDITION_LOGICAL,
    RUSH_QUEST_LOGICAL,
    UI_STRING_LOGICAL,
)
PAYLOAD_LOGICALS = TABLE_LOGICALS + SWIMEX_SKILL_LOGICALS


class PublishError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def member_name(logical: str) -> str:
    digest = core.sha1_path(logical)
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def live_path(root: Path, logical: str) -> Path:
    digest = core.sha1_path(logical)
    return root / "assets/asset-patch/production/upload" / digest[:2] / digest[2:]


def active_archives(root: Path, manifest: dict[str, Any]) -> list[Path]:
    result: list[Path] = []
    for patch in manifest.get("patches", []):
        if not patch.get("enabled", True):
            continue
        names: list[str] = []
        if patch.get("archive"):
            names.append(str(patch["archive"]))
        names.extend(str(value) for value in patch.get("chain", []))
        seen: set[str] = set()
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            path = root / "assets/asset-patch/active" / name
            if not path.is_file():
                raise PublishError(f"active manifest archive is missing: {path}")
            result.append(path)
    return result


def terminal_tables(
    root: Path,
    manifest: dict[str, Any],
) -> tuple[dict[str, bytes], dict[str, str]]:
    wanted = {member_name(logical): logical for logical in PAYLOAD_LOGICALS}
    values: dict[str, bytes] = {}
    sources: dict[str, str] = {}
    for archive_path in active_archives(root, manifest):
        with zipfile.ZipFile(archive_path) as archive:
            available = set(archive.namelist())
            for member, logical in wanted.items():
                if member in available:
                    values[logical] = archive.read(member)
                    sources[logical] = archive_path.name
    missing = set(PAYLOAD_LOGICALS) - set(values)
    if missing:
        raise PublishError(f"active terminal lacks required tables: {sorted(missing)}")
    return values, sources


def read_manifest(root: Path) -> tuple[dict[str, Any], bytes]:
    path = root / "assets/asset-patch/manifest.json"
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8-sig"))
    if value.get("cdn_version") != BASE_VERSION:
        raise PublishError(f"manifest is not at {BASE_VERSION}: {path}")
    if any(entry.get("id") == PATCH_ID for entry in value.get("patches", [])):
        raise PublishError(f"patch is already present: {path}")
    archive_path = root / "assets/asset-patch/active" / ARCHIVE_NAME
    if archive_path.exists():
        raise PublishError(f"target archive already exists: {archive_path}")
    return value, raw


def row(values: list[str]) -> str:
    return core.write_csv_lines([values])


def parsed_table(raw: bytes, logical: str) -> dict[str, Any]:
    value = quest.parse_node(raw)
    if not isinstance(value, dict):
        raise PublishError(f"table root is not an ordered map: {logical}")
    return value


def walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def patch_swimex_skill(raw_deflate: bytes, logical: str) -> bytes:
    raw = zlib.decompress(raw_deflate, -15)
    parsed = wf_dsl.parse_dsl(raw)
    nodes = [
        node for node in walk(parsed["tree"])
        if isinstance(node, list) and node and node[0] == "ACToleranceOfElement"
    ]
    expected = [[
        "ACToleranceOfElement",
        [{"min": 1200, "max": 1200}],
        2,
        [{"min": -0.15, "max": -0.15}],
        [{"min": 1, "max": 1}],
    ]]
    if nodes != expected:
        raise PublishError(f"Swim EX resistance node drifted: {logical}: {nodes!r}")
    element_numbers = [
        number for number in parsed["numbers"]
        if number["type"] == "int"
        and number["value"] == 2
        and str(number["ctx"]).endswith("ACToleranceOfElement")
    ]
    if len(element_numbers) != 1:
        raise PublishError(
            f"Swim EX resistance element leaf count drifted: {logical}: "
            f"{element_numbers!r}"
        )
    patched, _log = wf_dsl.patch_numbers(raw, [{**element_numbers[0], "value": 3}])
    patched_nodes = [
        node for node in walk(wf_dsl.parse_dsl(patched)["tree"])
        if isinstance(node, list) and node and node[0] == "ACToleranceOfElement"
    ]
    if patched_nodes != [[
        "ACToleranceOfElement",
        [{"min": 1200, "max": 1200}],
        3,
        [{"min": -0.15, "max": -0.15}],
        [{"min": 1, "max": 1}],
    ]]:
        raise PublishError(f"Swim EX thunder fix readback failed: {logical}")
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(patched) + compressor.flush()


def require_absent(table: dict[str, Any], key: str, logical: str) -> None:
    if key in table:
        raise PublishError(f"target key already exists: {logical}/{key}")


def build_payloads(
    terminal: dict[str, bytes],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    tables = {
        logical: copy.deepcopy(parsed_table(terminal[logical], logical))
        for logical in TABLE_LOGICALS
    }

    folders = tables[EVENT_FOLDER_LOGICAL]
    folder_events = tables[EVENT_FOLDER_EVENTS_LOGICAL]
    event_list = tables[EVENT_LIST_LOGICAL]
    unlocks = tables[GAME_UNLOCK_LOGICAL]
    conditions = tables[GAME_UNLOCK_CONDITION_LOGICAL]
    rush_quests = tables[RUSH_QUEST_LOGICAL]
    ui_strings = tables[UI_STRING_LOGICAL]

    require_absent(folders, FOLDER_ID, EVENT_FOLDER_LOGICAL)
    require_absent(folder_events, FOLDER_ID, EVENT_FOLDER_EVENTS_LOGICAL)
    require_absent(unlocks, UNLOCK_ID, GAME_UNLOCK_LOGICAL)
    require_absent(conditions, UNLOCK_CONDITION_ID, GAME_UNLOCK_CONDITION_LOGICAL)
    require_absent(ui_strings, UNLOCK_MESSAGE_ID, UI_STRING_LOGICAL)
    require_absent(ui_strings, UNLOCK_SHORT_MESSAGE_ID, UI_STRING_LOGICAL)

    expected_event_rows = {
        FANTASY_EVENT_ID: ["11", FANTASY_EVENT_ID, "900098"],
        DEEP_ABYSS_EVENT_ID: ["11", DEEP_ABYSS_EVENT_ID, "700099"],
    }
    for event_id, expected in expected_event_rows.items():
        current = event_list.get(event_id)
        if not isinstance(current, str) or core.read_csv_lines(current) != [expected]:
            raise PublishError(f"direct event-list row drifted: {event_id}")

    folders[FOLDER_ID] = row([
        FOLDER_STRING_ID,
        "quest/event/banner/rush_event/mod_fifteen_stage_banner_001",
        "quest/event/background/rush_event/combat_diver_01_background",
        "RushEvent",
        UNLOCK_ID,
        "false",
        "900099",
    ])
    folder_events[FOLDER_ID] = {
        "1": row(["11", FANTASY_EVENT_ID, "2"]),
        "2": row(["11", DEEP_ABYSS_EVENT_ID, "1"]),
    }
    del event_list[FANTASY_EVENT_ID]
    del event_list[DEEP_ABYSS_EVENT_ID]

    unlocks[UNLOCK_ID] = row([
        UNLOCK_CONDITION_ID,
        UNLOCK_MESSAGE_ID,
        UNLOCK_SHORT_MESSAGE_ID,
        "1",
    ])
    conditions[UNLOCK_CONDITION_ID] = {
        "1": row([
            "(None)", "", "", "", "(None)",
            "(None)", "", "", "", "(None)",
            "(None)", "", "", "", "(None)", MIN_PLAYER_RANK,
        ])
    }
    ui_strings[UNLOCK_MESSAGE_ID] = core.write_csv_lines([[
        "玩家等级达到::need_player_rank::后，解锁幻想连战与深渊连战。"
    ]])
    ui_strings[UNLOCK_SHORT_MESSAGE_ID] = core.write_csv_lines([[
        "玩家等级达到::need_player_rank::"
    ]])

    changed_quest_rows: dict[str, list[str]] = {}
    for event_id in (FANTASY_EVENT_ID, DEEP_ABYSS_EVENT_ID):
        event_quests = rush_quests.get(event_id)
        if not isinstance(event_quests, dict) or not event_quests:
            raise PublishError(f"Rush quest group is missing: {event_id}")
        changed_quest_rows[event_id] = []
        for quest_key, encoded in event_quests.items():
            if not isinstance(encoded, str):
                raise PublishError(f"Rush quest row is not CSV: {event_id}/{quest_key}")
            parsed = core.read_csv_lines(encoded)
            if len(parsed) != 1 or len(parsed[0]) != 103:
                raise PublishError(f"Rush quest row shape drifted: {event_id}/{quest_key}")
            cells = parsed[0]
            if cells[48] != "(None)":
                raise PublishError(
                    f"selectable_player_rank already changed: {event_id}/{quest_key}={cells[48]}"
                )
            cells[48] = MIN_PLAYER_RANK
            event_quests[quest_key] = row(cells)
            changed_quest_rows[event_id].append(quest_key)

    payloads = {
        member_name(logical): quest.build_node(tables[logical])
        for logical in TABLE_LOGICALS
    }
    for logical in SWIMEX_SKILL_LOGICALS:
        payloads[member_name(logical)] = patch_swimex_skill(terminal[logical], logical)
    for logical in TABLE_LOGICALS:
        rebuilt = payloads[member_name(logical)]
        if quest.parse_node(rebuilt) != tables[logical]:
            raise PublishError(f"table build/readback failed: {logical}")
        if rebuilt == terminal[logical]:
            raise PublishError(f"expected table did not change: {logical}")

    verify_payloads(payloads)
    return payloads, {
        "folder_id": int(FOLDER_ID),
        "children": [int(FANTASY_EVENT_ID), int(DEEP_ABYSS_EVENT_ID)],
        "minimum_player_rank": int(MIN_PLAYER_RANK),
        "rush_quest_rows": {
            event_id: len(keys) for event_id, keys in changed_quest_rows.items()
        },
        "advent_multiplayer_quests_changed": False,
        "swimex_resistance_down": {
            "target": "thunder",
            "value": -0.15,
            "duration_frames": 1200,
            "skill_levels": [1, 2],
        },
    }


def verify_payloads(payloads: dict[str, bytes]) -> None:
    decoded = {
        logical: parsed_table(payloads[member_name(logical)], logical)
        for logical in TABLE_LOGICALS
    }
    folders = decoded[EVENT_FOLDER_LOGICAL]
    children = decoded[EVENT_FOLDER_EVENTS_LOGICAL]
    event_list = decoded[EVENT_LIST_LOGICAL]
    unlocks = decoded[GAME_UNLOCK_LOGICAL]
    conditions = decoded[GAME_UNLOCK_CONDITION_LOGICAL]
    rush_quests = decoded[RUSH_QUEST_LOGICAL]
    ui_strings = decoded[UI_STRING_LOGICAL]

    if core.read_csv_lines(folders[FOLDER_ID])[0][4] != UNLOCK_ID:
        raise PublishError("EventFolder unlock binding readback failed")
    expected_children = {
        "1": ["11", FANTASY_EVENT_ID, "2"],
        "2": ["11", DEEP_ABYSS_EVENT_ID, "1"],
    }
    for key, expected in expected_children.items():
        if core.read_csv_lines(children[FOLDER_ID][key]) != [expected]:
            raise PublishError(f"EventFolder child readback failed: {key}")
    if FANTASY_EVENT_ID in event_list or DEEP_ABYSS_EVENT_ID in event_list:
        raise PublishError("direct event-list entries remain after folder migration")
    if core.read_csv_lines(unlocks[UNLOCK_ID])[0][:3] != [
        UNLOCK_CONDITION_ID, UNLOCK_MESSAGE_ID, UNLOCK_SHORT_MESSAGE_ID
    ]:
        raise PublishError("game-system unlock readback failed")
    condition = core.read_csv_lines(conditions[UNLOCK_CONDITION_ID]["1"])[0]
    if len(condition) != 16 or condition[15] != MIN_PLAYER_RANK:
        raise PublishError("rank-130 unlock condition readback failed")
    if "::need_player_rank::" not in core.read_csv_lines(ui_strings[UNLOCK_MESSAGE_ID])[0][0]:
        raise PublishError("unlock UI string readback failed")
    for event_id in (FANTASY_EVENT_ID, DEEP_ABYSS_EVENT_ID):
        for quest_key, encoded in rush_quests[event_id].items():
            cells = core.read_csv_lines(encoded)[0]
            if cells[48] != MIN_PLAYER_RANK:
                raise PublishError(
                    f"Rush selectable rank readback failed: {event_id}/{quest_key}"
                )
    for logical in SWIMEX_SKILL_LOGICALS:
        raw = zlib.decompress(payloads[member_name(logical)], -15)
        nodes = [
            node for node in walk(wf_dsl.parse_dsl(raw)["tree"])
            if isinstance(node, list) and node and node[0] == "ACToleranceOfElement"
        ]
        if len(nodes) != 1 or nodes[0][2] != 3:
            raise PublishError(f"Swim EX thunder resistance readback failed: {logical}")


def build_archive(payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for member in sorted(payloads):
            if not member.startswith("production/upload/") or ".." in member:
                raise PublishError(f"unsafe/non-active archive member: {member}")
            info = zipfile.ZipInfo(member, (2026, 8, 18, 23, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[member])
    raw = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != sorted(payloads):
            raise PublishError("archive member order/readback failed")
        for member, expected in payloads.items():
            if archive.read(member) != expected:
                raise PublishError(f"archive payload readback failed: {member}")
    return raw


def updated_manifest(
    manifest: dict[str, Any],
    archive_raw: bytes,
    payloads: dict[str, bytes],
) -> bytes:
    value = copy.deepcopy(manifest)
    value["patches"].append({
        "id": PATCH_ID,
        "type": "patch",
        "name": "连战活动文件夹与130级入口 1.4.83",
        "description": (
            "将幻想连战与深渊连战收入同一个活动文件夹，统一采用玩家等级130级的入口限制；"
            "幻想连战多人救援参战不受该限制。"
        ),
        "version": PATCH_VERSION,
        "depends_on": BASE_VERSION,
        "enabled": True,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive_raw),
        "files": sorted(payloads),
        "changes": [
            "移除幻想连战（700098）与深渊连战（700099）的两个活动直达入口，改为同一个活动文件夹内的两个子入口。",
            "共同活动文件夹的解锁等级设为130级，并新增对应中文锁定提示。",
            "两套Rush单人关卡的selectable_player_rank统一设为130级，防止客户端深链绕过外层入口。",
            "幻想连战Advent多人关卡未写入等级限制，低等级玩家仍可通过救援加入高等级玩家创建的房间。",
            "泳皇女 EX（139997）主动技能低生命分支的全体敌人耐性降低由误配的水属性修正为雷属性；数值仍为-15%，持续20秒。",
        ],
        "created_at": "2026-08-18",
        "archive_integrity": [{
            "name": ARCHIVE_NAME,
            "size": len(archive_raw),
            "sha256": sha256_bytes(archive_raw),
            "members": len(payloads),
        }],
    })
    value["cdn_version"] = PATCH_VERSION
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def updated_changelog(raw: bytes) -> bytes:
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    marker = f"|---|---|---|---|---|---|{newline}"
    if marker not in text:
        raise PublishError("asset patch changelog table header drifted")
    rows = (
        f"| 2026-08-18 | event_folder | 2 | 幻想连战与深渊连战合并为一个活动文件夹 | 1.4.83 | active增量包 |{newline}"
        f"| 2026-08-18 | unlock/rush_quest | 700098/700099 | 共同入口与Rush单人关卡设为130级；多人救援不受限 | 1.4.83 | active增量包 |{newline}"
        f"| 2026-08-18 | action_skill | 139997 | 泳皇女 EX 主动技能耐性降低由水属性修正为雷属性 | 1.4.83 | active增量包 |{newline}"
    )
    return text.replace(marker, marker + rows, 1).encode("utf-8")


def atomic_write(raw: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".gauntlet-hub-1.4.83.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)


def assert_target(root: Path, target: Path) -> None:
    target.resolve(strict=False).relative_to(root.resolve(strict=True))


def build_targets(
    root: Path,
    label: str,
    manifest_raw: bytes,
    changelog_raw: bytes,
    archive_raw: bytes,
    payloads: dict[str, bytes],
) -> dict[str, tuple[Path, bytes, Path]]:
    result: dict[str, tuple[Path, bytes, Path]] = {}

    def add(name: str, path: Path, raw: bytes) -> None:
        assert_target(root, path)
        key = f"{label}-{name}"
        if key in result or path in (entry[0] for entry in result.values()):
            raise PublishError(f"duplicate publication target: {path}")
        result[key] = (path, raw, root)

    add("active-archive", root / "assets/asset-patch/active" / ARCHIVE_NAME, archive_raw)
    for logical in PAYLOAD_LOGICALS:
        add(f"live-{core.sha1_path(logical)}", live_path(root, logical), payloads[member_name(logical)])
    add("changelog", root / "assets/asset-patch/changelog.md", changelog_raw)
    add("manifest", root / "assets/asset-patch/manifest.json", manifest_raw)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    source_manifest, source_manifest_current = read_manifest(SOURCE_ROOT)
    deploy_manifest, deploy_manifest_current = read_manifest(DEPLOY_ROOT)
    if source_manifest != deploy_manifest or source_manifest_current != deploy_manifest_current:
        raise PublishError("source and local runtime manifests differ")

    source_terminal, source_sources = terminal_tables(SOURCE_ROOT, source_manifest)
    deploy_terminal, deploy_sources = terminal_tables(DEPLOY_ROOT, deploy_manifest)
    if source_terminal != deploy_terminal:
        raise PublishError("source and local runtime terminal client tables differ")

    payloads, effects = build_payloads(source_terminal)
    archive_raw = build_archive(payloads)
    manifest_raw = updated_manifest(source_manifest, archive_raw, payloads)

    source_changelog_path = SOURCE_ROOT / "assets/asset-patch/changelog.md"
    deploy_changelog_path = DEPLOY_ROOT / "assets/asset-patch/changelog.md"
    if source_changelog_path.read_bytes() != deploy_changelog_path.read_bytes():
        raise PublishError("source and local runtime changelogs differ")
    changelog_raw = updated_changelog(source_changelog_path.read_bytes())

    report: dict[str, Any] = {
        "apply": args.apply,
        "from_version": BASE_VERSION,
        "version": PATCH_VERSION,
        "patch_id": PATCH_ID,
        "archive": ARCHIVE_NAME,
        "archive_size": len(archive_raw),
        "archive_sha256": sha256_bytes(archive_raw),
        "members": sorted(payloads),
        "effects": effects,
        "terminal_sources": source_sources,
        "runtime_terminal_sources": deploy_sources,
        "cdn_archive_directory": "assets/asset-patch/active",
        "wrote_dot_cdn": False,
    }
    if not args.apply:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    targets: dict[str, tuple[Path, bytes, Path]] = {}
    targets.update(build_targets(
        SOURCE_ROOT, "source", manifest_raw, changelog_raw, archive_raw, payloads,
    ))
    targets.update(build_targets(
        DEPLOY_ROOT, "runtime", manifest_raw, changelog_raw, archive_raw, payloads,
    ))

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_ROOT / f"gauntlet-hub-rank130-1.4.83-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    existence: dict[str, bool] = {}
    for label, (path, _raw, _root) in targets.items():
        existence[label] = path.is_file()
        if existence[label]:
            destination = backup / label
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    (backup / "existence.json").write_text(
        json.dumps(existence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    try:
        for label, (path, raw, _root) in targets.items():
            if label.endswith("-manifest"):
                continue
            atomic_write(raw, path)
        for label, (path, raw, _root) in targets.items():
            if label.endswith("-manifest"):
                atomic_write(raw, path)

        for label, (path, expected, _root) in targets.items():
            if not path.is_file() or path.read_bytes() != expected:
                raise PublishError(f"publication readback failed: {label}")
        for root in (SOURCE_ROOT, DEPLOY_ROOT):
            written = json.loads(
                (root / "assets/asset-patch/manifest.json").read_text(encoding="utf-8-sig")
            )
            matches = [entry for entry in written["patches"] if entry.get("id") == PATCH_ID]
            if written.get("cdn_version") != PATCH_VERSION or len(matches) != 1:
                raise PublishError(f"manifest readback failed: {root}")
            with zipfile.ZipFile(root / "assets/asset-patch/active" / ARCHIVE_NAME) as archive:
                if archive.namelist() != sorted(payloads):
                    raise PublishError(f"archive member readback failed: {root}")
                for member, expected in payloads.items():
                    if archive.read(member) != expected:
                        raise PublishError(f"archive payload readback failed: {root}/{member}")
    except Exception:
        for label, (path, _raw, root) in reversed(list(targets.items())):
            assert_target(root, path)
            if existence[label]:
                atomic_write((backup / label).read_bytes(), path)
            elif path.exists():
                path.unlink()
        raise

    report["backup"] = str(backup)
    (backup / "receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
