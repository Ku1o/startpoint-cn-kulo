const test = require("node:test")
const assert = require("node:assert/strict")

const baseGachas = require("../assets/gacha.json")
const cnmodGachas = require("../assets/gacha_cnmod.json")
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
const EXPECTED_RATE_UP_WEIGHTS = new Map([
    [149995, 40_356],
    [169996, 40_356],
    [169997, 40_356],
    [119996, 10_620],
    [119997, 10_620],
    [149996, 10_620],
    [139997, 10_620],
    [129999, 10_620],
    [139998, 10_620],
    [139999, 10_620],
    [149998, 10_620],
    [149999, 10_620],
    [169998, 10_620],
    [169999, 10_620],
    [179999, 10_620],
    [129997, 10_620],
    [149997, 10_620],
])

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
        { "1": 248, "2": 125, "3": 76 },
    )
    assert.deepEqual(
        Object.fromEntries(Object.entries(gacha.pool).map(([bucket, entries]) => [bucket, poolTotal(entries)])),
        { "1": 1_593_000, "2": 2_184, "3": 1_113 },
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
    assert.equal(totalWeight, 1_593_000)

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
        const expectedRate = expectedWeight === 40_356 ? 0.0038 : 0.001
        for (const fiveStarRate of fiveStarRates) {
            assert.ok(Math.abs(fiveStarRate * rows[0].odds / totalWeight - expectedRate) < 1e-12)
        }
    }
})
