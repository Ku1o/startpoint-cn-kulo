require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const { randomUUID } = require("node:crypto")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const databaseDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "exp-pool-real-time-db-"))
const previousDataDirectory = process.env.DATA_DIR
process.env.DATA_DIR = databaseDirectory

const { initializeDatabase } = require("../src/data")
const { getDb } = require("../src/data/db")
const { insertAccountSync } = require("../src/data/domains/account")
const {
    collectPlayerDataPooledExpSync,
    getPlayerSync,
    insertDefaultPlayerSync,
    replacePlayerDataSync,
} = require("../src/data/domains/player")
const { getMergedPlayerDataSync } = require("../src/data/utils")
const { getTimeOffset, setServerTimeOffset } = require("../src/utils")

const previousTimeOffset = getTimeOffset()
let db

function cleanup() {
    if (db?.open) db.close()
    setServerTimeOffset(previousTimeOffset)
    fs.rmSync(databaseDirectory, { recursive: true, force: true })
    if (previousDataDirectory === undefined) delete process.env.DATA_DIR
    else process.env.DATA_DIR = previousDataDirectory
}

process.once("exit", cleanup)

const DAY_MS = 24 * 60 * 60 * 1000
const MINUTE_MS = 60 * 1000

function setPoolState(playerId, { expPool, expPooledTime, timeOffset }) {
    db.prepare(`
        UPDATE players
        SET exp_pool = ?, exp_pooled_time = ?, time_offset = ?
        WHERE id = ?
    `).run(expPool, expPooledTime.toISOString(), timeOffset, playerId)
    const player = getPlayerSync(playerId)
    assert.ok(player)
    return player
}

function assertDate(actual, expected, message) {
    assert.equal(actual.toISOString(), expected.toISOString(), message)
}

function settle(playerId, now) {
    const player = getPlayerSync(playerId)
    assert.ok(player)
    collectPlayerDataPooledExpSync(player, now)
    const settled = getPlayerSync(playerId)
    assert.ok(settled)
    return settled
}

function main() {
    const initialOffset = 45 * DAY_MS
    setServerTimeOffset(initialOffset)
    initializeDatabase()
    db = getDb()

    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "test",
        idpId: `exp-pool-real-time-${randomUUID()}`,
        status: "normal",
    })
    const playerId = insertDefaultPlayerSync(account.id).id
    assert.equal(
        getPlayerSync(playerId).timeOffset,
        initialOffset,
        "新存档必须记录创建时的虚拟时间偏移",
    )

    const realCheckpoint = Date.parse("2024-01-01T00:00:00.000Z")

    // Moving the virtual clock backwards must preserve ten real elapsed minutes.
    const laterOffset = 90 * DAY_MS
    const earlierOffset = -30 * DAY_MS
    const rollbackNow = new Date(realCheckpoint + 10 * MINUTE_MS + earlierOffset)
    setServerTimeOffset(earlierOffset)
    setPoolState(playerId, {
        expPool: 100,
        expPooledTime: new Date(realCheckpoint + laterOffset),
        timeOffset: laterOffset,
    })
    let settled = settle(playerId, rollbackNow)
    assert.equal(settled.expPool, 110, "时间回拨后应只结算真实经过的十分钟")
    assertDate(settled.expPooledTime, rollbackNow, "回拨结算点必须落在当前虚拟时钟")
    assert.equal(settled.timeOffset, earlierOffset)

    // Moving the virtual clock forwards must not mint EXP for the skipped dates.
    const forwardNow = new Date(realCheckpoint + 10 * MINUTE_MS + laterOffset)
    setServerTimeOffset(laterOffset)
    setPoolState(playerId, {
        expPool: 200,
        expPooledTime: new Date(realCheckpoint + earlierOffset),
        timeOffset: earlierOffset,
    })
    settled = settle(playerId, forwardNow)
    assert.equal(settled.expPool, 210, "时间前跳后应只结算真实经过的十分钟")
    assertDate(settled.expPooledTime, forwardNow, "前跳结算点必须落在当前虚拟时钟")
    assert.equal(settled.timeOffset, laterOffset)

    // A legacy future checkpoint has no recoverable real-time basis. Preserve
    // its explicit balance and make it safe for the client on first load.
    const legacyNow = new Date(realCheckpoint + earlierOffset)
    setServerTimeOffset(earlierOffset)
    setPoolState(playerId, {
        expPool: 777,
        expPooledTime: new Date(legacyNow.getTime() + 5 * DAY_MS),
        timeOffset: null,
    })
    settled = settle(playerId, legacyNow)
    assert.equal(settled.expPool, 777, "旧存档自愈不得清空已有经验")
    assertDate(settled.expPooledTime, legacyNow, "未来结算点必须自愈到当前时间")
    assert.equal(settled.timeOffset, earlierOffset)

    // A normal legacy checkpoint remains collectible while establishing its
    // time-offset baseline for subsequent clock switches.
    setPoolState(playerId, {
        expPool: 50,
        expPooledTime: new Date(legacyNow.getTime() - 5 * MINUTE_MS),
        timeOffset: null,
    })
    settled = settle(playerId, legacyNow)
    assert.equal(settled.expPool, 55, "正常旧存档首次加载仍应结算已有五分钟")
    assert.equal(settled.timeOffset, earlierOffset)

    // Rebasing a sub-minute checkpoint must retain its partial minute rather
    // than discarding it during the one-time repair write.
    const partialNow = new Date(realCheckpoint + 30 * 1000 + earlierOffset)
    setPoolState(playerId, {
        expPool: 900,
        expPooledTime: new Date(realCheckpoint + laterOffset),
        timeOffset: laterOffset,
    })
    settled = settle(playerId, partialNow)
    assert.equal(settled.expPool, 900)
    assertDate(
        settled.expPooledTime,
        new Date(realCheckpoint + earlierOffset),
        "不足一分钟时应保留已流逝的秒数",
    )
    settled = settle(playerId, new Date(realCheckpoint + 61 * 1000 + earlierOffset))
    assert.equal(settled.expPool, 901, "累计满一分钟后应正常增加一点经验")

    // Import, clone and template restore share replacePlayerDataSync. They must
    // keep the explicit balance while resetting the checkpoint to now.
    const replacement = getMergedPlayerDataSync(playerId)
    assert.ok(replacement)
    replacement.player.expPool = 4321
    replacement.player.expPooledTime = new Date(realCheckpoint + laterOffset)
    replacement.player.timeOffset = laterOffset
    const replaceStartedAt = Date.now() + earlierOffset
    replacePlayerDataSync(replacement)
    const replaced = getPlayerSync(playerId)
    assert.ok(replaced)
    assert.equal(replaced.expPool, 4321, "存档替换必须保留显式经验余额")
    assert.equal(replaced.timeOffset, earlierOffset, "存档替换必须采用当前偏移")
    assert.ok(
        Math.abs(replaced.expPooledTime.getTime() - replaceStartedAt) < 5000,
        "存档替换必须从当前虚拟时间重新开始结算",
    )

    console.log("player EXP-pool real-time tests passed")
}

try {
    main()
} finally {
    cleanup()
    process.removeListener("exit", cleanup)
}
