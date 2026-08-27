#!/usr/bin/env node
"use strict"

const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")

const REPOSITORY_ROOT = path.resolve(__dirname, "..")
const BASE_GACHA_PATH = path.join(REPOSITORY_ROOT, "assets", "gacha.json")
const CNMOD_GACHA_PATH = path.join(REPOSITORY_ROOT, "assets", "gacha_cnmod.json")
const ABYSS_GACHA_ID = "990001"

// Audited against every non-990001 pool in gacha.json and gacha_cnmod.json.
// These characters are rewards, shop characters, trial characters, tutorial
// characters, or collaboration/event giveaways rather than gacha characters.
const AUDITED_NON_GACHA_CHARACTER_IDS = Object.freeze([
    10,
    113001,
    123001,
    131182,
    141003,
    153001,
    163001,
    213001,
    213007,
    213013,
    223001,
    223007,
    223013,
    223019,
    233001,
    233007,
    233013,
    243001,
    243007,
    243013,
    243019,
    253001,
    253007,
    253013,
    253019,
    263001,
    263002,
    263003,
    263009,
    263015,
    323001,
    333001,
])
const RETAINED_NON_GACHA_EXCEPTION_IDS = Object.freeze([
    123001,
    131182,
    213007,
    263003,
    263009,
    263015,
])
const retainedNonGachaExceptionIdSet = new Set(RETAINED_NON_GACHA_EXCEPTION_IDS)
const REMOVED_NON_GACHA_CHARACTER_IDS = Object.freeze(
    AUDITED_NON_GACHA_CHARACTER_IDS.filter(id => !retainedNonGachaExceptionIdSet.has(id)),
)

function readJson(filePath) {
    return JSON.parse(fs.readFileSync(filePath, "utf8"))
}

function writeJson(filePath, value) {
    fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8")
}

function collectOtherGachaCharacterIds(...gachaSources) {
    const result = new Set()
    for (const gachas of gachaSources) {
        for (const [gachaId, gacha] of Object.entries(gachas)) {
            if (gachaId === ABYSS_GACHA_ID || !gacha || typeof gacha !== "object") continue
            for (const entries of Object.values(gacha.pool ?? {})) {
                if (!Array.isArray(entries)) continue
                for (const entry of entries) {
                    if (Number.isInteger(entry?.id) && entry.id > 0) result.add(entry.id)
                }
            }
        }
    }
    return result
}

function findNonGachaFillers(abyssGacha, otherGachaCharacterIds) {
    const result = []
    for (const [bucket, entries] of Object.entries(abyssGacha.pool ?? {})) {
        assert.ok(Array.isArray(entries), `abyss pool ${bucket} must be an array`)
        for (const entry of entries) {
            if (entry.isRateUp !== true && !otherGachaCharacterIds.has(entry.id)) {
                result.push({ bucket, id: entry.id })
            }
        }
    }
    return result
}

function poolTotal(entries) {
    return entries.reduce((sum, entry) => sum + entry.odds, 0)
}

function rateUpSignature(abyssGacha) {
    const result = []
    for (const [bucket, entries] of Object.entries(abyssGacha.pool)) {
        const bucketTotal = poolTotal(entries)
        for (const entry of entries) {
            if (entry.isRateUp === true) {
                result.push({ bucket, id: entry.id, odds: entry.odds, bucketTotal })
            }
        }
    }
    return result
}

function removeAndRedistribute(entries, removableIds) {
    const totalBefore = poolTotal(entries)
    const removed = entries.filter((entry) => removableIds.has(entry.id))
    const survivors = entries
        .filter((entry) => !removableIds.has(entry.id))
        .map((entry) => ({ ...entry }))
    const recipients = survivors.filter((entry) => entry.isRateUp !== true)
    const removedWeight = poolTotal(removed)

    if (removedWeight === 0) return survivors
    assert.ok(recipients.length > 0, "cannot redistribute removed weight without non-UP survivors")

    const quotient = Math.floor(removedWeight / recipients.length)
    const remainder = removedWeight % recipients.length
    for (const [index, entry] of recipients.entries()) {
        entry.odds += quotient + (index < remainder ? 1 : 0)
    }
    for (const entry of survivors) {
        entry.rarity = 1000 * entry.odds / totalBefore
    }
    assert.equal(poolTotal(survivors), totalBefore, "rarity bucket total weight changed")
    return survivors
}

function cleanupAbyssGacha(baseGachas, cnmodGachas) {
    const baseAbyss = baseGachas[ABYSS_GACHA_ID]
    const cnmodAbyss = cnmodGachas[ABYSS_GACHA_ID]
    assert.ok(baseAbyss, "base abyss gacha is missing")
    assert.ok(cnmodAbyss, "cnmod abyss gacha is missing")
    assert.deepEqual(cnmodAbyss, baseAbyss, "mirrored abyss gachas differ before cleanup")

    const otherGachaCharacterIds = collectOtherGachaCharacterIds(baseGachas, cnmodGachas)
    const discovered = findNonGachaFillers(baseAbyss, otherGachaCharacterIds)
    const allowedIds = new Set(AUDITED_NON_GACHA_CHARACTER_IDS)
    const unexpected = discovered.filter(({ id }) => !allowedIds.has(id))
    assert.deepEqual(unexpected, [], `unexpected non-gacha abyss fillers: ${JSON.stringify(unexpected)}`)

    const discoveredIds = discovered.map(({ id }) => id).sort((a, b) => a - b)
    const retainedMissing = RETAINED_NON_GACHA_EXCEPTION_IDS.filter(
        id => !discoveredIds.includes(id),
    )
    assert.deepEqual(retainedMissing, [], "approved retained abyss characters are missing")

    const removableIds = new Set(REMOVED_NON_GACHA_CHARACTER_IDS)
    const removable = discovered.filter(({ id }) => removableIds.has(id))
    if (removable.length === 0) {
        assert.deepEqual(
            discoveredIds,
            [...RETAINED_NON_GACHA_EXCEPTION_IDS],
            "cleaned abyss non-gacha exception set has drifted",
        )
        return {
            changed: false,
            removed: [],
            retained: [...RETAINED_NON_GACHA_EXCEPTION_IDS],
        }
    }

    const rateUpsBefore = rateUpSignature(baseAbyss)
    const totalsBefore = Object.fromEntries(
        Object.entries(baseAbyss.pool).map(([bucket, entries]) => [bucket, poolTotal(entries)]),
    )
    const cleanedAbyss = structuredClone(baseAbyss)
    for (const [bucket, entries] of Object.entries(cleanedAbyss.pool)) {
        cleanedAbyss.pool[bucket] = removeAndRedistribute(entries, removableIds)
    }

    assert.deepEqual(rateUpSignature(cleanedAbyss), rateUpsBefore, "UP probability changed")
    assert.deepEqual(
        Object.fromEntries(
            Object.entries(cleanedAbyss.pool).map(([bucket, entries]) => [bucket, poolTotal(entries)]),
        ),
        totalsBefore,
        "abyss rarity bucket totals changed",
    )
    assert.deepEqual(
        findNonGachaFillers(cleanedAbyss, otherGachaCharacterIds)
            .map(({ id }) => id)
            .sort((a, b) => a - b),
        [...RETAINED_NON_GACHA_EXCEPTION_IDS],
        "approved retained abyss character set changed",
    )

    baseGachas[ABYSS_GACHA_ID] = cleanedAbyss
    cnmodGachas[ABYSS_GACHA_ID] = structuredClone(cleanedAbyss)
    return {
        changed: true,
        removed: removable,
        retained: [...RETAINED_NON_GACHA_EXCEPTION_IDS],
    }
}

function main() {
    const baseGachas = readJson(BASE_GACHA_PATH)
    const cnmodGachas = readJson(CNMOD_GACHA_PATH)
    const result = cleanupAbyssGacha(baseGachas, cnmodGachas)
    if (result.changed) {
        writeJson(BASE_GACHA_PATH, baseGachas)
        writeJson(CNMOD_GACHA_PATH, cnmodGachas)
    }
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`)
}

if (require.main === module) main()

module.exports = {
    ABYSS_GACHA_ID,
    AUDITED_NON_GACHA_CHARACTER_IDS,
    REMOVED_NON_GACHA_CHARACTER_IDS,
    RETAINED_NON_GACHA_EXCEPTION_IDS,
    cleanupAbyssGacha,
    collectOtherGachaCharacterIds,
    findNonGachaFillers,
    poolTotal,
    rateUpSignature,
}
