#!/usr/bin/env node
"use strict"

const fs = require("node:fs")
const path = require("node:path")

const repo = path.resolve(__dirname, "..")
const source = process.argv[2]
const shopSource = process.argv[3]
if (!source || !shopSource) {
    throw new Error("usage: node tools/integrate_rank_p5b_content.cjs <content-data-fragments> <shop-data-fragments>")
}

function readJson(file) {
    return JSON.parse(fs.readFileSync(file, "utf8"))
}

function writeJson(relative, value) {
    const file = path.join(repo, relative)
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8")
}

function copyFragment(sourceName, targetRelative) {
    writeJson(targetRelative, readJson(path.join(source, sourceName)))
}

copyFragment("character.json", "assets/character_rank_p5b.json")
copyFragment("mana-node.json", "assets/mana_node_rank_p5b.json")
copyFragment("gacha-990002.json", "assets/gacha_rank_p5b.json")
copyFragment("cdndata-character.json", "assets/cdndata/character_rank_p5b.json")
copyFragment("cdndata-character-text.json", "assets/cdndata/character_text_rank_p5b.json")
copyFragment("cdndata-gacha-990002.json", "assets/cdndata/gacha_rank_p5b.json")
copyFragment("cdndata-gacha-feature-990002.json", "assets/cdndata/gacha_feature_content_rank_p5b.json")
copyFragment("item-ids-rank-p5b.json", "assets/item_ids_rank_p5b.json")

writeJson("assets/degree_rank_p5b.json", {
    "9900002": { string_id: "degree_mod_abyss_rush_champion", name: "深渊冠军", kana: "しんえんおうじゃ", condition: "获得条件：深渊连战赛季排名第1", category_id: 6 },
    "9900003": { string_id: "degree_mod_abyss_rush_runner_up", name: "深渊亚季军", kana: "しんえんじょうい", condition: "获得条件：深渊连战赛季排名第2～3", category_id: 6 },
    "9900004": { string_id: "degree_mod_abyss_rush_upper_rank", name: "深渊上位者", kana: "しんえんじょういしゃ", condition: "获得条件：深渊连战赛季排名第4～15", category_id: 6 },
    "9900005": { string_id: "degree_mod_abyss_rush_participant", name: "深渊参与者", kana: "しんえんさんかしゃ", condition: "获得条件：完整通关深渊连战并参与赛季排名", category_id: 6 },
    "9900006": { string_id: "degree_mod_veteran_player", name: "资深玩家", kana: "ベテランプレイヤー", condition: "获得条件：在深渊商店购买", category_id: 6 },
    "9900007": { string_id: "degree_mod_stellar_abyss_overlord", name: "星渊主宰者", kana: "せいえんしゅさいしゃ", condition: "获得条件：新赛季排行榜排名第1", category_id: 6 },
    "9900008": { string_id: "degree_mod_stellar_abyss_conqueror", name: "星渊征服者", kana: "せいえんせいふくしゃ", condition: "获得条件：新赛季排行榜排名第2", category_id: 6 },
    "9900009": { string_id: "degree_mod_stellar_abyss_slayer", name: "星渊讨伐者", kana: "せいえんとうばつしゃ", condition: "获得条件：新赛季排行榜排名第3", category_id: 6 },
    "9900010": { string_id: "degree_mod_breakthrough_pioneer", name: "破阵先行者", kana: "はじんせんこうしゃ", condition: "获得条件：新赛季排行榜排名第4～15", category_id: 6 },
    "9900011": { string_id: "degree_mod_stellar_abyss_together", name: "共赴星渊", kana: "ともにせいえんへ", condition: "获得条件：参加新赛季排行榜", category_id: 6 },
})

const incomingShop = readJson(path.join(shopSource, "event-shop-700099.json"))
writeJson("assets/event_item_shop_rank_p5b.json", {
    "11": { "700099": { "9700118": incomingShop["9700118"] } },
})
const incomingMap = readJson(path.join(shopSource, "event-shop-id-map-9700101-9700118.json"))
writeJson("assets/event_item_shop_id_map_rank_p5b.json", { "9700118": incomingMap["9700118"] })

console.log("rank-p5b sparse server overlays generated")
