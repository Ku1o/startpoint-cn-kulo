# -*- coding: utf-8 -*-
"""主线 boss 的降临讨伐关卡候选包生成器。

模板 = 机兵降临讨伐节点 60（5 档难度）。每个 boss 生成：
  - boss_battle_quest['1'][节点] 5 行（首档前置 = 该 boss 的主线关卡，其后逐档解锁）
  - boss_battle_stage_node['1'][节点] 1 行（降临讨伐分组，沿用机兵币商店分类 60）
  - field_data / zone 各 1 行（zone 原样复制主线关卡的 boss 配置）
  - 联机地形 1 个：主线地形只有 3 个复活位，联机按三人分 9 个，补 6 个

只读 live 数据（.cdn + active 链），产物写到 --out，不碰 store。
用法：
  python tools/fantasy-gauntlet-mod-tools/build_mainboss_battle_candidate.py --boss epuration --out <目录>
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import sys
import zipfile
import zlib
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOD_DIR))
import wf_dsl  # noqa: E402
import wf_quest_lib as q  # noqa: E402

TEMPLATE_NODE = "60"
SHOP_CATEGORY = "60"

BOSSES = {
    "epuration": {
        "node": "80",
        "name": "歼灭者",
        "main": ("9", "5", "2"),
        "main_multiplied_id": "9005002",
        "main_field": "main_9_5_2",
        "key": "mod_mainboss_epuration",
        "terrain": "battle/terrain/multi_normal_quest/mod_main_boss/boss_battle_epuration",
        "thumbnail": "quest/thumbnail/world_9/battle_9_5_2",
        "bgm": "world09_battle_epuration_boss",
        "element": "5",
    },
}

# 联机复活位：沿用领主战不死王地形（同为 272 宽主线板型）的上半区坐标。
EXTRA_COFFINS = [
    (130.5, 62.174), (150.334, 64.1739), (105.962, 58.9548),
    (184.296, 83.219), (181.5, 133.0), (132.008, 181.719),
]


def _row(text: str) -> list[str]:
    return next(csv.reader([text]))


def _join(row: list[str]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(row)
    return buf.getvalue()


def hashed_member(logical: str) -> str:
    digest = hashlib.sha1((logical + q.SALT).encode("utf-8")).hexdigest()
    return f"production/upload/{digest[:2]}/{digest[2:]}"


def quest_id(node: str, index: int) -> int:
    return 1000000 + int(node) * 1000 + index


def build(spec: dict) -> dict[str, bytes]:
    node = spec["node"]
    files: dict[str, bytes] = {}

    bb = q.load_table("master/quest/boss_battle_quest.orderedmap")
    if node in bb["1"]:
        raise SystemExit(f"boss_battle_quest 已有节点 {node}")
    rows = {}
    for key, text in bb["1"][TEMPLATE_NODE].items():
        row = _row(text)
        index = int(key)
        row[0] = str(quest_id(node, index))
        row[2] = f"{spec['name']} ::quest_rank::"
        row[3] = spec["thumbnail"]
        row[5] = "2000-01-01 00:00:00"
        if index == 1:
            row[7:12] = ["0", *spec["main"], spec["main_multiplied_id"]]
        else:
            row[7:12] = ["2", "1", node, str(index - 1), str(quest_id(node, index - 1))]
        row[72] = spec["element"]
        row[109] = spec["key"]
        row[110] = spec["bgm"]
        rows[key] = _join(row)
    bb["1"][node] = rows
    files["master/quest/boss_battle_quest.orderedmap"] = q.build_node(bb)

    sn = q.load_table("master/quest/boss_battle_stage_node.orderedmap")
    row = _row(sn["1"][TEMPLATE_NODE])
    row[1] = f"{spec['name']}讨伐"
    row[3] = "(None)"
    row[6] = SHOP_CATEGORY
    row[11] = spec["thumbnail"]
    sn["1"][node] = _join(row)
    files["master/quest/boss_battle_stage_node.orderedmap"] = q.build_node(sn)

    fd = q.load_table("master/battle/field_data.orderedmap")
    zn = q.load_table("master/battle/zone.orderedmap")
    if spec["key"] in fd or spec["key"] in zn:
        raise SystemExit(f"field/zone 已有 {spec['key']}")
    main_field = _row(fd[spec["main_field"]])
    fd[spec["key"]] = _join([main_field[0], spec["terrain"], spec["key"]])
    zn[spec["key"]] = copy.deepcopy(zn[main_field[2]])
    files["master/battle/field_data.orderedmap"] = q.build_node(fd)
    files["master/battle/zone.orderedmap"] = q.build_node(zn)

    raw = q.read_raw(main_field[1] + ".amf3.deflate")
    terrain = wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]
    if len(terrain["layers"]) != 1:
        raise SystemExit("只处理单层地形；多波地形每层都要补复活位")
    objects = terrain["layers"][0]["objects"]
    coffins = [o for o in objects if o["type"] == "COFFIN"]
    if len(coffins) != 3:
        raise SystemExit(f"主线地形复活位数 {len(coffins)}，预期 3")
    next_id = max(o["id"] for o in objects) + 1
    at = objects.index(coffins[-1]) + 1
    for i, (x, y) in enumerate(EXTRA_COFFINS):
        coffin = copy.deepcopy(coffins[0])
        coffin.update(id=next_id + i, x=x, y=y)
        objects.insert(at + i, coffin)
    if "nextobjectid" in terrain:
        terrain["nextobjectid"] = max(terrain["nextobjectid"], next_id + len(EXTRA_COFFINS))
    encoded = wf_dsl.encode_amf3(terrain)
    if wf_dsl.parse_dsl(encoded)["tree"] != terrain:
        raise SystemExit("地形编码往返不一致")
    deflater = zlib.compressobj(9, zlib.DEFLATED, -15)
    files[spec["terrain"] + ".amf3.deflate"] = deflater.compress(encoded) + deflater.flush()

    for logical, data in files.items():
        if logical.endswith(".orderedmap") and not isinstance(q.parse_node(data), dict):
            raise SystemExit(f"{logical} 重解析失败")
    return files


def write_zip(files: dict[str, bytes], path: Path) -> dict:
    members = {hashed_member(lp): data for lp, data in files.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            archive.writestr(name, members[name])
    blob = path.read_bytes()
    return {
        "name": path.name,
        "size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "members": len(members),
        "files": sorted(members),
        "member_sha256": {n: hashlib.sha256(members[n]).hexdigest() for n in sorted(members)},
        "logical_paths": {hashed_member(lp): lp for lp in sorted(files)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--boss", choices=sorted(BOSSES), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--archive-name")
    args = parser.parse_args()
    spec = BOSSES[args.boss]
    name = args.archive_name or f"mainboss-{args.boss}.zip"
    integrity = write_zip(build(spec), args.out / name)
    (args.out / f"mainboss-{args.boss}.integrity.json").write_text(
        json.dumps(integrity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: integrity[k] for k in ("name", "size", "sha256", "members")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
