import { getPlayerClientExpTime } from "../../lib/player-time-compat"
import { randomInt } from "crypto"
import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify"
import { resolvePlayerIdSync } from "../../data/activeAccount"
import {
    getPlayerMultiSpecialExchangeCampaignsSync,
    updatePlayerMultiSpecialExchangeCampaignSync,
} from "../../data/domains/campaign"
import { getPlayerItemSync, givePlayerItemSync, setPlayerItemSync } from "../../data/domains/item"
import { getPlayerSync } from "../../data/domains/player"
import { getSession } from "../../data/domains/session"
import { reconcileAwakeUnlockCharacterList } from "../../lib/mission"
import { reconcileActiveMissionFacts } from "../../lib/mission/active-reconciliation"
import { getContentSnapshot } from "../../content/runtime/content-snapshot"
import { givePlayerCharacterSync } from "../../lib/character"
import {
    getMultiSpecialExchangeCampaignDefinition,
    isMultiSpecialExchangeCharacter,
    resolveMultiSpecialExchangeCampaign,
} from "../../lib/multi-special-exchange"
import { runPersistenceTransaction } from "../../lib/persistence-coordinator"
import { generateDataHeaders, getServerTime } from "../../utils"
import { contentDecision } from "../../lib/content-operations"

interface CampaignBody {
    viewer_id?: number
    campaign_id?: number
}

interface ExchangeCharacterBody extends CampaignBody {
    character_id?: number
    ticket_item_id?: number
}

function positiveSafeInteger(value: unknown): number | null {
    if (typeof value !== "number" && (typeof value !== "string" || !/^\d+$/.test(value))) return null
    const parsed = Number(value)
    return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
}

function requestBody(value: unknown): ExchangeCharacterBody {
    return value !== null && typeof value === "object" && !Array.isArray(value) ? value : {}
}

async function resolveViewer(body: CampaignBody): Promise<{ viewerId: number; playerId: number } | null> {
    const viewerId = positiveSafeInteger(body.viewer_id)
    if (viewerId === null) return null
    const session = await getSession(String(viewerId))
    if (!session) return null
    const playerId = resolvePlayerIdSync(session.accountId)
    return playerId === null ? null : { viewerId, playerId }
}

function sendResultCode(reply: FastifyReply, viewerId: number, resultCode: number) {
    reply.header("content-type", "application/x-msgpack")
    return reply.status(200).send({
        data_headers: generateDataHeaders({ viewer_id: viewerId, result_code: resultCode }),
        data: {},
    })
}

function reconcileFinalizedActiveMission(playerId: number, campaignId: number) {
    return campaignId === 2 ? reconcileActiveMissionFacts({
        playerId, repository: getContentSnapshot().repository, now: getServerTime() * 1000, patterns: [69],
    }) : []
}

async function drawTicket(playerId: number, campaignId: number): Promise<{ ticketItemId: number; itemAmount: number } | null> {
    const definition = getMultiSpecialExchangeCampaignDefinition(campaignId)
    if (!definition) return null
    const previous = getPlayerMultiSpecialExchangeCampaignsSync(playerId).find(value => value.campaignId === campaignId)
    const previousResolved = previous && resolveMultiSpecialExchangeCampaign(previous, id => getPlayerItemSync(playerId, id) ?? 0)
    if (previousResolved?.status !== 3 && contentDecision("multi_special_exchange_campaign", campaignId, "enter", Date.now()) === false) return null
    return runPersistenceTransaction({
        domain: "event", playerId, operation: "draw_multi_special_ticket",
    }, () => {
        const campaign = getPlayerMultiSpecialExchangeCampaignsSync(playerId)
            .find(value => value.campaignId === campaignId)
        if (!campaign) return null
        const resolved = resolveMultiSpecialExchangeCampaign(campaign, id => getPlayerItemSync(playerId, id) ?? 0)
        if (resolved?.status === 3) {
            if (campaign.status !== 3 || campaign.ticketItemId !== resolved.ticketItemId) {
                updatePlayerMultiSpecialExchangeCampaignSync(playerId, resolved)
            }
            const ticketItemId = resolved.ticketItemId!
            return { ticketItemId, itemAmount: getPlayerItemSync(playerId, ticketItemId) ?? 0 }
        }
        if (contentDecision("multi_special_exchange_campaign", campaignId, "enter", Date.now()) === false) return null
        const undecidedLegacy = campaign.status === 2 && campaign.ticketItemId == null
            && definition.ticketItemIds.every(id => (getPlayerItemSync(playerId, id) ?? 0) === 0)
        if (campaign.status !== 1 && resolved?.status !== 2 && !undecidedLegacy) return null
        const ticketItemId = resolved?.status === 2 && resolved.ticketItemId != null ? resolved.ticketItemId
            : definition.ticketItemIds[randomInt(definition.ticketItemIds.length)]
        const itemAmount = givePlayerItemSync(playerId, ticketItemId, 1)
        updatePlayerMultiSpecialExchangeCampaignSync(playerId, {
            campaignId,
            status: 3,
            ticketItemId,
        })
        return { ticketItemId, itemAmount }
    })
}

const routes = async (fastify: FastifyInstance) => {
    const registerDrawRoute = (path: string) => {
        fastify.post(path, async (request: FastifyRequest, reply: FastifyReply) => {
            const body = requestBody(request.body)
            const context = await resolveViewer(body)
            const campaignId = positiveSafeInteger(body.campaign_id)
            if (!context || campaignId === null) return sendResultCode(reply, context?.viewerId ?? 0, 4901)
            const definition = getMultiSpecialExchangeCampaignDefinition(campaignId)
            if (!definition) return sendResultCode(reply, context.viewerId, 4901)
            const drawn = await drawTicket(context.playerId, campaignId)
            if (!drawn) return sendResultCode(reply, context.viewerId, 4902)
            reply.header("content-type", "application/x-msgpack")
            return reply.status(200).send({
                data_headers: generateDataHeaders({ viewer_id: context.viewerId }),
                data: {
                    multi_special_exchange_campaign_list: [{
                        campaign_id: campaignId,
                        status: 3,
                        ticket_item_id: drawn.ticketItemId,
                    }],
                    item_list: { [drawn.ticketItemId]: drawn.itemAmount },
                    mail_arrived: false,
                },
            })
        })
    }

    registerDrawRoute("/single_draw_ticket")
    registerDrawRoute("/multi_draw_ticket")

    fastify.post("/exchange_character", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = requestBody(request.body)
        const context = await resolveViewer(body)
        const campaignId = positiveSafeInteger(body.campaign_id)
        const characterId = positiveSafeInteger(body.character_id)
        const ticketItemId = positiveSafeInteger(body.ticket_item_id)
        if (!context || campaignId === null || characterId === null || ticketItemId === null) {
            return sendResultCode(reply, context?.viewerId ?? 0, 4901)
        }
        const definition = getMultiSpecialExchangeCampaignDefinition(campaignId)
        if (!definition || !definition.ticketItemIds.includes(ticketItemId)) {
            return sendResultCode(reply, context.viewerId, 4901)
        }
        // Only characters listed for this ticket in the client master table
        // can be selected; other ids are rejected like any failed exchange.
        if (!isMultiSpecialExchangeCharacter(ticketItemId, characterId)) {
            return sendResultCode(reply, context.viewerId, 4902)
        }

        const previous = getPlayerMultiSpecialExchangeCampaignsSync(context.playerId).find(value => value.campaignId === campaignId)
        if (previous?.status !== 4 && contentDecision("multi_special_exchange_campaign", campaignId, "exchange", Date.now()) === false) {
            return sendResultCode(reply, context.viewerId, 4902)
        }

        const exchangeResult = await runPersistenceTransaction({
            domain: "event", playerId: context.playerId, operation: "exchange_character",
        }, () => {
            const campaign = getPlayerMultiSpecialExchangeCampaignsSync(context.playerId)
                .find(value => value.campaignId === campaignId)
            const ticketAmount = getPlayerItemSync(context.playerId, ticketItemId) ?? 0
            if (campaign?.status === 4) {
                // The archive contains completion, but no choice receipt.
                // Replay completion only, never invent or issue another reward.
                return { reward: null, newTicketAmount: ticketAmount,
                    activeMissions: reconcileFinalizedActiveMission(context.playerId, campaignId) }
            }
            if (contentDecision("multi_special_exchange_campaign", campaignId, "exchange", Date.now()) === false) return null
            const resolved = campaign && resolveMultiSpecialExchangeCampaign(campaign,
                id => getPlayerItemSync(context.playerId, id) ?? 0)
            if (!resolved || resolved.status !== 3 || resolved.ticketItemId !== ticketItemId || ticketAmount <= 0) {
                return null
            }
            const reward = givePlayerCharacterSync(context.playerId, characterId)
            if (!reward) return null
            const newTicketAmount = ticketAmount - 1
            setPlayerItemSync(context.playerId, ticketItemId, newTicketAmount)
            updatePlayerMultiSpecialExchangeCampaignSync(context.playerId, {
                campaignId,
                status: 4,
                ticketItemId: null,
            })
            return { reward, newTicketAmount,
                activeMissions: reconcileFinalizedActiveMission(context.playerId, campaignId) }
        })
        if (!exchangeResult) return sendResultCode(reply, context.viewerId, 4902)

        const characterList = exchangeResult.reward?.character
            ? reconcileAwakeUnlockCharacterList(context.playerId, [
                { ...exchangeResult.reward.character, viewer_id: context.viewerId },
            ])
            : []
        const itemList: Record<string, number> = {
            [ticketItemId]: exchangeResult.newTicketAmount,
        }
        if (exchangeResult.reward?.item) {
            itemList[String(exchangeResult.reward.item.id)] =
                exchangeResult.reward.item.inventoryCount
        }
        const player = getPlayerSync(context.playerId)
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: context.viewerId }),
            data: {
                multi_special_exchange_campaign_list: [{ campaign_id: campaignId, status: 4 }],
                character_list: characterList,
                active_mission_list: exchangeResult.activeMissions,
                item_list: itemList,
                user_info: player ? {
                    free_mana: player.freeMana,
                    exp_pool: player.expPool,
                    exp_pooled_time: getPlayerClientExpTime(player),
                    free_vmoney: player.freeVmoney,
                } : undefined,
                encyclopedia_info: {},
                mission_info: [],
                mail_arrived: false,
            },
        })
    })
}

export default routes
