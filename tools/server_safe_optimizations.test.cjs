require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const { randomUUID } = require("node:crypto")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const databaseDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "server-safe-optimizations-db-"))
const archiveDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "server-safe-optimizations-assets-"))
const previousDataDirectory = process.env.DATA_DIR
process.env.DATA_DIR = databaseDirectory
const serverModuleRoot = process.env.SERVER_SAFE_OPTIMIZATIONS_COMPILED === "1" ? "../out" : "../src"

let db
function cleanup() {
    if (db?.open) db.close()
    fs.rmSync(databaseDirectory, { recursive: true, force: true })
    fs.rmSync(archiveDirectory, { recursive: true, force: true })
    if (previousDataDirectory === undefined) delete process.env.DATA_DIR
    else process.env.DATA_DIR = previousDataDirectory
}
process.once("exit", cleanup)

const { initializeDatabase } = require(`${serverModuleRoot}/data`)
const initWdfpData = require(`${serverModuleRoot}/data/initializers/wdfpData`).default
const { getDb } = require(`${serverModuleRoot}/data/db`)
const { insertAccountSync } = require(`${serverModuleRoot}/data/domains/account`)
const { insertMailSync } = require(`${serverModuleRoot}/data/domains/mail`)
const { getPlayerSync, insertDefaultPlayerSync } = require(`${serverModuleRoot}/data/domains/player`)
const { getClientSerializedData } = require(`${serverModuleRoot}/data/utils/player-data`)
const { getPlayerEquipmentListSync } = require(`${serverModuleRoot}/data/domains/equipment`)
const {
    getPlayerCharactersManaNodesSync,
    getPlayerCharactersSync,
} = require(`${serverModuleRoot}/data/domains/character`)
const { getPlayerPartyGroupListSync } = require(`${serverModuleRoot}/data/domains/party`)
const {
    getPlayerQuestProgressSubsetSync,
    getPlayerQuestProgressSync,
} = require(`${serverModuleRoot}/data/domains/quest`)
const { runPermanentValidators } = require(`${serverModuleRoot}/lib/validate`)
const {
    addMissionCounterSync,
    getMissionCounterValueSync,
    setMissionCounterMaxSync,
    setMissionCounterMinSync,
} = require(`${serverModuleRoot}/lib/mission/counters`)
const { claimPlayerMailRewards } = require(`${serverModuleRoot}/routes/api/mail`)
const {
    getAssetArchiveMetadata,
    getVersionInfo,
    invalidateAssetArchiveCatalog,
    joinCdnPath,
    normalizeCdnBaseUrl,
} = require(`${serverModuleRoot}/routes/cn/asset`)
const {
    getZipFileSummary,
    invalidateZipSummaryCache,
} = require(`${serverModuleRoot}/lib/zip-summary-cache`)
const {
    getActiveMissionMasterDefinitions,
    getActiveMissionMasterDefinitionsByPatterns,
} = require(`${serverModuleRoot}/lib/mission/active-master-data`)
const { reconcileActiveMissionFacts } = require(`${serverModuleRoot}/lib/mission/active-reconciliation`)

initializeDatabase()
db = getDb()

function unreceivedMail(type, number, typeId = null) {
    return {
        reason_id: 0,
        subject: "test",
        description: "test",
        type,
        type_id: typeId,
        number,
        receive_time: "0000-00-00 00:00:00",
        create_time: new Date().toISOString(),
        reward_period_limited: 0,
        reward_limit_time: null,
    }
}

function assertIndexPlans() {
    const indexes = new Set(db.prepare(`
        SELECT name FROM sqlite_master WHERE type = 'index'
    `).all().map(row => row.name))
    assert.equal(indexes.has("idx_players_mails_player_receive_id"), true)
    assert.equal(indexes.has("idx_players_receive_history_player_created"), true)

    const historyPlan = db.prepare(`
        EXPLAIN QUERY PLAN
        SELECT * FROM players_receive_history
        WHERE player_id = ? AND create_time >= ?
        ORDER BY create_time DESC, id DESC LIMIT ?
    `).all(1, "2020-01-01", 500)
    assert.ok(historyPlan.some(row => String(row.detail).includes("idx_players_receive_history_player_created")))
    assert.equal(historyPlan.some(row => String(row.detail).includes("USE TEMP B-TREE")), false)

    const mailPlan = db.prepare(`
        EXPLAIN QUERY PLAN
        SELECT * FROM players_mails
        WHERE player_id = ? AND receive_time = '0000-00-00 00:00:00'
        ORDER BY id DESC LIMIT ?
    `).all(1, 100)
    assert.ok(mailPlan.some(row => String(row.detail).includes("idx_players_mails_player_receive_id")))
}

function assertExistingDatabaseIndexUpgrade() {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "test",
        idpId: `server-safe-index-upgrade-${randomUUID()}`,
        status: "normal",
    })
    const playerId = insertDefaultPlayerSync(account.id).id
    insertMailSync(playerId, unreceivedMail(4, 1))
    db.prepare(`
        INSERT INTO players_receive_history
            (player_id, type, type_id, number, reason_id, create_time)
        VALUES (?, 4, NULL, 1, 0, ?)
    `).run(playerId, new Date().toISOString())
    const mailCount = db.prepare(`SELECT COUNT(*) AS count FROM players_mails WHERE player_id = ?`).get(playerId).count
    const historyCount = db.prepare(`SELECT COUNT(*) AS count FROM players_receive_history WHERE player_id = ?`).get(playerId).count

    db.exec(`
        DROP INDEX idx_players_mails_player_receive_id;
        DROP INDEX idx_players_receive_history_player_created;
    `)
    initWdfpData(db, true)

    assert.equal(db.prepare(`SELECT COUNT(*) AS count FROM players_mails WHERE player_id = ?`).get(playerId).count, mailCount)
    assert.equal(db.prepare(`SELECT COUNT(*) AS count FROM players_receive_history WHERE player_id = ?`).get(playerId).count, historyCount)
}

function assertMissionCounterReturning() {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "test",
        idpId: `server-safe-counter-${randomUUID()}`,
        status: "normal",
    })
    const playerId = insertDefaultPlayerSync(account.id).id
    const query = {
        dimension: "test.optimized_returning",
        scopeType: "lifetime",
        scopeKey: "all",
        qualifier: { mode: "single" },
    }
    assert.equal(addMissionCounterSync(playerId, query, 2), 2)
    assert.equal(addMissionCounterSync(playerId, query, 3), 5)
    assert.equal(setMissionCounterMaxSync(playerId, query, 4), 5)
    assert.equal(setMissionCounterMaxSync(playerId, query, 7), 7)
    assert.equal(setMissionCounterMinSync(playerId, query, 9), 7)
    assert.equal(setMissionCounterMinSync(playerId, query, 3), 3)
    assert.equal(getMissionCounterValueSync(playerId, query), 3)
}

function assertPermanentRepairVersions() {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "test",
        idpId: `server-safe-repair-version-${randomUUID()}`,
        status: "normal",
    })
    const playerId = insertDefaultPlayerSync(account.id).id
    db.prepare(`UPDATE players SET party_slot = 0 WHERE id = ?`).run(playerId)
    const player = getPlayerSync(playerId)
    const equipmentList = getPlayerEquipmentListSync(playerId)
    assert.ok(runPermanentValidators(playerId, { player, equipmentList }) >= 1)
    assert.equal(getPlayerSync(playerId).partySlot, 1)

    const versions = db.prepare(`
        SELECT repair_key, repair_version
        FROM players_repair_versions
        WHERE player_id = ?
        ORDER BY repair_key
    `).all(playerId)
    assert.deepEqual(versions, [
        { repair_key: "max-level", repair_version: 1 },
        { repair_key: "party-slot", repair_version: 1 },
        { repair_key: "unison-unlock", repair_version: 1 },
    ])

    db.prepare(`UPDATE players SET party_slot = 0 WHERE id = ?`).run(playerId)
    assert.equal(runPermanentValidators(playerId), 0, "已应用版本不得在每次登录重复扫描")
    assert.equal(getPlayerSync(playerId).partySlot, 0)
    db.prepare(`DELETE FROM players_repair_versions WHERE player_id = ? AND repair_key = 'party-slot'`).run(playerId)
    assert.equal(runPermanentValidators(playerId), 1, "修复版本失效后必须重新校验")
    assert.equal(getPlayerSync(playerId).partySlot, 1)

    db.prepare(`DELETE FROM players WHERE id = ?`).run(playerId)
    assert.equal(
        db.prepare(`SELECT COUNT(*) AS count FROM players_repair_versions WHERE player_id = ?`).get(playerId).count,
        0,
        "替换或删除玩家时修复标记必须随外键级联清除",
    )
}

function assertQuestProgressSubsetRead() {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "test",
        idpId: `server-safe-quest-subset-${randomUUID()}`,
        status: "normal",
    })
    const playerId = insertDefaultPlayerSync(account.id).id
    const insert = db.prepare(`
        INSERT OR REPLACE INTO players_quest_progress
            (section, quest_id, finished, player_id)
        VALUES (?, ?, 1, ?)
    `)
    insert.run(1, 987654321, playerId)
    insert.run(4, 123, playerId)
    insert.run(18, 987654322, playerId)

    const subset = getPlayerQuestProgressSubsetSync(playerId, {
        sections: [1],
        questIds: [10_000_123],
    })
    assert.equal(subset["1"].some(progress => progress.questId === 987654321), true)
    assert.equal(subset["4"].some(progress => progress.questId === 123), true)
    assert.equal(
        (subset["18"] ?? []).some(progress => progress.questId === 987654322),
        false,
        "按需关卡读取不得带回无关 section",
    )
}

function assertArchiveCacheInvalidation() {
    const archivePath = path.join(archiveDirectory, "pinball-1.0.0-1.0.1-1-test.zip")
    fs.writeFileSync(archivePath, Buffer.alloc(3))
    assert.equal(getAssetArchiveMetadata(archiveDirectory)[0].size, 3)
    fs.writeFileSync(archivePath, Buffer.alloc(7))
    assert.equal(getAssetArchiveMetadata(archiveDirectory)[0].size, 3, "TTL 内必须复用元数据")
    fs.writeFileSync(path.join(archiveDirectory, "new-patch.zip"), Buffer.alloc(5))
    const forcedDirectoryTime = new Date(Date.now() + 2_000)
    fs.utimesSync(archiveDirectory, forcedDirectoryTime, forcedDirectoryTime)
    assert.equal(getAssetArchiveMetadata(archiveDirectory).length, 2, "新增补丁必须立即让目录缓存失效")
    fs.writeFileSync(archivePath, Buffer.alloc(9))
    invalidateAssetArchiveCatalog(archiveDirectory)
    assert.equal(
        getAssetArchiveMetadata(archiveDirectory).find(archive => archive.filename === path.basename(archivePath)).size,
        9,
        "显式失效后必须重新扫描",
    )

    const summaryDirectory = path.join(archiveDirectory, "summary")
    fs.mkdirSync(summaryDirectory)
    const summaryArchivePath = path.join(summaryDirectory, "first.zip")
    fs.writeFileSync(summaryArchivePath, Buffer.alloc(7))
    const initialZipSummary = getZipFileSummary(summaryDirectory)
    assert.equal(initialZipSummary.exists, true)
    assert.equal(initialZipSummary.count, 1)
    assert.equal(initialZipSummary.totalBytes, 7)
    assert.equal(Number.isFinite(Date.parse(initialZipSummary.latestMtime)), true)
    fs.writeFileSync(path.join(summaryDirectory, "second.zip"), Buffer.alloc(11))
    assert.equal(getZipFileSummary(summaryDirectory).count, 1, "TTL 内必须复用后台 ZIP 汇总")
    invalidateZipSummaryCache(summaryDirectory)
    assert.equal(getZipFileSummary(summaryDirectory).count, 2, "后台 ZIP 汇总失效后必须重新扫描")
}

function assertCloudflareCdnBaseSafety() {
    const cloudflareBase = normalizeCdnBaseUrl("https://assets.example.workers.dev/game/cn///")
    assert.equal(cloudflareBase, "https://assets.example.workers.dev/game/cn")
    assert.equal(
        joinCdnPath(cloudflareBase, "/archive-common-full/", "bundle.zip"),
        "https://assets.example.workers.dev/game/cn/archive-common-full/bundle.zip",
    )
    assert.equal(
        joinCdnPath("https://cdn-one.example/", "archive", "bundle.zip")
            === joinCdnPath("https://cdn-two.example/", "archive", "bundle.zip"),
        false,
        "目录元数据缓存不得固定 CDN 主机",
    )
    const versionInfo = getVersionInfo(`${cloudflareBase}/`, 123, "android")
    assert.equal(versionInfo.base_url.startsWith(`${cloudflareBase}/`), true)
    assert.equal(versionInfo.files_list.startsWith(`${cloudflareBase}/`), true)
    assert.equal(versionInfo.base_url.includes("//EntityLists"), false)
    assert.throws(() => normalizeCdnBaseUrl("ftp://assets.example/"), /HTTP or HTTPS/)
    assert.throws(() => normalizeCdnBaseUrl("https://assets.example/?token=secret"), /must not contain/)
    assert.throws(() => normalizeCdnBaseUrl("https://user:secret@assets.example/"), /must not contain/)
}

function assertActiveMissionPatternIndex() {
    const all = getActiveMissionMasterDefinitions()
    const patterns = [...new Set(all.slice(0, 50).map(definition => Number(definition.row[29])))]
        .filter(Number.isSafeInteger)
        .slice(0, 4)
    const expected = all
        .filter(definition => patterns.includes(Number(definition.row[29])))
        .map(definition => definition.missionId)
        .sort((a, b) => a - b)
    const actual = getActiveMissionMasterDefinitionsByPatterns(patterns)
        .map(definition => definition.missionId)
        .sort((a, b) => a - b)
    assert.deepEqual(actual, expected)
    assert.deepEqual(getActiveMissionMasterDefinitionsByPatterns([]), [])

    const rowA = []
    const rowB = []
    rowA[29] = "3"
    rowB[29] = "9"
    const repository = {
        table(name) {
            if (name === "mission_active.json") return { "910001": [rowA], "910002": [rowB] }
            if (name === "mission_active_event.json") return {}
            throw new Error(`unexpected table ${name}`)
        },
    }
    assert.deepEqual(
        getActiveMissionMasterDefinitionsByPatterns([9], repository).map(definition => definition.missionId),
        [910002],
    )
    assert.deepEqual(reconcileActiveMissionFacts({
        playerId: -999,
        repository,
        now: Date.now(),
        patterns: [123456],
    }), [], "没有对应条件的触发不得读取玩家事实表")
    assert.throws(() => reconcileActiveMissionFacts({
        playerId: -999,
        player: { id: -998 },
        repository,
        now: Date.now(),
        patterns: [9],
    }), /does not match/, "活动任务不得复用其他玩家的快照")
}

async function assertAtomicMailClaims() {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "test",
        idpId: `server-safe-optimizations-${randomUUID()}`,
        status: "normal",
    })
    const playerId = insertDefaultPlayerSync(account.id).id
    const startingFreeVmoney = getPlayerSync(playerId).freeVmoney
    const firstMailId = insertMailSync(playerId, unreceivedMail(4, 10))
    const secondMailId = insertMailSync(playerId, unreceivedMail(4, 20))

    const claimed = await claimPlayerMailRewards(
        playerId,
        [firstMailId, firstMailId, secondMailId, -1],
    )
    assert.deepEqual(claimed.claimedMailIds, [firstMailId, secondMailId])
    assert.equal(claimed.alreadyCount, 2)
    assert.equal(claimed.userInfo.free_vmoney, startingFreeVmoney + 30)
    assert.equal(getPlayerSync(playerId).freeVmoney, startingFreeVmoney + 30)
    assert.equal(db.prepare(`SELECT COUNT(*) AS count FROM players_receive_history WHERE player_id = ?`).get(playerId).count, 2)

    const replay = await claimPlayerMailRewards(playerId, [firstMailId, secondMailId])
    assert.deepEqual(replay.claimedMailIds, [])
    assert.equal(replay.alreadyCount, 2)
    assert.equal(getPlayerSync(playerId).freeVmoney, startingFreeVmoney + 30)
    await assert.rejects(
        claimPlayerMailRewards(playerId, Array.from({ length: 1001 }, (_, index) => index + 1)),
        /at most 1000 IDs/,
    )

    const beforeScalarBatch = getPlayerSync(playerId)
    const scalarCases = [
        { type: 3, field: "vmoney", response: "vmoney" },
        { type: 7, field: "starCrumb", response: "star_crumb" },
        { type: 9, field: "expPool", response: "exp_pool" },
        { type: 10, field: "bondToken", response: "bond_token" },
        { type: 11, field: "bossBoostPoint", response: "boss_boost_point" },
        { type: 12, field: "boostPoint", response: "boost_point" },
        { type: 15, field: "rankPoint", response: "rank_point" },
    ]
    const scalarMailIds = scalarCases.flatMap(testCase => [
        insertMailSync(playerId, unreceivedMail(testCase.type, 2)),
        insertMailSync(playerId, unreceivedMail(testCase.type, 3)),
    ])
    const scalarClaim = await claimPlayerMailRewards(playerId, scalarMailIds)
    const afterScalarBatch = getPlayerSync(playerId)
    for (const testCase of scalarCases) {
        assert.equal(afterScalarBatch[testCase.field], beforeScalarBatch[testCase.field] + 5)
        assert.equal(scalarClaim.userInfo[testCase.response], afterScalarBatch[testCase.field])
    }

    const concurrentMailId = insertMailSync(playerId, unreceivedMail(4, 31))
    const concurrent = await Promise.all([
        claimPlayerMailRewards(playerId, [concurrentMailId]),
        claimPlayerMailRewards(playerId, [concurrentMailId]),
    ])
    assert.equal(concurrent.flatMap(result => result.claimedMailIds).length, 1)
    assert.equal(getPlayerSync(playerId).freeVmoney, startingFreeVmoney + 61)

    const rollbackMailId = insertMailSync(playerId, unreceivedMail(4, 999))
    db.exec(`
        CREATE TRIGGER fail_test_receive_history
        BEFORE INSERT ON players_receive_history
        WHEN NEW.player_id = ${playerId} AND NEW.number = 999
        BEGIN
            SELECT RAISE(ABORT, 'forced receive-history failure');
        END;
    `)
    await assert.rejects(
        claimPlayerMailRewards(playerId, [rollbackMailId]),
        /forced receive-history failure/,
    )
    assert.equal(
        db.prepare(`SELECT receive_time FROM players_mails WHERE id = ?`).get(rollbackMailId).receive_time,
        "0000-00-00 00:00:00",
    )
    assert.equal(getPlayerSync(playerId).freeVmoney, startingFreeVmoney + 61)
    db.exec(`DROP TRIGGER fail_test_receive_history`)

    const olderMailId = insertMailSync(playerId, unreceivedMail(4, 7))
    const insertNewer = db.transaction(() => {
        for (let index = 0; index < 1001; index += 1) {
            insertMailSync(playerId, unreceivedMail(999, 0))
        }
    })
    insertNewer()
    const olderClaim = await claimPlayerMailRewards(playerId, [olderMailId])
    assert.deepEqual(olderClaim.claimedMailIds, [olderMailId], "精确 ID 查询不能受旧的 1000 封分页上限影响")
    assert.equal(getPlayerSync(playerId).freeVmoney, startingFreeVmoney + 68)

    const freshPlayer = getPlayerSync(playerId)
    const characterList = getPlayerCharactersSync(playerId)
    const characterManaNodeList = getPlayerCharactersManaNodesSync(playerId)
    const equipmentList = getPlayerEquipmentListSync(playerId)
    const partyGroupList = getPlayerPartyGroupListSync(playerId)
    const questProgress = getPlayerQuestProgressSync(playerId)
    const serializedFromQuery = getClientSerializedData(playerId, {
        viewerId: account.id,
        preloadedPlayer: { ...freshPlayer },
    })
    const serializedFromSnapshot = getClientSerializedData(playerId, {
        viewerId: account.id,
        preloadedPlayer: { ...freshPlayer },
        preloadedCharacterList: characterList,
        preloadedCharacterManaNodeList: characterManaNodeList,
        preloadedEquipmentList: equipmentList,
        preloadedPartyGroupList: partyGroupList,
        preloadedQuestProgress: questProgress,
    })
    assert.deepEqual(serializedFromSnapshot, serializedFromQuery, "完整请求内快照复用必须保持 /load 序列化结果一致")
    assert.throws(() => getClientSerializedData(playerId, {
        viewerId: account.id,
        preloadedPlayer: { ...freshPlayer, id: playerId + 1 },
    }), /does not match/, "序列化不得复用其他玩家的快照")
}

async function main() {
    assertExistingDatabaseIndexUpgrade()
    assertIndexPlans()
    assertMissionCounterReturning()
    assertPermanentRepairVersions()
    assertQuestProgressSubsetRead()
    assertArchiveCacheInvalidation()
    assertCloudflareCdnBaseSafety()
    assertActiveMissionPatternIndex()
    await assertAtomicMailClaims()
    console.log("server safe optimization tests passed")
}

main().catch(error => {
    console.error(error)
    process.exitCode = 1
})
