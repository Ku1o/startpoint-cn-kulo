require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const databaseDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "admin-overview-performance-"))
const previousDataDirectory = process.env.DATA_DIR
process.env.DATA_DIR = databaseDirectory

async function main() {
    const Fastify = require("fastify")
    const data = require("../src/data")
    const { insertAccountSync } = require("../src/data/domains/account")
    const { insertDefaultPlayerSync } = require("../src/data/domains/player")
    const { SessionType } = require("../src/data/types")
    const {
        getAdminPlayerSelectionState,
        saveAccountDefaultPlayer,
        setActivePlayerId,
    } = require("../src/data/activeAccount")
    const { buildShortUpCharacterGachaTimeline } = require("../src/lib/admin-clairvoyance")
    const serverRoutes = require("../src/routes/web_api/server").default

    const db = data.initializeDatabase()
    const createAccount = label => insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "admin-overview-test",
        idpId: label,
        status: "normal",
    })

    const firstAccount = createAccount("batch-first")
    const secondAccount = createAccount("batch-second")
    db.prepare("UPDATE accounts SET admin_note = ? WHERE id = ?").run("重点账号", firstAccount.id)

    const firstPlayer = insertDefaultPlayerSync(firstAccount.id)
    const secondPlayer = insertDefaultPlayerSync(firstAccount.id)
    const thirdPlayer = insertDefaultPlayerSync(secondAccount.id)
    db.prepare("UPDATE players SET name = ?, comment = ?, degree_id = ? WHERE id = ?")
        .run("第一存档", "第一备注", 11, firstPlayer.id)
    db.prepare("UPDATE players SET name = ?, comment = ?, degree_id = ? WHERE id = ?")
        .run("第二存档", "第二备注", 22, secondPlayer.id)
    db.prepare("UPDATE players SET name = ?, comment = ?, degree_id = ? WHERE id = ?")
        .run("第三存档", "第三备注", 33, thirdPlayer.id)
    db.prepare("INSERT INTO sessions (token, account_id, expires, type) VALUES (?, ?, ?, ?)")
        .run("viewer-first", firstAccount.id, "2099-01-01T00:00:00.000Z", SessionType.VIEWER)
    db.prepare("INSERT INTO device_bindings (device_id, account_id, last_seen, name) VALUES (?, ?, ?, ?)")
        .run(700001, firstAccount.id, new Date().toISOString(), "测试设备")
    saveAccountDefaultPlayer(firstAccount.id, secondPlayer.id)
    setActivePlayerId(secondPlayer.id)

    const app = Fastify({ logger: false })
    app.register(serverRoutes, { prefix: "/api/server" })
    await app.ready()

    const sqlStatements = []
    const originalPrepare = db.prepare
    db.prepare = function instrumentedPrepare(sql) {
        sqlStatements.push(String(sql))
        return originalPrepare.call(db, sql)
    }

    try {
        const response = await app.inject({ method: "GET", url: "/api/server/accounts" })
        assert.equal(response.statusCode, 200)
        const accounts = response.json()
        const first = accounts.find(account => account.id === firstAccount.id)
        assert.equal(first.viewerId, "viewer-first")
        assert.equal(first.note, "重点账号")
        assert.deepEqual(first.bindings, [{ deviceId: 700001 }])
        assert.equal(first.defaultPlayerId, secondPlayer.id)
        assert.equal(first.activePlayerId, secondPlayer.id)
        assert.deepEqual(first.players.map(player => ({
            id: player.id,
            name: player.name,
            comment: player.comment,
            degreeId: player.degreeId,
            isDefault: player.isDefault,
            isActive: player.isActive,
        })), [
            { id: firstPlayer.id, name: "第一存档", comment: "第一备注", degreeId: 11, isDefault: false, isActive: false },
            { id: secondPlayer.id, name: "第二存档", comment: "第二备注", degreeId: 22, isDefault: true, isActive: true },
        ])

        const playerReads = sqlStatements.filter(sql => /\bFROM\s+players\b/i.test(sql))
        const sessionReads = sqlStatements.filter(sql => /\bFROM\s+sessions\b/i.test(sql))
        const bindingReads = sqlStatements.filter(sql => /\bFROM\s+device_bindings\b/i.test(sql))
        assert.equal(playerReads.length, 1, playerReads.join("\n"))
        assert.equal(sessionReads.length, 1, sessionReads.join("\n"))
        assert.equal(bindingReads.length, 1, bindingReads.join("\n"))
        assert.deepEqual(getAdminPlayerSelectionState().defaultPlayers[firstAccount.id], secondPlayer.id)

        const early = buildShortUpCharacterGachaTimeline(new Date("2021-10-18T14:00:00.000Z"))
        const later = buildShortUpCharacterGachaTimeline(new Date("2021-10-18T15:00:00.000Z"))
        assert.strictEqual(early.timeline, later.timeline)
        assert.strictEqual(early.searchIndex, later.searchIndex)
        assert.notEqual(early.currentTime, later.currentTime)
        assert.equal(Object.isFrozen(early.timeline), true)

        console.log(JSON.stringify({
            ok: true,
            accountCount: accounts.length,
            playerQueryCount: playerReads.length,
            sessionQueryCount: sessionReads.length,
            bindingQueryCount: bindingReads.length,
            cachedTimelineRows: early.timeline.length,
        }, null, 2))
    } finally {
        db.prepare = originalPrepare
        await app.close()
        db.close()
    }
}

main().catch(error => {
    console.error(error)
    process.exitCode = 1
}).finally(() => {
    fs.rmSync(databaseDirectory, { recursive: true, force: true })
    if (previousDataDirectory === undefined) delete process.env.DATA_DIR
    else process.env.DATA_DIR = previousDataDirectory
    process.exit(process.exitCode ?? 0)
})
