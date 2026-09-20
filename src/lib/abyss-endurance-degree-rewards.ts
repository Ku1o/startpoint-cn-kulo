import { readFileSync } from "node:fs"
import path from "node:path"
import { getDb } from "../data/db"
import { grantPlayerDegreeSync } from "../data/domains/degree"
import { getPlayerSync } from "../data/domains/player"
import {
    abandonLeaderboardRunsSync, finishLeaderboardRoundSync, getActiveLeaderboardRunSync,
    getLeaderboardSeasonSync, insertLeaderboardRunSync, markLeaderboardRoundStartedSync,
    LeaderboardRoundParty, LeaderboardRun,
} from "../data/domains/leaderboard"
import { compareVersion, getPatchManifest } from "./version"
import { QuestCategory } from "./types"
import type { LeaderboardQuestIdentity } from "./leaderboard/service"

export const ABYSS_ENDURANCE_CONFIG_PATH = path.resolve(__dirname, "..", "..", "assets", "abyss_endurance_degree_reward.json")
const REWARDS = Object.freeze([
    { degree_id: 9911101, battle_ms: 60 * 60_000 },
    { degree_id: 9911102, battle_ms: 120 * 60_000 },
    { degree_id: 9911103, battle_ms: 180 * 60_000 },
])
interface Mode { mode: "normal" | "ex"; event_id: number | null; folder_id: number }
interface Config { schema_version: number; enabled: boolean; modes: Mode[] }
export interface EnduranceOptions { configPath?: string }

function configuredModes(options: EnduranceOptions): Mode[] {
    try {
        const config: Config = JSON.parse(readFileSync(options.configPath ?? ABYSS_ENDURANCE_CONFIG_PATH, "utf8"))
        if (config.schema_version !== 2 || config.enabled !== true || !Array.isArray(config.modes)
            || config.modes.length !== 2 || config.modes[0].mode !== "normal" || config.modes[1].mode !== "ex"
            || config.modes[0].event_id !== 700099 || config.modes[0].folder_id !== 1
            || config.modes.some(mode => !Number.isSafeInteger(mode.folder_id) || mode.folder_id < 1
                || (mode.event_id !== null && (!Number.isSafeInteger(mode.event_id) || mode.event_id <= 0)))
            || config.modes[1].event_id === 700099) return []
        return config.modes
    } catch { return [] }
}

function target(quest: Pick<LeaderboardQuestIdentity, "category" | "eventId" | "folderId">, options: EnduranceOptions): Mode | null {
    if (quest.category !== QuestCategory.RUSH_EVENT) return null
    return configuredModes(options).find(mode => mode.event_id !== null
        && mode.event_id === quest.eventId && mode.folder_id === quest.folderId) ?? null
}
function key(mode: Mode): string { return `achievement:abyss-endurance:${mode.event_id}:${mode.folder_id}` }
function revision(mode: Mode): string | null {
    let result: string | null = null, version: string | null = null
    for (const patch of getPatchManifest().patches) {
        const candidate = patch.quest_time_revisions?.[`rush:${mode.event_id}`]
        if (!patch.enabled || patch.type !== "patch" || candidate === undefined) continue
        if (!/^[a-f0-9]{64}$/.test(candidate)) throw new Error("Invalid endurance tower revision")
        const order = version === null ? 1 : compareVersion(patch.version, version)
        if (order === 0 && result !== candidate) throw new Error("Conflicting endurance tower revisions")
        if (order > 0) { result = candidate; version = patch.version }
    }
    return result
}
function validQuest(quest: LeaderboardQuestIdentity): boolean {
    return quest.totalRounds === 30 && Number.isSafeInteger(quest.round)
        && quest.round! >= 1 && quest.round! <= 30 && Number.isSafeInteger(quest.questId)
        && quest.questId > 0
}

/** Separate run identity: closing a ranking season never disables achievement timing. */
export function startAbyssEnduranceQuestSync(playerId: number, quest: LeaderboardQuestIdentity,
    startedAtMs = Date.now(), options: EnduranceOptions = {}): void {
    const mode = target(quest, options)
    if (!mode || !validQuest(quest) || !Number.isSafeInteger(startedAtMs) || startedAtMs < 0) return
    const tower = revision(mode)
    if (tower === null) return
    getDb().transaction(() => {
        const competitionKey = key(mode)
        const season = getLeaderboardSeasonSync(competitionKey, startedAtMs, tower)
        const active = getActiveLeaderboardRunSync(playerId, competitionKey)
        if (active && active.season === season && active.totalRounds === 30
            && quest.round! > 1 && active.roundsCleared === quest.round! - 1) {
            markLeaderboardRoundStartedSync(active.id, quest.round!, quest.questId, startedAtMs)
            return
        }
        abandonLeaderboardRunsSync({ competitionKey, playerId, endedAtMs: startedAtMs })
        const player = getPlayerSync(playerId)
        if (!player) return
        insertLeaderboardRunSync({ competitionKey, playerId, playerName: player.name, season,
            startedAtMs, totalRounds: 30, trackedFromRound: quest.round!,
            pendingRound: quest.round!, pendingQuestId: quest.questId })
    })()
}

function grantCompletedRun(playerId: number, run: LeaderboardRun, acquiredAt: number): number[] {
    if (run.playerId !== playerId || run.status !== "completed" || run.trackedFromRound !== 1
        || run.roundsCleared !== 30 || run.totalRounds !== 30) return []
    const rows = getDb().prepare(`SELECT round_number AS round, client_battle_ms AS ms
        FROM leaderboard_run_rounds WHERE run_id = ? ORDER BY round_number`).all(run.id) as { round: number; ms: number }[]
    if (rows.length !== 30 || rows.some((row, i) => row.round !== i + 1
        || !Number.isSafeInteger(row.ms) || row.ms <= 0)) return []
    const total = rows.reduce((sum, row) => sum + row.ms, 0)
    if (!Number.isSafeInteger(total) || total !== run.clientBattleMs) return []
    return REWARDS.filter(reward => total > reward.battle_ms
        && grantPlayerDegreeSync(playerId, reward.degree_id, acquiredAt)).map(reward => reward.degree_id)
}

export function finishAbyssEnduranceQuestSync(input: {
    playerId: number; quest: LeaderboardQuestIdentity; accomplished: boolean;
    clientBattleMs: number; party: LeaderboardRoundParty; finishedAtMs?: number;
}, options: EnduranceOptions = {}): number[] {
    const mode = target(input.quest, options)
    const finishedAtMs = input.finishedAtMs ?? Date.now()
    if (!mode || !validQuest(input.quest) || !input.accomplished
        || !Number.isSafeInteger(finishedAtMs) || finishedAtMs < 0
        || !Number.isSafeInteger(input.clientBattleMs) || input.clientBattleMs <= 0
        || input.clientBattleMs > 2_147_483_647) return []
    const tower = revision(mode)
    if (tower === null) return []
    return getDb().transaction(() => {
        const season = getLeaderboardSeasonSync(key(mode), finishedAtMs, tower)
        const run = getActiveLeaderboardRunSync(input.playerId, key(mode))
        if (!run || run.season !== season) return []
        const completed = finishLeaderboardRoundSync({ run, round: input.quest.round!,
            questId: input.quest.questId, clientBattleMs: input.clientBattleMs, finishedAtMs, party: input.party })
        return completed === null ? [] : grantCompletedRun(input.playerId, completed, finishedAtMs)
    })()
}

export function resetAbyssEnduranceQuestSync(playerId: number,
    quest: Pick<LeaderboardQuestIdentity, "category" | "eventId" | "folderId">,
    endedAtMs = Date.now(), options: EnduranceOptions = {}): void {
    const mode = target(quest, options)
    if (mode) abandonLeaderboardRunsSync({ competitionKey: key(mode), playerId, endedAtMs })
}
