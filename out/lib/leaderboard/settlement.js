"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createLeaderboardSettlementScheduler = exports.runDueLeaderboardSettlementsSync = exports.getLeaderboardSettlementOverviewSync = exports.rolloverLeaderboardSeasonSync = exports.settleLeaderboardSeasonSync = exports.validateRewardTiers = exports.putLeaderboardSettlementConfigSync = exports.getLeaderboardSettlementConfigSync = void 0;
const db_1 = require("../../data/db");
const leaderboard_1 = require("../../data/domains/leaderboard");
const mail_1 = require("../../data/domains/mail");
const competition_1 = require("./competition");
const rewards_1 = require("./rewards");
const availability_1 = require("./availability");
function defaultConfig(competitionKey, nowMs) {
    var _a, _b;
    const displayName = (_b = (_a = (0, competition_1.getLeaderboardCompetition)(competitionKey)) === null || _a === void 0 ? void 0 : _a.displayName) !== null && _b !== void 0 ? _b : competitionKey;
    return {
        competitionKey,
        autoEnabled: false,
        settleAtMs: null,
        repeatIntervalMs: null,
        rewardTiers: [...(0, rewards_1.getLeaderboardRewardTiers)(competitionKey)],
        mailSubject: `${displayName}赛季排名报酬`,
        mailBody: `感谢参与${displayName}。本邮件为本赛季最终排名报酬。`,
        excludeBots: true,
        updatedAtMs: nowMs,
    };
}
function deserializeConfig(row) {
    return {
        competitionKey: row.competition_key,
        autoEnabled: row.auto_enabled !== 0,
        settleAtMs: row.settle_at_ms,
        repeatIntervalMs: row.repeat_interval_ms,
        rewardTiers: JSON.parse(row.reward_tiers_json),
        mailSubject: row.mail_subject,
        mailBody: row.mail_body,
        excludeBots: row.exclude_bots !== 0,
        updatedAtMs: row.updated_at_ms,
    };
}
function getLeaderboardSettlementConfigSync(competitionKey, nowMs = Date.now()) {
    const initial = defaultConfig(competitionKey, nowMs);
    (0, db_1.getDb)().prepare(`
        INSERT OR IGNORE INTO leaderboard_settlement_configs (
            competition_key, auto_enabled, settle_at_ms, repeat_interval_ms,
            reward_tiers_json, mail_subject, mail_body, exclude_bots, updated_at_ms
        ) VALUES (?, 0, NULL, NULL, ?, ?, ?, 1, ?)
    `).run(competitionKey, JSON.stringify(initial.rewardTiers), initial.mailSubject, initial.mailBody, nowMs);
    const row = (0, db_1.getDb)().prepare(`
        SELECT * FROM leaderboard_settlement_configs WHERE competition_key = ?
    `).get(competitionKey);
    const config = deserializeConfig(row);
    if ((0, rewards_1.isLegacyDefaultLeaderboardRewardTiers)(competitionKey, config.rewardTiers)) {
        config.rewardTiers = [...(0, rewards_1.getLeaderboardRewardTiers)(competitionKey)];
        config.updatedAtMs = nowMs;
        putLeaderboardSettlementConfigSync(config);
    }
    return config;
}
exports.getLeaderboardSettlementConfigSync = getLeaderboardSettlementConfigSync;
function putLeaderboardSettlementConfigSync(config) {
    validateRewardTiers(config.rewardTiers);
    if (config.settleAtMs !== null && !Number.isSafeInteger(config.settleAtMs)) {
        throw new Error("settleAtMs must be an epoch millisecond value or null.");
    }
    if (config.repeatIntervalMs !== null
        && (!Number.isSafeInteger(config.repeatIntervalMs) || config.repeatIntervalMs <= 0))
        throw new Error("repeatIntervalMs must be a positive millisecond value or null.");
    (0, db_1.getDb)().prepare(`
        INSERT INTO leaderboard_settlement_configs (
            competition_key, auto_enabled, settle_at_ms, repeat_interval_ms,
            reward_tiers_json, mail_subject, mail_body, exclude_bots, updated_at_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (competition_key) DO UPDATE SET
            auto_enabled = excluded.auto_enabled,
            settle_at_ms = excluded.settle_at_ms,
            repeat_interval_ms = excluded.repeat_interval_ms,
            reward_tiers_json = excluded.reward_tiers_json,
            mail_subject = excluded.mail_subject,
            mail_body = excluded.mail_body,
            exclude_bots = excluded.exclude_bots,
            updated_at_ms = excluded.updated_at_ms
    `).run(config.competitionKey, config.autoEnabled ? 1 : 0, config.settleAtMs, config.repeatIntervalMs, JSON.stringify(config.rewardTiers), config.mailSubject, config.mailBody, config.excludeBots ? 1 : 0, config.updatedAtMs);
}
exports.putLeaderboardSettlementConfigSync = putLeaderboardSettlementConfigSync;
function validateRewardTiers(tiers) {
    if (!Array.isArray(tiers))
        throw new Error("Reward tiers must be an array.");
    let expected = 1;
    for (const [index, tier] of tiers.entries()) {
        if (tier === null || typeof tier !== "object") {
            throw new Error("Every reward tier must be an object.");
        }
        if (!Number.isSafeInteger(tier.fromRank) || tier.fromRank !== expected) {
            throw new Error(`Reward tiers must be contiguous from rank ${expected}.`);
        }
        if (tier.toRank !== null && (!Number.isSafeInteger(tier.toRank) || tier.toRank < tier.fromRank))
            throw new Error("Reward tier end rank is invalid.");
        if (tier.itemId !== null && (!Number.isSafeInteger(tier.itemId) || tier.itemId <= 0)) {
            throw new Error("Reward item id is invalid.");
        }
        if (!Number.isSafeInteger(tier.itemCount) || tier.itemCount < 0) {
            throw new Error("Reward item count is invalid.");
        }
        if (tier.itemId === null && tier.itemCount !== 0) {
            throw new Error("A reward tier without an item must use itemCount 0.");
        }
        if (tier.itemId !== null && (tier.itemCount <= 0
            || typeof tier.itemName !== "string"
            || tier.itemName.trim() === ""))
            throw new Error("An item reward requires a positive count and item name.");
        if (tier.degreeId !== null && (!Number.isSafeInteger(tier.degreeId) || tier.degreeId <= 0)) {
            throw new Error("Reward degree id is invalid.");
        }
        if (tier.degreeId !== null && (typeof tier.degreeName !== "string" || tier.degreeName.trim() === ""))
            throw new Error("A title reward requires a title name.");
        if (tier.itemId === null && tier.degreeId === null) {
            throw new Error("Every reward tier must grant an item or title.");
        }
        if (tier.toRank === null) {
            if (index !== tiers.length - 1) {
                throw new Error("An open-ended reward tier must be the final tier.");
            }
            return;
        }
        expected = tier.toRank + 1;
    }
}
exports.validateRewardTiers = validateRewardTiers;
function isBotPlayerSync(playerId) {
    const row = (0, db_1.getDb)().prepare(`
        SELECT a.idp_code
        FROM players p JOIN accounts a ON a.id = p.account_id
        WHERE p.id = ?
    `).get(playerId);
    return (row === null || row === void 0 ? void 0 : row.idp_code) === "rushbot";
}
function mailTime(nowMs) {
    return new Date(nowMs).toISOString().replace("T", " ").slice(0, 19);
}
function settleLeaderboardSeasonSync(competitionKey, source, nowMs = Date.now()) {
    const season = (0, competition_1.getLeaderboardCompetitionSeasonSync)(competitionKey, nowMs);
    const existing = (0, db_1.getDb)().prepare(`
        SELECT id, ranked_players, rewarded_players
        FROM leaderboard_settlements
        WHERE competition_key = ? AND season = ? AND status = 'completed'
    `).get(competitionKey, season);
    if (existing !== undefined)
        return {
            ok: true,
            competitionKey,
            season,
            settlementId: existing.id,
            rankedPlayers: existing.ranked_players,
            rewardedPlayers: existing.rewarded_players,
            reason: "already-settled",
        };
    const total = (0, leaderboard_1.countLeaderboardRanksSync)(competitionKey, season);
    const config = getLeaderboardSettlementConfigSync(competitionKey, nowMs);
    const records = (0, leaderboard_1.getLeaderboardRankPageSync)({
        competitionKey,
        season,
        offset: 0,
        limit: total,
    });
    return (0, db_1.getDb)().transaction(() => {
        var _a, _b, _c, _d;
        const settlement = (0, db_1.getDb)().prepare(`
            INSERT INTO leaderboard_settlements (
                competition_key, season, source, settled_at_ms,
                ranked_players, rewarded_players, status, summary_json
            ) VALUES (?, ?, ?, ?, ?, 0, 'running', '{}')
        `).run(competitionKey, season, source, nowMs, records.length);
        const settlementId = Number(settlement.lastInsertRowid);
        let rewardedPlayers = 0;
        const skipped = {};
        for (const record of records) {
            const tier = (0, rewards_1.matchLeaderboardRewardTier)(config.rewardTiers, record.rankNumber);
            let skipReason = null;
            if (tier === null)
                skipReason = "no-tier";
            else if (!record.playerExists)
                skipReason = "deleted-player";
            else if (config.excludeBots && isBotPlayerSync(record.playerId))
                skipReason = "bot";
            const mailIds = [];
            if (tier !== null && skipReason === null) {
                const base = {
                    reason_id: 0,
                    subject: config.mailSubject,
                    description: `${config.mailBody}\n最终名次：第 ${record.rankNumber} 名`,
                    receive_time: "0000-00-00 00:00:00",
                    create_time: mailTime(nowMs),
                    reward_period_limited: 0,
                    reward_limit_time: null,
                };
                if (tier.itemId !== null && tier.itemCount > 0) {
                    mailIds.push((0, mail_1.insertMailSync)(record.playerId, Object.assign(Object.assign({}, base), { type: mail_1.MailType.ITEM, type_id: tier.itemId, number: tier.itemCount })));
                }
                if (tier.degreeId !== null) {
                    mailIds.push((0, mail_1.insertMailSync)(record.playerId, Object.assign(Object.assign({}, base), { type: mail_1.MailType.DEGREE, type_id: tier.degreeId, number: 1 })));
                }
                if (mailIds.length > 0)
                    rewardedPlayers++;
            }
            else if (skipReason !== null) {
                skipped[skipReason] = ((_a = skipped[skipReason]) !== null && _a !== void 0 ? _a : 0) + 1;
            }
            (0, db_1.getDb)().prepare(`
                INSERT INTO leaderboard_settlement_results (
                    settlement_id, rank_number, run_id, player_id, player_name,
                    client_battle_ms, item_id, item_count, degree_id,
                    skip_reason, mail_ids_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            `).run(settlementId, record.rankNumber, record.id, record.playerId, record.displayName, record.clientBattleMs, (_b = tier === null || tier === void 0 ? void 0 : tier.itemId) !== null && _b !== void 0 ? _b : null, (_c = tier === null || tier === void 0 ? void 0 : tier.itemCount) !== null && _c !== void 0 ? _c : 0, (_d = tier === null || tier === void 0 ? void 0 : tier.degreeId) !== null && _d !== void 0 ? _d : null, skipReason, JSON.stringify(mailIds));
        }
        (0, db_1.getDb)().prepare(`
            UPDATE leaderboard_settlements
            SET rewarded_players = ?, status = 'completed', summary_json = ?
            WHERE id = ?
        `).run(rewardedPlayers, JSON.stringify({ skipped }), settlementId);
        return {
            ok: true,
            competitionKey,
            season,
            settlementId,
            rankedPlayers: records.length,
            rewardedPlayers,
        };
    })();
}
exports.settleLeaderboardSeasonSync = settleLeaderboardSeasonSync;
function rolloverLeaderboardSeasonSync(competitionKey, source, nowMs = Date.now()) {
    const season = (0, competition_1.getLeaderboardCompetitionSeasonSync)(competitionKey, nowMs);
    const settled = (0, db_1.getDb)().prepare(`
        SELECT 1 FROM leaderboard_settlements
        WHERE competition_key = ? AND season = ? AND status = 'completed'
    `).get(competitionKey, season);
    if (settled === undefined)
        return {
            ok: false,
            competitionKey,
            season,
            rolled: false,
            nextSeason: season,
            reason: "season-not-settled",
        };
    const nextSeason = season + 1;
    (0, db_1.getDb)().transaction(() => {
        const result = (0, db_1.getDb)().prepare(`
            UPDATE leaderboard_seasons
            SET season = ?, started_at_ms = ?, source = ?
            WHERE competition_key = ? AND season = ?
        `).run(nextSeason, nowMs, source, competitionKey, season);
        if (result.changes !== 1)
            throw new Error("Leaderboard season changed concurrently.");
        (0, leaderboard_1.abandonLeaderboardRunsSync)({ competitionKey, endedAtMs: nowMs });
    })();
    return { ok: true, competitionKey, season, rolled: true, nextSeason };
}
exports.rolloverLeaderboardSeasonSync = rolloverLeaderboardSeasonSync;
function getLeaderboardSettlementOverviewSync(competitionKey) {
    const config = getLeaderboardSettlementConfigSync(competitionKey);
    const season = (0, competition_1.getLeaderboardCompetitionSeasonSync)(competitionKey);
    const history = (0, db_1.getDb)().prepare(`
        SELECT id, season, source, settled_at_ms, ranked_players,
            rewarded_players, status, summary_json
        FROM leaderboard_settlements
        WHERE competition_key = ? ORDER BY season DESC LIMIT 30
    `).all(competitionKey);
    return {
        competitionKey,
        season,
        total: (0, leaderboard_1.countLeaderboardRanksSync)(competitionKey, season),
        config,
        history,
    };
}
exports.getLeaderboardSettlementOverviewSync = getLeaderboardSettlementOverviewSync;
function runDueLeaderboardSettlementsSync(nowMs = Date.now()) {
    for (const competition of (0, competition_1.getLeaderboardCompetitions)()) {
        const config = getLeaderboardSettlementConfigSync(competition.key, nowMs);
        if (!config.autoEnabled || config.settleAtMs === null || config.settleAtMs > nowMs)
            continue;
        const outcome = settleLeaderboardSeasonSync(competition.key, "scheduler", nowMs);
        if (!outcome.ok)
            continue;
        (0, availability_1.setLeaderboardAvailabilitySync)(competition.key, false, nowMs);
        const nextSettleAtMs = config.repeatIntervalMs === null
            ? null
            : config.settleAtMs + (Math.floor((nowMs - config.settleAtMs) / config.repeatIntervalMs) + 1) * config.repeatIntervalMs;
        putLeaderboardSettlementConfigSync(Object.assign(Object.assign({}, config), { settleAtMs: nextSettleAtMs, autoEnabled: config.repeatIntervalMs !== null, updatedAtMs: nowMs }));
    }
}
exports.runDueLeaderboardSettlementsSync = runDueLeaderboardSettlementsSync;
function createLeaderboardSettlementScheduler(intervalMs = 60000) {
    let timer = null;
    return {
        start() {
            if (timer !== null)
                return;
            timer = setInterval(() => {
                try {
                    runDueLeaderboardSettlementsSync();
                }
                catch (error) {
                    console.error("[LEADERBOARD] settlement scheduler failed", error);
                }
            }, intervalMs);
            timer.unref();
        },
        stop() {
            if (timer !== null)
                clearInterval(timer);
            timer = null;
        },
    };
}
exports.createLeaderboardSettlementScheduler = createLeaderboardSettlementScheduler;
