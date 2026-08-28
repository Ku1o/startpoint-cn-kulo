require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const { randomUUID } = require("node:crypto")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const databaseDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "mission-regular-facts-db-"))
const previousDataDirectory = process.env.DATA_DIR
const previousDatabaseDirectory = process.env.WDFP_DATABASE_DIR
process.env.DATA_DIR = databaseDirectory
delete process.env.WDFP_DATABASE_DIR
let db

function cleanup() {
    if (db?.open) db.close()
    fs.rmSync(databaseDirectory, { recursive: true, force: true })
    if (previousDataDirectory === undefined) delete process.env.DATA_DIR
    else process.env.DATA_DIR = previousDataDirectory
    if (previousDatabaseDirectory === undefined) delete process.env.WDFP_DATABASE_DIR
    else process.env.WDFP_DATABASE_DIR = previousDatabaseDirectory
}

process.once("exit", cleanup)

const { initializeDatabase } = require("../src/data")
const { getDb } = require("../src/data/db")
const { insertAccountSync } = require("../src/data/domains/account")
const {
    getMissionBattleCountersSync,
    recordMissionBattleResultSync,
} = require("../src/data/domains/mission_battle_facts")
const { insertPlayerQuestProgressSync } = require("../src/data/domains/quest")
const {
    dailyResetPlayerDataSync,
    getPlayerSync,
    insertDefaultPlayerSync,
    updatePlayerSync,
} = require("../src/data/domains/player")
const { getComputer } = require("../src/lib/mission/registry")
const { recordBattleMissionDimensions } = require("../src/lib/mission/battle-dimensions")
const { settleMissionCategories } = require("../src/lib/mission/settlement")
const { getSnapshot, takeSnapshot } = require("../src/lib/mission/snapshot")
const { getRankDegree } = require("../src/lib/stamina")
const { getMergedPlayerDataSync } = require("../src/data/utils/player-data")
const { replacePlayerDataSync } = require("../src/data/domains/player")
const { getPlayerEquipmentListSync } = require("../src/data/domains/equipment")
const { getMissionMasterDefinitions } = require("../src/lib/mission/master-data")
const { isMissionEnabledAt } = require("../src/lib/mission/patterns")
const { getQuestFromCategorySync } = require("../src/lib/assets")

initializeDatabase()
db = getDb()

const account = insertAccountSync({
    appId: "wf_cn",
    idpAlias: "",
    idpCode: "test",
    idpId: `mission-regular-facts-${randomUUID()}`,
    status: "normal",
})
const playerId = insertDefaultPlayerSync(account.id).id
assert.equal(getPlayerSync(playerId).totalLoginDays, 1, "新存档创建当天应计为首个登录日")
assert.equal(getSnapshot(playerId, "daily").staminaUsed, 0)
assert.equal(
    getSnapshot(playerId, "weekly").loginDays,
    0,
    "新存档的每周基线应保留首日登录进度",
)

assert.deepEqual(getMissionBattleCountersSync(playerId), {
    singlePlayCount: 0,
    singleClearCount: 0,
    multiPlayCount: 0,
    multiClearCount: 0,
    multiHostClearCount: 0,
    multiGuestClearCount: 0,
    singleRankSsCount: 0,
    rankSsCount: 0,
    rankSCount: 0,
    rankACount: 0,
    rankBCount: 0,
})

recordMissionBattleResultSync(playerId, { isMulti: false, accomplished: false })
for (let index = 0; index < 3; index++) {
    recordMissionBattleResultSync(playerId, {
        isMulti: false,
        accomplished: true,
        clearRank: index === 0 ? 5 : 4,
    })
}
recordMissionBattleResultSync(playerId, { isMulti: true, isHost: true, accomplished: true })
recordMissionBattleResultSync(playerId, { isMulti: true, isHost: false, accomplished: false })
for (let index = 0; index < 14; index++) {
    recordMissionBattleResultSync(playerId, { isMulti: true, isHost: false, accomplished: true })
}

assert.deepEqual(getMissionBattleCountersSync(playerId), {
    singlePlayCount: 4,
    singleClearCount: 3,
    multiPlayCount: 16,
    multiClearCount: 15,
    multiHostClearCount: 1,
    multiGuestClearCount: 14,
    singleRankSsCount: 1,
    rankSsCount: 1,
    rankSCount: 2,
    rankACount: 0,
    rankBCount: 0,
})

insertPlayerQuestProgressSync(playerId, 1, {
    questId: 101,
    finished: true,
    clearRank: 5,
})
updatePlayerSync({
    id: playerId,
    rankPoint: 10000,
    totalStaminaUsed: 50,
    totalPowerflips: 7,
    totalDashes: 10,
    totalLoginDays: 3,
})
takeSnapshot(playerId, "daily", {
    questClears: 0,
    staminaUsed: 0,
    rankSs: 0,
    rankS: 0,
    rankA: 0,
    rankB: 0,
    singlePlayCount: 0,
    singleClearCount: 0,
    multiPlayCount: 0,
    multiClearCount: 0,
    multiHostClearCount: 0,
    multiGuestClearCount: 0,
    dashCount: 0,
    powerFlipCount: 0,
    loginDays: 0,
})
takeSnapshot(playerId, "weekly", {
    questClears: 0,
    staminaUsed: 0,
    rankSs: 0,
    rankS: 0,
    rankA: 0,
    rankB: 0,
    singlePlayCount: 0,
    singleClearCount: 0,
    multiPlayCount: 0,
    multiClearCount: 0,
    multiHostClearCount: 0,
    multiGuestClearCount: 0,
    dashCount: 0,
    powerFlipCount: 0,
    loginDays: 0,
})

const regular = getComputer(1)
const regularContext = regular.buildContext(playerId, 1)
assert.equal(regular.compute(2, regularContext, 0), 1, "SS 评价按 clear_rank=5 的累计达成次数计算")
assert.equal(regular.compute(3, regularContext, 0), 10)
assert.equal(regular.compute(6, regularContext, 0), 3, "重复通关同一关也必须增加累计通关")
assert.equal(regular.compute(7, regularContext, 0), 7)
assert.equal(regular.compute(22, regularContext, 0), getRankDegree(10000))
assert.equal(regular.compute(24, regularContext, 0), 3)
assert.equal(regular.compute(25, regularContext, 0), 15)
assert.equal(regular.compute(26, regularContext, 0), 1)
assert.equal(regular.compute(27, regularContext, 0), 14)

const rescueAccount = insertAccountSync({
    appId: "wf_cn",
    idpAlias: "",
    idpCode: "test",
    idpId: `mission-rescue-rank-${randomUUID()}`,
    status: "normal",
})
const rescuePlayerId = insertDefaultPlayerSync(rescueAccount.id).id
for (let questRank = 1; questRank <= 5; questRank++) {
    recordBattleMissionDimensions({
        type: "battle_finish",
        playerId: rescuePlayerId,
        questCategory: 2,
        questId: 1060000 + questRank,
        accomplished: true,
        mode: "multi",
        role: "guest",
        isRescue: true,
        clearTimeMs: 1000,
        partyCharacterIds: [],
        unisonCharacterIds: [],
        statistics: {
            dashCount: 0,
            powerFlipCount: 0,
            powerFlipLv3Count: 0,
            skillCount: 0,
            maxComboCount: 0,
            maxSkillChainCount: 0,
            feverCount: 0,
            feverTimeMs: 0,
            weakenEnemyCount: 0,
            clearEnemyBuffCount: 0,
            clearSelfDebuffCount: 0,
            buffCompanionCount: 0,
            healCompanionCount: 0,
            emotionCount: 0,
            enemyKillCount: 0,
            weakPointDestroyCount: 0,
            coffinReduceCount: 0,
        },
    })
}
const rescueContext = regular.buildContext(rescuePlayerId, 1)
for (const missionId of [62, 63, 64, 87, 100]) {
    assert.equal(
        regular.compute(missionId, rescueContext, 0),
        1,
        `rescue rank mission ${missionId} should use its own difficulty counter`,
    )
}
const rescueSettlement = settleMissionCategories(
    rescuePlayerId,
    [1],
    new Date("2024-08-14T12:00:00.000Z"),
)
assert.deepEqual(
    rescueSettlement.missionInfo
        .filter(entry => [62, 63, 64, 87, 100].includes(entry.mission_id))
        .map(entry => entry.mission_id),
    [62, 63, 64, 87, 100],
)
assert.equal(rescueSettlement.itemList["49000"], 20)
assert.equal(rescueSettlement.itemList["49001"], 20)
assert.equal(rescueSettlement.itemList["49002"], 10)

const daily = getComputer(2)
const dailyContext = daily.buildContext(playerId, 2)
assert.equal(daily.compute(11, dailyContext, 0), 3)
assert.equal(daily.compute(13, dailyContext, 0), 15)
assert.equal(daily.compute(14, dailyContext, 0), 10)
assert.equal(daily.compute(16, dailyContext, 0), 50)

const weekly = getComputer(10)
const weeklyContext = weekly.buildContext(playerId, 10)
assert.equal(weekly.compute(1, weeklyContext, 0), 3, "每周登录必须读取 category 10 自身主数据")
assert.equal(weekly.compute(2, weeklyContext, 0), 15, "每周协力必须读取本周期累计通关")

const weeklySettlement = settleMissionCategories(playerId, [10], new Date("2024-08-14T12:00:00.000Z"))
assert.deepEqual(
    weeklySettlement.missionInfo.map(entry => entry.mission_id),
    [1, 2],
    "每周只应结算现有的登录与协力两条任务",
)
const reloadedWeeklyContext = getComputer(10).buildContext(playerId, 10)
assert.equal(weekly.compute(1, reloadedWeeklyContext, 0), 3, "重新读取仍应保留本周登录进度")
assert.equal(weekly.compute(2, reloadedWeeklyContext, 0), 15, "重新读取仍应保留本周协力进度")
assert.deepEqual(
    settleMissionCategories(playerId, [10], new Date("2024-08-14T12:00:00.000Z")).missionInfo,
    [],
    "重复结算不得再次发放每周任务奖励",
)

const evaluationTime = new Date("2024-08-14T12:00:00.000Z")
const dailySettlement = settleMissionCategories(playerId, [2], evaluationTime)
assert.deepEqual(
    dailySettlement.missionInfo
        .filter(entry => entry.mission_id < 100)
        .map(entry => entry.mission_id),
    [11, 13, 14, 16, 17],
    "四项基础每日任务应在同一次结算中触发全部完成任务",
)

const boundaryAccount = insertAccountSync({
    appId: "wf_cn",
    idpAlias: "",
    idpCode: "test",
    idpId: `mission-weekly-boundary-${randomUUID()}`,
    status: "normal",
})
const boundaryPlayerId = insertDefaultPlayerSync(boundaryAccount.id).id
updatePlayerSync({
    id: boundaryPlayerId,
    lastLoginTime: new Date("2024-08-18T20:00:00.000Z"),
})
for (let index = 0; index < 2; index++) {
    recordMissionBattleResultSync(boundaryPlayerId, {
        isMulti: true,
        isHost: false,
        accomplished: true,
    })
}

assert.equal(
    dailyResetPlayerDataSync(
        getPlayerSync(boundaryPlayerId),
        new Date("2024-08-18T20:59:59.999Z"),
    ),
    false,
    "北京时间周一 05:00 前不得重置周常",
)
assert.equal(getSnapshot(boundaryPlayerId, "weekly").multiClearCount, 0)
assert.equal(
    dailyResetPlayerDataSync(
        getPlayerSync(boundaryPlayerId),
        new Date("2024-08-18T21:00:00.000Z"),
    ),
    true,
    "北京时间周一 05:00 必须生成新的周常快照",
)
assert.equal(getSnapshot(boundaryPlayerId, "weekly").multiClearCount, 2)

for (let index = 0; index < 3; index++) {
    recordMissionBattleResultSync(boundaryPlayerId, {
        isMulti: true,
        isHost: false,
        accomplished: true,
    })
}
const boundaryWeeklyContext = getComputer(10).buildContext(boundaryPlayerId, 10)
assert.equal(getComputer(10).compute(2, boundaryWeeklyContext, 0), 3)
assert.equal(
    dailyResetPlayerDataSync(
        getPlayerSync(boundaryPlayerId),
        new Date("2024-08-18T21:00:01.000Z"),
    ),
    false,
    "同一周重复 load 不得再次重置",
)
const repeatedLoadContext = getComputer(10).buildContext(boundaryPlayerId, 10)
assert.equal(
    getComputer(10).compute(2, repeatedLoadContext, 0),
    3,
    "重复 load 后本周协力进度必须保持",
)

const replacement = getMergedPlayerDataSync(playerId)
assert.ok(replacement)
replacePlayerDataSync(replacement)
const replacedPlayer = getPlayerSync(playerId)
assert.equal(getSnapshot(playerId, "daily").staminaUsed, replacedPlayer.totalStaminaUsed)
assert.equal(getSnapshot(playerId, "daily").dashCount, replacedPlayer.totalDashes)
assert.equal(getSnapshot(playerId, "weekly").loginDays, replacedPlayer.totalLoginDays)

async function verifyChapterMissions() {
    const at = new Date("2026-08-28T04:00:00.000Z")
    const chapterMissions = getMissionMasterDefinitions(1).filter(definition => (
        Number(definition.row[2]) === 22 && isMissionEnabledAt(1, definition.missionId, at)
    ))
    const chapterAccount = insertAccountSync({
        appId: "wf_cn", idpAlias: "", idpCode: "test",
        idpId: `mission-chapters-${randomUUID()}`, status: "normal",
    })
    const chapterPlayerId = insertDefaultPlayerSync(chapterAccount.id).id
    const tables = {
        1: require("../assets/main_quest.json"),
        4: require("../assets/ex_quest.json"),
    }
    const chapterQuestIds = (category, chapter) => Object.keys(tables[category])
        .map(Number).filter(id => Math.floor(id / 1_000_000) === chapter)
    const missing = new Map()
    db.transaction(() => {
        for (const [categoryText, table] of Object.entries(tables)) {
            const category = Number(categoryText)
            for (let chapter = 1; chapter <= 12; chapter++) {
                const ids = chapterQuestIds(category, chapter)
                assert.ok(ids.length > 0)
                // Leave a story unfinished in MAIN where possible: the battle
                // finale alone must not prove the entire chapter is complete.
                const missingId = ids.find(id => table[id].sPlusRewardId === undefined) ?? ids[0]
                missing.set(`${category}:${chapter}`, missingId)
                for (const questId of ids) {
                    assert.ok(getQuestFromCategorySync(category, questId))
                    insertPlayerQuestProgressSync(chapterPlayerId, category, {
                        questId, finished: questId !== missingId, clearRank: 5,
                    })
                }
            }
        }
        // Neither a different category nor a made-up row may fill the gap.
        insertPlayerQuestProgressSync(chapterPlayerId, 2, {
            questId: missing.get("4:1"), finished: true, clearRank: 5,
        })
        insertPlayerQuestProgressSync(chapterPlayerId, 4, {
            questId: 1999999, finished: true, clearRank: 5,
        })
    })()
    const partialContext = regular.buildContext(chapterPlayerId, 1, at)
    for (const definition of chapterMissions) {
        assert.equal(regular.compute(definition.missionId, partialContext, 0), 0,
            `未完成整章不得发奖: ${definition.pattern}`)
    }

    const { updatePlayerQuestProgressSync } = require("../src/data/domains/quest")
    for (const [key, questId] of missing) {
        if (!key.startsWith("1:")) continue
        updatePlayerQuestProgressSync(chapterPlayerId, 1, { questId, finished: true })
    }
    const mainOnlyContext = regular.buildContext(chapterPlayerId, 1, at)
    for (const definition of chapterMissions) {
        assert.equal(regular.compute(definition.missionId, mainOnlyContext, 0),
            Number(definition.row[7]) === 0 ? 1 : 0,
            `普通和高难必须分别判定: ${definition.pattern}`)
    }
    for (const [key, questId] of missing) {
        if (!key.startsWith("4:")) continue
        updatePlayerQuestProgressSync(chapterPlayerId, 4, { questId, finished: true })
    }
    const completedContext = regular.buildContext(chapterPlayerId, 1, at)
    for (const definition of chapterMissions) {
        assert.equal(regular.compute(definition.missionId, completedContext, 0), 1,
            `旧通关记录应恢复章节成就: ${definition.pattern}`)
    }
    assert.equal(regular.compute(71, partialContext, 1), 1, "不得回退已保存的成就进度")

    const Fastify = require("fastify")
    const { insertSessionWithToken } = require("../src/data/domains/session")
    const { saveAccountDefaultPlayer } = require("../src/data/activeAccount")
    saveAccountDefaultPlayer(chapterAccount.id, chapterPlayerId)
    const viewerId = 886328028
    await insertSessionWithToken({
        token: String(viewerId), accountId: chapterAccount.id,
        expires: new Date(Date.now() + 86400000), type: 2,
    })
    const app = Fastify({ logger: false })
    app.addHook("onSend", (_request, reply, payload, done) => {
        if (String(reply.getHeader("content-type") ?? "").startsWith("application/x-msgpack")
            && typeof payload === "object") return done(null, JSON.stringify(payload))
        done(null, payload)
    })
    await app.register(require("../src/routes/api/mission").default, { prefix: "/mission" })
    try {
        const openMissions = () => app.inject({
            method: "POST", url: "/mission/get_mission_progress",
            payload: { viewer_id: viewerId, api_count: 1, category_list: [{ category: 1 }] },
        })
        const first = await openMissions()
        assert.equal(first.statusCode, 200, first.body)
        const result = first.json().data
        assert.equal(result.mission_info.length, 48, "应补发 12 章的 48 条现行章节成就")
        for (const definition of chapterMissions) {
            assert.equal(result.mission_progress_list.find(row => row.mission_id === definition.missionId)?.progress_value, 1)
        }
        const inventory = getPlayerEquipmentListSync(chapterPlayerId)
        for (const id of [3080002, 3020003, 3060010]) {
            assert.equal(inventory[id]?.stack, 0, `战士装备 ${id} 应获得一件`)
        }
        for (const id of [5030037, 5050033, 5010057, 5090028, 5100016, 5080029]) {
            assert.equal(inventory[id]?.stack, 4, `星芥装备 ${id} 应获得五件`)
        }
        assert.equal(result.equipment_list.length, 9)
        const second = await openMissions()
        assert.equal(second.statusCode, 200)
        assert.deepEqual(second.json().data.mission_info, [], "重复打开成就页不得重复发奖")
        assert.deepEqual(getPlayerEquipmentListSync(chapterPlayerId), inventory)
        assert.equal(regular.compute(71, regular.buildContext(playerId, 1, at), 0), 0,
            "不同玩家不得复用章节完成状态")

        const degree = getComputer(5)
        const originalBuildContext = degree.buildContext
        let degreeContextBuilds = 0
        const degreeMissionScopes = []
        degree.buildContext = (...args) => {
            degreeContextBuilds++
            degreeMissionScopes.push(args[3])
            return originalBuildContext(...args)
        }
        try {
            const clientDegree = await app.inject({
                method: "POST", url: "/mission/update_mission_progress",
                payload: {
                    viewer_id: viewerId,
                    api_count: 1,
                    mission_param_list: [{
                        progress_value: 1,
                        mission_pattern: "character_detail_zoom_illust_for_1min_count",
                    }],
                },
            })
            assert.equal(clientDegree.statusCode, 200, clientDegree.body)
            assert.deepEqual(degreeMissionScopes, [[47000]], "客户端称号事实只能结算匹配的称号")
            assert.ok(clientDegree.json().data.degree_list.some(entry => entry.degree_id === 47000),
                "客户端称号事实应在当前响应立即发放")

            degreeContextBuilds = 0
            degreeMissionScopes.length = 0
            const openDegrees = () => app.inject({
                method: "POST", url: "/mission/get_mission_progress",
                payload: { viewer_id: viewerId, api_count: 1, category_list: [{ category: 5 }] },
            })
            const firstDegreePage = await openDegrees()
            assert.equal(firstDegreePage.statusCode, 200, firstDegreePage.body)
            assert.equal(degreeContextBuilds, 1, "称号页结算与返回必须复用同一次计算")

            db.prepare("DELETE FROM players_degrees WHERE player_id = ? AND degree_id = ?")
                .run(chapterPlayerId, 47000)
            const repairedDegreePage = await openDegrees()
            assert.equal(repairedDegreePage.statusCode, 200, repairedDegreePage.body)
            assert.ok(repairedDegreePage.json().data.degree_list.some(entry => entry.degree_id === 47000),
                "旧存档已领取但缺失的称号所有权必须自动修复")

            const changesBeforeNoop = db.prepare("SELECT total_changes() AS value").get().value
            const secondDegreePage = await openDegrees()
            const changesAfterNoop = db.prepare("SELECT total_changes() AS value").get().value
            assert.equal(secondDegreePage.statusCode, 200, secondDegreePage.body)
            assert.equal(degreeContextBuilds, 3, "每次请求只允许构建一次称号上下文")
            assert.equal(changesAfterNoop, changesBeforeNoop, "无进度或奖励变化时不得开启空写入")
        } finally {
            degree.buildContext = originalBuildContext
        }
    } finally {
        await app.close()
    }
}

verifyChapterMissions().then(() => {
    console.log("mission regular facts tests passed (including 48 chapter missions and reward replay)")
    cleanup()
    process.removeListener("exit", cleanup)
}).catch(error => {
    console.error(error)
    process.exitCode = 1
})
