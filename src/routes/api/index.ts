import { recordContentActionFactsSync } from "../../lib/mission/content-action-facts";
import { getPlayerBusinessDateSync } from "../../lib/player-time-compat"
import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { SessionType } from "../../data/types";
import { getClientSerializedData, serializePlayerData } from "../../data/utils";
import { collectPlayerDataPooledExpSync, collectPlayerPooledExpSync, dailyResetPlayerDataSync, getPlayerDailyChallengePointListSync, getPlayerSync, updatePlayerSync } from "../../data/domains/player"
import { getPlayerActiveMissionsSync, getPlayerClearedRegularMissionListSync } from "../../data/domains/mission"
import { getPlayerBoxGachasSync } from "../../data/domains/boxGacha"
import { getPlayerCharactersManaNodesSync, getPlayerCharactersSync } from "../../data/domains/character"
import { getPlayerDrawnQuestsSync, getPlayerQuestProgressSync } from "../../data/domains/quest"
import { getPlayerEquipmentListSync } from "../../data/domains/equipment"
import { getPlayerGachaInfoListSync } from "../../data/domains/gacha"
import { getPlayerItemsSync } from "../../data/domains/item"
import { getPlayerMultiSpecialExchangeCampaignsSync, getPlayerPeriodicRewardPointsSync, getPlayerStartDashExchangeCampaignsSync } from "../../data/domains/campaign"
import { getPlayerOptionsSync } from "../../data/domains/option"
import { getPlayerPartyGroupListSync } from "../../data/domains/party"
import { getPlayerTriggeredTutorialsSync } from "../../data/domains/tutorial"
import { getSession } from "../../data/domains/session"
import { resolvePlayerIdSync } from "../../data/activeAccount";
import { generateDataHeaders, getServerDate, getRealServerDate, getTimeOffset, withServerClock } from "../../utils";
import { ensureDailyVmoneyMailForPlayerSync } from "../../lib/daily-vmoney-mail";
import { runPermanentValidators } from "../../lib/validate";
import { runPersistenceTransaction } from "../../lib/persistence-coordinator";
import { ensurePlayerClockStateForLoadSync } from "../../lib/server-clock-state";
import { getDb } from "../../data/db";

import { contentOperations } from "../../lib/content-operations";
import { contentClientReload } from "../../lib/content-client-reload";

interface LoadBody {
    app_secret: string,
    graphics_device_name: string,
    device_id: number,
    access_token: string,
    storage_directory_path: string,
    app_admin: string,
    kakao_pid: string,
    keychain: number,
    viewer_id: number,
    platform_os_version: string
}

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/load", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as LoadBody

        const zat = body.access_token
        let viewerId = body.viewer_id
        if (!zat || !viewerId || isNaN(viewerId)) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid request body."
        })

        const session = await getSession(zat)
        if (session === null || session.type !== SessionType.ZAT) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid zat provided."
        })

        const viewerSession = await getSession(String(viewerId))
        if (viewerSession === null || viewerSession.type !== SessionType.VIEWER) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid viewer ID provided."
        })

        const accountId = session.accountId
        if (viewerSession.accountId !== accountId) return reply.status(400).send({
            error: "Bad Request", message: "Viewer ID does not belong to the authenticated account.",
        })

        const playerId = resolvePlayerIdSync(accountId)!
        if (playerId === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No players bound to account."
        })

        const player = getPlayerSync(playerId)
        if (player === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No player data."
        })

        const loadedReloadEpoch = contentClientReload().state().epoch
        const clock = await runPersistenceTransaction({
            domain: "player", playerId, operation: "legacy_load_snapshot",
        }, () => {
            ensurePlayerClockStateForLoadSync(playerId, getDb())
            const now = getServerDate()
            const current = getPlayerSync(playerId)
            if (!current) throw new Error("Player disappeared during load maintenance.")
            ensureDailyVmoneyMailForPlayerSync(playerId, getRealServerDate().getTime())
            dailyResetPlayerDataSync(current, now)
            collectPlayerDataPooledExpSync(current, now)
            updatePlayerSync({ id: playerId, lastLoginTime: getPlayerBusinessDateSync(playerId, now) })
            recordContentActionFactsSync(playerId, { kind: "login", nowMs: getRealServerDate().getTime() })
            runPermanentValidators(playerId)
            return { now, offset: getTimeOffset() ?? 0 }
        })
        const clientData = withServerClock(clock.now, () => getClientSerializedData(playerId, { viewerId }), clock.offset)
        if (clientData === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No player data."
        })

        const response = {
            "data_headers": generateDataHeaders({
                asset_update: true,
                viewer_id: viewerId
            }),
            "data": { ...clientData, content_operations: contentOperations().snapshot(Date.now()) }
        }
        await runPersistenceTransaction({ domain: "account", operation: "acknowledge_legacy_client_load" }, () => {
            contentClientReload().acknowledge(viewerId, loadedReloadEpoch)
            contentClientReload().pruneFinishedPlays(playerId)
        })
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send(response)
    })
}

export default routes;
