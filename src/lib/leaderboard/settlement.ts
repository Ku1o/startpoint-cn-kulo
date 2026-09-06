import { getDb } from "../../data/db"
import { abandonLeaderboardRunsSync, countLeaderboardRanksSync, getLeaderboardRankPageSync, LeaderboardRankFilter } from "../../data/domains/leaderboard"
import { degreeDefinitions } from "../content-master"
import { insertMailSync, MailType } from "../../data/domains/mail"
import {
    getLeaderboardCompetition,
    getLeaderboardCompetitions,
    getLeaderboardCompetitionSeasonSync,
} from "./competition"
import {
    getLeaderboardRewardTiers,
    isPercentRewardTier,
    LeaderboardRewardRule,
    LeaderboardRewardTier,
    matchLeaderboardRewardTier,
    resolveLeaderboardRewardTiers,
    upgradeLeaderboardRewardRules,
} from "./rewards"
import { getLeaderboardAvailabilitySync, setLeaderboardAvailabilitySync } from "./availability"

export interface LeaderboardSettlementConfig {
    competitionKey: string
    autoEnabled: boolean
    freezeEnabled: boolean
    settleAtMs: number | null
    repeatIntervalMs: number | null
    rewardTiers: LeaderboardRewardRule[]
    mailSubject: string
    mailBody: string
    excludeBots: boolean
    updatedAtMs: number
}

interface RawConfig {
    competition_key: string
    auto_enabled: number
    freeze_enabled: number
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
        freezeEnabled: false,
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
        freezeEnabled: row.freeze_enabled !== 0 || row.auto_enabled !== 0,
        settleAtMs: row.settle_at_ms,
        repeatIntervalMs: row.repeat_interval_ms,
        rewardTiers: JSON.parse(row.reward_tiers_json) as LeaderboardRewardRule[],
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
    const upgraded = upgradeLeaderboardRewardRules(competitionKey, config.rewardTiers)
    if (upgraded !== null) {
        config.rewardTiers = upgraded
        config.updatedAtMs = nowMs
        putLeaderboardSettlementConfigSync(config)
    }
    return config
}

export function putLeaderboardSettlementConfigSync(
    config: LeaderboardSettlementConfig,
): void {
    validateRewardTiers(config.rewardTiers)
    if (typeof config.autoEnabled !== "boolean" || typeof config.freezeEnabled !== "boolean") {
        throw new Error("Schedule switches must be booleans.")
    }
    if (config.settleAtMs !== null && (!Number.isSafeInteger(config.settleAtMs)
        || config.settleAtMs < 0 || config.settleAtMs > 8_640_000_000_000_000 - 28_800_000)) {
        throw new Error("settleAtMs must be an epoch millisecond value or null.")
    }
    if (
        config.repeatIntervalMs !== null
        && (!Number.isSafeInteger(config.repeatIntervalMs) || config.repeatIntervalMs <= 0)
    ) throw new Error("repeatIntervalMs must be a positive millisecond value or null.")
    getDb().prepare(`
        INSERT INTO leaderboard_settlement_configs (
            competition_key, auto_enabled, freeze_enabled, settle_at_ms, repeat_interval_ms,
            reward_tiers_json, mail_subject, mail_body, exclude_bots, updated_at_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (competition_key) DO UPDATE SET
            auto_enabled = excluded.auto_enabled,
            freeze_enabled = excluded.freeze_enabled,
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
        config.freezeEnabled || config.autoEnabled ? 1 : 0,
        config.settleAtMs,
        config.repeatIntervalMs,
        JSON.stringify(config.rewardTiers),
        config.mailSubject,
        config.mailBody,
        config.excludeBots ? 1 : 0,
        config.updatedAtMs,
    )
}

export function validateRewardTiers(tiers: readonly LeaderboardRewardRule[]): void {
    if (!Array.isArray(tiers)) throw new Error("Reward tiers must be an array.")
    const percentMode = tiers[0] !== null && typeof tiers[0] === "object"
        && isPercentRewardTier(tiers[0])
    let expected = percentMode ? 0 : 1
    for (const [index, tier] of tiers.entries()) {
        if (tier === null || typeof tier !== "object") {
            throw new Error("Every reward tier must be an object.")
        }
        if (isPercentRewardTier(tier) !== percentMode) {
            throw new Error("Cannot mix rank and percentage reward tiers.")
        }
        if (isPercentRewardTier(tier)) {
            if ("fromRank" in tier || "toRank" in tier
                || !Number.isSafeInteger(tier.fromPercent) || tier.fromPercent !== expected
                || !Number.isSafeInteger(tier.toPercent) || tier.toPercent <= tier.fromPercent
                || tier.toPercent > 100) {
                throw new Error("Percentage tiers must be contiguous integer percentages from 0 to 100.")
            }
            expected = tier.toPercent
        } else {
            if ("toPercent" in tier || !Number.isSafeInteger(tier.fromRank) || tier.fromRank !== expected) {
                throw new Error(`Reward tiers must be contiguous from rank ${expected}.`)
            }
            if (tier.toRank !== null && (
                !Number.isSafeInteger(tier.toRank) || tier.toRank < tier.fromRank
            )) throw new Error("Reward tier end rank is invalid.")
            if (tier.toRank === null && index !== tiers.length - 1) {
                throw new Error("An open-ended reward tier must be the final tier.")
            }
            expected = tier.toRank === null ? 0 : tier.toRank + 1
        }
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
    }
    if (percentMode && expected !== 100) throw new Error("Percentage tiers must cover through 100%.")
}

export function getLeaderboardRewardRankFilter(config: LeaderboardSettlementConfig): LeaderboardRankFilter {
    return config.rewardTiers.some(isPercentRewardTier)
        ? { excludeDeleted: true, excludeBots: config.excludeBots }
        : {}
}

export interface LeaderboardSeasonRewardView {
    total: number
    rewardTiers: LeaderboardRewardTier[]
    rewardRules: readonly LeaderboardRewardRule[]
    filter: LeaderboardRankFilter
    settled: boolean
}

// Settlement snapshots also serve old-season views after configuration changes.
export function getLeaderboardSeasonRewardViewSync(
    competitionKey: string, season: number,
): LeaderboardSeasonRewardView {
    const settled = getDb().prepare(`
        SELECT id, ranked_players, summary_json FROM leaderboard_settlements
        WHERE competition_key = ? AND season = ? AND status = 'completed'
    `).get(competitionKey, season) as {
        id: number; ranked_players: number; summary_json: string
    } | undefined
    const config = getLeaderboardSettlementConfigSync(competitionKey)
    if (settled !== undefined) {
        const summary = JSON.parse(settled.summary_json) as {
            rewardTiers?: LeaderboardRewardTier[]
            rewardRules?: LeaderboardRewardRule[]
        }
        // Earlier settlements persisted actual prizes but not display metadata.
        // Recover their ranges from those results, never apply new percentages.
        const rewardTiers = summary.rewardTiers ?? getLegacySettlementRewardTiers(settled.id, config.rewardTiers)
        return { total: settled.ranked_players, rewardTiers, rewardRules: summary.rewardRules ?? rewardTiers,
            filter: { settled: true }, settled: true }
    }
    const filter = getLeaderboardRewardRankFilter(config)
    const total = countLeaderboardRanksSync(competitionKey, season, filter)
    return { total, rewardTiers: resolveLeaderboardRewardTiers(config.rewardTiers, total),
        rewardRules: config.rewardTiers, filter, settled: false }
}

function getLegacySettlementRewardTiers(
    settlementId: number, rules: readonly LeaderboardRewardRule[],
): LeaderboardRewardTier[] {
    const rows = getDb().prepare(`
        SELECT rank_number, item_id, item_count, degree_id
        FROM leaderboard_settlement_results WHERE settlement_id = ? ORDER BY rank_number
    `).all(settlementId) as {
        rank_number: number; item_id: number | null; item_count: number; degree_id: number | null
    }[]
    const tiers: LeaderboardRewardTier[] = []
    for (const row of rows) {
        if (row.item_id === null && row.degree_id === null) continue
        const previous = tiers[tiers.length - 1]
        if (previous && previous.toRank === row.rank_number - 1
            && previous.itemId === row.item_id && previous.itemCount === row.item_count
            && previous.degreeId === row.degree_id) {
            previous.toRank = row.rank_number
            continue
        }
        const degree = row.degree_id === null ? undefined
            : (degreeDefinitions as Record<string, { name: string; string_id: string }>)[row.degree_id]
        tiers.push({
            fromRank: row.rank_number, toRank: row.rank_number,
            itemId: row.item_id, itemCount: row.item_count,
            itemName: row.item_id === null ? null
                : rules.find(tier => tier.itemId === row.item_id)?.itemName ?? `道具 #${row.item_id}`,
            degreeId: row.degree_id,
            degreeName: degree?.name ?? (row.degree_id === null ? null : `称号 #${row.degree_id}`),
            degreeImage: degree ? `dynamic/degree/${degree.string_id}.png` : null,
        })
    }
    return tiers
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
    // Freeze independently of the mail transaction: an award failure must not
    // reopen the competition or accept extra results before a retry.
    setLeaderboardAvailabilitySync(competitionKey, false, nowMs)
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

    const config = getLeaderboardSettlementConfigSync(competitionKey, nowMs)
    const filter = getLeaderboardRewardRankFilter(config)
    return getDb().transaction(() => {
        const total = countLeaderboardRanksSync(competitionKey, season, filter)
        const records = getLeaderboardRankPageSync({
            competitionKey,
            season,
            offset: 0,
            limit: total,
            filter,
        })
        const rewardTiers = resolveLeaderboardRewardTiers(config.rewardTiers, total)

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
            const tier = matchLeaderboardRewardTier(rewardTiers, record.rankNumber)
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
        `).run(rewardedPlayers, JSON.stringify({
            skipped, rewardTiers, rewardRules: config.rewardTiers,
            excludeBots: config.excludeBots, rounding: "cumulative-ceiling",
        }), settlementId)
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
    const view = getLeaderboardSeasonRewardViewSync(competitionKey, season)
    const history = getDb().prepare(`
        SELECT id, season, source, settled_at_ms, ranked_players,
            rewarded_players, status, summary_json
        FROM leaderboard_settlements
        WHERE competition_key = ? ORDER BY season DESC LIMIT 30
    `).all(competitionKey)
    return {
        competitionKey,
        season,
        total: view.total,
        resolvedRewardTiers: view.rewardTiers,
        config,
        history,
    }
}

export function runDueLeaderboardSettlementsSync(nowMs: number = Date.now()): void {
    for (const competition of getLeaderboardCompetitions()) {
        const config = getLeaderboardSettlementConfigSync(competition.key, nowMs)
        if ((!config.freezeEnabled && !config.autoEnabled)
            || config.settleAtMs === null || config.settleAtMs > nowMs) continue
        getLeaderboardAvailabilitySync(competition.key, nowMs)
        if (!config.autoEnabled) continue
        const outcome = settleLeaderboardSeasonSync(competition.key, "scheduler", nowMs)
        if (!outcome.ok) continue
        const nextSettleAtMs = config.repeatIntervalMs === null
            ? null
            : config.settleAtMs + (
                Math.floor((nowMs - config.settleAtMs) / config.repeatIntervalMs) + 1
            ) * config.repeatIntervalMs
        putLeaderboardSettlementConfigSync({
            ...config,
            settleAtMs: nextSettleAtMs,
            autoEnabled: config.repeatIntervalMs !== null,
            freezeEnabled: config.repeatIntervalMs !== null,
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
            const tick = () => {
                try { runDueLeaderboardSettlementsSync() }
                catch (error) { console.error("[LEADERBOARD] settlement scheduler failed", error) }
            }
            // Catch up an overdue schedule immediately when the service starts.
            tick()
            timer = setInterval(tick, intervalMs)
            timer.unref()
        },
        stop() {
            if (timer !== null) clearInterval(timer)
            timer = null
        },
    }
}
