const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-percent-rewards-"))
process.env.DATA_DIR = temporaryDataDir
const { getDb } = require("../out/data/db")
const { insertAccountSync } = require("../out/data/domains/account")
const { insertPlayerSync } = require("../out/data/domains/player")
const { getDefaultPlayerData } = require("../out/data/utils")
const { countLeaderboardRanksSync } = require("../out/data/domains/leaderboard")
const { getLeaderboardCompetition, getLeaderboardCompetitionSeasonSync } = require("../out/lib/leaderboard/competition")
const { DEEP_ABYSS_REWARD_TIERS, resolveLeaderboardRewardTiers, matchLeaderboardRewardTier } = require("../out/lib/leaderboard/rewards")
const {
    getLeaderboardSettlementConfigSync, putLeaderboardSettlementConfigSync,
    validateRewardTiers, settleLeaderboardSeasonSync, getLeaderboardSeasonRewardViewSync,
    rolloverLeaderboardSeasonSync,
} = require("../out/lib/leaderboard/settlement")
const { buildNativeLeaderboardPayload, getOfficialLeaderboardPageSync, buildLeaderboardTermsText } = require("../out/lib/leaderboard/presentation")
const { degreeDefinitions } = require("../out/lib/content-master")
const { setLeaderboardAvailabilitySync } = require("../out/lib/leaderboard/availability")
const policy = require("../assets/leaderboard_reward_policy.json")
const Fastify = require("fastify")
const adminRoutes = require("../out/routes/web_api/leaderboards").default
const competition = getLeaderboardCompetition("rush:700099:1")
const db = getDb()
let season
let identity = 0

test.beforeEach(() => {
    for (const table of ["leaderboard_settlement_results", "leaderboard_settlements", "leaderboard_run_rounds",
        "leaderboard_runs", "leaderboard_settlement_configs", "leaderboard_seasons", "leaderboard_availability",
        "players_mails", "players_degrees", "players", "accounts"]) db.prepare(`DELETE FROM ${table}`).run()
    season = getLeaderboardCompetitionSeasonSync(competition.key)
})

test.after(() => {
    db.close()
    assert.equal(path.dirname(path.resolve(temporaryDataDir)), path.resolve(os.tmpdir()))
    fs.rmSync(temporaryDataDir, { recursive: true, force: true })
})

function player(name, bot = false) {
    const account = insertAccountSync({ appId: "wf_cn", idpAlias: String(++identity),
        idpCode: bot ? "rushbot" : "leiting", idpId: "", status: "normal" })
    return insertPlayerSync(account.id, { ...getDefaultPlayerData(), name })
}

function run(playerId, ms, finishedAt = 1_000_000 + ms, trackedFrom = 1, roundCount = 2) {
    const result = db.prepare(`INSERT INTO leaderboard_runs (
        competition_key, player_id, season, status, started_at_ms, finished_at_ms,
        client_battle_ms, rounds_cleared, total_rounds, tracked_from_round, character_id_1
    ) VALUES (?, ?, ?, 'completed', 1000, ?, ?, 2, 2, ?, 1)`)
        .run(competition.key, playerId, season, finishedAt, ms, trackedFrom)
    const id = Number(result.lastInsertRowid)
    for (let round = 1; round <= roundCount; round++) db.prepare(`INSERT INTO leaderboard_run_rounds (
        run_id, round_number, quest_id, client_battle_ms, server_elapsed_ms, started_at_ms, finished_at_ms
    ) VALUES (?, ?, ?, ?, ?, 1000, ?)`).run(id, round, 700099000 + round, ms / 2, ms / 2, finishedAt)
    return id
}

function participants(total) {
    return db.transaction(() => Array.from({ length: total }, (_, index) => {
        const id = player(`Rank ${index + 1}`)
        run(id, (index + 1) * 100)
        return id
    }))()
}

function ranges(total) {
    return resolveLeaderboardRewardTiers(DEEP_ABYSS_REWARD_TIERS, total)
        .map(tier => [tier.fromRank, tier.toRank, tier.degreeId])
}

test("累计截止名次向上取整：零人、单人、小人数和整百分比边界", () => {
    assert.deepEqual(ranges(0), [])
    assert.deepEqual(ranges(1), [[1, 1, 9900007]])
    assert.deepEqual(ranges(2), [[1, 1, 9900007], [2, null, 9900011]])
    assert.deepEqual(ranges(6), [[1, 1, 9900007], [2, 2, 9900010], [3, null, 9900011]])
    assert.deepEqual(ranges(50), [[1, 1, 9900007], [2, 3, 9900008], [4, 5, 9900009], [6, 10, 9900010], [11, null, 9900011]])
    assert.deepEqual(ranges(200), [[1, 2, 9900007], [3, 10, 9900008], [11, 20, 9900009], [21, 40, 9900010], [41, null, 9900011]])
    assert.deepEqual(ranges(1000), [[1, 10, 9900007], [11, 50, 9900008], [51, 100, 9900009], [101, 200, 9900010], [201, null, 9900011]])
    for (let total = 1; total <= 200; total++) {
        const tiers = resolveLeaderboardRewardTiers(DEEP_ABYSS_REWARD_TIERS, total)
        assert.equal(matchLeaderboardRewardTier(tiers, 1).degreeId, 9900007)
        for (let rank = 1; rank <= total; rank++) {
            assert.equal(tiers.filter(tier => rank >= tier.fromRank && (tier.toRank === null || rank <= tier.toRank)).length, 1)
        }
    }
})

test("既有五档迁移只改边界，保留后台定制的 5/4/3/2/3 数量和称号", () => {
    const original = getLeaderboardSettlementConfigSync(competition.key)
    const bounds = [[1, 1], [2, 2], [3, 3], [4, 15], [16, null]]
    const counts = [5, 4, 3, 2, 3]
    const legacy = original.rewardTiers.map(({ fromPercent, toPercent, ...reward }, i) => ({
        ...reward, fromRank: bounds[i][0], toRank: bounds[i][1], itemCount: counts[i],
        degreeName: `自定义称号 ${i}`, degreeId: 9900007 + i,
    }))
    db.prepare("UPDATE leaderboard_settlement_configs SET reward_tiers_json = ? WHERE competition_key = ?")
        .run(JSON.stringify(legacy), competition.key)
    const migrated = getLeaderboardSettlementConfigSync(competition.key)
    assert.deepEqual(migrated.rewardTiers.map(tier => [tier.fromPercent, tier.toPercent]), [[0, 1], [1, 5], [5, 10], [10, 20], [20, 100]])
    assert.deepEqual(migrated.rewardTiers.map(tier => tier.itemCount), counts)
    assert.deepEqual(migrated.rewardTiers.map(tier => tier.degreeName), legacy.map(tier => tier.degreeName))
    assert.ok(migrated.rewardTiers.every(tier => !("fromRank" in tier)))
    assert.deepEqual(getLeaderboardSettlementConfigSync(competition.key), migrated)
})

test("空榜预览五档奖励但真实人数与结算档位仍为空；参榜后切回实际名次", () => {
    const config = getLeaderboardSettlementConfigSync(competition.key)
    const counts = [5, 4, 3, 2, 3]
    putLeaderboardSettlementConfigSync({ ...config,
        rewardTiers: config.rewardTiers.map((tier, i) => ({ ...tier, itemCount: counts[i] })) })
    const preview = buildNativeLeaderboardPayload(competition, null)
    assert.equal(preview.total, 0)
    assert.deepEqual(preview.rows, [])
    assert.equal(preview.name, `${competition.displayName}（按100人参榜预览）`)
    assert.deepEqual(preview.reward.map(tier => [tier.fromRank, tier.toRank]),
        [[1, 1], [2, 5], [6, 10], [11, 20], [21, null]])
    assert.deepEqual(preview.reward.map(tier => tier.itemCount), counts)
    assert.deepEqual(getLeaderboardSeasonRewardViewSync(competition.key, season).rewardTiers, [])
    const terms = buildLeaderboardTermsText(competition)
    assert.match(terms, /按100人参榜预览/)
    assert.match(terms, /第2～5名/)
    const [id] = participants(1)
    const single = buildNativeLeaderboardPayload(competition, id)
    assert.equal(single.total, 1)
    assert.equal(single.name, competition.displayName)
    assert.deepEqual(single.reward.map(tier => [tier.fromRank, tier.toRank]), [[1, 1]])
    assert.doesNotMatch(buildLeaderboardTermsText(competition), /预览/)
    participants(49)
    const fifty = buildNativeLeaderboardPayload(competition, id)
    assert.equal(fifty.total, 50)
    assert.equal(fifty.name, competition.displayName)
    assert.deepEqual(fifty.reward.map(tier => [tier.fromRank, tier.toRank]),
        [[1, 1], [2, 3], [4, 5], [6, 10], [11, null]])
})

test("空赛季预览不发奖，结算后按规则快照预览并明确本期无人获奖", () => {
    const before = buildNativeLeaderboardPayload(competition, null)
    const outcome = settleLeaderboardSeasonSync(competition.key, "empty-preview")
    assert.equal(outcome.rankedPlayers, 0)
    assert.equal(outcome.rewardedPlayers, 0)
    assert.equal(db.prepare("SELECT COUNT(*) n FROM players_mails").get().n, 0)
    assert.equal(db.prepare("SELECT COUNT(*) n FROM leaderboard_settlement_results").get().n, 0)
    assert.deepEqual(getLeaderboardSeasonRewardViewSync(competition.key, season).rewardTiers, [])
    const config = getLeaderboardSettlementConfigSync(competition.key)
    putLeaderboardSettlementConfigSync({ ...config,
        rewardTiers: config.rewardTiers.map(tier => ({ ...tier, itemCount: 999 })) })
    const settled = buildNativeLeaderboardPayload(competition, null)
    assert.equal(settled.total, 0)
    assert.equal(settled.time, "已结算")
    assert.match(settled.name, /本期无人获奖；按100人参榜预览/)
    assert.deepEqual(settled.reward, before.reward)
    assert.match(buildLeaderboardTermsText(competition), /本期无人获奖/)
})

test("管理接口保存百分比奖励并拒绝混用、重叠、缺档、小数和越界", async t => {
    const app = Fastify()
    await app.register(adminRoutes, { prefix: "/leaderboards" })
    t.after(() => app.close())
    const url = `/leaderboards/${encodeURIComponent(competition.key)}/config`
    const config = getLeaderboardSettlementConfigSync(competition.key)
    const saved = await app.inject({ method: "PATCH", url, payload: { rewardTiers: config.rewardTiers } })
    assert.equal(saved.statusCode, 200, saved.payload)
    for (const bad of [
        [{ ...config.rewardTiers[0], toPercent: 1.5 }, ...config.rewardTiers.slice(1)],
        [{ ...config.rewardTiers[0], toPercent: 6 }, ...config.rewardTiers.slice(1)],
        config.rewardTiers.slice(0, 4),
        [{ ...config.rewardTiers[0], fromPercent: -1, toPercent: 100 }],
        [{ ...config.rewardTiers[0], toPercent: 101 }],
        [{ ...config.rewardTiers[0], fromRank: 1, toRank: 1 }, ...config.rewardTiers.slice(1)],
        [null],
    ]) {
        const result = await app.inject({ method: "PATCH", url, payload: { rewardTiers: bad } })
        assert.equal(result.statusCode, 400, result.payload)
    }
    const { fromPercent, toPercent, ...reward } = config.rewardTiers[0]
    validateRewardTiers([{ ...reward, fromRank: 1, toRank: null }])
    assert.deepEqual(getLeaderboardSettlementConfigSync(competition.key).rewardTiers, config.rewardTiers)
})

test("完整有效成绩去重且先排除机器人和删除玩家；500 人显示上限不截断结算", async t => {
    const ids = participants(501)
    const bot = player("Bot", true)
    run(bot, 1)
    const deleted = player("Deleted")
    run(deleted, 2)
    // Simulate old/imported records whose player has already disappeared.
    db.pragma("foreign_keys = OFF")
    try { db.prepare("DELETE FROM players WHERE id = ?").run(deleted) }
    finally { db.pragma("foreign_keys = ON") }
    run(ids[0], 999999) // Slower repeat must not increase the denominator.
    run(player("Partial"), 3, 3000, 2)
    run(player("Missing round"), 4, 3000, 1, 1)
    assert.equal(countLeaderboardRanksSync(competition.key, season), 503)
    const preview = buildNativeLeaderboardPayload(competition, ids[500])
    assert.equal(preview.total, 501)
    assert.equal(preview.rows.length, 500)
    assert.equal(preview.item.rank, "501位")
    assert.deepEqual(preview.reward.map(tier => [tier.fromRank, tier.toRank]), [[1, 6], [7, 26], [27, 51], [52, 101], [102, null]])
    assert.match(buildLeaderboardTermsText(competition), /第7～26名/)
    const official = getOfficialLeaderboardPageSync({ competition, playerId: ids[0], page: 0 })
    assert.equal(official.total, 501)
    assert.equal(official.rows[0].rank_number, 1)
    const app = Fastify()
    await app.register(adminRoutes, { prefix: "/leaderboards" })
    t.after(() => app.close())
    const admin = (await app.inject({ method: "GET", url: `/leaderboards/${encodeURIComponent(competition.key)}` })).json()
    assert.equal(admin.total, 501)
    assert.equal(admin.rows[0].playerId, ids[0])
    assert.deepEqual(admin.overview.resolvedRewardTiers, preview.reward)
    const result = settleLeaderboardSeasonSync(competition.key, "test")
    assert.equal(result.rankedPlayers, 501)
    assert.equal(result.rewardedPlayers, 501)
    assert.deepEqual(db.prepare(`SELECT degree_id, COUNT(*) n FROM leaderboard_settlement_results
        WHERE settlement_id = ? GROUP BY degree_id ORDER BY degree_id`).all(result.settlementId), [
        { degree_id: 9900007, n: 6 }, { degree_id: 9900008, n: 20 }, { degree_id: 9900009, n: 25 },
        { degree_id: 9900010, n: 50 }, { degree_id: 9900011, n: 400 },
    ])
    assert.equal(db.prepare("SELECT COUNT(*) n FROM players_mails").get().n, 1002)
    const repeat = settleLeaderboardSeasonSync(competition.key, "repeat")
    assert.equal(repeat.reason, "already-settled")
    assert.equal(db.prepare("SELECT COUNT(*) n FROM players_mails").get().n, 1002)
})

test("结算后的奖档和名次不随配置、参榜人数或机器人开关变化，换季回看仍一致", () => {
    const ids = participants(21)
    const preview = buildNativeLeaderboardPayload(competition, ids[0])
    settleLeaderboardSeasonSync(competition.key, "test")
    const config = getLeaderboardSettlementConfigSync(competition.key)
    putLeaderboardSettlementConfigSync({ ...config, excludeBots: false,
        rewardTiers: config.rewardTiers.map(tier => ({ ...tier, itemCount: 999 })) })
    run(player("Late leader"), 1)
    const frozen = buildNativeLeaderboardPayload(competition, ids[0])
    assert.equal(frozen.total, 21)
    assert.equal(frozen.item.rank, "1位")
    assert.deepEqual(frozen.reward, preview.reward)
    assert.equal(frozen.time, "已结算")
    db.prepare("DELETE FROM players WHERE id = ?").run(ids[1])
    const deletedAfterSettlement = buildNativeLeaderboardPayload(competition, ids[0])
    assert.equal(deletedAfterSettlement.rows.length, 21)
    assert.equal(deletedAfterSettlement.rows[1].name, "Rank 2")
    assert.equal(deletedAfterSettlement.rows[1].id, 0)
    assert.deepEqual(deletedAfterSettlement.reward, preview.reward)
    assert.equal(rolloverLeaderboardSeasonSync(competition.key, "test").rolled, true)
    assert.deepEqual(buildNativeLeaderboardPayload(competition, ids[0], false).reward, preview.reward)
    setLeaderboardAvailabilitySync(competition.key, true)
    assert.equal(buildNativeLeaderboardPayload(competition, ids[0], true).total, 0)
    assert.equal(buildNativeLeaderboardPayload(competition, ids[0], true).reward.length, 5)
    assert.match(buildNativeLeaderboardPayload(competition, ids[0], true).name, /按100人参榜预览/)
})

test("相同用时按完成时间和记录 ID 稳定排序；旧结算从实际发奖记录恢复", () => {
    const ids = participants(3)
    db.prepare("UPDATE leaderboard_runs SET client_battle_ms = 100, finished_at_ms = 2000").run()
    db.prepare("UPDATE leaderboard_runs SET finished_at_ms = 1999 WHERE player_id = ?").run(ids[1])
    const result = settleLeaderboardSeasonSync(competition.key, "test")
    const ranks = db.prepare("SELECT player_id FROM leaderboard_settlement_results WHERE settlement_id = ? ORDER BY rank_number").all(result.settlementId)
    assert.deepEqual(ranks.map(row => row.player_id), [ids[1], ids[0], ids[2]])
    db.prepare("UPDATE leaderboard_settlements SET summary_json = '{}' WHERE id = ?").run(result.settlementId)
    const historical = getLeaderboardSeasonRewardViewSync(competition.key, season)
    assert.equal(historical.total, 3)
    assert.deepEqual(historical.rewardTiers.map(tier => [tier.fromRank, tier.toRank, tier.degreeId]), [[1, 1, 9900007], [2, 3, 9900011]])
})

test("发奖失败事务回滚，恢复后重试完整发奖；空赛季不产生邮件", () => {
    participants(6)
    db.exec(`CREATE TEMP TRIGGER fail_reward BEFORE INSERT ON players_mails
        WHEN (SELECT COUNT(*) FROM players_mails) >= 2 BEGIN SELECT RAISE(ABORT, 'mail-failed'); END`)
    try {
        assert.throws(() => settleLeaderboardSeasonSync(competition.key, "test"), /mail-failed/)
        assert.equal(db.prepare("SELECT COUNT(*) n FROM leaderboard_settlements").get().n, 0)
        assert.equal(db.prepare("SELECT COUNT(*) n FROM leaderboard_settlement_results").get().n, 0)
        assert.equal(db.prepare("SELECT COUNT(*) n FROM players_mails").get().n, 0)
    } finally { db.exec("DROP TRIGGER fail_reward") }
    assert.equal(settleLeaderboardSeasonSync(competition.key, "retry").rewardedPlayers, 6)
    rolloverLeaderboardSeasonSync(competition.key, "test")
    const empty = settleLeaderboardSeasonSync(competition.key, "empty")
    assert.equal(empty.rankedPlayers, 0)
    assert.equal(empty.rewardedPlayers, 0)
    assert.equal(db.prepare("SELECT COUNT(*) n FROM players_mails").get().n, 12)
})

test("本期称号有效主数据使用可复用获得条件，旧赛季和商店称号保持原条件", () => {
    for (let id = 9900007; id <= 9900011; id++) assert.equal(degreeDefinitions[id].condition, policy.titleCondition)
    assert.match(degreeDefinitions[9900002].condition, /排名第1/)
    assert.match(degreeDefinitions[9900006].condition, /商店购买/)
})
