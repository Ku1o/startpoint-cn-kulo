import type { FastifyInstance } from "fastify"
import { getSession } from "../data/domains/session"
import { resolvePlayerIdSync } from "../data/activeAccount"
import { getPlayerStartDashExchangeCampaignsSync } from "../data/domains/campaign"
import { getPlayerItemSync, setPlayerItemSync } from "../data/domains/item"
import { getPlayerSync } from "../data/domains/player"
import { givePlayerCharacterSync } from "./character"
import { givePlayerEquipmentSync } from "./equipment"
import { reconcileAwakeUnlockCharacterList } from "./mission"
import { contentDecision } from "./content-operations"
import { runPersistenceTransaction } from "./persistence-coordinator"
import { getExchangeEntitlementSync, completeExchangeEntitlementSync, getSpecialExchangeEntitlementsSync, matchesExchangeReceiptSync } from "./exchange-campaign-entitlements"
import { generateDataHeaders, getServerTime } from "../utils"
import { getPlayerClientExpTime } from "./player-time-compat"

function positive(value: unknown): number | null {
    return typeof value === "number" && Number.isSafeInteger(value) && value > 0 ? value : null
}

export function serializeExchangeCampaignsSync(playerId: number, startDash: boolean) {
    return startDash ? getPlayerStartDashExchangeCampaignsSync(playerId).map(row => ({
        campaign_id: row.campaignId, gacha_id: row.gachaId, term_index: row.termIndex, status: row.status,
        period_start_time: getServerTime(row.periodStartTime), period_end_time: getServerTime(row.periodEndTime),
    })) : getSpecialExchangeEntitlementsSync(playerId)
}

/** Exchange-only: opening operations does not manufacture a purchased qualification. */
export function exchangeCampaignRoutes(startDash: boolean) {
    const type = startDash ? "start_dash_exchange_campaign" : "special_exchange_campaign"
    const listKey = `${type}_list`
    return async (fastify: FastifyInstance) => {
        const viewer = async (body: Record<string, unknown>) => {
            const viewerId = positive(body.viewer_id)
            if (!viewerId) return null
            const session = await getSession(String(viewerId))
            const playerId = session ? resolvePlayerIdSync(session.accountId) : null
            return playerId ? { playerId, viewerId } : null
        }
        fastify.post("/get_retained_campaigns", async (request, reply) => {
            const context = await viewer((request.body ?? {}) as Record<string, unknown>)
            if (!context) return reply.status(401).send({ error: "Invalid viewer" })
            reply.header("content-type", "application/x-msgpack")
            return { data_headers: generateDataHeaders({ viewer_id: context.viewerId }), data: {
                [listKey]: serializeExchangeCampaignsSync(context.playerId, startDash),
            } }
        })
        // Buying or granting new campaign rights needs a separately reviewed acquisition policy.
        fastify.post("/buy_ticket", async (_request, reply) => reply.status(400).send({ error: "Campaign acquisition is not enabled" }))
        fastify.post("/enter_campaign", async (request, reply) => {
            const body = (request.body ?? {}) as Record<string, unknown>
            const context = await viewer(body), campaignId = positive(body.campaign_id)
            if (!context || !campaignId) return reply.status(400).send({ error: "Invalid campaign" })
            const state = getExchangeEntitlementSync(context.playerId, campaignId, startDash)
            if (!state || ![2, 3].includes(state.status)) return reply.status(400).send({ error: "No retained campaign qualification" })
            // Native special enter can grant a free ticket. This retained-rights path only reads.
            reply.header("content-type", "application/x-msgpack")
            return { data_headers: generateDataHeaders({ viewer_id: context.viewerId }), data: {
                [listKey]: serializeExchangeCampaignsSync(context.playerId, startDash).filter(row => row.campaign_id === campaignId),
            } }
        })
        for (const rewardType of startDash ? [0] : [0, 1]) {
            fastify.post(rewardType === 0 ? "/exchange_character" : "/exchange_equipment", async (request, reply) => {
                const body = (request.body ?? {}) as Record<string, unknown>
                const context = await viewer(body), campaignId = positive(body.campaign_id)
                const rewardId = positive(rewardType === 0 ? body.character_id : body.equipment_id)
                if (!context || !campaignId || !rewardId) return reply.status(400).send({ error: "Invalid exchange" })
                const result = await runPersistenceTransaction({ domain: "event", playerId: context.playerId, operation: `exchange_${type}` }, () => {
                    const state = getExchangeEntitlementSync(context.playerId, campaignId, startDash)
                    if (!state || state.rewardType !== rewardType || !state.rewardIds.includes(rewardId)) return null
                    const items: Record<string, number> = {}
                    if (state.status === 3) return matchesExchangeReceiptSync(context.playerId, campaignId, startDash, rewardType, rewardId)
                        ? { characters: [] as object[], equipment: [] as object[], items } : null
                    if (state.status !== 2 || contentDecision(type, campaignId, "exchange", Date.now()) === false) return null
                    const tickets = getPlayerItemSync(context.playerId, state.ticketItemId) ?? 0
                    if (tickets < 1) return null
                    let characters: object[] = [], equipment: object[] = []
                    if (rewardType === 0) {
                        const reward = givePlayerCharacterSync(context.playerId, rewardId)
                        if (!reward) throw new Error("Campaign reward definition unavailable")
                        if (reward.character) characters = reconcileAwakeUnlockCharacterList(context.playerId,
                            [{ ...reward.character, viewer_id: context.viewerId }])
                        if (reward.item) items[String(reward.item.id)] = reward.item.inventoryCount
                    } else equipment = [givePlayerEquipmentSync(context.playerId, rewardId, 1)]
                    setPlayerItemSync(context.playerId, state.ticketItemId, tickets - 1)
                    items[String(state.ticketItemId)] = tickets - 1
                    completeExchangeEntitlementSync(context.playerId, campaignId, startDash, rewardType, rewardId)
                    return { characters, equipment, items }
                })
                if (!result) return reply.status(400).send({ error: "Campaign exchange unavailable or not qualified" })
                const player = getPlayerSync(context.playerId)
                reply.header("content-type", "application/x-msgpack")
                return { data_headers: generateDataHeaders({ viewer_id: context.viewerId }), data: {
                    [listKey]: serializeExchangeCampaignsSync(context.playerId, startDash).filter(row => row.campaign_id === campaignId),
                    character_list: result.characters, equipment_list: result.equipment, item_list: result.items,
                    user_info: player ? { free_mana: player.freeMana, exp_pool: player.expPool,
                        exp_pooled_time: getPlayerClientExpTime(player), free_vmoney: player.freeVmoney } : undefined,
                    encyclopedia_info: {}, mission_info: [], mail_arrived: false,
                } }
            })
        }
    }
}
