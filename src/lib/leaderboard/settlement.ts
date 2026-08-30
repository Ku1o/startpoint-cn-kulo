import { getDb } from "../../data/db"
import { abandonLeaderboardRunsSync, countLeaderboardRanksSync, getLeaderboardRankPageSync } from "../../data/domains/leaderboard"
import { insertMailSync, MailType } from "../../data/domains/mail"
import {
    getLeaderboardCompetition,
    getLeaderboardCompetitions,
    getLeaderboardCompetitionSeasonSync,
} from "./competition"
import {
    getLeaderboardRewardTiers,
    isLegacyDefaultLeaderboardRewardTiers,
    LeaderboardRewardTier,
    matchLeaderboardRewardTier,
} from "./rewards"
import { setLeaderboardAvailabilitySync } from "./availability"

export interface LeaderboardSettlementConfig {
    competitionKey: string
    autoEnabled: boolean
    settleAtMs: number | null
    repeatIntervalMs: number | null
    rewardTiers: LeaderboardRewardTier[]
    mailSubject: string
    mailBody: string
    excludeBots: boolean
    updatedAtMs: number
}

interface RawConfig {
    competition_key: string
    auto_enabled: number
    settle_at_ms: number | null
    repeat_interval_ms: number | null
    reward_tiers_json: string
    mail_subject: string
    mail_body: string
    exclude_bots: number
    updated_at_ms: number
}

function defaultConfig(competitionKey: string, nowMs: number): LeaderboardSettlementConfig {
    const displayName = getLeaderboardCompetition(competitionKey)?.displayName ?? competitionKey
    return {
        competitionKey,
        autoEnabled: false,
        settleAtMs: null,
        repeatIntervalMs: null,
        rewardTiers: [...getLeaderboardRewardTiers(competitionKey)],
        mailSubject: `${displayName}赛季排名报酬`,
        mailBody: `感谢参与${displayName}。本邮件为本赛季最终排名报酬。`,
        excludeBots: true,
        updatedAtMs: nowMs,
    }
}

function deserializeConfig(row: RawConfig): LeaderboardSettlementConfig {
    return {
        competitionKey: row.competition_key,
        autoEnabled: row.auto_enabled !== 0,
        settleAtMs: row.settle_at_ms,
        repeatIntervalMs: row.repeat_interval_ms,
        rewardTiers: JSON.parse(row.reward_tiers_json) as LeaderboardRewardTier[],
        mailSubject: row.mail_subject,
        mailBody: row.mail_body,
        excludeBots: row.exclude_bots !== 0,
        updatedAtMs: row.updated_at_ms,
    }
}

export function getLeaderboardSettlementConfigSync(
    competitionKey: string,
    nowMs: number = Date.now(),
): LeaderboardSettlementConfig {
    const initial = defaultConfig(competitionKey, nowMs)
    getDb().prepare(`
        INSERT OR IGNORE INTO leaderboard_settlement_configs (
            competition_key, auto_enabled, settle_at_ms, repeat_interval_ms,
            reward_tiers_json, mail_subject, mail_body, exclude_bots, updated_at_ms
        ) VALUES (?, 0, NULL, NULL, ?, ?, ?, 1, ?)
    `).run(
        competitionKey,
        JSON.stringify(initial.rewardTiers),
        initial.mailSubject,
        initial.mailBody,
        nowMs,
    )
    const row = getDb().prepare(`
        SELECT * FROM leaderboard_settlement_configs WHERE competition_key = ?
    `).get(competitionKey) as RawConfig
    const config = deserializeConfig(row)
    if (isLegacyDefaultLeaderboardRewardTiers(competitionKey, config.rewardTiers)) {
        config.rewardTiers = [...getLeaderboardRewardTiers(competitionKey)]
        config.updatedAtMs = nowMs
        putLeaderboardSettlementConfigSync(config)
    }
    return config
}

export function putLeaderboardSettlementConfigSync(
    config: LeaderboardSettlementConfig,
): void {
    validateRewardTiers(config.rewardTiers)
    if (config.settleAtMs !== null && !Number.isSafeInteger(config.settleAtMs)) {
        throw new Error("settleAtMs must be an epoch millisecond value or null.")
    }
    if (
        config.repeatIntervalMs !== null
        && (!Number.isSafeInteger(config.repeatIntervalMs) || config.repeatIntervalMs <= 0)
    ) throw new Error("repeatIntervalMs must be a positive millisecond value or null.")
    getDb().prepare(`
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
    `).run(
        config.competitionKey,
        config.autoEnabled ? 1 : 0,
        config.settleAtMs,
        config.repeatIntervalMs,
        JSON.stringify(config.rewardTiers),
        config.mailSubject,
        config.mailBody,
        config.excludeBots ? 1 : 0,
        config.updatedAtMs,
    )
}

export function validateRewardTiers(tiers: readonly LeaderboardRewardTier[]): void {
    if (!Array.isArray(tiers)) throw new Error("Reward tiers must be an array.")
    let expected = 1
    for (const [index, tier] of tiers.entries()) {
        if (tier === null || typeof tier !== "object") {
            throw new Error("Every reward tier must be an object.")
        }
        if (!Number.isSafeInteger(tier.fromRank) || tier.fromRank !== expected) {
            throw new Error(`Reward tiers must be contiguous from rank ${expected}.`)
        }
        if (tier.toRank !== null && (
            !Number.isSafeInteger(tier.toRank) || tier.toRank < tier.fromRank
        )) throw new Error("Reward tier end rank is invalid.")
        if (tier.itemId !== null && (!Number.isSafeInteger(tier.itemId) || tier.itemId <= 0)) {
            throw new Error("Reward item id is invalid.")
        }
        if (!Number.isSafeInteger(tier.itemCount) || tier.itemCount < 0) {
            throw new Error("Reward item count is invalid.")
        }
        if (tier.itemId === null && tier.itemCount !== 0) {
            throw new Error("A reward tier without an item must use itemCount 0.")
        }
        if (tier.itemId !== null && (
            tier.itemCount <= 0
            || typeof tier.itemName !== "string"
            || tier.itemName.trim() === ""
        )) throw new Error("An item reward requires a positive count and item name.")
        if (tier.degreeId !== null && (!Number.isSafeInteger(tier.degreeId) || tier.degreeId <= 0)) {
            throw new Error("Reward degree id is invalid.")
        }
        if (tier.degreeId !== null && (
            typeof tier.degreeName !== "string" || tier.degreeName.trim() === ""
        )) throw new Error("A title reward requires a title name.")
        if (tier.itemId === null && tier.degreeId === null) {
            throw new Error("Every reward tier must grant an item or title.")
        }
        if (tier.toRank === null) {
            if (index !== tiers.length - 1) {
                throw new Error("An open-ended reward tier must be the final tier.")
            }
            return
        }
        expected = tier.toRank + 1
    }
}

export interface SettlementOutcome {
    ok: boolean
    competitionKey: string
    season: number
    settlementId: number | null
    rankedPlayers: number
    rewardedPlayers: number
    reason?: string
}

function isBotPlayerSync(playerId: number): boolean {
    const row = getDb().prepare(`
        SELECT a.idp_code
        FROM players p JOIN accounts a ON a.id = p.account_id
        WHERE p.id = ?
    `).get(playerId) as { idp_code: string } | undefined
    return row?.idp_code === "rushbot"
}

function mailTime(nowMs: number): string {
    return new Date(nowMs).toISOString().replace("T", " ").slice(0, 19)
}

export function settleLeaderboardSeasonSync(
    competitionKey: string,
    source: string,
    nowMs: number = Date.now(),
): SettlementOutcome {
    const season = getLeaderboardCompetitionSeasonSync(competitionKey, nowMs)
    const existing = getDb().prepare(`
        SELECT id, ranked_players, rewarded_players
        FROM leaderboard_settlements
        WHERE competition_key = ? AND season = ? AND status = 'completed'
    `).get(competitionKey, season) as {
        id: number
        ranked_players: number
        rewarded_players: number
    } | undefined
    if (existing !== undefined) return {
        ok: true,
        competitionKey,
        season,
        settlementId: existing.id,
        rankedPlayers: existing.ranked_players,
        rewardedPlayers: existing.rewarded_players,
        reason: "already-settled",
    }

    const total = countLeaderboardRanksSync(competitionKey, season)
    const config = getLeaderboardSettlementConfigSync(competitionKey, nowMs)
    const records = getLeaderboardRankPageSync({
        competitionKey,
        season,
        offset: 0,
        limit: total,
    })

    return getDb().transaction(() => {
        const settlement = getDb().prepare(`
            INSERT INTO leaderboard_settlements (
                competition_key, season, source, settled_at_ms,
                ranked_players, rewarded_players, status, summary_json
            ) VALUES (?, ?, ?, ?, ?, 0, 'running', '{}')
        `).run(competitionKey, season, source, nowMs, records.length)
        const settlementId = Number(settlement.lastInsertRowid)
        let rewardedPlayers = 0
        const skipped: Record<string, number> = {}

        for (const record of records) {
            const tier = matchLeaderboardRewardTier(config.rewardTiers, record.rankNumber)
            let skipReason: string | null = null
            if (tier === null) skipReason = "no-tier"
            else if (!record.playerExists) skipReason = "deleted-player"
            else if (config.excludeBots && isBotPlayerSync(record.playerId)) skipReason = "bot"

            const mailIds: number[] = []
            if (tier !== null && skipReason === null) {
                const base = {
                    reason_id: 0,
                    subject: config.mailSubject,
                    description: `${config.mailBody}\n最终名次：第 ${record.rankNumber} 名`,
                    receive_time: "0000-00-00 00:00:00",
                    create_time: mailTime(nowMs),
                    reward_period_limited: 0,
                    reward_limit_time: null,
                }
                if (tier.itemId !== null && tier.itemCount > 0) {
                    mailIds.push(insertMailSync(record.playerId, {
                        ...base,
                        type: MailType.ITEM,
                        type_id: tier.itemId,
                        number: tier.itemCount,
                    }))
                }
                if (tier.degreeId !== null) {
                    mailIds.push(insertMailSync(record.playerId, {
                        ...base,
                        type: MailType.DEGREE,
                        type_id: tier.degreeId,
                        number: 1,
                    }))
                }
                if (mailIds.length > 0) rewardedPlayers++
            } else if (skipReason !== null) {
                skipped[skipReason] = (skipped[skipReason] ?? 0) + 1
            }

            getDb().prepare(`
                INSERT INTO leaderboard_settlement_results (
                    settlement_id, rank_number, run_id, player_id, player_name,
                    client_battle_ms, item_id, item_count, degree_id,
                    skip_reason, mail_ids_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            `).run(
                settlementId,
                record.rankNumber,
                record.id,
                record.playerId,
                record.displayName,
                record.clientBattleMs,
                tier?.itemId ?? null,
                tier?.itemCount ?? 0,
                tier?.degreeId ?? null,
                skipReason,
                JSON.stringify(mailIds),
            )
        }

        getDb().prepare(`
            UPDATE leaderboard_settlements
            SET rewarded_players = ?, status = 'completed', summary_json = ?
            WHERE id = ?
        `).run(rewardedPlayers, JSON.stringify({ skipped }), settlementId)
        return {
            ok: true,
            competitionKey,
            season,
            settlementId,
            rankedPlayers: records.length,
            rewardedPlayers,
        }
    })()
}

export interface LeaderboardRolloverOutcome {
    ok: boolean
    competitionKey: string
    season: number
    rolled: boolean
    nextSeason: number
    reason?: "season-not-settled"
}

export function rolloverLeaderboardSeasonSync(
    competitionKey: string,
    source: string,
    nowMs: number = Date.now(),
): LeaderboardRolloverOutcome {
    const season = getLeaderboardCompetitionSeasonSync(competitionKey, nowMs)
    const settled = getDb().prepare(`
        SELECT 1 FROM leaderboard_settlements
        WHERE competition_key = ? AND season = ? AND status = 'completed'
    `).get(competitionKey, season)
    if (settled === undefined) return {
        ok: false,
        competitionKey,
        season,
        rolled: false,
        nextSeason: season,
        reason: "season-not-settled",
    }
    const nextSeason = season + 1
    getDb().transaction(() => {
        const result = getDb().prepare(`
            UPDATE leaderboard_seasons
            SET season = ?, started_at_ms = ?, source = ?
            WHERE competition_key = ? AND season = ?
        `).run(nextSeason, nowMs, source, competitionKey, season)
        if (result.changes !== 1) throw new Error("Leaderboard season changed concurrently.")
        abandonLeaderboardRunsSync({ competitionKey, endedAtMs: nowMs })
    })()
    return { ok: true, competitionKey, season, rolled: true, nextSeason }
}

export function getLeaderboardSettlementOverviewSync(competitionKey: string): object {
    const config = getLeaderboardSettlementConfigSync(competitionKey)
    const season = getLeaderboardCompetitionSeasonSync(competitionKey)
    const history = getDb().prepare(`
        SELECT id, season, source, settled_at_ms, ranked_players,
            rewarded_players, status, summary_json
        FROM leaderboard_settlements
        WHERE competition_key = ? ORDER BY season DESC LIMIT 30
    `).all(competitionKey)
    return {
        competitionKey,
        season,
        total: countLeaderboardRanksSync(competitionKey, season),
        config,
        history,
    }
}

export function runDueLeaderboardSettlementsSync(nowMs: number = Date.now()): void {
    for (const competition of getLeaderboardCompetitions()) {
        const config = getLeaderboardSettlementConfigSync(competition.key, nowMs)
        if (!config.autoEnabled || config.settleAtMs === null || config.settleAtMs > nowMs) continue
        const outcome = settleLeaderboardSeasonSync(competition.key, "scheduler", nowMs)
        if (!outcome.ok) continue
        setLeaderboardAvailabilitySync(competition.key, false, nowMs)
        const nextSettleAtMs = config.repeatIntervalMs === null
            ? null
            : config.settleAtMs + (
                Math.floor((nowMs - config.settleAtMs) / config.repeatIntervalMs) + 1
            ) * config.repeatIntervalMs
        putLeaderboardSettlementConfigSync({
            ...config,
            settleAtMs: nextSettleAtMs,
            autoEnabled: config.repeatIntervalMs !== null,
            updatedAtMs: nowMs,
        })
    }
}

export function createLeaderboardSettlementScheduler(intervalMs: number = 60_000): {
    start(): void
    stop(): void
} {
    let timer: NodeJS.Timeout | null = null
    return {
        start() {
            if (timer !== null) return
            timer = setInterval(() => {
                try { runDueLeaderboardSettlementsSync() }
                catch (error) { console.error("[LEADERBOARD] settlement scheduler failed", error) }
            }, intervalMs)
            timer.unref()
        },
        stop() {
            if (timer !== null) clearInterval(timer)
            timer = null
        },
    }
}
