const test = require('node:test')
const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const temporaryRoot = path.resolve(os.tmpdir())
const isolatedDirectory = fs.mkdtempSync(path.join(temporaryRoot, 'holiday-pool-migration-'))
process.env.DATA_DIR = path.join(isolatedDirectory, 'database')
process.env.GACHA_SEED_DIR = path.join(isolatedDirectory, 'seeds')
process.env.GAME_VERBOSE_LOGS = 'false'
fs.mkdirSync(process.env.GACHA_SEED_DIR, { recursive: true })

const { getGachaSync } = require('../out/lib/assets')
const { getExchangeableGachaItem } = require('../out/lib/gacha-rules')
const { serverGachas } = require('../out/lib/content-master')

const GACHA_SPECS = {
    990001: {
        total: 150000,
        weight: 2000,
        pickupRate: 0.002,
        rates: { normal: [150, 350, 500], multiGuarantee: [150, 850] },
        newExchangeable: false,
        rows: 294,
    },
    990002: {
        total: 950000,
        weight: 10000,
        pickupRate: 0.01,
        rates: { normal: [950, 20, 30], multiGuarantee: [950, 50] },
        newExchangeable: true,
        rows: 318,
    },
}
const NEW_IDS = [119992, 119990, 169988, 169991, 149987, 159995, 119991, 139992, 139991, 149986, 139990, 159994]
const PRIOR_IDS = [139994, 139993, 159998, 159997, 159996, 169992, 129991]
const PRIOR_SET = new Set(PRIOR_IDS)
const EXISTING_MOD_IDS = [
    139994, 139993, 159998, 159997, 159996, 169992, 129991,
    149990, 119989, 149989, 169989, 149988, 129992, 139995,
    129952, 169980, 169994, 169995, 179981, 119996, 119997,
    129997, 129999, 139997, 139998, 139999, 149996, 149997,
    149998, 149999, 169998, 169999, 179999, 149995, 169996,
    169997, 119993, 119994, 119995, 129993, 129994, 129995,
    129996, 129998, 139996, 149991, 149992, 149993, 149994,
    159999, 169993,
]
const NON_MOD_BASELINE = {
    990001: {
        396: [151147, 151153, 151159, 151165, 151171, 151182, 161001, 161002, 161004, 161005, 161006, 161007, 161008, 161009, 161015, 161021, 161027, 161033, 161039, 161045, 161051, 161057, 161063, 161069, 161081, 161082, 161087, 161093, 161099, 161105, 161111, 161117, 161123, 161129, 161135, 161141, 161147, 161153, 161159, 161165, 161171, 161177, 161183, 161189, 161195, 161201, 261089],
        397: [151081, 151087, 151093, 151099, 151105, 151111, 151117, 151123, 151129, 151141],
        398: [151033, 151039, 151045, 151051, 151057, 151063, 151069, 151075],
        399: [111001, 111002, 111003, 111004, 111005, 111006, 111007, 111009, 111015, 111021, 111027, 111033, 111039, 111045, 111051, 111057, 111063, 111069, 111081, 111087, 111093, 111099, 111105, 111111, 111117, 111123, 111129, 111135, 111141, 111147, 111153, 111159, 111165, 111171, 111177, 111183, 121001, 121002, 121003, 121004, 121005, 121006, 121007, 121008, 121009, 121015, 121021, 121027, 121033, 121039, 121045, 121051, 121057, 121069, 121070, 121075, 121081, 121087, 121093, 121099, 121105, 121111, 121117, 121123, 121129, 121135, 121141, 121147, 121153, 121159, 121165, 121171, 121177, 121183, 121189, 123001, 131001, 131002, 131003, 131004, 131005, 131011, 131012, 131013, 131014, 131020, 131026, 131032, 131038, 131044, 131050, 131056, 131062, 131068, 131074, 131080, 131086, 131092, 131098, 131104, 131110, 131116, 131122, 131128, 131134, 131140, 131146, 131152, 131158, 131164, 131170, 131176, 131182, 141001, 141002, 141004, 141005, 141006, 141007, 141008, 141009, 141015, 141021, 141027, 141033, 141039, 141045, 141051, 141057, 141063, 141069, 141081, 141087, 141093, 141099, 141105, 141111, 141117, 141123, 141129, 141135, 141141, 141147, 141153, 141159, 141165, 141171, 141177, 141183, 141189, 141201, 151001, 151002, 151003, 151004, 151005, 151006, 151007, 151009, 151011, 151012, 151013, 151014, 151015, 151021, 151027],
    },
    990002: {
        1903: [151045, 151051, 151057, 151063, 151069, 151075, 151081, 151087, 151093, 151099, 151105, 151111, 151117, 151123, 151129, 151141, 151147, 151153, 151159, 151165, 151171, 151182, 161001, 161002, 161004, 161005, 161006, 161007, 161008, 161009, 161015, 161021, 161027, 161033, 161039, 161045, 161051, 161057, 161063, 161069, 161081, 161082, 161087, 161093, 161099, 161105, 161111, 161117, 161123, 161129, 161135, 161141, 161147, 161153, 161159, 161165, 161171, 161177, 161183, 161189, 161195, 161201, 261089],
        1904: [151011, 151012, 151013, 151014, 151015, 151021, 151027, 151033, 151039],
        1905: [121123, 121129, 121135, 121141, 121147, 121153, 121159, 121165, 121171, 121177, 121183, 121189, 123001, 131003, 131013, 131014, 131020, 131026, 131056, 131074, 131086, 131104, 131122, 131128, 131134, 131140, 131146, 131152, 131158, 131164, 131170, 131176, 131182, 141001, 141002, 141004, 141005, 141006, 141007, 141008, 141009, 141015, 141021, 141027, 141033, 141039, 141045, 141051, 141057, 141063, 141069, 141081, 141087, 141093, 141099, 141105, 141111, 141117, 141123, 141129, 141135, 141141, 141147, 141153, 141159, 141165, 141171, 141177, 141183, 141189, 141201, 151001, 151002, 151003, 151004, 151005, 151006, 151007, 151009],
        1906: [121001, 121002, 131001, 131002, 131004, 131005, 131011, 131012, 131032, 131038, 131044, 131050, 131062, 131068, 131080, 131092, 131098, 131110, 131116, 111001, 111002, 111003, 111004, 111005, 111006, 111007, 111009, 111015, 111021, 111027, 111033, 111039, 111045, 111051, 111057, 111063, 111069, 111081, 111087, 111093, 111099, 111105, 111111, 111117, 111123, 111129, 111135, 111141, 111147, 111153, 111159, 111165, 111171, 111177, 111183, 121003, 121004, 121005, 121006, 121007, 121008, 121009, 121015, 121021, 121027, 121033, 121039, 121045, 121051, 121057, 121069, 121070, 121075, 121081, 121087, 121093, 121099, 121105, 121111, 121117],
    },
}
const ZERO_DISABLED_BASELINE = {
    990001: { limited: [] , unlimited: [] },
    990002: {
        limited: [119950, 119951, 119970, 129950, 129951, 129970, 139950, 139951, 139970, 149950, 149951, 149970, 159950, 159951, 159970, 169950, 169951, 169970, 179970],
        unlimited: [179982, 179983, 179984, 179985, 179986],
    },
}
const LOW_STAR_BASELINE = {
    990001: {
        2: { length: 125, sum: 2184, sha256: 'f79786891bb50405e4b1370d4f6eef55117c4a249aaa14df1a9b5f6edff16409' },
        3: { length: 76, sum: 1113, sha256: '846a5bfd1faf02a312a48838fa2bcd78a3846278f295ab5d79ae86d47ac0d01f' },
    },
    990002: {
        2: { length: 125, sum: 2184, sha256: '11b3a7cbbe22ba230463aed4c3bc9dc01f8be253b15f35033687211f042f65f7' },
        3: { length: 76, sum: 1113, sha256: '45fab03f0123affdacc62188da102b95ef447da0254a3ed08cd95c79ea92f17c' },
    },
}

function canonicalize(value) {
    if (Array.isArray(value)) return value.map(canonicalize)
    if (value && typeof value === 'object') {
        return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonicalize(value[key])]))
    }
    return value
}

function digestRows(rows) {
    return crypto.createHash('sha256').update(JSON.stringify(canonicalize(rows))).digest('hex')
}

function assertExactPickupProbabilities(gacha, spec, ids) {
    const pool = gacha.pool['1']
    const byId = new Map(pool.map(row => [row.id, row]))
    for (const ratesKey of ['normal', 'multiGuarantee']) {
        const rates = gacha.rankRates[ratesKey]
        assert.equal(rates.reduce((sum, value) => sum + value, 0), 1000)
        const fiveStarRate = rates[0] / 1000
        for (const id of ids) {
            const row = byId.get(id)
            assert.ok(row, `missing pickup ${id} in ${id === 990001 ? 'abyss' : 'race'} pool`)
            const actual = fiveStarRate * row.odds / spec.total
            assert.ok(Math.abs(actual - spec.pickupRate) < 1e-15, `${id}/${ratesKey} probability drift`)
        }
    }
}

function assertLargestRemainderAllocation(rows, baselineGroups, addedWeight) {
    const byId = new Map(rows.map(row => [row.id, row]))
    const baseline = []
    for (const [oldOdds, ids] of Object.entries(baselineGroups)) {
        for (const id of ids) baseline.push({ id, oldOdds: Number(oldOdds) })
    }
    assert.equal(baseline.length, 231)
    const oldTotal = baseline.reduce((sum, entry) => sum + entry.oldOdds, 0)
    assert.ok(oldTotal === 92000 || oldTotal === 440000)
    const targetTotal = oldTotal - addedWeight
    const projected = baseline.map(entry => {
        const numerator = entry.oldOdds * targetTotal
        return {
            id: entry.id,
            floor: Math.floor(numerator / oldTotal),
            remainder: numerator % oldTotal,
        }
    })
    const seats = targetTotal - projected.reduce((sum, entry) => sum + entry.floor, 0)
    const sortedRemainders = projected.map(entry => entry.remainder).sort((a, b) => b - a)
    const threshold = seats > 0 && seats < projected.length ? sortedRemainders[seats - 1] : null
    const actualRows = rows.filter(row => !row.isRateUp && row.odds > 0)
    assert.deepEqual(
        actualRows.map(row => row.id).sort((a, b) => a - b),
        projected.map(entry => entry.id).sort((a, b) => a - b),
    )
    let ceilCount = 0
    for (const entry of projected) {
        const row = byId.get(entry.id)
        assert.ok(row, `missing adjusted non-MOD row ${entry.id}`)
        assert.equal(row.isRateUp, false)
        const lower = entry.floor
        const upper = entry.remainder === 0 ? lower : lower + 1
        assert.ok(row.odds === lower || row.odds === upper, `${entry.id} is outside the largest-remainder bounds`)
        if (seats <= 0) {
            assert.equal(row.odds, lower)
        } else if (seats >= projected.length) {
            assert.equal(row.odds, upper)
        } else if (entry.remainder > threshold) {
            assert.equal(row.odds, upper)
        } else if (entry.remainder < threshold) {
            assert.equal(row.odds, lower)
        }
        if (row.odds === upper && upper !== lower) ceilCount += 1
    }
    assert.equal(ceilCount, seats)
    assert.equal(actualRows.reduce((sum, row) => sum + row.odds, 0), targetTotal)
}

function assertZeroDisabledUnchanged(rows, baseline) {
    const actual = rows.filter(row => row.odds === 0 && row.isRateUp === false)
    const expectedIds = [...baseline.limited, ...baseline.unlimited]
    assert.deepEqual(actual.map(row => row.id).sort((a, b) => a - b), expectedIds.slice().sort((a, b) => a - b))
    const limited = new Set(baseline.limited)
    for (const row of actual) {
        assert.deepEqual(row, {
            id: row.id,
            rank: 5,
            odds: 0,
            isRateUp: false,
            isLimited: limited.has(row.id),
            isExchangeable: false,
            rarity: 0,
            trialReadingForced: false,
        })
    }
}

function assertLowStarUnchanged(gacha, baseline) {
    for (const bucket of ['2', '3']) {
        const rows = gacha.pool[bucket]
        assert.equal(rows.length, baseline[bucket].length)
        assert.equal(rows.reduce((sum, row) => sum + row.odds, 0), baseline[bucket].sum)
        assert.equal(digestRows(rows), baseline[bucket].sha256, `${bucket}-star pool drifted`)
    }
}

test('winning accessor, mirrored pools and exact holiday pickup weights are stable', () => {
    const base = require('../assets/gacha.json')
    const mirrors = {
        990001: require('../assets/gacha_cnmod.json'),
        990002: require('../assets/gacha_rank_p5b.json'),
    }
    for (const [gachaId, spec] of Object.entries(GACHA_SPECS)) {
        const gacha = getGachaSync(Number(gachaId))
        assert.ok(gacha, `winning accessor missed ${gachaId}`)
        assert.strictEqual(gacha, serverGachas[gachaId])
        assert.deepEqual(gacha, base[gachaId])
        assert.deepEqual(base[gachaId], mirrors[gachaId][gachaId])
        assert.deepEqual(gacha, mirrors[gachaId][gachaId])
        assert.deepEqual(gacha.rankRates, spec.rates)
        const rows = gacha.pool['1']
        assert.equal(rows.length, spec.rows)
        assert.equal(new Set(rows.map(row => row.id)).size, rows.length)
        assert.equal(rows.reduce((sum, row) => sum + row.odds, 0), spec.total)
        const byId = new Map(rows.map(row => [row.id, row]))

        for (const id of NEW_IDS) {
            const row = byId.get(id)
            assert.ok(row, `missing new character ${id} in ${gachaId}`)
            assert.equal(row.rank, 5)
            assert.equal(row.isRateUp, true)
            assert.equal(row.odds, spec.weight)
            assert.equal(row.isExchangeable, spec.newExchangeable)
            assert.equal(getExchangeableGachaItem(gacha, id) !== null, spec.newExchangeable)
        }
        for (const id of PRIOR_IDS) {
            const row = byId.get(id)
            assert.ok(row, `missing prior character ${id} in ${gachaId}`)
            assert.equal(row.rank, 5)
            assert.equal(row.isRateUp, true)
            assert.equal(row.odds, spec.weight)
            assert.equal(row.isExchangeable, true)
            assert.ok(getExchangeableGachaItem(gacha, id))
        }
        for (const id of EXISTING_MOD_IDS) {
            const row = byId.get(id)
            assert.ok(row, `missing existing MOD ${id} in ${gachaId}`)
            assert.equal(row.isRateUp, true)
            assert.equal(row.odds, gachaId === '990001' && !PRIOR_SET.has(id) ? 1000 : spec.weight)
        }
        assertExactPickupProbabilities(gacha, spec, [...NEW_IDS, ...PRIOR_IDS])
        assertLargestRemainderAllocation(rows, NON_MOD_BASELINE[gachaId], NEW_IDS.length * spec.weight)
        assertZeroDisabledUnchanged(rows, ZERO_DISABLED_BASELINE[gachaId])
        assertLowStarUnchanged(gacha, LOW_STAR_BASELINE[gachaId])
    }
})

test('exchange route honors the 12 new and 7 prior holiday character rotation', async t => {
    const Fastify = require('fastify')
    const route = require('../out/routes/api/gacha').default
    const { insertAccountSync } = require('../out/data/domains/account')
    const { insertDefaultPlayerSync } = require('../out/data/domains/player')
    const { saveAccountDefaultPlayer } = require('../out/data/activeAccount')
    const { insertSessionWithToken } = require('../out/data/domains/session')
    const { insertPlayerGachaInfoSync, getPlayerGachaInfoSync, updatePlayerGachaInfoSync } = require('../out/data/domains/gacha')
    const { getPlayerCharacterSync } = require('../out/data/domains/character')
    const { getDb } = require('../out/data/db')

    const app = Fastify({ logger: false })
    app.addHook('onSend', (_request, reply, payload, done) => done(null,
        String(reply.getHeader('content-type') || '').startsWith('application/x-msgpack') && typeof payload === 'object'
            ? JSON.stringify(payload)
            : payload))
    t.after(async () => {
        await app.close()
        getDb().close()
        const target = path.resolve(isolatedDirectory)
        assert.ok(target.startsWith(temporaryRoot + path.sep) && target !== temporaryRoot)
        fs.rmSync(target, { recursive: true, force: true })
    })
    await app.register(route, { prefix: '/gacha' })

    const account = insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'holiday-migration-test', idpId: '', status: 'normal' })
    const player = insertDefaultPlayerSync(account.id)
    saveAccountDefaultPlayer(account.id, player.id)
    const viewer = 79192001
    await insertSessionWithToken({ token: String(viewer), accountId: account.id, expires: new Date(Date.now() + 86400000), type: 2 })

    function points(gachaId, amount) {
        if (getPlayerGachaInfoSync(player.id, gachaId)) {
            updatePlayerGachaInfoSync(player.id, { gachaId, gachaExchangePoint: amount })
        } else {
            insertPlayerGachaInfoSync(player.id, {
                gachaId,
                isAccountFirst: false,
                isDailyFirst: false,
                gachaExchangePoint: amount,
            })
        }
    }

    const exchange = (gachaId, characterId) => app.inject({
        method: 'POST',
        url: '/gacha/exchange_character',
        payload: { viewer_id: viewer, gacha_id: gachaId, character_id: characterId, api_count: 1 },
    })

    for (const id of NEW_IDS) {
        const before = getPlayerCharacterSync(player.id, id)
        points(990001, 250)
        const rejected = await exchange(990001, id)
        assert.equal(rejected.statusCode, 400, rejected.payload)
        assert.equal(rejected.json().message, 'Character is not exchangeable from this gacha.')
        assert.equal(getPlayerGachaInfoSync(player.id, 990001).gachaExchangePoint, 250)
        assert.deepEqual(getPlayerCharacterSync(player.id, id), before)

        points(990002, 250)
        const accepted = await exchange(990002, id)
        assert.equal(accepted.statusCode, 200, accepted.payload)
        assert.equal(getPlayerGachaInfoSync(player.id, 990002).gachaExchangePoint, 0)
        assert.ok(getPlayerCharacterSync(player.id, id), `race exchange did not grant ${id}`)
    }

    for (const id of PRIOR_IDS) {
        for (const gachaId of [990001, 990002]) {
            points(gachaId, 250)
            const accepted = await exchange(gachaId, id)
            assert.equal(accepted.statusCode, 200, `${gachaId}/${id}: ${accepted.payload}`)
            assert.equal(getPlayerGachaInfoSync(player.id, gachaId).gachaExchangePoint, 0)
            assert.ok(getPlayerCharacterSync(player.id, id), `${gachaId} exchange did not grant ${id}`)
        }
    }
})
