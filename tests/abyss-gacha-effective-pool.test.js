const test = require("node:test")
const assert = require("node:assert/strict")

const baseGachas = require("../assets/gacha.json")
const cnmodGachas = require("../assets/gacha_cnmod.json")
const { getGachaSync } = require("../out/lib/assets")

const ABYSS_GACHA_ID = "990001"
const NEW_CHARACTER_IDS = [149995, 169996, 169997]

test("keeps the mirrored abyss pool identical in both runtime sources", () => {
    assert.deepEqual(cnmodGachas[ABYSS_GACHA_ID], baseGachas[ABYSS_GACHA_ID])
})

test("loads all three new characters at an effective 0.38% rate", () => {
    const gacha = getGachaSync(Number(ABYSS_GACHA_ID))
    assert.ok(gacha)
    assert.deepEqual(gacha.rankRates.normal, [150, 350, 500])
    assert.deepEqual(gacha.rankRates.multiGuarantee, [150, 850])
    assert.equal(gacha.onceTicketItemId, 999013)
    assert.equal(gacha.tenTicketItemId, 999014)

    const fiveStarPool = gacha.pool["1"]
    assert.equal(fiveStarPool.length, 253)
    assert.equal(new Set(fiveStarPool.map(item => item.id)).size, 253)
    const totalWeight = fiveStarPool.reduce((sum, item) => sum + item.odds, 0)
    assert.equal(totalWeight, 1_593_000)

    const fiveStarRates = [gacha.rankRates.normal, gacha.rankRates.multiGuarantee]
        .map(rates => rates[0] / rates.reduce((sum, weight) => sum + weight, 0))
    for (const characterId of NEW_CHARACTER_IDS) {
        const rows = fiveStarPool.filter(item => item.id === characterId)
        assert.equal(rows.length, 1)
        assert.equal(rows[0].odds, 40_356)
        assert.equal(rows[0].isRateUp, true)
        assert.equal(rows[0].isLimited, true)
        assert.equal(rows[0].isExchangeable, false)
        for (const fiveStarRate of fiveStarRates) {
            assert.ok(Math.abs(fiveStarRate * rows[0].odds / totalWeight - 0.0038) < 1e-12)
        }
    }
})
