# -*- coding: utf-8 -*-
"""27 个 boss 的专属武器套：武器 ×2 + Lv120 强化 + 强化核/领主币 + 掉落 + 商店。

叠加在 build_mainboss_battle_candidate.build() 之上（通过其 extend 钩子），
共享表（boss_battle_quest / stage_node / hard_multi_event(_quest)）只构建一次。

每个 boss（boss_index = BOSSES 的顺序，0 起）：
  武器      5930000 + i*10 + 1/2，★5，模板 = 6 把官方机兵武器（Lv120 强化数据完整），
            每个 boss 取两把不同模板（轮换，6 把都会用到）；词条/强化词条数值照抄，
            属性词（Red/Blue/...）整格替换为该 boss 的推荐属性；Lv70 换名「·改」。
  强化      强化类目 8「boss武器强化」，每把 6 阶 69/70/98/99/119/120，需满破 5，per_level 付料：
            按级阶段 1 强化核/级；突破阶段 70/99/120 = 10/20/40 强化核 + 5/10/20 武器币。
  道具      强化核 10000401 + i*2（共同决战掉落）；
            9 个主线 boss 另有新领主币 10000400 + i*2（领主战掉落）；18 个官方 boss 沿用其紫币。
  掉落      领主战（仅主线）score 组 12000000 + node*10 + k（k=1..5），稀有池 12000000 + node*10；
            共同决战 score 组 12100000 + node，稀有池同号（rare 表）。
  商店      主线 boss 新建领主币分类 80-88（stage_node c6 指过去）；官方 boss 加进原分类。
            每 boss 2 件武器（限购 5，30 币）；主线 boss 另有强化核/星空记忆晶兑换。

图标全部是「可替换字段」：WEAPON_ICON_OVERRIDES / ITEM_ICON_OVERRIDES，默认借官方图标。

用法：
  python tools/fantasy-gauntlet-mod-tools/build_boss_weapon_sets.py --out <目录> --archive-name <名.zip>
         [--server-assets <要改的 assets 目录，默认本仓 assets/>] [--no-server]
"""
from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parent
REPO_ROOT = MOD_DIR.parent.parent
sys.path.insert(0, str(MOD_DIR))
import build_mainboss_battle_candidate as mb  # noqa: E402
import wf_battle_atlas_repack as atlas_codec  # noqa: E402
import wf_client_legality as L  # noqa: E402
import wf_quest_lib as q  # noqa: E402

START = "2000-01-01 00:00:00"
# 完整版合法性门禁（旧仓 wf_client_legality，依赖链长）；存在时以子进程调用，避免与本仓同名模块冲突。
FULL_LEGALITY_DIR = Path(os.environ.get("WF_FULL_LEGALITY_DIR", r"D:\WF\_archive\startpoint-cn-old\repo\mod-tools"))

# ---------------------------------------------------------------- 表路径
EQUIPMENT = "master/item/equipment.orderedmap"
ITEM = "master/item/item.orderedmap"
SOUL = "master/ability/ability_soul.orderedmap"
EQ_STATUS = "master/item/equipment_status.orderedmap"
ENH = "master/equipment_enhancement/equipment_enhancement.orderedmap"
ENH_STATUS = "master/equipment_enhancement/equipment_enhancement_status.orderedmap"
EA = "master/equipment_enhancement/equipment_enhancement_ability.orderedmap"
ENH_SHOP = "master/equipment_enhancement/equipment_enhancement_shop.orderedmap"
ENH_CAT = "master/equipment_enhancement/equipment_enhancement_shop_category.orderedmap"
SCORE = "master/reward/score_reward.orderedmap"
RARE = "master/reward/rare_score_reward.orderedmap"
COIN_SHOP = "master/shop/boss_coin_shop.orderedmap"
COIN_CAT = "master/shop/boss_coin_shop_category.orderedmap"
BBQ = "master/quest/boss_battle_quest.orderedmap"
SN = "master/quest/boss_battle_stage_node.orderedmap"
HE = "master/quest/event/hard_multi_event.orderedmap"
HQ = "master/quest/event/hard_multi_event_quest.orderedmap"
ATLASES = ("item_icon/sprite_sheet", "item/sprite_sheet", "item_sec/sprite_sheet", "scene/general/sprite_sheet")

# ---------------------------------------------------------------- 模板与常量
# (模板武器 id, 类别, 名词, 说明用词, 服务端 lookup 类别取模板)
TEMPLATES = [
    ("5010073", "剑", "裁决之刃", "剑"),
    ("5020042", "斧", "碎岳战斧", "斧"),
    ("5070044", "拳", "崩山拳甲", "拳套"),
    ("5080032", "盾", "镇魂坚盾", "盾"),
    ("5090047", "饰", "心核坠饰", "项链"),
    ("5100020", "铳", "穿星魔铳", "铳"),
]
ELEMENT_TOKENS = ["Red", "Blue", "Yellow", "Green", "White", "Black"]  # 0 火 1 水 2 雷 3 风 4 光 5 暗
ELEMENT_NAMES = ["火", "水", "雷", "风", "光", "暗"]
CORE_COLOR = ["red", "blue", "yellow", "green", "white", "black"]

ENH_CATEGORY = "8"
ENH_CATEGORY_DISPLAY_ORDER = "-3"
ENH_BANNER = "dynamic/equipment_enhancement/mod_boss_weapon_banner"   # 1000x184，assets/mainboss_art/make_enh.py
ENH_HEADER = "dynamic/equipment_enhancement/mod_boss_weapon_header"   # 1440x556
ENH_CATEGORY_TEMPLATE = "3"           # how_to_play / help id 只能用官方已有值：照抄类目 3
ENH_SHOP_TEMPLATES = ["2005", "2006", "2007", "2008", "2027", "2028"]  # 5010073 的 6 阶
STAGE_CAPS = [69, 70, 98, 99, 119, 120]
BREAK_CORE = {70: 10, 99: 20, 120: 40}
BREAK_COIN = {70: 5, 99: 10, 120: 20}
REQUIRE_AWAKENING = 5

WEAPON_COST = 30                       # 每把武器 30 枚（主线=新领主币，官方=紫币）
WEAPON_STOCK = 5
COIN_SHOP_ITEM_TEMPLATE = "10029015"   # 机兵共通分类 60：紫币换全能齿轮
COIN_SHOP_WEAPON_TEMPLATE = "10028168"
COIN_CATEGORY_TEMPLATE = "60"
COIN_CATEGORY_DISPLAY_BASE = 2970      # 80..88 → 2970..2978（全表未用；2984-3000 已占）
# 主线 boss 便利商品：(道具, 数量, 币价, 限购, 列表序)
def _convenience(core: str) -> list[tuple[str, int, int, int, int]]:
    return [(core, 1, 3, 300, 20), ("14040", 1, 15, 10, 10)]

LORD_COINS = [2, 3, 5, 8, 12]          # 领主战 k=1..5 每次通关的领主币
LORD_RARE = (5, 0.1)                   # 稀有：再 +5 枚，10%
HARD_CORES = 5                         # 共同决战每次通关强化核
HARD_MEDAL = ("49300", 1)              # 共同决战功劳勋章（保持交易所经济）
HARD_RARE = (10, 0.15)                 # 稀有：再 +10 强化核，15%

# 可替换图标：武器 id → {"lv0","lv70","soul"}；道具 id → {"thumb","icon"}（icon 必须是图集子纹理）
WEAPON_ICON_OVERRIDES: dict[str, dict[str, str]] = {}
ITEM_ICON_OVERRIDES: dict[str, dict[str, str]] = {}
COIN_ICON_DEFAULT = {"thumb": "item/materials/boss_coin/lich_3", "icon": "item_icon/materials/boss_coin/boss_coin_3"}

DESC_LIMIT = {"equipment": 57, "enhancement": 54, "shop": 60}
NAME_LIMIT = 12

SHORT = {
    "epuration": "歼灭者", "org": "奥格", "maou2": "魔王", "high_epuration": "上位歼灭者",
    "benzaiten": "弁天", "variant_epuration": "异形歼灭者", "star_devourer": "噬星者",
    "cursed_blade": "咒剑", "origin_dragon": "终始之龙",
    "queen_water": "青之女王", "queen_fire": "赤之女王", "queen_wind": "碧之女王",
    "queen_light": "皓之女王", "queen_thunder": "金之女王", "queen_dark": "墨之女王",
    "dragon_thunder": "伊尔考普斯", "dragon_fire": "伊萨巴迪卡", "dragon_water": "伊劳德雷斯",
    "dragon_wind": "伊尔格拉乌", "dragon_light": "伊尔梅塔雷", "dragon_dark": "伊尔昂斯拉",
    "beast_fire": "奥尔塔尼亚", "beast_water": "斯拉姆冈", "beast_thunder": "普罗格雷奥",
    "beast_wind": "亚特摩西亚", "beast_light": "杜梅欧", "beast_dark": "希亚特利欧",
}


def _row(text: str) -> list[str]:
    return next(csv.reader([text]))


def _join(row: list[str]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(row)
    return buf.getvalue()


def _rows(text: str) -> list[list[str]]:
    return [_row(line) for line in text.split("\n") if line.strip()]


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(msg)


def _text(kind: str, text: str) -> str:
    _require(len(text) <= DESC_LIMIT[kind], f"{kind} 文案 {len(text)} 字超上限 {DESC_LIMIT[kind]}：{text}")
    _require("," not in text and "\n" not in text, f"{kind} 文案含半角逗号/换行：{text}")
    return text


# ---------------------------------------------------------------- 规格
def boss_specs() -> list[dict]:
    """BOSSES 顺序即 boss_index。每项补上武器/道具/掉落/商店的全部 id。"""
    out = []
    for i, (key, spec) in enumerate(mb.BOSSES.items()):
        node = int(spec["node"])
        elem = int(spec["element"])
        main = not spec.get("existing")
        t1 = i % 6
        t2 = (i + 1 + (i // 6) % 5) % 6
        weapons = []
        for n, t in ((1, t1), (2, t2)):
            tid, cat, noun, word = TEMPLATES[t]
            wid = str(5930000 + i * 10 + n)
            name = f"{SHORT[key]}的{noun}"
            _require(len(name) + 2 <= NAME_LIMIT, f"武器名过长：{name}")
            weapons.append({"id": wid, "n": n, "template": tid, "category": cat, "word": word, "name": name})
        core = str(10000401 + i * 2)
        coin = str(10000400 + i * 2) if main else None
        out.append({
            "index": i, "key": key, "spec": spec, "node": node, "element": elem, "main": main,
            "boss_name": spec["name"], "short": SHORT[key], "weapons": weapons, "core": core, "coin": coin,
            "hard_event": mb.hard_event_id(spec["node"]),
            "hard_quest": f"{mb.hard_event_id(spec['node'])}001",
            "hard_group": str(12100000 + node),
            "lord_groups": {k: str(12000000 + node * 10 + k) for k in range(1, 6)} if main else {},
            "lord_rare": str(12000000 + node * 10) if main else None,
            "coin_category": str(node) if main else None,   # 80..88
            "product_base": 594000000 + i * 100,
        })
    return out


def _weapon_icons(w: dict, equip_row: list[str], enh_row: list[str], item_row: list[str]) -> dict[str, str]:
    icons = {"lv0": equip_row[6], "lv70": enh_row[4], "soul": item_row[3]}
    icons.update(WEAPON_ICON_OVERRIDES.get(w["id"], {}))
    return icons


def _core_icons(b: dict) -> dict[str, str]:
    path = f"item/materials/equipment_enhancement_materials/steam_robot_material_{CORE_COLOR[b['element']]}_r5"
    icons = {"thumb": path, "icon": path}
    icons.update(ITEM_ICON_OVERRIDES.get(b["core"], {}))
    return icons


def _coin_icons(b: dict) -> dict[str, str]:
    icons = dict(COIN_ICON_DEFAULT)
    icons.update(ITEM_ICON_OVERRIDES.get(b["coin"], {}))
    return icons


# ---------------------------------------------------------------- 客户端
class Builder:
    def __init__(self) -> None:
        self.bosses = boss_specs()
        self.t = {lp: q.load_table(lp) for lp in (EQUIPMENT, ITEM, SOUL, EQ_STATUS, ENH, ENH_STATUS, EA, ENH_SHOP,
                                                   ENH_CAT, SCORE, RARE, COIN_SHOP, COIN_CAT)}
        self.live = {lp: q.load_table(lp) for lp in self.t}          # 未改动副本，查冲突用
        self.new_keys: dict[str, set[str]] = {lp: set() for lp in self.t}
        self.server: dict = {}
        self.ability_rows: list[tuple[str, str, list[str], list[str]]] = []  # (表, 标签, 新行, 模板行)
        self.official_coin: dict[int, str] = {}

    def _put(self, lp: str, key: str, value) -> None:
        _require(key not in self.live[lp], f"{lp} 键已存在：{key}")
        _require(key not in self.t[lp] or key in self.new_keys[lp], f"{lp} 键冲突：{key}")
        self.t[lp][key] = value
        self.new_keys[lp].add(key)

    # 钩子：在 mb.build 的共享表序列化之前调用
    def __call__(self, shared: dict, files: dict[str, bytes]) -> None:
        bb, sn, he, hq = shared[BBQ], shared[SN], shared[HE], shared[HQ]
        for b in self.bosses:
            if not b["main"]:
                row = _row(sn["1"][str(b["node"])])
                b["coin_category"] = row[6]
                b["coin"] = row[9]                               # 紫币 = 第 3 枚
                b["coin_display"] = row[9]
                _require("紫币" in _row(self.t[ITEM][b["coin"]])[2], f"{b['key']} 紫币识别失败：{b['coin']}")
                _require(b["coin_category"] in self.t[COIN_CAT], f"{b['key']} 原分类缺行")
        self._items()
        self._weapons()
        self._enhancement()
        self._drops(bb, hq, he)
        self._shops(sn, files)
        for lp, table in self.t.items():
            if self.new_keys[lp] or lp in (ENH_CAT,):
                files[lp] = q.build_node(table)

    # -------------------------------------------------- 道具
    def _items(self) -> None:
        coin_tpl = _row(self.t[ITEM]["40022"])
        core_tpl = _row(self.t[ITEM]["40408"])
        for b in self.bosses:
            icons = _core_icons(b)
            row = list(core_tpl)
            row[0] = f"mod_boss_core_{b['key']}"
            row[1] = b["core"]
            row[2] = f"{b['short']}强化核"
            row[3], row[4] = icons["thumb"], icons["icon"]
            row[5] = f"凝聚了{b['boss_name']}之力的核心。可用于强化以其为原型打造的专属武器。"
            row[17], row[18] = "5", "9999"
            row[19], row[20] = START, "(None)"
            _require(row[6] == "1" and row[14] == "9", "强化核模板列义漂移")
            self._put(ITEM, b["core"], _join(row))
            b["core_icons"] = icons
            if b["main"]:
                icons = _coin_icons(b)
                row = list(coin_tpl)
                row[0] = f"mod_boss_coin_{b['key']}"
                row[1] = b["coin"]
                row[2] = f"{b['boss_name']}的紫币"
                row[3], row[4] = icons["thumb"], icons["icon"]
                row[5] = f"刻有{b['boss_name']}的紫币。收藏家们似乎正在收集它。能在商店兑换道具。"
                row[19], row[20] = START, "(None)"
                _require(row[6] == "15" and row[14] == "6" and row[15] == "0", "领主币模板列义漂移")
                self._put(ITEM, b["coin"], _join(row))
                b["coin_icons"] = icons
                b["coin_display"] = b["coin"]

    # -------------------------------------------------- 武器
    def _weapons(self) -> None:
        for b in self.bosses:
            token = ELEMENT_TOKENS[b["element"]]
            elem = ELEMENT_NAMES[b["element"]]
            for w in b["weapons"]:
                tid, wid = w["template"], w["id"]
                eq = _row(self.t[EQUIPMENT][tid])
                it = _row(self.t[ITEM][tid])
                enh = _row(self.t[ENH][tid])
                icons = _weapon_icons(w, eq, enh, it)
                w["icons"] = icons
                src_token = _row(self.t[SOUL][tid].split("\n")[0])[8]
                _require(src_token in ELEMENT_TOKENS, f"模板 {tid} 属性列异常")
                w["desc"] = _text("equipment", f"以{b['boss_name']}的残骸为核心锻造的{w['word']}。"
                                               f"蕴含着为克制其而调校的{elem}之力。")
                w["enh_desc"] = _text("enhancement", f"以{b['short']}强化核反复淬炼的{w['word']}。"
                                                     f"封存其中的{elem}之力已完全觉醒。")
                # equipment
                row = list(eq)
                row[0] = f"mod_boss_weapon_{b['key']}_{w['n']}"
                row[1], row[6], row[7], row[10] = w["name"], icons["lv0"], w["desc"], wid
                _require(row[2] == "0" and row[8] == "5" and row[11] == "5", "equipment 模板列义漂移")
                self._put(EQUIPMENT, wid, _join(row))
                # item（同 id 魂珠，缺了 ItemLogic 取空崩）；c12 = 魂珠属性
                row = list(it)
                row[0], row[1], row[2], row[3] = f"mod_boss_weapon_{b['key']}_{w['n']}", wid, f"{w['name']}魂珠", icons["soul"]
                row[5] = "能力魂珠"  # 斧/剑模板残留日文「アビリティソウル」，统一成国服文案
                _require(row[12] == str(ELEMENT_TOKENS.index(src_token)), f"魂珠 c12 与模板属性不符：{tid}")
                row[12] = str(b["element"])
                row[19], row[20] = START, "(None)"
                self._put(ITEM, wid, _join(row))
                # 词条：属性词整格替换
                for lp, kind in ((SOUL, "ability_soul"), (EA, "equipment_enhancement_ability")):
                    new_rows = []
                    for idx, r in enumerate(_rows(self.t[lp][tid])):
                        nr = [token if c == src_token else c for c in r]
                        _require(not any(c in ELEMENT_TOKENS and c != token for c in nr), f"{tid} 残留他属性词")
                        self.ability_rows.append((kind, f"{wid}#{idx}", nr, r))
                        new_rows.append(_join(nr))
                    self._put(lp, wid, "\n".join(new_rows))
                self._put(EQ_STATUS, wid, copy.deepcopy(self.t[EQ_STATUS][tid]))
                # 强化主表：Lv70 换名换图
                row = list(enh)
                _require(row[0] == "120" and row[3] == "70", f"强化模板 {tid} 列义漂移")
                row[2], row[4], row[6], row[8] = f"{w['name']}·改", icons["lv70"], w["enh_desc"], START
                self._put(ENH, wid, _join(row))
                self._put(ENH_STATUS, wid, copy.deepcopy(self.t[ENH_STATUS][tid]))

    # -------------------------------------------------- 强化商店
    def _enhancement(self) -> None:
        cat = _row(self.t[ENH_CAT][ENH_CATEGORY_TEMPLATE])
        orders = {_row(v.strip())[1] for v in self.t[ENH_CAT].values()}
        _require(ENH_CATEGORY_DISPLAY_ORDER not in orders, "强化类目 display_order 已被占用")
        cat[0], cat[1], cat[3], cat[8], cat[9] = "boss_weapon", ENH_CATEGORY_DISPLAY_ORDER, "领主武装·觉醒", START, "(None)"
        cat[4], cat[5] = ENH_BANNER, ENH_HEADER   # 模板 3 的是机兵横幅/页头，换成自己的
        self._put(ENH_CAT, ENH_CATEGORY, _join(cat))
        tpls = [_row(self.t[ENH_SHOP][k]) for k in ENH_SHOP_TEMPLATES]
        _require([int(t[30]) for t in tpls] == STAGE_CAPS, "强化商店模板阶段漂移")
        shop_json = {}
        for b in self.bosses:
            for w in b["weapons"]:
                for stage, (cap, tpl) in enumerate(zip(STAGE_CAPS, tpls), start=1):
                    if cap in BREAK_CORE:
                        costs = [(b["core"], BREAK_CORE[cap]), (b["coin"], BREAK_COIN[cap])]
                    else:
                        costs = [(b["core"], 1)]
                    cells = []
                    for item_id, amount in costs:
                        cells += [item_id, str(amount)]
                    while len(cells) < 8:
                        cells += ["(None)", ""]
                    row = list(tpl)
                    row[0], row[2], row[3], row[5] = ENH_CATEGORY, w["id"], str(stage), "100"
                    row[14:22] = cells
                    row[22], row[23] = START, "(None)"
                    row[29], row[30], row[31] = w["id"], str(cap), str(REQUIRE_AWAKENING)
                    key = f"{w['id']}{stage:02d}"
                    self._put(ENH_SHOP, key, _join(row))
                    shop_json[key] = {
                        "costs": [{"id": int(i), "amount": a} for i, a in costs], "rewards": [],
                        "availableFrom": START, "availableUntil": None, "stock": -1,
                        "shopCategoryId": int(ENH_CATEGORY), "groupId": int(w["id"]), "stage": stage,
                        "equipmentId": int(w["id"]), "enhancementMaxLevel": cap,
                        "requireAwakeningLevel": REQUIRE_AWAKENING, "enhancementPurchaseMode": "per_level",
                    }
        self.server["equipment_enhancement_shop.json"] = shop_json

    # -------------------------------------------------- 掉落
    def _drops(self, bb: dict, hq: dict, he: dict) -> None:
        score_srv: dict = {}
        rare_srv: dict = {}

        def add_group(gid: str, label: str, normal: list[tuple[str, int]], rare: tuple[str, float] | None) -> None:
            client = {}
            server = []
            pos = 0
            for item_id, count in normal:
                pos += 1
                client[str(pos)] = _join([label, "0", "0", item_id, str(count), "100", "", ""])
                server.append({"position": pos, "name": "", "type": 0, "reward_type": 0, "count": count,
                               "field5": 100, "id": int(item_id)})
            if rare:
                pos += 1
                client[str(pos)] = _join([label, "1", "", "", "", "", rare[0], f"{rare[1]:g}"])
                server.append({"position": pos, "name": "", "type": 1, "id": int(rare[0]), "rarity": rare[1]})
            self._put(SCORE, gid, client)
            score_srv[gid] = server

        def add_rare(pid: str, label: str, item_id: str, count: int) -> None:
            self._put(RARE, pid, {"1": _join([label, "0", item_id, str(count), "1", "false"])})
            rare_srv[pid] = [{"name": "", "type": 0, "rarity": 1.0, "id": int(item_id), "count": count}]

        bbq_srv: dict = {}
        hmq_srv: dict = {}
        for b in self.bosses:
            node = str(b["node"])
            # 共同决战
            label = f"mod_boss_hard_{b['key']}"
            add_rare(b["hard_group"], f"{label}_rare", b["core"], HARD_RARE[0])
            add_group(b["hard_group"], label, [(b["core"], HARD_CORES), HARD_MEDAL], (b["hard_group"], HARD_RARE[1]))
            row = _row(hq[b["hard_event"]]["1"])
            _require(row[0] == b["hard_quest"] and row[71].isdigit(), f"hard_multi_event_quest {b['hard_quest']} 列义漂移")
            row[71] = b["hard_group"]
            hq[b["hard_event"]]["1"] = _join(row)
            row = _row(he[b["hard_event"]])
            row[16:20] = [b["core"], HARD_MEDAL[0], "(None)", "(None)"]
            he[b["hard_event"]] = _join(row)
            hmq_srv[b["hard_quest"]] = {"scoreRewardGroupId": int(b["hard_group"]), "name": f"{b['boss_name']} ::quest_rank::"}
            # 领主战（仅主线）
            if b["main"]:
                label = f"mod_boss_lord_{b['key']}"
                add_rare(b["lord_rare"], f"{label}_rare", b["coin"], LORD_RARE[0])
                for k, gid in b["lord_groups"].items():
                    add_group(gid, f"{label}_{k}", [(b["coin"], LORD_COINS[k - 1])], (b["lord_rare"], LORD_RARE[1]))
                    row = _row(bb["1"][node][str(k)])
                    qid = str(mb.quest_id(node, k))
                    _require(row[0] == qid and row[70].isdigit(), f"boss_battle_quest {qid} 列义漂移")
                    row[70] = gid
                    bb["1"][node][str(k)] = _join(row)
                    bbq_srv[qid] = {"k": k, "scoreRewardGroupId": int(gid), "element": int(b["element"])}
        self.server["score_reward_cnmod.json"] = score_srv
        self.server["rare_score_reward_cnmod.json"] = rare_srv
        self.server["_bbq"] = bbq_srv
        self.server["_hmq"] = hmq_srv

    # -------------------------------------------------- 领主币商店
    def _shops(self, sn: dict, files: dict[str, bytes]) -> None:
        wtpl = _row(self.t[COIN_SHOP][COIN_SHOP_WEAPON_TEMPLATE])
        itpl = _row(self.t[COIN_SHOP][COIN_SHOP_ITEM_TEMPLATE])
        ctpl = _row(self.t[COIN_CAT][COIN_CATEGORY_TEMPLATE])
        used_orders = {_row(v.strip())[1] for v in self.t[COIN_CAT].values()}
        shop_srv: dict = {}
        cmap: dict = {}

        def product(b: dict, pid: str, name: str, desc: str, icon: str, rarity: str, kind: str, rid: str,
                    count: int, cost: int, stock: int, order: int, tpl: list[str]) -> None:
            row = list(tpl)
            row[0], row[6], row[7], row[8], row[9] = b["coin_category"], name, pid, "1", str(order)
            row[10], row[12], row[13] = _text("shop", desc), icon, rarity
            row[17], row[18] = b["coin"], str(cost)
            row[19:25] = ["(None)", "", "(None)", "", "(None)", ""]
            row[25], row[26] = START, "(None)"
            row[28], row[31] = str(stock), str(stock)
            row[32], row[33], row[34] = kind, rid, str(count)
            self._put(COIN_SHOP, pid, _join(row))
            shop_srv.setdefault(b["coin_category"], {})[pid] = {
                "costs": [{"id": int(b["coin"]), "amount": cost}],
                "rewards": [{"type": int(kind), "id": int(rid), "count": count}],
                "availableFrom": START, "availableUntil": None, "stock": stock}
            cmap[pid] = int(b["coin_category"])

        for b in self.bosses:
            base = b["product_base"]
            if b["main"]:
                cid = b["coin_category"]
                order = str(COIN_CATEGORY_DISPLAY_BASE + b["node"] - 80)
                _require(order not in used_orders, f"领主币分类 display_order {order} 已占用")
                art = b["spec"]["art"]
                banner = f"quest/boss_battle/banner/mod_mainboss_{art}_exchange"
                files[banner + ".png"] = mb._store_png(mb.ART_DIR / f"banner_{art}.png")
                node = str(b["node"])
                snr = _row(sn["1"][node])
                row = list(ctpl)
                row[0], row[1], row[2] = f"mod_mainboss_{b['key']}", order, "(None)"
                row[3:8] = ["2", "1", node, "1", str(mb.quest_id(node, 1))]
                row[8], row[9], row[10], row[11], row[12] = "(None)", banner, snr[12], "", "false"
                self._put(COIN_CAT, cid, _join(row))
                # stage_node：c6 指新分类，c7-c10 展示新币
                snr[6] = cid
                snr[7:11] = [b["coin"], "(None)", "(None)", "(None)"]
                sn["1"][node] = _join(snr)
                for n, (rid, count, cost, stock, order_) in enumerate(_convenience(b["core"]), start=11):
                    it = _row(self.t[ITEM][rid])
                    product(b, str(base + n), it[2], f"可用{b['boss_name']}的紫币兑换。", it[3],
                            it[17], "0", rid, count, cost, stock, order_, itpl)
            for w, order_ in zip(b["weapons"], (200, 199)):
                product(b, str(base + w["n"]), w["name"], w["desc"], w["icons"]["lv0"], "5", "4", w["id"],
                        1, WEAPON_COST, WEAPON_STOCK, order_, wtpl)
        self.server["boss_coin_shop.json"] = shop_srv
        self.server["boss_coin_shop_item_category_map.json"] = cmap


# ---------------------------------------------------------------- 服务端
def _cnmod_dumps(data: dict) -> str:
    """score_reward_cnmod / rare_score_reward_cnmod 的排版：每条奖励一行。"""
    parts = []
    for key, rows in data.items():
        lines = ["    { " + json.dumps(r, ensure_ascii=False)[1:-1] + " }" for r in rows]
        parts.append(f'  {json.dumps(key)}: [\n' + ",\n".join(lines) + "\n  ]")
    return "{\n" + ",\n".join(parts) + "\n}\n"


def _styles():
    for indent in (2, 1, 4, None):
        for tail in ("\n", ""):
            yield f"indent{indent}{tail!r}", (lambda d, i=indent, t=tail: json.dumps(d, ensure_ascii=False, indent=i) + t)
    for tail in ("\n", ""):
        yield f"lines{tail!r}", (lambda d, t=tail: "[\n" + ",\n".join(map(str, d)) + "\n]" + t)
    yield "cnmod", _cnmod_dumps


def _load_styled(path: Path):
    raw = path.read_bytes().decode("utf-8")
    data = json.loads(raw)
    for name, fn in _styles():
        try:
            if fn(data) == raw:
                return data, fn
        except TypeError:
            continue
    raise SystemExit(f"{path.name} 排版无法复现，拒绝改写（避免整文件 diff）")


class ServerDelta:
    def __init__(self, assets: Path) -> None:
        self.assets = assets
        self.data: dict[str, object] = {}
        self.fmt: dict[str, object] = {}
        self.changed: set[str] = set()

    def get(self, name: str):
        if name not in self.data:
            self.data[name], self.fmt[name] = _load_styled(self.assets / name)
        return self.data[name]

    def peek(self, name: str):
        """只读查冲突（不改写的文件不要求排版可复现）。"""
        if name in self.data:
            return self.data[name]
        return json.loads((self.assets / name).read_text(encoding="utf-8"))

    def put_new(self, name: str, key: str, value, sub: str | None = None) -> None:
        """新 id：已存在且内容相同 = 幂等重跑；内容不同 = 冲突。"""
        d = self.get(name)
        if sub is not None:
            d = d.setdefault(sub, {})
        if key in d and d[key] != value:
            raise SystemExit(f"服务端 {name}{'[' + sub + ']' if sub else ''} 键 {key} 已被占用且内容不同")
        if d.get(key) != value:
            d[key] = value
            self.changed.add(name)

    def upsert(self, name: str, key: str, value) -> None:
        d = self.get(name)
        if d.get(key) != value:
            d[key] = value
            self.changed.add(name)

    def append_ids(self, name: str, ids: list[int]) -> None:
        d = self.get(name)
        have = set(d)
        add = [i for i in ids if i not in have]
        if add:
            d.extend(add)
            self.changed.add(name)

    def write(self) -> list[str]:
        for name in sorted(self.changed):
            (self.assets / name).write_bytes(self.fmt[name](self.data[name]).encode("utf-8"))
        return sorted(self.changed)


def apply_server(b: Builder, assets: Path) -> ServerDelta:
    s = ServerDelta(assets)
    lookup_tpl = s.get("equipment_lookup.json")
    weapons = [w for boss in b.bosses for w in boss["weapons"]]
    for boss in b.bosses:
        for w in boss["weapons"]:
            wid = w["id"]
            s.put_new("equipment_lookup.json", wid, {"name": w["name"], "rarity": "5",
                                                      "category": lookup_tpl[w["template"]]["category"]})
            s.put_new("equipment_max_level.json", wid, 5)
            s.put_new("equipment_element.json", wid, boss["element"])
            s.put_new("item_sale.json", wid, {"category": 5, "sale_price": 500, "sellable": True})
            s.put_new("equipment_dissolve.json", wid, {"ability_soul_id": int(wid), "obtain_source": 1,
                                                        "generate_ability_soul": True, "max_level": 5})
            s.put_new("item_lookup_cnmod.json", wid, f"{w['name']}魂珠")
    s.append_ids("equipment_ids.json", [int(w["id"]) for w in weapons])
    items = []
    for boss in b.bosses:
        for iid, name, sale in ((boss["core"], f"{boss['short']}强化核", {"category": 9, "sale_price": 500, "sellable": True}),
                                (boss["coin"] if boss["main"] else None, f"{boss['boss_name']}的紫币",
                                 {"category": 6, "sale_price": 30, "sellable": True})):
            if iid is None:
                continue
            items.append(int(iid))
            s.put_new("item_lookup_cnmod.json", iid, name)
            s.put_new("item_sale.json", iid, sale)
    base_lookup = s.peek("item_lookup.json")
    clash = [i for i in items + [int(w["id"]) for w in weapons] if str(i) in base_lookup]
    _require(not clash, f"item_lookup.json 已有道具 id：{clash[:5]}")
    s.append_ids("item_ids.json", sorted(items + [int(w["id"]) for w in weapons]))
    for key, value in b.server["equipment_enhancement_shop.json"].items():
        s.put_new("equipment_enhancement_shop.json", key, value)
    for gid, rows in b.server["score_reward_cnmod.json"].items():
        _require(gid not in s.peek("score_reward.json"), f"score_reward.json 已有组 {gid}")
        s.put_new("score_reward_cnmod.json", gid, rows)
    for pid, rows in b.server["rare_score_reward_cnmod.json"].items():
        _require(pid not in s.peek("rare_score_reward.json"), f"rare_score_reward.json 已有池 {pid}")
        s.put_new("rare_score_reward_cnmod.json", pid, rows)
    for cat, products in b.server["boss_coin_shop.json"].items():
        for pid, value in products.items():
            s.put_new("boss_coin_shop.json", pid, value, sub=cat)
    for pid, cat in b.server["boss_coin_shop_item_category_map.json"].items():
        s.put_new("boss_coin_shop_item_category_map.json", pid, cat)
    # 领主战（cnmod 覆盖 base）：主线 5 档，模板 = 本仓已有的 1080001-1080005
    bbq = s.get("boss_battle_quest_cnmod.json")
    for qid, info in b.server["_bbq"].items():
        tpl = copy.deepcopy(bbq.get(qid) or bbq[f"108000{info['k']}"])
        tpl["scoreRewardGroupId"] = info["scoreRewardGroupId"]
        tpl["element"] = info["element"]
        s.upsert("boss_battle_quest_cnmod.json", qid, tpl)
    # 共同决战：模板 = 1006001（与客户端行同源）
    hmq = s.get("hard_multi_event_quest.json")
    for qid, info in b.server["_hmq"].items():
        tpl = copy.deepcopy(hmq.get(qid) or hmq["1006001"])
        tpl.update(info)
        s.upsert("hard_multi_event_quest.json", qid, tpl)
    return s


# ---------------------------------------------------------------- 校验
def _full_legality(rows: list[tuple[str, str, list[str], list[str]]]) -> dict:
    if not (FULL_LEGALITY_DIR / "wf_client_legality.py").exists():
        return {"skipped": f"{FULL_LEGALITY_DIR} 不存在"}
    script = (
        "import json,sys\n"
        "import wf_client_legality as L, wf_describe as D\n"
        "rows=json.load(sys.stdin)\n"
        "out={'problems':[],'capabilities':[],'describe':[]}\n"
        "for kind,label,r,t in rows:\n"
        "    out['problems']+=[label+': '+p for p in L.client_legality_problems(kind,r)]\n"
        "    out['problems']+=[label+': '+p for p in L.ability_element_column_problems(kind,r)]\n"
        "    out['capabilities']+=[label+': '+c for c in L.required_client_capabilities(kind,r)]\n"
        "    out['describe'].append([label,D.describe_line(r,kind),D.describe_line(t,kind)])\n"
        "sys.stdout.write(json.dumps(out,ensure_ascii=False))\n"
    )
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-c", script], cwd=FULL_LEGALITY_DIR, env=env,
                          input=json.dumps(rows, ensure_ascii=False).encode("utf-8"), capture_output=True)
    _require(proc.returncode == 0, "完整合法性门禁执行失败：" + proc.stderr.decode("utf-8", "replace")[-2000:])
    return json.loads(proc.stdout.decode("utf-8"))


def validate(b: Builder, files: dict[str, bytes], server: ServerDelta | None) -> dict:
    report: dict = {}
    # 1. 全部 orderedmap 重解析
    parsed = {}
    for lp, data in files.items():
        if lp.endswith(".orderedmap"):
            node = q.parse_node(data)
            _require(isinstance(node, dict), f"{lp} 重解析失败")
            parsed[lp] = node
    # 2. 词条合法性
    problems = []
    for kind, label, r, _ in b.ability_rows:
        problems += [f"{label}: {p}" for p in L.client_legality_problems(kind, r)]
    full = _full_legality(b.ability_rows)
    problems += full.get("problems", [])
    problems += [f"缺 capability {c}" for c in full.get("capabilities", [])]
    _require(not problems, "词条合法性问题：\n" + "\n".join(problems[:40]))
    if "describe" in full:
        # 描述只应在属性字上与模板不同
        for label, new, old in full["describe"]:
            norm = lambda s: "".join("@" if ch in "".join(ELEMENT_NAMES) else ch for ch in s)
            _require(norm(new) == norm(old), f"{label} 改属性后语义漂移：{old} → {new}")
    report["ability_rows"] = len(b.ability_rows)
    report["full_legality"] = full.get("skipped", "ok")
    # 3. 强化表
    enh_status = parsed[ENH_STATUS]
    shop = parsed[ENH_SHOP]
    for boss in b.bosses:
        for w in boss["weapons"]:
            wid = w["id"]
            _require(list(enh_status[wid])[-1] == "120", f"{wid} 强化 status 末键 ≠ 120")
            _require(_row(parsed[ENH][wid])[0] == "120", f"{wid} 强化上限 ≠ 120")
            stages = sorted((_row(v) for k, v in shop.items() if k.startswith(wid) and len(k) == len(wid) + 2),
                            key=lambda r: int(r[3]))
            _require([int(r[30]) for r in stages] == STAGE_CAPS, f"{wid} 强化阶段 {[r[30] for r in stages]}")
            _require(all(r[31] == "5" and r[0] == ENH_CATEGORY for r in stages), f"{wid} 强化阶段类目/觉醒要求异常")
            for lp in (EQUIPMENT, ITEM, SOUL, EQ_STATUS, ENH, EA):
                _require(wid in parsed[lp], f"{wid} 缺 {lp}")
    # 4. 图集
    frames = set()
    for sheet in ATLASES:
        frames |= {f["n"] for f in atlas_codec.decode_atlas(q.read_raw(sheet + ".atlas.amf3.deflate"))}
    items = parsed[ITEM]
    shown = {b_["core"] for b_ in b.bosses} | {b_["coin"] for b_ in b.bosses} | {HARD_MEDAL[0], "14040"}
    for iid in sorted(shown):
        icon = _row(items[iid])[4]
        _require(icon in frames, f"道具 {iid} c4 小图标 {icon} 不在图集里（C8004）")
    for boss in b.bosses:
        if boss["main"]:
            c3 = _row(items[boss["coin"]])[3]
            _require(c3 in frames or f"{c3}.png" in files, f"币 {boss['coin']} c3 既不在图集也不在补丁里")
    report["atlas_checked_items"] = len(shown)
    # 5. 掉落对齐
    score, rare = parsed[SCORE], parsed[RARE]
    if server is not None:
        srv_score = server.get("score_reward_cnmod.json")
        srv_rare = server.get("rare_score_reward_cnmod.json")
        for gid in b.new_keys[SCORE]:
            rows = srv_score[gid]
            _require(sorted(score[gid], key=int) == [str(r["position"]) for r in rows], f"score 组 {gid} 序号不对齐")
            for r in rows:
                c = _row(score[gid][str(r["position"])])
                if r["type"] == 0:
                    _require(c[1] == "0" and c[3] == str(r["id"]) and c[4] == str(r["count"]), f"score {gid}#{r['position']} 不对齐")
                else:
                    _require(c[1] == "1" and c[6] == str(r["id"]) and str(r["id"]) in rare, f"score {gid}#{r['position']} 稀有池不对齐")
        for pid in b.new_keys[RARE]:
            rows = srv_rare[pid]
            _require(len(rows) == len(rare[pid]), f"rare {pid} 条数不对齐")
            for i, r in enumerate(rows, start=1):
                c = _row(rare[pid][str(i)])
                _require(c[2] == str(r["id"]) and c[3] == str(r["count"]), f"rare {pid}#{i} 不对齐")
        bbq = server.get("boss_battle_quest_cnmod.json")
        hmq = server.get("hard_multi_event_quest.json")
        for boss in b.bosses:
            row = _row(parsed[HQ][boss["hard_event"]]["1"])
            _require(row[71] == boss["hard_group"] == str(hmq[boss["hard_quest"]]["scoreRewardGroupId"]),
                     f"共同决战 {boss['hard_quest']} 掉落组不对齐")
            for k, gid in boss["lord_groups"].items():
                qid = str(mb.quest_id(str(boss["node"]), k))
                row = _row(parsed[BBQ]["1"][str(boss["node"])][str(k)])
                _require(row[70] == gid == str(bbq[qid]["scoreRewardGroupId"]), f"领主战 {qid} 掉落组不对齐")
        # 6. 商店四处同步
        srv_shop = server.get("boss_coin_shop.json")
        cmap = server.get("boss_coin_shop_item_category_map.json")
        cats = parsed[COIN_CAT]
        for pid in b.new_keys[COIN_SHOP]:
            c = _row(parsed[COIN_SHOP][pid])
            cat = c[0]
            _require(cat in cats, f"商品 {pid} 分类 {cat} 缺客户端分类行")
            _require(cmap.get(pid) == int(cat), f"商品 {pid} 分类映射不一致")
            entry = srv_shop.get(cat, {}).get(pid)
            _require(entry is not None, f"商品 {pid} 服务端缺行")
            _require(entry["costs"] == [{"id": int(c[17]), "amount": int(c[18])}], f"商品 {pid} 价格不一致")
            _require(entry["rewards"] == [{"type": int(c[32]), "id": int(c[33]), "count": int(c[34])}], f"商品 {pid} 奖励不一致")
            _require(entry["stock"] == int(c[28]), f"商品 {pid} 限购不一致")
        for boss in b.bosses:
            if boss["main"]:
                snr = _row(parsed[SN]["1"][str(boss["node"])])
                _require(snr[6] == boss["coin_category"] and snr[7] == boss["coin"], f"stage_node {boss['node']} 未指向新分类/新币")
        # 强化商店客户端 ↔ 服务端
        srv_enh = server.get("equipment_enhancement_shop.json")
        for key in b.new_keys[ENH_SHOP]:
            c = _row(shop[key])
            e = srv_enh[key]
            costs = [{"id": int(c[i]), "amount": int(c[i + 1])} for i in (14, 16, 18, 20) if c[i] not in ("", "(None)")]
            _require(e["costs"] == costs and e["enhancementMaxLevel"] == int(c[30]) and e["groupId"] == int(c[2])
                     and e["stage"] == int(c[3]) and e["shopCategoryId"] == int(c[0]), f"强化商店 {key} 不一致")
    report["new_keys"] = {lp: len(v) for lp, v in b.new_keys.items() if v}
    return report


# ---------------------------------------------------------------- 入口
ICON_DIR = mb.ART_DIR / "icons"   # weapons/<id>.png、<id>_lv70.png；coins/<art>.png；cores/<art>.png（像素 API 出图，20×20）
ICON_PREFIX = "item/equipment/mod/mainboss"
MAT_PREFIX = "item/materials/mod/mainboss"


def _install_icons(files: dict[str, bytes]) -> None:
    """把自制图标登记为覆盖项并放进补丁（独立 PNG，CDN 小写签名）。c4 小图标仍用图集默认值。"""
    files[ENH_BANNER + ".png"] = mb._store_png(mb.ART_DIR / "enh_banner.png")
    files[ENH_HEADER + ".png"] = mb._store_png(mb.ART_DIR / "enh_header.png")
    for spec in boss_specs():
        art = spec["spec"]["art"]
        for w in spec["weapons"]:
            lv0, lv70 = ICON_DIR / "weapons" / f"{w['id']}.png", ICON_DIR / "weapons" / f"{w['id']}_lv70.png"
            if lv0.exists():
                o = {"lv0": f"{ICON_PREFIX}/{w['id']}_lv0", "soul": f"{ICON_PREFIX}/{w['id']}_lv0"}
                files[o["lv0"] + ".png"] = mb._store_png(lv0)
                if lv70.exists():
                    o["lv70"] = f"{ICON_PREFIX}/{w['id']}_lv70"
                    files[o["lv70"] + ".png"] = mb._store_png(lv70)
                WEAPON_ICON_OVERRIDES[w["id"]] = o
        core = ICON_DIR / "cores" / f"{art}.png"
        if core.exists():
            path = f"{MAT_PREFIX}/core_{art}"
            files[path + ".png"] = mb._store_png(core)
            ITEM_ICON_OVERRIDES.setdefault(spec["core"], {})["thumb"] = path
        coin = ICON_DIR / "coins" / f"{art}.png"
        if spec["coin"] and coin.exists():
            path = f"{MAT_PREFIX}/coin_{art}"
            files[path + ".png"] = mb._store_png(coin)
            ITEM_ICON_OVERRIDES.setdefault(spec["coin"], {})["thumb"] = path


def build_all() -> tuple[dict[str, bytes], Builder]:
    icon_files: dict[str, bytes] = {}
    _install_icons(icon_files)
    b = Builder()
    files = mb.build(list(mb.BOSSES.values()), extend=b)
    files.update(icon_files)
    return files, b


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--archive-name", default="boss-weapon-sets.zip")
    parser.add_argument("--server-assets", type=Path, default=REPO_ROOT / "assets")
    parser.add_argument("--no-server", action="store_true", help="只出客户端包，不改服务端 JSON")
    args = parser.parse_args()

    files, b = build_all()
    server = None if args.no_server else apply_server(b, args.server_assets)
    report = validate(b, files, server)
    written = server.write() if server is not None else []
    integrity = mb.write_zip(files, args.out / args.archive_name)
    stem = Path(args.archive_name).stem
    (args.out / f"{stem}.integrity.json").write_text(json.dumps(integrity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plan = [{
        "index": x["index"], "key": x["key"], "node": x["node"], "name": x["boss_name"],
        "element": ELEMENT_NAMES[x["element"]], "coin": x["coin"], "core": x["core"],
        "coin_category": x["coin_category"], "hard_quest": x["hard_quest"], "hard_group": x["hard_group"],
        "lord_groups": x["lord_groups"], "lord_rare": x["lord_rare"],
        "weapons": [{k: w[k] for k in ("id", "name", "template", "category", "icons")} for w in x["weapons"]],
        "products": sorted(k for k in b.new_keys[COIN_SHOP] if int(k) // 100 == x["product_base"] // 100),
    } for x in b.bosses]
    (args.out / f"{stem}.plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"archive": {k: integrity[k] for k in ("name", "size", "sha256", "members")},
                      "server_written": written, "validation": report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
