require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const { randomUUID } = require("node:crypto")
const Fastify = require("fastify")
const fs = require("node:fs")
const { pack, unpack } = require("msgpackr")
const os = require("node:os")
const path = require("node:path")

const databaseDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "unlock-regression-db-"))
const previousDataDirectory = process.env.DATA_DIR
const previousDatabaseDirectory = process.env.WDFP_DATABASE_DIR
process.env.DATA_DIR = databaseDirectory
delete process.env.WDFP_DATABASE_DIR

const projectRoot = path.resolve(__dirname, "..")
const { BUNDLED_CDN_CATALOG_VERSION } = require("../src/content/constants")
const {
    productionContentSnapshotProvider,
} = require("../src/content/runtime/content-snapshot")
const previousSnapshot = productionContentSnapshotProvider.snapshot
const tableCache = new Map()
productionContentSnapshotProvider.snapshot = {
    cdn: { targetVersion: BUNDLED_CDN_CATALOG_VERSION },
    repository: {
        info: () => ({
            source: "bundled",
            assetVersion: BUNDLED_CDN_CATALOG_VERSION,
            generatorVersion: 1,
            releaseDigest: null,
        }),
        table(tableName) {
            if (!tableCache.has(tableName)) {
                tableCache.set(tableName, require(path.join(projectRoot, "assets", tableName)))
            }
            return tableCache.get(tableName)
        },
    },
}

const { initializeDatabase } = require("../src/data")
const { getDb } = require("../src/data/db")
const { insertAccountSync } = require("../src/data/domains/account")
const { getPlayerSync, insertDefaultPlayerSync, updatePlayerSync } = require("../src/data/domains/player")
const { insertPlayerQuestProgressSync } = require("../src/data/domains/quest")
const { insertPlayerTriggeredTutorialSync } = require("../src/data/domains/tutorial")
const { getClientSerializedData } = require("../src/data/utils/player-data")
const {
    isStartTutorialActive,
} = require("../src/lib/start-tutorial-state")
const {
    getUnisonUnlockRepairStatusSync,
    repairUnisonUnlockProgressSync,
} = require("../src/lib/validate/unison-unlock")
const tutorialRoutes = require("../src/routes/api/tutorial").default

initializeDatabase()
const db = getDb()

function createPlayer(viewerId) {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "test",
        idpId: `unlock-regression-${randomUUID()}`,
        status: "normal",
    })
    const playerId = insertDefaultPlayerSync(account.id).id
    if (viewerId !== undefined) {
        db.prepare("INSERT INTO sessions (token, account_id, expires, type) VALUES (?, ?, ?, ?)")
            .run(String(viewerId), account.id, new Date("2099-12-31T23:59:59.000Z").toISOString(), 2)
    }
    return playerId
}

function getRawQuestProgress(playerId, questId) {
    return db.prepare(`
        SELECT finished, host_finished, unlocked, clear_rank
        FROM players_quest_progress
        WHERE player_id = ? AND section = 1 AND quest_id = ?
    `).get(playerId, questId)
}

function countTutorialMarker(playerId, tutorialId) {
    return db.prepare(`
        SELECT COUNT(*) AS count
        FROM players_triggered_tutorials
        WHERE player_id = ? AND id = ?
    `).get(playerId, tutorialId).count
}

async function main() {
    assert.equal(isStartTutorialActive(5, true), true)
    assert.equal(isStartTutorialActive(6, true), false)
    assert.equal(isStartTutorialActive(16, false), true)
    assert.equal(isStartTutorialActive(17, false), false)
    assert.equal(isStartTutorialActive(null, false), false)

    const tutorialPlayerId = createPlayer()
    insertPlayerQuestProgressSync(tutorialPlayerId, 1, {
        questId: 1001001,
        finished: true,
        clearRank: 5,
    })

    updatePlayerSync({
        id: tutorialPlayerId,
        tutorialStep: 6,
        tutorialSkipFlag: true,
    })
    let serialized = getClientSerializedData(tutorialPlayerId, { viewerId: 800000001 })
    assert.equal(serialized.user_tutorial, null)
    assert.equal(
        serialized.quest_progress["1"].find(progress => progress.quest_id === 1001001).finished,
        true,
    )

    updatePlayerSync({ id: tutorialPlayerId, tutorialStep: 5, tutorialSkipFlag: true })
    serialized = getClientSerializedData(tutorialPlayerId, { viewerId: 800000001 })
    assert.equal(serialized.user_tutorial.tutorial_step, 5)

    insertPlayerTriggeredTutorialSync(tutorialPlayerId, 12)
    serialized = getClientSerializedData(tutorialPlayerId, { viewerId: 800000001 })
    assert.equal(serialized.user_tutorial.tutorial_step, 5)

    updatePlayerSync({ id: tutorialPlayerId, tutorialStep: 16, tutorialSkipFlag: false })
    serialized = getClientSerializedData(tutorialPlayerId, { viewerId: 800000001 })
    assert.equal(serialized.user_tutorial.tutorial_step, 16)

    updatePlayerSync({ id: tutorialPlayerId, tutorialStep: 17, tutorialSkipFlag: false })
    serialized = getClientSerializedData(tutorialPlayerId, { viewerId: 800000001 })
    assert.equal(serialized.user_tutorial, null)

    const routeViewerId = 800000002
    const routePlayerId = createPlayer(routeViewerId)
    updatePlayerSync({ id: routePlayerId, tutorialStep: 5, tutorialSkipFlag: true })
    insertPlayerTriggeredTutorialSync(routePlayerId, 12)

    const fastify = Fastify()
    fastify.addContentTypeParser(
        "application/x-www-form-urlencoded",
        { parseAs: "string" },
        (_request, body, done) => done(null, unpack(Buffer.from(body, "base64"))),
    )
    fastify.addHook("onSend", (_request, reply, payload, done) => {
        if (String(reply.getHeader("content-type")).includes("application/x-msgpack")) {
            done(null, pack(payload).toString("base64"))
            return
        }
        done(null, payload)
    })
    await fastify.register(tutorialRoutes, { prefix: "/api/index.php/tutorial" })
    await fastify.ready()
    const finishShortenedTutorial = await fastify.inject({
        method: "POST",
        url: "/api/index.php/tutorial/update_step",
        headers: { "content-type": "application/x-www-form-urlencoded" },
        payload: pack({
            viewer_id: routeViewerId,
            api_count: 1,
            statistics: {},
            step: 5,
            skip: true,
        }).toString("base64"),
    })
    assert.equal(finishShortenedTutorial.statusCode, 200, finishShortenedTutorial.body)
    assert.equal(getPlayerSync(routePlayerId).tutorialStep, 6)
    const repeatFinishedTutorial = await fastify.inject({
        method: "POST",
        url: "/api/index.php/tutorial/update_step",
        headers: { "content-type": "application/x-www-form-urlencoded" },
        payload: pack({
            viewer_id: routeViewerId,
            api_count: 2,
            statistics: {},
            step: 6,
            skip: true,
        }).toString("base64"),
    })
    assert.equal(repeatFinishedTutorial.statusCode, 400)
    await fastify.close()

    const completedUnisonPlayerId = createPlayer()
    insertPlayerQuestProgressSync(completedUnisonPlayerId, 1, {
        questId: 1006001,
        finished: true,
        hostFinished: false,
        unlocked: false,
    })
    assert.equal(getUnisonUnlockRepairStatusSync(completedUnisonPlayerId), "already_unlocked")
    assert.equal(repairUnisonUnlockProgressSync(completedUnisonPlayerId), 0)
    assert.deepEqual(getRawQuestProgress(completedUnisonPlayerId, 1006001), {
        finished: 1,
        host_finished: 0,
        unlocked: 0,
        clear_rank: null,
    })
    assert.equal(countTutorialMarker(completedUnisonPlayerId, 12), 0)

    const missingUnisonPlayerId = createPlayer()
    insertPlayerQuestProgressSync(missingUnisonPlayerId, 1, {
        questId: 1006002,
        finished: true,
        clearRank: 5,
    })
    assert.equal(getUnisonUnlockRepairStatusSync(missingUnisonPlayerId), "needs_repair")
    assert.equal(repairUnisonUnlockProgressSync(missingUnisonPlayerId), 1)
    assert.deepEqual(getRawQuestProgress(missingUnisonPlayerId, 1006001), {
        finished: 1,
        host_finished: 0,
        unlocked: 0,
        clear_rank: null,
    })
    assert.equal(getUnisonUnlockRepairStatusSync(missingUnisonPlayerId), "already_unlocked")
    assert.equal(countTutorialMarker(missingUnisonPlayerId, 12), 0)

    const unfinishedUnisonPlayerId = createPlayer()
    insertPlayerQuestProgressSync(unfinishedUnisonPlayerId, 1, {
        questId: 1006001,
        finished: false,
        hostFinished: false,
        unlocked: false,
        clearRank: 1,
    })
    assert.equal(getUnisonUnlockRepairStatusSync(unfinishedUnisonPlayerId), "not_eligible")
    assert.equal(repairUnisonUnlockProgressSync(unfinishedUnisonPlayerId), 0)
    assert.deepEqual(getRawQuestProgress(unfinishedUnisonPlayerId, 1006001), {
        finished: 0,
        host_finished: 0,
        unlocked: 0,
        clear_rank: 1,
    })

    const laterQuestPlayerId = createPlayer()
    insertPlayerQuestProgressSync(laterQuestPlayerId, 1, {
        questId: 1006001,
        finished: false,
        hostFinished: false,
        unlocked: false,
        clearRank: 2,
    })
    insertPlayerQuestProgressSync(laterQuestPlayerId, 1, {
        questId: 1006002,
        finished: true,
    })
    assert.equal(repairUnisonUnlockProgressSync(laterQuestPlayerId), 1)
    assert.deepEqual(getRawQuestProgress(laterQuestPlayerId, 1006001), {
        finished: 1,
        host_finished: 0,
        unlocked: 0,
        clear_rank: 2,
    })
    assert.equal(countTutorialMarker(laterQuestPlayerId, 12), 0)

    console.log("tutorial/unison unlock regression tests passed")
}

main().catch(error => {
    console.error(error)
    process.exitCode = 1
}).finally(() => {
    db.close()
    productionContentSnapshotProvider.snapshot = previousSnapshot
    fs.rmSync(databaseDirectory, { recursive: true, force: true })
    if (previousDataDirectory === undefined) delete process.env.DATA_DIR
    else process.env.DATA_DIR = previousDataDirectory
    if (previousDatabaseDirectory === undefined) delete process.env.WDFP_DATABASE_DIR
    else process.env.WDFP_DATABASE_DIR = previousDatabaseDirectory
})
