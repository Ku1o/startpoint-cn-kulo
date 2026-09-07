import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify"
import { getLeaderboardRankPageSync } from "../../data/domains/leaderboard"
import {
    getLeaderboardCompetition,
    getLeaderboardCompetitions,
    getLeaderboardCompetitionSeasonSync,
} from "../../lib/leaderboard/competition"
import {
    getLeaderboardSettlementConfigSync,
    getLeaderboardSettlementOverviewSync,
    getLeaderboardSeasonRewardViewSync,
    putLeaderboardSettlementConfigSync,
    rolloverLeaderboardSeasonSync,
    settleLeaderboardSeasonSync,
    validateRewardTiers,
} from "../../lib/leaderboard/settlement"
import type { LeaderboardRewardRule } from "../../lib/leaderboard/rewards"
import {
    getLeaderboardAvailabilitySync,
    isLeaderboardDeadlineDueSync,
    setLeaderboardAvailabilitySync,
} from "../../lib/leaderboard/availability"

interface KeyParams { key: string }

function resolveKey(request: FastifyRequest, reply: FastifyReply): string | null {
    const key = (request.params as KeyParams).key
    if (getLeaderboardCompetition(key) !== null) return key
    reply.status(404).send({ error: "Leaderboard competition not found." })
    return null
}

const routes = async (fastify: FastifyInstance) => {
    fastify.get("/", async (_request, reply) => reply.send(
        getLeaderboardCompetitions().map(competition => ({
            competition,
            availability: getLeaderboardAvailabilitySync(competition.key),
            overview: getLeaderboardSettlementOverviewSync(competition.key),
        })),
    ))

    fastify.get("/:key", async (request, reply) => {
        const key = resolveKey(request, reply)
        if (key === null) return
        const competition = getLeaderboardCompetition(key)!
        const season = getLeaderboardCompetitionSeasonSync(key)
        const { total, filter } = getLeaderboardSeasonRewardViewSync(key, season)
        const query = request.query as { page?: string }
        const page = Math.max(0, Math.floor(Number(query.page ?? 0) || 0))
        return reply.send({
            competition,
            availability: getLeaderboardAvailabilitySync(key),
            overview: getLeaderboardSettlementOverviewSync(key),
            page,
            rows: getLeaderboardRankPageSync({
                competitionKey: key,
                season,
                offset: page * competition.pageSize,
                limit: competition.pageSize,
                filter,
            }),
            total,
        })
    })

    fastify.patch("/:key/availability", async (request, reply) => {
        const key = resolveKey(request, reply)
        if (key === null) return
        const body = (request.body ?? {}) as Record<string, unknown>
        if (typeof body.enabled !== "boolean") {
            return reply.status(400).send({ error: "enabled must be a boolean." })
        }
        if (body.enabled) {
            const season = getLeaderboardCompetitionSeasonSync(key)
            if (getLeaderboardSeasonRewardViewSync(key, season).settled) {
                return reply.status(409).send({ error: "当前赛季已结算，请先换季再开启排行榜。" })
            }
            if (isLeaderboardDeadlineDueSync(key)) {
                return reply.status(409).send({ error: "已到截止时间，请先修改截止时间或关闭定时开关，再开启排行榜。" })
            }
        }
        return reply.send({
            ok: true,
            ...setLeaderboardAvailabilitySync(key, body.enabled),
        })
    })

    fastify.patch("/:key/config", async (request, reply) => {
        const key = resolveKey(request, reply)
        if (key === null) return
        const current = getLeaderboardSettlementConfigSync(key)
        const body = (request.body ?? {}) as Record<string, unknown>
        const rewardTiers = body.rewardTiers === undefined
            ? current.rewardTiers
            : body.rewardTiers as LeaderboardRewardRule[]
        try {
            for (const field of ["autoEnabled", "freezeEnabled"] as const) {
                if (body[field] !== undefined && typeof body[field] !== "boolean") {
                    throw new Error("到时冻结和自动发奖开关必须是布尔值。")
                }
            }
            const autoEnabled = body.autoEnabled === undefined ? current.autoEnabled : body.autoEnabled as boolean
            const freezeEnabled = autoEnabled || (body.freezeEnabled === undefined
                ? current.freezeEnabled : body.freezeEnabled as boolean)
            const settleAtMs = body.settleAtMs === undefined ? current.settleAtMs
                : body.settleAtMs === null ? null : Number(body.settleAtMs)
            if ((autoEnabled || freezeEnabled) && settleAtMs === null) {
                throw new Error("开启定时冻结或自动发奖时必须设置截止时间。")
            }
            validateRewardTiers(rewardTiers)
            putLeaderboardSettlementConfigSync({
                ...current,
                autoEnabled,
                freezeEnabled,
                settleAtMs,
                repeatIntervalMs: body.repeatIntervalMs === undefined
                    ? current.repeatIntervalMs
                    : body.repeatIntervalMs === null ? null : Number(body.repeatIntervalMs),
                rewardTiers,
                mailSubject: typeof body.mailSubject === "string"
                    ? body.mailSubject : current.mailSubject,
                mailBody: typeof body.mailBody === "string"
                    ? body.mailBody : current.mailBody,
                excludeBots: body.excludeBots === undefined
                    ? current.excludeBots : Boolean(body.excludeBots),
                updatedAtMs: Date.now(),
            })
        } catch (error) {
            return reply.status(400).send({
                error: error instanceof Error ? error.message : "Invalid settlement config.",
            })
        }
        return reply.send({ ok: true, config: getLeaderboardSettlementConfigSync(key) })
    })

    fastify.post("/:key/settle", async (request, reply) => {
        const key = resolveKey(request, reply)
        if (key === null) return
        const outcome = settleLeaderboardSeasonSync(key, "admin-manual")
        return reply.status(outcome.ok ? 200 : 409).send(outcome)
    })

    fastify.post("/:key/rollover", async (request, reply) => {
        const key = resolveKey(request, reply)
        if (key === null) return
        const outcome = rolloverLeaderboardSeasonSync(key, "admin-rollover")
        return reply.status(outcome.ok ? 200 : 409).send(outcome.ok ? outcome : {
            ...outcome,
            error: "当前赛季尚未结算，不能换季。",
        })
    })
}

export default routes
