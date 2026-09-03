const test = require("node:test")
const assert = require("node:assert/strict")
const crypto = require("node:crypto")
const path = require("node:path")
const zlib = require("node:zlib")
const unzipper = require("unzipper")

const baseCharacters = require("../assets/character.json")
const rankCharacters = require("../assets/character_rank_p5b.json")
const rankDegrees = require("../assets/degree_rank_p5b.json")
const rankGacha = require("../assets/gacha_rank_p5b.json")
const rankShop = require("../assets/event_item_shop_rank_p5b.json")
const rankShopMap = require("../assets/event_item_shop_id_map_rank_p5b.json")
const rankItems = require("../assets/item_ids_rank_p5b.json")
const itemLookup = require("../assets/item_lookup_cnmod.json")
const rankPatchAudit = require("../assets/asset-patch/audit/home-load-rank-p5b-1.4.92/report.json")
const seasonRankTitleAudit = require("../assets/asset-patch/audit/season-rank-titles-1.4.97/report.json")
const { serverCharacters, serverEventShops, serverGachas } = require("../out/lib/content-master")

const RANK_CHARACTER_IDS = Object.keys(rankCharacters).map(Number).sort((a, b) => a - b)
const RANK_BOSS_CHARACTER_IDS = [169980, 169994, 169995, 179981]
const CDN_PATH_SALT = "K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy"
const rankPatchArchives = rankPatchAudit.archives.map(entry => path.join(
    __dirname,
    "..",
    "assets",
    "asset-patch",
    "active",
    entry.name,
))

function decodeOrderedMap(raw, compressedRows) {
    const indexLength = raw.readUInt32LE(0)
    const index = zlib.inflateSync(raw.subarray(4, 4 + indexLength))
    const count = index.readUInt32LE(0)
    const keyBytesStart = 4 + count * 8
    const keyBytes = index.subarray(keyBytesStart)
    const valueBytes = raw.subarray(4 + indexLength)
    const result = new Map()
    let previousKeyEnd = 0
    let previousValueEnd = 0
    for (let indexOffset = 0; indexOffset < count; indexOffset += 1) {
        const keyEnd = index.readUInt32LE(4 + indexOffset * 8)
        const valueEnd = index.readUInt32LE(8 + indexOffset * 8)
        const key = keyBytes.subarray(previousKeyEnd, keyEnd).toString("utf8")
        const storedValue = valueBytes.subarray(previousValueEnd, valueEnd)
        result.set(key, compressedRows && storedValue.length > 0
            ? zlib.inflateSync(storedValue)
            : storedValue)
        previousKeyEnd = keyEnd
        previousValueEnd = valueEnd
    }
    return result
}

async function readRankPatchLogical(logicalPath) {
    const digest = crypto.createHash("sha1")
        .update(logicalPath + CDN_PATH_SALT)
        .digest("hex")
    const memberName = `production/upload/${digest.slice(0, 2)}/${digest.slice(2)}`
    for (const archivePath of rankPatchArchives) {
        const archive = await unzipper.Open.file(archivePath)
        const member = archive.files.find(entry => entry.path === memberName)
        if (member) return member.buffer()
    }
    assert.fail(`missing rank-P5B logical file: ${logicalPath}`)
}

test("rank-p5b 内容以稀疏覆盖接入，不改写现有深渊与装备主数据", () => {
    assert.equal(RANK_CHARACTER_IDS.length, 45)
    for (const characterId of RANK_BOSS_CHARACTER_IDS) assert.ok(RANK_CHARACTER_IDS.includes(characterId))
    assert.deepEqual(serverCharacters["700099"], baseCharacters["700099"])
    assert.deepEqual(Object.keys(rankShop), ["11"])
    assert.deepEqual(Object.keys(rankShop["11"]["700099"]), ["9700118"])
    assert.deepEqual(Object.keys(rankShopMap), ["9700118"])
    assert.ok(serverEventShops["11"]["700099"]["9700118"])
})

test("旧称号保留并追加五个新赛季称号、两种竞速票券和四个 Boss 角色卡池", () => {
    assert.deepEqual(Object.keys(rankDegrees).map(Number), [
        9900002, 9900003, 9900004, 9900005, 9900006,
        9900007, 9900008, 9900009, 9900010, 9900011,
    ])
    assert.equal(rankDegrees["9900002"].name, "深渊冠军")
    assert.deepEqual(
        [9900007, 9900008, 9900009, 9900010, 9900011].map(id => rankDegrees[String(id)].name),
        ["星渊主宰者", "星渊征服者", "星渊讨伐者", "破阵先行者", "共赴星渊"],
    )
    assert.ok(rankItems.includes(999015))
    assert.ok(rankItems.includes(999016))
    assert.ok(rankItems.includes(999017))
    assert.ok(rankItems.includes(999018))
    assert.equal(itemLookup["999015"], "终焉裁定券")
    assert.equal(itemLookup["999016"], "终焉裁定券（十连）")

    const gacha = serverGachas["990002"]
    assert.equal(gacha.onceTicketItemId, 999017)
    assert.equal(gacha.tenTicketItemId, 999018)
    const poolIds = new Set(Object.values(gacha.pool).flat().map(row => row.id))
    for (const characterId of RANK_BOSS_CHARACTER_IDS) {
        assert.ok(poolIds.has(characterId), `missing ${characterId}`)
    }
})

test("四个 Boss 是普通双板角色，不误注册为角色觉醒活动", async () => {
    const selectedTables = new Set(rankPatchAudit.tables.map(entry => entry.logical))
    assert.ok(![...selectedTables].some(logical => (
        logical.includes("character_awake_event")
        || logical.includes("character_awake_mission")
    )))

    const awakeStatus = decodeOrderedMap(
        await readRankPatchLogical("master/character/character_awake_status.orderedmap"),
        true,
    )
    const abilities = decodeOrderedMap(
        await readRankPatchLogical("master/ability/ability.orderedmap"),
        true,
    )
    const actionSkills = decodeOrderedMap(
        await readRankPatchLogical("master/skill/action_skill.orderedmap"),
        false,
    )
    const characterRows = require("../assets/cdndata/character_rank_p5b.json")

    for (const characterId of RANK_BOSS_CHARACTER_IDS) {
        assert.equal(awakeStatus.get(String(characterId)).toString("utf8").trim(), "0,0")
        for (let slot = 1; slot <= 6; slot += 1) {
            const rows = abilities.get(`${characterId}${slot}`).toString("utf8").trim().split(/\r?\n/)
            for (const row of rows) {
                const leadingFields = row.split(",", 5)
                assert.equal(leadingFields[3], "0", `${characterId}/${slot} has an awake-gated ability row`)
                assert.equal(leadingFields[4], "", `${characterId}/${slot} has an awake-level ability row`)
            }
        }

        const codeName = characterRows[String(characterId)][0][0]
        const variants = decodeOrderedMap(actionSkills.get(codeName), true)
        assert.deepEqual([...variants.keys()], ["1", "2"], `${characterId} unexpectedly has skill evolution 3`)
    }
})

test("深渊武器客户端分解标记保留，实际产魂仍仅限死亡使者", () => {
    const marker = seasonRankTitleAudit.client_disassembly
    assert.deepEqual(marker.abyss_marker_values, Array(15).fill("true"))
    assert.equal(marker.death_bringer_marker, "true")
    assert.deepEqual(marker.server_soul_generation_ids, [5900101])
})
