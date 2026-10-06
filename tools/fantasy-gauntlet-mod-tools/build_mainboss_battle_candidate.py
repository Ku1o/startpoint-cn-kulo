# -*- coding: utf-8 -*-
"""主线大型 boss 的「领主战 + 共同决战」候选包生成器。

每个 boss 生成两套：
  领主战：boss_battle_quest['1'][节点] 5 行，逐列套机兵节点 60 的 5 档难度（Lv20-100）；
          首档前置 = 该 boss 的主线关卡，其后逐档解锁。入口行套领主战节点 3（领主战分组），
          领主币商店分类沿用 3。
  共同决战：hard_multi_event / hard_multi_event_quest 各 1 行，套「共同决战【暗凛机兵】」(1006)；
          无前置、常驻可见，挂在活动页「终始之战」分组里；敌人 Lv100、boss 血量 ×HARD_HP、攻击 ×HARD_ATK。
          活动横幅/活动 logo/boss 战小横幅用 assets/mainboss_art 的自制图，其余（背景动画、战斗图）暂借机兵。
  两套共用：field_data / zone（原样复制主线关卡 boss 配置），联机地形（主线 3 个复活位补到 9 个）。

只读 live 数据（.cdn + active 链），产物写到 --out，不碰 store。
用法：
  python tools/fantasy-gauntlet-mod-tools/build_mainboss_battle_candidate.py --boss epuration org --out <目录>
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

TEMPLATE_NODE = "60"        # 关卡行：机兵降临讨伐 5 档
TEMPLATE_STAGE_NODE = "3"   # 入口行：领主战·不死王
SHOP_CATEGORY = "3"
TEMPLATE_HARD_EVENT = "1006"  # 共同决战【暗凛机兵】
EVENT_FOLDER = "2"          # 活动页「终始之战」分组（原先只收三个连战）
HARD_HP = "1.5"
HARD_ATK = "1.3"

BOSSES = {
    "epuration": {
        "node": "80",
        "name": "歼灭者",
        "main": ("9", "5", "2"),
        "main_multiplied_id": "9005002",
        "main_field": "main_9_5_2",
        "field": "mod_mainboss_epuration",
        "terrain": "battle/terrain/multi_normal_quest/mod_main_boss/boss_battle_epuration",
        "thumbnail": "quest/thumbnail/world_9/battle_9_5_2",
        "bgm": "world09_battle_epuration_boss",
        "element": "5",
        "art": "epu",
    },
    "org": {
        "node": "81",
        "name": "丑王奥格",
        "main": ("8", "14", "1"),
        "main_multiplied_id": "8014001",
        "main_field": "main_8_14_1",
        "field": "mod_mainboss_org",
        "terrain": "battle/terrain/multi_normal_quest/mod_main_boss/boss_battle_org",
        "thumbnail": "quest/thumbnail/world_hell/battle_8_14_1",
        "bgm": "hell_battle_lastboss",
        "element": "4",
        "art": "org",
    },
    "maou2": {
        "node": "82",
        "name": "魔王",
        "main": ('7', '14', '2'),
        "main_multiplied_id": "7014002",
        "main_field": "main_7_14_2",
        "field": "mod_mainboss_maou2",
        "terrain": "battle/terrain/multi_normal_quest/mod_main_boss/boss_battle_maou2",
        "thumbnail": "quest/thumbnail/world_light/battle_7_14_2",
        "bgm": "seven_battle_boss_zone2",
        "element": "4",
        "art": "maou2",
    },
    "high_epuration": {
        "node": "83",
        "name": "上位歼灭者",
        "main": ('9', '9', '2'),
        "main_multiplied_id": "9009002",
        "main_field": "main_9_9_2",
        "field": "mod_mainboss_high_epu",
        "terrain": "battle/terrain/multi_normal_quest/mod_main_boss/boss_battle_high_epu",
        "thumbnail": "quest/thumbnail/world_9/battle_9_9_2",
        "bgm": "world09_battle_high_epuration_boss",
        "element": "5",
        "art": "high_epu",
    },
    "benzaiten": {
        "node": "84",
        "name": "形似弁天的魔物",
        "main": ('10', '8', '1'),
        "main_multiplied_id": "10008001",
        "main_field": "main_10_8_1",
        "field": "mod_mainboss_benzaiten",
        "terrain": "battle/terrain/multi_normal_quest/mod_main_boss/boss_battle_benzaiten",
        "thumbnail": "quest/thumbnail/world_10/battle_10_8_1",
        "bgm": "world_10_battle_benten",
        "element": "2",
        "art": "benzaiten",
    },
    "variant_epuration": {
        "node": "85",
        "name": "异形歼灭者",
        "main": ('10', '14', '1'),
        "main_multiplied_id": "10014001",
        "main_field": "main_10_14_1",
        "field": "mod_mainboss_variant_epu",
        "terrain": "battle/terrain/multi_normal_quest/mod_main_boss/boss_battle_variant_epu",
        "thumbnail": "quest/thumbnail/world_10/battle_10_14_1",
        "bgm": "world_10_battle_syukusei",
        "element": "1",
        "art": "variant_epu",
    },
    "star_devourer": {
        "node": "86",
        "name": "吞噬星辰之物",
        "main": ('11', '6', '2'),
        "main_multiplied_id": "11006002",
        "main_field": "main_11_6_2",
        "field": "mod_mainboss_star_devourer",
        "terrain": "battle/terrain/multi_normal_quest/mod_main_boss/boss_battle_star_devourer",
        "thumbnail": "quest/thumbnail/world_11/battle_11_6_2",
        "bgm": "world_11_battle_middle_boss",
        "element": "5",
        "art": "star_devourer",
    },
    "cursed_blade": {
        "node": "87",
        "name": "咒剑",
        "main": ('12', '4', '1'),
        "main_multiplied_id": "12004001",
        "main_field": "main_12_2_4",
        "field": "mod_mainboss_cursed_blade",
        "terrain": "battle/terrain/multi_normal_quest/mod_main_boss/boss_battle_cursed_blade",
        "thumbnail": "quest/thumbnail/world_12/battle_12_2",
        "bgm": "world_12_battle_middle_boss",
        "element": "5",
        "art": "cursed_blade",
        "wave": "1",
    },
    "origin_dragon": {
        "node": "88",
        "name": "终始之龙",
        "main": ('12', '10', '1'),
        "main_multiplied_id": "12010001",
        "main_field": "main_12_10_01",
        "field": "mod_mainboss_origin_dragon",
        "terrain": "battle/terrain/multi_normal_quest/mod_main_boss/boss_battle_origin_dragon",
        "thumbnail": "quest/thumbnail/world_12/battle_12_5",
        "bgm": "world_12_battle_boss",
        "element": "5",
        "art": "origin_dragon",
    },
}

# 已有降临讨伐节点的 boss：只加共同决战（hard_multi_event），沿用其最高档关卡的场地与 zone。
EXISTING_BOSSES = {
    "queen_water": {"node": "35", "name": "青之女王", "field": "multi_normal_1_22_4", "thumbnail": "quest/thumbnail/multi_battle/multi_pick_22_4", "bgm": "multi_pickup_empress_01_boss", "element": "2", "art": "queen_water", "existing": True},
    "queen_fire": {"node": "37", "name": "赤之女王", "field": "multi_reine_rouge_4", "thumbnail": "quest/thumbnail/multi_battle/multi_pick_31_4", "bgm": "multi_pickup_empress_02_boss", "element": "1", "art": "queen_fire", "existing": True},
    "queen_wind": {"node": "38", "name": "碧之女王", "field": "multi_variant_empress_wind_5", "thumbnail": "quest/thumbnail/advent_event/variant_empress_wind/5", "bgm": "multi_pickup_empress_03_boss", "element": "0", "art": "queen_wind", "existing": True},
    "queen_light": {"node": "39", "name": "皓之女王", "field": "multi_variant_empress_light_5", "thumbnail": "quest/thumbnail/advent_event/variant_empress_light/5", "bgm": "advent_variant_empress_light", "element": "5", "art": "queen_light", "existing": True},
    "queen_thunder": {"node": "40", "name": "金之女王", "field": "multi_variant_empress_thunder", "thumbnail": "quest/thumbnail/advent_event/variant_empress_thunder/5", "bgm": "advent_variant_empress_thunder_battle", "element": "3", "art": "queen_thunder", "existing": True},
    "queen_dark": {"node": "41", "name": "墨之女王", "field": "multi_variant_empress_dark_5", "thumbnail": "quest/thumbnail/advent_event/variant_empress_dark/5", "bgm": "advent_variant_empress_dark_battle", "element": "4", "art": "queen_dark", "existing": True},
    "dragon_thunder": {"node": "25", "name": "伊尔考普斯", "field": "advent_event_multi_advent_discarded_dragon_thunder_single_4", "thumbnail": "quest/thumbnail/advent_event/dragon_thunder/4", "bgm": "end_hairyu_thunder_battle_zone2", "element": "3", "art": "dragon_thunder", "existing": True},
    "dragon_fire": {"node": "26", "name": "伊萨巴迪卡", "field": "advent_event_discarded_dragon_fire_4", "thumbnail": "quest/thumbnail/advent_event/dragon_fire/4", "bgm": "advent_discarded_dragon_fire", "element": "1", "art": "dragon_fire", "existing": True},
    "dragon_water": {"node": "27", "name": "伊劳德雷斯", "field": "advent_event_discarded_dragon_water_re_lv80", "thumbnail": "quest/thumbnail/advent_event/dragon_water/4", "bgm": "advent_discarded_dragon_water", "element": "2", "art": "dragon_water", "existing": True},
    "dragon_wind": {"node": "28", "name": "伊尔格拉乌", "field": "advent_event_discarded_dragon_wind_4", "thumbnail": "quest/thumbnail/advent_event/dragon_wind/4", "bgm": "advent_discarded_dragon_wind", "element": "0", "art": "dragon_wind", "existing": True},
    "dragon_light": {"node": "29", "name": "伊尔梅塔雷", "field": "advent_event_discarded_dragon_light_4", "thumbnail": "quest/thumbnail/advent_event/dragon_light/4", "bgm": "advent_discarded_dragon_light", "element": "5", "art": "dragon_light", "existing": True},
    "dragon_dark": {"node": "30", "name": "伊尔昂斯拉", "field": "advent_event_discarded_dragon_dark_4", "thumbnail": "quest/thumbnail/advent_event/dragon_dark/4", "bgm": "advent_discarded_dragon_dark", "element": "4", "art": "dragon_dark", "existing": True},
    "beast_fire": {"node": "51", "name": "火魔奥尔塔尼亚", "field": "advent_spirit_beast_fire_1", "thumbnail": "quest/thumbnail/advent_event/spirit_beast_fire/5", "bgm": "advent_spirit_beast_fire_battle", "element": "1", "art": "beast_fire", "existing": True},
    "beast_water": {"node": "52", "name": "水鬼斯拉姆冈", "field": "advent_spirit_beast_water_4", "thumbnail": "quest/thumbnail/advent_event/spirit_beast_water/5", "bgm": "advent_spirit_beast_water_battle", "element": "2", "art": "beast_water", "existing": True},
    "beast_thunder": {"node": "53", "name": "雷龟普罗格雷奥", "field": "advent_spirit_beast_thunder_4", "thumbnail": "quest/thumbnail/advent_event/spirit_beast_thunder/5", "bgm": "advent_spirit_beast_thunder_battle", "element": "3", "art": "beast_thunder", "existing": True},
    "beast_wind": {"node": "54", "name": "风师亚特摩西亚", "field": "advent_spirit_beast_wind_1", "thumbnail": "quest/thumbnail/advent_event/spirit_beast_storm/5", "bgm": "advent_spirit_beast_storm_battle", "element": "0", "art": "beast_wind", "existing": True},
    "beast_light": {"node": "55", "name": "光蛛杜梅欧", "field": "advent_spirit_beast_light", "thumbnail": "quest/thumbnail/advent_event/spirit_beast_light/5", "bgm": "advent_spirit_beast_light_battle", "element": "5", "art": "beast_light", "existing": True},
    "beast_dark": {"node": "56", "name": "暗凤希亚特利欧", "field": "advent_spirit_beast_dark_5", "thumbnail": "quest/thumbnail/advent_event/spirit_beast_dark/5", "bgm": "advent_spirit_beast_dark_battle", "element": "4", "art": "beast_dark", "existing": True},
}
BOSSES.update(EXISTING_BOSSES)

ART_DIR = MOD_DIR / "assets" / "mainboss_art"  # make_art.py 生成：列表横幅/活动 logo/boss 战小横幅

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


def hard_event_id(node: str) -> str:
    return str(2000 + int(node))


def build(specs: list[dict], extend=None) -> dict[str, bytes]:
    """extend(tables, files)：在共享表序列化之前调用，供 build_boss_weapon_sets 等叠加改动，
    保证 boss_battle_quest / stage_node / hard_multi_event(_quest) 只构建一次。
    tables 键为逻辑路径，值为本函数已改过的表对象（原地修改即可）。"""
    files: dict[str, bytes] = {}
    bb = q.load_table("master/quest/boss_battle_quest.orderedmap")
    sn = q.load_table("master/quest/boss_battle_stage_node.orderedmap")
    fd = q.load_table("master/battle/field_data.orderedmap")
    zn = q.load_table("master/battle/zone.orderedmap")
    he = q.load_table("master/quest/event/hard_multi_event.orderedmap")
    hq = q.load_table("master/quest/event/hard_multi_event_quest.orderedmap")
    ff = q.load_table("master/quest/event/event_folder_events.orderedmap")
    for spec in specs:
        if not spec.get("existing"):
            _add_boss(spec, bb, sn, fd, zn, files)
        _add_hard(spec, he, hq, fd, zn, files)
        folder = ff[EVENT_FOLDER]
        order = max(int(_row(r)[2]) for r in folder.values()) + 1
        folder[str(max(int(k) for k in folder) + 1)] = _join(["13", hard_event_id(spec["node"]), str(order)])
    if extend is not None:
        extend({
            "master/quest/boss_battle_quest.orderedmap": bb,
            "master/quest/boss_battle_stage_node.orderedmap": sn,
            "master/quest/event/hard_multi_event.orderedmap": he,
            "master/quest/event/hard_multi_event_quest.orderedmap": hq,
        }, files)
    files["master/quest/event/event_folder_events.orderedmap"] = q.build_node(ff)
    files["master/quest/event/hard_multi_event.orderedmap"] = q.build_node(he)
    files["master/quest/event/hard_multi_event_quest.orderedmap"] = q.build_node(hq)
    files["master/quest/boss_battle_quest.orderedmap"] = q.build_node(bb)
    files["master/quest/boss_battle_stage_node.orderedmap"] = q.build_node(sn)
    files["master/battle/field_data.orderedmap"] = q.build_node(fd)
    files["master/battle/zone.orderedmap"] = q.build_node(zn)
    for logical, data in files.items():
        if logical.endswith(".orderedmap") and not isinstance(q.parse_node(data), dict):
            raise SystemExit(f"{logical} 重解析失败")
    return files


def _add_boss(spec: dict, bb: dict, sn: dict, fd: dict, zn: dict, files: dict[str, bytes]) -> None:
    node = spec["node"]
    if node in bb["1"] or node in sn["1"]:
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
        row[109] = spec["field"]
        row[110] = spec["bgm"]
        rows[key] = _join(row)
    bb["1"][node] = rows

    row = _row(sn["1"][TEMPLATE_STAGE_NODE])
    row[1] = f"{spec['name']}讨伐"
    row[6] = SHOP_CATEGORY
    row[11] = spec["thumbnail"]
    if spec.get("art"):
        # 领主战页头（含 boss 名），模板节点 3 的是不死王瑞西塔尔，必须换成本 boss 的。
        row[12] = f"quest/boss_battle/background/mod_mainboss_{spec['art']}"
        files[row[12] + ".png"] = _store_png(ART_DIR / f"hdr_{spec['art']}.png")
    sn["1"][node] = _join(row)

    if spec["field"] in fd or spec["field"] in zn:
        raise SystemExit(f"field/zone 已有 {spec['field']}")
    main_field = _row(fd[spec["main_field"]])
    fd[spec["field"]] = _join([main_field[0], spec["terrain"], spec["field"]])
    wave = spec.get("wave", "0")
    # 多波主线关（如咒剑先打小怪）只保留 boss 那一波：地形留对应层并改名为 "0"，zone 同步。
    zn[spec["field"]] = {"0": copy.deepcopy(zn[main_field[2]][wave])}

    raw = q.read_raw(main_field[1] + ".amf3.deflate")
    terrain = wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]
    layer = next(L for L in terrain["layers"] if L.get("name") == wave)
    layer["name"] = "0"
    terrain["layers"] = [layer]
    objects = layer["objects"]
    coffins = [o for o in objects if o["type"] == "COFFIN"]
    if len(coffins) not in (3, 9):
        raise SystemExit(f"主线地形复活位数 {len(coffins)}，预期 3 或 9")
    # 主线剧情的助战角色（ASSIST_CHARACTER，如奥格关的两位公主）在三人房里每人一份，
    # 特效叠加拖帧，且不该出现在 boss 战里，一律去掉。
    objects[:] = [o for o in objects if not o["type"].startswith("ASSIST_CHARACTER")]
    next_id = max(o["id"] for o in objects) + 1
    at = objects.index(coffins[-1]) + 1
    for i, (x, y) in enumerate(EXTRA_COFFINS if len(coffins) == 3 else []):
        coffin = copy.deepcopy(coffins[0])
        coffin.update(id=next_id + i, x=x, y=y)
        objects.insert(at + i, coffin)
    if "nextobjectid" in terrain:
        terrain["nextobjectid"] = max(terrain["nextobjectid"], next_id + len(EXTRA_COFFINS))  # 只增不减，9 位时也安全
    encoded = wf_dsl.encode_amf3(terrain)
    if wf_dsl.parse_dsl(encoded)["tree"] != terrain:
        raise SystemExit("地形编码往返不一致")
    deflater = zlib.compressobj(9, zlib.DEFLATED, -15)
    files[spec["terrain"] + ".amf3.deflate"] = deflater.compress(encoded) + deflater.flush()


CDN_PNG_SIGNATURE = bytes([0x89]) + b"png\r\n\x1a\n"  # CDN 里的 PNG 签名为小写


def _event_scene(art: str, files: dict[str, bytes]) -> str:
    """活动页 boss 展示：用该 boss 关卡缩略图（boss 站在自己场地里）做单层像素场景。

    结构照抄机兵 hard_multi_steam_robot_dark/background：目录图集 + 两段式 .gen 帧名，
    整体 s=6（与机兵相同）。
    """
    from PIL import Image

    d = f"quest/event/animation_background/hard_multi/mod_mainboss_{art}"
    frame = f"{d}/.gen/background/a"
    # 缩略图本身就是 boss 站在自己场地里的 1:1 像素画（240×188），s=6 放大后正好铺满活动页上半屏。
    scene = Image.open(ART_DIR / f"thumb_{art}.png").convert("RGBA")
    buf = io.BytesIO()
    scene.save(buf, "PNG")
    data = buf.getvalue()
    files[f"{d}/mod_mainboss_{art}.png"] = CDN_PNG_SIGNATURE + data[8:]

    def deflate(tree) -> bytes:
        raw = wf_dsl.encode_amf3(tree)
        if wf_dsl.parse_dsl(raw)["tree"] != tree:
            raise SystemExit(f"{d} 编码往返不一致")
        z = zlib.compressobj(9, zlib.DEFLATED, -15)
        return z.compress(raw) + z.flush()

    files[f"{d}/mod_mainboss_{art}.atlas.amf3.deflate"] = deflate(
        [{"n": frame, "w": scene.width, "h": scene.height, "x": 0, "y": 0}])
    files[f"{d}/background.parts.amf3.deflate"] = deflate({
        "i": [{"s": False, "p": frame}],
        "g": [{"t": 7110, "s": [{"s": 0, "i": 0, "l": [{"m": 4351, "t": 7110}]}]}],
        "m": [],
        "a": [1],
        "o": [],
        "t": [{"a": 4096, "b": 0, "c": 0, "d": 4096, "x": 0, "y": 0},
              {"a": 4096, "b": 0, "c": 0, "d": 4096, "x": 0, "y": 0}],
        "c": [],
        "s": 6,
    })
    files[f"{d}/background.timeline.amf3.deflate"] = deflate({
        "sequences": [{"begin": 1, "end": 7110, "name": "start", "kind": "loop"}],
        "sounds": [], "points": [], "circles": [], "rectangles": [], "matrices": []})
    return f"{d}/background"


def _store_png(path: Path) -> bytes:
    """CDN 里的 PNG 签名是小写 \x89png；标准 \x89PNG 原样下发会让客户端报 C8105。"""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path} 不是 PNG")
    return b"\x89png" + data[4:]


def _add_hard(spec: dict, he: dict, hq: dict, fd: dict, zn: dict, files: dict[str, bytes]) -> None:
    event = hard_event_id(spec["node"])
    if event in he or event in hq:
        raise SystemExit(f"hard_multi_event 已有 {event}")
    hard_key = spec["field"] + "_hard"
    fd[hard_key] = _join([*_row(fd[spec["field"]])[:2], hard_key])
    zn[hard_key] = copy.deepcopy(zn[_row(fd[spec["field"]])[2]])

    row = _row(he[TEMPLATE_HARD_EVENT])
    row[0] = f"hard_multi_mainboss_{spec['field']}"
    row[2] = f"共同决战【{spec['name']}】"
    art = spec.get("art")
    if art:
        base = f"quest/event/{{}}/hard_multi/mod_mainboss_{art}"
        row[4] = base.format("banner")
        row[5] = base.format("bossbattle_banner")
        row[7] = base.format("logo")
        files[row[4] + ".png"] = _store_png(ART_DIR / f"banner_{art}.png")
        files[row[5] + ".png"] = _store_png(ART_DIR / f"bb_{art}.png")
        files[row[7] + ".png"] = _store_png(ART_DIR / f"logo_{art}.png")
        row[6] = _event_scene(art, files)
    row[23] = "2000-01-01 00:00:00"
    he[event] = _join(row)

    row = _row(hq[TEMPLATE_HARD_EVENT]["1"])
    row[0] = f"{event}001"
    row[2] = f"{spec['name']} ::quest_rank::"
    row[3] = spec["thumbnail"]
    row[5] = "2000-01-01 00:00:00"
    # 可见条件清空：有前置时活动在「未通关」页直接隐藏，玩家找不到入口。
    row[7:17] = ["(None)", "", "", "", "(None)"] * 2
    row[69] = spec["element"]  # 限定属性编队（机兵共同决战同款），取该 boss 的推荐属性
    row[73] = spec["element"]
    row[98:101] = [HARD_HP] * 3
    row[101:104] = [HARD_ATK] * 3
    row[107] = "100"
    row[110] = hard_key
    row[111] = spec["bgm"]
    hq[event] = {"1": _join(row)}


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
    parser.add_argument("--boss", choices=sorted(BOSSES), nargs="+", required=True,
                        help="可给多个；节点已存在于当前数据的 boss 会报错")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--archive-name")
    args = parser.parse_args()
    tag = "-".join(args.boss) if len(args.boss) <= 2 else f"{len(args.boss)}bosses"
    name = args.archive_name or f"mainboss-{tag}.zip"
    integrity = write_zip(build([BOSSES[b] for b in args.boss]), args.out / name)
    (args.out / f"mainboss-{tag}.integrity.json").write_text(
        json.dumps(integrity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: integrity[k] for k in ("name", "size", "sha256", "members")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
