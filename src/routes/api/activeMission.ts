import { getPlayerClientExpTime } from "../../lib/player-time-compat"
// Active mission reward claiming endpoint
import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { getPlayerActiveMissionsSync, updatePlayerActiveMissionStageSync } from "../../data/domains/mission"
import { getPlayerSync } from "../../data/domains/player"
import { getSession } from "../../data/domains/session"
import { getDb } from "../../data/db"
import { getPlayerMailCountSync } from "../../data/domains/mail"
import { getPlayerQuestProgressSync } from "../../data/domains/quest"
import { generateDataHeaders, getServerTime } from "../../utils";
import { resolvePlayerIdSync } from "../../data/activeAccount";
import { reconcileAwakeUnlockCharacterList, validateMissionRewardClaims } from "../../lib/mission/index";
import { MissionRewardGranter } from "../../lib/mission/grants";
import { getContentSnapshot } from "../../content/runtime/content-snapshot";
import { gameVerboseLog } from "../../lib/game-logging";
import { runPersistenceTransaction } from "../../lib/persistence-coordinator";
import { ContentOperationError } from "../../lib/content-operations-store";

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/receive", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as {
            viewer_id: number,
            api_count: number,
            active_mission_list: { mission_id: number, stages: number[] }[]
        }

        const viewerId = body.viewer_id
        if (!viewerId || isNaN(viewerId)) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid request body."
        })

        const session = await getSession(viewerId.toString())
        if (!session) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid viewer id."
        })

        const playerId = resolvePlayerIdSync(session.accountId)!
        if (playerId === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No players bound to account."
        })

        const player = getPlayerSync(playerId)
        if (!player) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "Player not found."
        })

        const activeMissions = getPlayerActiveMissionsSync(playerId)
        const requestList = body.active_mission_list || []
        const validation = validateMissionRewardClaims(activeMissions, requestList, {
            repository: getContentSnapshot().repository,
            now: getServerTime() * 1000,
            questProgress: getPlayerQuestProgressSync(playerId),
        })
        if (!validation.ok) return reply.status(400).send({
            "error": "Bad Request",
            "message": validation.message
        })

        let granter: MissionRewardGranter
        const resultByMission = new Map<number, {
            mission_id: number,
            progress_value: number,
            stages: { stage: number, received: boolean }[]
        }>()

        const characterList = await runPersistenceTransaction({
            domain: "mission", playerId, operation: "claim_active_missions",
        }, () => {
            const currentPlayer = getPlayerSync(playerId)
            if (!currentPlayer) throw new ContentOperationError("Player not found.", 500)
            const currentValidation = validateMissionRewardClaims(getPlayerActiveMissionsSync(playerId), requestList, {
                repository: getContentSnapshot().repository,
                now: getServerTime() * 1000,
                questProgress: getPlayerQuestProgressSync(playerId),
            })
            if (!currentValidation.ok) throw new ContentOperationError(currentValidation.message)
            granter = new MissionRewardGranter(playerId, currentPlayer)
            for (const claim of currentValidation.claims) {
                updatePlayerActiveMissionStageSync(playerId, claim.stage, claim.missionId, true)
                let result = resultByMission.get(claim.missionId)
                if (!result) {
                    result = { mission_id: claim.missionId, progress_value: claim.progress, stages: [] }
                    resultByMission.set(claim.missionId, result)
                }
                result.stages.push({ stage: claim.stage, received: true })
                granter.grant(claim.rewards)
            }
            granter.persistPlayer()
            const existingCharacterList = granter.characterList as unknown as Record<string, unknown>[]
            return currentValidation.claims.length > 0
                ? reconcileAwakeUnlockCharacterList(playerId, existingCharacterList)
                : existingCharacterList
        })

        const resultList = [...resultByMission.values()]
        const savedGranter = granter!
        gameVerboseLog(() => `[ACTIVE_MISSION] receive viewer=${viewerId} missions=${requestList.length} items=${Object.keys(savedGranter.itemList).length}`)

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({ viewer_id: viewerId }),
            "data": {
                "active_mission_list": resultList,
                "user_info": {
                    ...savedGranter.getUserInfo(),
                    "exp_pooled_time": getPlayerClientExpTime(getPlayerSync(playerId)!)
                },
                "character_list": characterList,
                "equipment_list": savedGranter.equipmentList,
                "item_list": savedGranter.itemList,
                "degree_list": savedGranter.degreeList.map(degreeId => ({ viewer_id: viewerId, degree_id: degreeId })),
                "mail_arrived": getPlayerMailCountSync(playerId, true) > 0
            }
        })
    })
}

export default routes;
