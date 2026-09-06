const test = require("node:test")
const assert = require("node:assert/strict")
const crypto = require("node:crypto")
const fs = require("node:fs/promises")
const path = require("node:path")
const zlib = require("node:zlib")
const unzipper = require("unzipper")

const baseGachas = require("../assets/gacha.json")
const cnmodGachas = require("../assets/gacha_cnmod.json")
const rankGachas = require("../assets/gacha_rank_p5b.json")
const characterTable = require("../data/character_table.json")
const { getGachaSync } = require("../out/lib/assets")
const { getExchangeableGachaItem } = require("../out/lib/gacha-rules")
const manifest = require("../assets/asset-patch/manifest.json")
const {
    AUDITED_NON_GACHA_CHARACTER_IDS,
    REMOVED_NON_GACHA_CHARACTER_IDS,
    RETAINED_NON_GACHA_EXCEPTION_IDS,
    collectOtherGachaCharacterIds,
    findNonGachaFillers,
    poolTotal,
} = require("../tools/cleanup_abyss_gacha_pool.cjs")

const ABYSS_GACHA_ID = "990001"
const RACE_GACHA_ID = "990002"
const ABYSS_NON_EXCHANGEABLE_IDS = new Set([
    129952, // 水魔女（潮汐的魔女）
    169980, // 深渊之兽
    169994, // 白虎
    169995, // 魔王
    179981, // 歼灭者
])
const CLIENT_PATCH_DIR = path.join(
    __dirname,
    "..",
    "assets",
    "asset-patch",
    "active",
)
const CLIENT_EXCHANGE_ARCHIVE = "pinball-1.4.99-1.4.100-1-abyss-exchange-shop-banners.zip"
const CLIENT_TITLE_ARCHIVE = "pinball-1.4.99-1.4.100-2-rank-title-conditions.zip"
const clientArchives = new Map()
const CLIENT_HASH_SALT = "K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy"
const EXPECTED_RATE_UP_WEIGHTS = new Map([
    [129952, 30_000],
    [169980, 30_000],
    [169994, 30_000],
    [169995, 30_000],
    [179981, 30_000],
    [119996, 10_000],
    [119997, 10_000],
    [129997, 10_000],
    [129999, 10_000],
    [139997, 10_000],
    [139998, 10_000],
    [139999, 10_000],
    [149996, 10_000],
    [149997, 10_000],
    [149998, 10_000],
    [149999, 10_000],
    [169998, 10_000],
    [169999, 10_000],
    [179999, 10_000],
    [149995, 10_000],
    [169996, 10_000],
    [169997, 10_000],
])

function decodeOrderedMapRaw(raw) {
    const indexLength = raw.readUInt32LE(0)
    const index = zlib.inflateSync(raw.subarray(4, 4 + indexLength))
    const count = index.readUInt32LE(0)
    const keyStart = 4 + count * 8
    const keyBlob = index.subarray(keyStart)
    const valueBlob = raw.subarray(4 + indexLength)
    const keys = []
    const rows = []
    let keyEnd = 0
    let rowEnd = 0
    for (let indexOffset = 0; indexOffset < count; indexOffset += 1) {
        const nextKeyEnd = index.readUInt32LE(4 + indexOffset * 8)
        const nextRowEnd = index.readUInt32LE(8 + indexOffset * 8)
        keys.push(keyBlob.subarray(keyEnd, nextKeyEnd).toString("utf8"))
        rows.push(valueBlob.subarray(rowEnd, nextRowEnd))
        keyEnd = nextKeyEnd
        rowEnd = nextRowEnd
    }
    return { keys, rows }
}

async function readClientPayload(logical) {
    const digest = crypto.createHash("sha1")
        .update(logical + CLIENT_HASH_SALT)
        .digest("hex")
    const memberName = `production/upload/${digest.slice(0, 2)}/${digest.slice(2)}`
    const releases = manifest.patches.filter(item => item.enabled && item.type === "patch")
    for (const release of [...releases].reverse()) {
        const names = release.chain ?? [release.archive]
        for (const name of [...names].reverse()) {
            if (!clientArchives.has(name)) {
                clientArchives.set(name, unzipper.Open.file(path.join(CLIENT_PATCH_DIR, name)))
            }
            const archive = await clientArchives.get(name)
            const member = archive.files.find(file => file.path === memberName)
            if (member) return member.buffer()
        }
    }
    assert.fail(`active client chain is missing ${logical}`)
}

async function readClientOddsRows(logical) {
    const outer = decodeOrderedMapRaw(await readClientPayload(logical))
    assert.equal(outer.keys.length, 1)
    const inner = decodeOrderedMapRaw(outer.rows[0])
    return inner.rows.map(row => zlib.inflateSync(row).toString("utf8"))
}

test("keeps the mirrored abyss pool identical in both runtime sources", () => {
    assert.deepEqual(cnmodGachas[ABYSS_GACHA_ID], baseGachas[ABYSS_GACHA_ID])
})

test("abyss exchange flags allow only UP and collab characters except five locked pickups", () => {
    const gacha = getGachaSync(ABYSS_GACHA_ID)
    assert.ok(gacha)
    assert.deepEqual(gacha, cnmodGachas[ABYSS_GACHA_ID])
    const collabIds = new Set(
        characterTable
            .filter(entry => entry.source === "联动")
            .map(entry => Number(entry.code_number)),
    )
    const entries = Object.values(gacha.pool).flat()
    const expectedExchangeable = entry => (
        !ABYSS_NON_EXCHANGEABLE_IDS.has(entry.id)
        && (entry.isRateUp || collabIds.has(entry.id))
    )

    for (const entry of entries) {
        assert.equal(
            entry.isExchangeable,
            expectedExchangeable(entry),
            `exchange policy drifted for character ${entry.id}`,
        )
    }
    assert.equal(entries.filter(entry => entry.isExchangeable).length, 39)
    assert.deepEqual(
        entries.filter(entry => entry.isRateUp && !entry.isExchangeable).map(entry => entry.id),
        [...ABYSS_NON_EXCHANGEABLE_IDS].filter(id => entries.some(entry => entry.id === id)),
    )
})

test("removes audited fillers except the six approved characters without changing any UP rate", () => {
    const gacha = getGachaSync(Number(ABYSS_GACHA_ID))
    assert.ok(gacha)
    assert.deepEqual(gacha.rankRates.normal, [150, 350, 500])
    assert.deepEqual(gacha.rankRates.multiGuarantee, [150, 850])
    assert.equal(gacha.onceTicketItemId, 999013)
    assert.equal(gacha.tenTicketItemId, 999014)

    assert.deepEqual(
        Object.fromEntries(Object.entries(gacha.pool).map(([bucket, entries]) => [bucket, entries.length])),
        { "1": 253, "2": 125, "3": 76 },
    )
    assert.deepEqual(
        Object.fromEntries(Object.entries(gacha.pool).map(([bucket, entries]) => [bucket, poolTotal(entries)])),
        { "1": 1_500_000, "2": 2_184, "3": 1_113 },
    )
    const allIds = Object.values(gacha.pool).flat().map(item => item.id)
    assert.equal(new Set(allIds).size, allIds.length)
    for (const characterId of REMOVED_NON_GACHA_CHARACTER_IDS) {
        assert.equal(allIds.includes(characterId), false)
    }
    for (const characterId of RETAINED_NON_GACHA_EXCEPTION_IDS) {
        assert.equal(allIds.filter(id => id === characterId).length, 1)
    }

    const otherGachaCharacterIds = collectOtherGachaCharacterIds(baseGachas, cnmodGachas)
    for (const characterId of AUDITED_NON_GACHA_CHARACTER_IDS) {
        assert.equal(otherGachaCharacterIds.has(characterId), false)
    }
    assert.deepEqual(
        findNonGachaFillers(gacha, otherGachaCharacterIds)
            .map(({ id }) => id)
            .sort((a, b) => a - b),
        [...RETAINED_NON_GACHA_EXCEPTION_IDS],
    )

    const fiveStarPool = gacha.pool["1"]
    const totalWeight = poolTotal(fiveStarPool)
    assert.equal(totalWeight, 1_500_000)

    const fiveStarRates = [gacha.rankRates.normal, gacha.rankRates.multiGuarantee]
        .map(rates => rates[0] / rates.reduce((sum, weight) => sum + weight, 0))
    const actualRateUps = fiveStarPool.filter(item => item.isRateUp)
    assert.deepEqual(actualRateUps.map(item => item.id), [...EXPECTED_RATE_UP_WEIGHTS.keys()])
    for (const [characterId, expectedWeight] of EXPECTED_RATE_UP_WEIGHTS) {
        const rows = fiveStarPool.filter(item => item.id === characterId)
        assert.equal(rows.length, 1)
        assert.equal(rows[0].odds, expectedWeight)
        assert.equal(rows[0].isRateUp, true)
        assert.equal(rows[0].isLimited, true)
        const expectedRate = expectedWeight === 30_000 ? 0.003 : 0.001
        for (const fiveStarRate of fiveStarRates) {
            assert.ok(Math.abs(fiveStarRate * rows[0].odds / totalWeight - expectedRate) < 1e-12)
        }
    }
})

test("removes the same audited fillers from the race pool while preserving zero-weight placeholders", () => {
    const gacha = getGachaSync(Number(RACE_GACHA_ID))
    assert.ok(gacha)
    assert.deepEqual(gacha.rankRates.normal, [950, 20, 30])
    assert.deepEqual(gacha.rankRates.multiGuarantee, [950, 50])
    assert.equal(gacha.onceTicketItemId, 999017)
    assert.equal(gacha.tenTicketItemId, 999018)
    assert.deepEqual(
        Object.fromEntries(Object.entries(gacha.pool).map(([bucket, entries]) => [bucket, entries.length])),
        { "1": 286, "2": 125, "3": 76 },
    )
    assert.deepEqual(
        Object.fromEntries(Object.entries(gacha.pool).map(([bucket, entries]) => [bucket, poolTotal(entries)])),
        { "1": 950_000, "2": 2_184, "3": 1_113 },
    )

    const allIds = Object.values(gacha.pool).flat().map(item => item.id)
    assert.equal(new Set(allIds).size, allIds.length)
    for (const characterId of REMOVED_NON_GACHA_CHARACTER_IDS) {
        assert.equal(allIds.includes(characterId), false)
    }
    for (const characterId of RETAINED_NON_GACHA_EXCEPTION_IDS) {
        assert.equal(allIds.filter(id => id === characterId).length, 1)
    }

    const sourceZeroWeightIds = Object.values(rankGachas[RACE_GACHA_ID].pool)
        .flat()
        .filter(item => item.odds === 0)
        .map(item => item.id)
    assert.equal(sourceZeroWeightIds.length, 19)
    for (const characterId of sourceZeroWeightIds) {
        assert.equal(gacha.pool["1"].find(item => item.id === characterId)?.odds, 0)
    }
})

test(
    "effective client chain mirrors both runtime pools and exchange eligibility",
    async () => {
    const specs = [
        ["990001", "cnmod_abyss_limited_gacha"],
        ["990002", "cnmod_ashen_verdict_gacha"],
    ]
    for (const [gachaId, prefix] of specs) {
        const gacha = getGachaSync(gachaId)
        const pool = gacha.pool
        for (const [rank, bucket] of [[5, "1"], [4, "2"], [3, "3"]]) {
            const logical = `master/gacha_odds/${prefix}_character_${rank}.orderedmap`
            const actual = await readClientOddsRows(logical)
            const expected = pool[bucket].map(entry => [
                entry.id,
                entry.rank,
                entry.odds,
                String(entry.isRateUp).toLowerCase(),
                String(entry.isLimited).toLowerCase(),
                String(entry.isExchangeable).toLowerCase(),
                String(entry.trialReadingForced).toLowerCase(),
            ].join(","))
            assert.deepEqual(actual, expected, `${gachaId}/${rank} client rows drifted`)
            for (const row of actual) {
                const fields = row.split(",")
                assert.equal(
                    getExchangeableGachaItem(gacha, Number(fields[0])) !== null,
                    fields[5] === "true",
                    `${gachaId}/${fields[0]} client display disagrees with exchange route`,
                )
            }
        }
    }
})

test("1.4.100 combines six resources and preserves published archives", async () => {
    const release = manifest.patches.find(item => item.id === "abyss-exchange-shop-banners-1.4.100")
    assert.ok(release?.enabled)
    assert.equal(release.depends_on, "1.4.99")
    assert.equal(release.version, "1.4.100")
    assert.equal(manifest.cdn_version, "1.4.100")
    assert.deepEqual(release.chain, [CLIENT_EXCHANGE_ARCHIVE, CLIENT_TITLE_ARCHIVE])
    assert.equal(release.files.length, 6)
    assert.equal(release.archive_integrity[0].sha256, "8875fe6cdefc39b25dc0bd28905c988fe5b6cfc9877817f7fbd6a9fc64c86f12")
    const prior = manifest.patches.find(item => item.id === "siete-balance-visual-restore-1.4.99")
    assert.equal(prior.chain.length, 3)
    const priorHashes = [
        "3a024838a67eecd8bc8a7cd853b50b45f1072dea3372fdaf8cf4b538ddad1d7b",
        "05bd5107c71e0d0cc37092f47ceb1d7d422ae99193ee70de4c2646fc8b898fac",
        "adeb67bc1c5af46221c92ba3ca3e8a90471632dd90ead78ad9950f7a9e6a7ec3",
    ]
    assert.deepEqual(prior.archive_integrity.map(item => item.sha256), priorHashes)
    for (const item of [...prior.archive_integrity, ...release.archive_integrity]) {
        const bytes = await fs.readFile(path.join(CLIENT_PATCH_DIR, item.name))
        assert.equal(bytes.length, item.size)
        assert.equal(crypto.createHash("sha256").update(bytes).digest("hex"), item.sha256)
    }
    const archive = await unzipper.Open.file(path.join(CLIENT_PATCH_DIR, CLIENT_EXCHANGE_ARCHIVE))
    assert.deepEqual(archive.files.map(file => file.path), release.archive_integrity[0].files)
    const banners = [
        ["production/upload/af/6ad4e513edc45a835d26ae8482ec384ff62ce7", 1000, 184, "157a2af894b4500cb373ac7af56b34c74e70be757e17a2614058aae5af7d8ca3"],
        ["production/upload/35/937c7ff9d7006ffa407887910bbec9fc41bc06", 1440, 556, "19bef4da76737ab0bdad1cf81d3d5d50759a3a8059dd43ed86d882483d46ec3c"],
    ]
    for (const [name, width, height, sha256] of banners) {
        const bytes = await archive.files.find(file => file.path === name).buffer()
        assert.equal(crypto.createHash("sha256").update(bytes).digest("hex"), sha256)
        assert.equal(bytes.readUInt32BE(16), width)
        assert.equal(bytes.readUInt32BE(20), height)
    }
    const note = zlib.inflateRawSync(await readClientPayload("rich_text/cnmod_abyss_limited_gacha_note.html.deflate")).toString("utf8")
    assert.ok(note.includes("除水魔女、深渊之兽、白虎、魔王、歼灭者外，其余UP角色及池内联动角色可兑换，每名需250点；其余角色不可兑换。"))
    assert.ok(note.includes("其余231名★5角色的总出现概率为11.8%"))
    assert.equal(note.includes("其余★5角色各需250点兑换"), false)
})

test("same .100 update changes only five title conditions and preserves all other title data", async () => {
    const audit = require("../assets/asset-patch/audit/rank-title-conditions-1.4.100/report.json")
    const policy = require("../assets/leaderboard_reward_policy.json")
    const { degreeDefinitions } = require("../out/lib/content-master")
    const sourceArchive = await unzipper.Open.file(path.join(CLIENT_PATCH_DIR, path.basename(audit.source.archive)))
    const beforeRaw = await sourceArchive.files.find(file => file.path === audit.source.member).buffer()
    assert.equal(crypto.createHash("sha256").update(beforeRaw).digest("hex"), audit.source.sha256)
    const afterRaw = await readClientPayload("master/degree/degree.orderedmap")
    const before = decodeOrderedMapRaw(beforeRaw)
    const after = decodeOrderedMapRaw(afterRaw)
    assert.deepEqual(after.keys, before.keys)
    const changed = []
    const targets = new Set(["9900007", "9900008", "9900009", "9900010", "9900011"])
    for (const [index, key] of before.keys.entries()) {
        if (!targets.has(key)) {
            assert.deepEqual(after.rows[index], before.rows[index], `${key} was unexpectedly changed`)
            continue
        }
        const oldFields = zlib.inflateSync(before.rows[index]).toString("utf8").split(",")
        const newFields = zlib.inflateSync(after.rows[index]).toString("utf8").split(",")
        assert.equal(newFields.length, 9)
        assert.deepEqual([...newFields.slice(0, 4), ...newFields.slice(5)], [...oldFields.slice(0, 4), ...oldFields.slice(5)])
        assert.notEqual(oldFields[4], newFields[4])
        assert.equal(newFields[4], policy.titleCondition)
        assert.equal(newFields[4], degreeDefinitions[key].condition)
        assert.equal(newFields[0], degreeDefinitions[key].string_id)
        assert.equal(newFields[2], degreeDefinitions[key].name)
        changed.push(key)
    }
    assert.deepEqual(changed, [...targets])
    const archive = await unzipper.Open.file(path.join(CLIENT_PATCH_DIR, CLIENT_TITLE_ARCHIVE))
    assert.deepEqual(archive.files.map(file => file.path), [audit.source.member])
    const integrated = require("../assets/asset-patch/audit/abyss-exchange-shop-banners-1.4.100/integrated-release.json")
    assert.equal(integrated.version, "1.4.100")
    assert.equal(integrated.total_bytes, integrated.archive_integrity.reduce((sum, item) => sum + item.size, 0))
    assert.equal(integrated.files.length, 6)
})
