const test = require("node:test")
const assert = require("node:assert/strict")
const crypto = require("node:crypto")
const path = require("node:path")
const zlib = require("node:zlib")
const unzipper = require("unzipper")

const baseGachas = require("../assets/gacha.json")
const cnmodGachas = require("../assets/gacha_cnmod.json")
const rankGachas = require("../assets/gacha_rank_p5b.json")
const { getGachaSync } = require("../out/lib/assets")
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
const CLIENT_PATCH_ARCHIVE = path.join(
    __dirname,
    "..",
    "assets",
    "asset-patch",
    "active",
    "pinball-1.4.98-1.4.99-3-gacha-non-gacha-cleanup.zip",
)
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

async function readClientOddsRows(logical) {
    const digest = crypto.createHash("sha1")
        .update(logical + CLIENT_HASH_SALT)
        .digest("hex")
    const memberName = `production/upload/${digest.slice(0, 2)}/${digest.slice(2)}`
    const archive = await unzipper.Open.file(CLIENT_PATCH_ARCHIVE)
    const member = archive.files.find(file => file.path === memberName)
    assert.ok(member, `client cleanup patch is missing ${logical}`)
    const outer = decodeOrderedMapRaw(await member.buffer())
    assert.equal(outer.keys.length, 1)
    const inner = decodeOrderedMapRaw(outer.rows[0])
    return inner.rows.map(row => zlib.inflateSync(row).toString("utf8"))
}

test("keeps the mirrored abyss pool identical in both runtime sources", () => {
    assert.deepEqual(cnmodGachas[ABYSS_GACHA_ID], baseGachas[ABYSS_GACHA_ID])
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

test("client cleanup patch mirrors both final server pools", async () => {
    const manifest = require("../assets/asset-patch/manifest.json")
    const release = manifest.patches.find(item => item.id === "siete-balance-visual-restore-1.4.99")
    assert.ok(release)
    assert.equal(manifest.cdn_version, "1.4.99")
    assert.ok(release.chain.includes(path.basename(CLIENT_PATCH_ARCHIVE)))
    assert.equal(release.chain.length, 3)
    assert.equal(release.archive, release.chain[0])
    assert.equal(release.archive_size, release.archive_integrity[0].size)
    assert.equal(
        manifest.patches.some(item => item.id === "gacha-non-gacha-cleanup-client-1.4.100"),
        false,
    )
    const specs = [
        ["990001", "cnmod_abyss_limited_gacha", baseGachas],
        ["990002", "cnmod_ashen_verdict_gacha", rankGachas],
    ]
    for (const [gachaId, prefix, sources] of specs) {
        const pool = sources[gachaId].pool
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
        }
    }
})
