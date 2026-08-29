import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { MailType, RawPlayerMail, getPlayerMailCountSync, getPlayerMailsSync, getUnreceivedPlayerMailsByIdsSync, insertReceiveHistorySync, receiveAllMailsSync } from "../../data/domains/mail"
import { getPlayerCharacterSync, insertDefaultPlayerCharacterSync, updatePlayerCharacterSync } from "../../data/domains/character"
import { getPlayerItemSync, givePlayerItemSync } from "../../data/domains/item"
import { adjustPlayerExpPoolSync, getPlayerSync, updatePlayerSync } from "../../data/domains/player"
import { getSession } from "../../data/domains/session"
import { insertPlayerEquipmentSync } from "../../data/domains/equipment"
import { resolvePlayerIdSync } from "../../data/activeAccount";
import { generateDataHeaders, getServerTime } from "../../utils";
import { clientSerializeDate } from "../../data/utils";
import { givePlayerEquipmentSync } from "../../lib/equipment";
import { serializeRealTimeForVirtualClient } from "../../lib/client-display-time";
import { grantPlayerDegreeSync } from "../../data/domains/degree";
import { reconcileAwakeUnlockCharacterList } from "../../lib/mission";
import { calculateFreeManaGrant } from "../../lib/mana";
import { runImmediateTransactionWithRetry, withPlayerWriteQueue } from "../../lib/sqlite-write-coordinator";
import type { Player } from "../../data/types";

interface IndexBody {
    api_count: number
    viewer_id: number
    current_page: number
}

interface ReceiveBody {
    api_count: number
    viewer_id: number
    mail_id: number
}

interface ReceiveAllBody {
    api_count: number
    viewer_id: number
    mail_ids: number[]
}

const MAX_MAIL_CLAIM_IDS = 1000

function formatMailResponse(mail: RawPlayerMail) {
    return {
        id: mail.id,
        reason_id: mail.reason_id,
        subject: mail.subject,
        description: mail.description,
        type: mail.type,
        type_id: mail.type_id != null && mail.type_id > 2147483647 ? 0 : mail.type_id,
        number: mail.number,
        receive_time: serializeRealTimeForVirtualClient(mail.receive_time),
        create_time: serializeRealTimeForVirtualClient(mail.create_time),
        reward_period_limited: mail.reward_period_limited === 1,
        reward_limit_time: serializeRealTimeForVirtualClient(mail.reward_limit_time),
    }
}

interface MailRewardResult {
    characterList: any[]
    equipmentList: any[]
    itemList: Record<string, number>
    userInfo: Record<string, any>
    degreeIds: number[]
}

export interface ClaimedMailRewards extends MailRewardResult {
    claimedMailIds: number[]
    alreadyCount: number
}

function applyMailReward(playerId: number, player: Player, mail: RawPlayerMail): MailRewardResult {
    const characterList: any[] = []
    const equipmentList: any[] = []
    const itemList: Record<string, number> = {}
    const userInfo: Record<string, any> = {}
    const degreeIds: number[] = []

    switch (mail.type) {
        case MailType.ITEM: {
            if (mail.type_id === null) break
            const newAmount = givePlayerItemSync(playerId, mail.type_id, mail.number)
            itemList[String(mail.type_id)] = newAmount
            break
        }
        case MailType.PAID_VMONEY: {
            const newVmoney = player.vmoney + mail.number
            updatePlayerSync({ id: playerId, vmoney: newVmoney })
            player.vmoney = newVmoney
            userInfo['vmoney'] = newVmoney
            break
        }
        case MailType.FREE_VMONEY: {
            const newFreeVmoney = player.freeVmoney + mail.number
            updatePlayerSync({ id: playerId, freeVmoney: newFreeVmoney })
            player.freeVmoney = newFreeVmoney
            userInfo['free_vmoney'] = newFreeVmoney
            break
        }
        case MailType.CHARACTER: {
            if (mail.type_id === null) break
            const existing = getPlayerCharacterSync(playerId, mail.type_id)
            if (existing) {
                updatePlayerCharacterSync(playerId, mail.type_id, {
                    entryCount: existing.entryCount + 1
                })
            } else {
                insertDefaultPlayerCharacterSync(playerId, mail.type_id)
            }
            const charData = getPlayerCharacterSync(playerId, mail.type_id)!
            characterList.push({
                character_id: mail.type_id,
                entry_count: charData.entryCount,
                evolution_level: charData.evolutionLevel,
                over_limit_step: charData.overLimitStep,
                protection: charData.protection,
                exp: charData.exp,
                stack: charData.stack,
                bond_token_list: charData.bondTokenList?.map(bt => ({
                    mana_board_index: bt.manaBoardIndex,
                    status: bt.status
                })) ?? [],
                join_time: clientSerializeDate(charData.joinTime),
                update_time: clientSerializeDate(charData.updateTime)
            })
            break
        }
        case MailType.EQUIPMENT: {
            if (mail.type_id === null) break
            const result = givePlayerEquipmentSync(playerId, mail.type_id, mail.number)
            equipmentList.push(result)
            break
        }
        case MailType.STAR_CRUMB: {
            const newCrumb = player.starCrumb + mail.number
            updatePlayerSync({ id: playerId, starCrumb: newCrumb })
            player.starCrumb = newCrumb
            userInfo['star_crumb'] = newCrumb
            break
        }
        case MailType.FREE_MANA: {
            const manaGrant = calculateFreeManaGrant(player, mail.number)
            const totalManaObtained = (player.totalManaObtained ?? 0) + mail.number
            updatePlayerSync({ id: playerId, freeMana: manaGrant.freeMana, totalManaObtained })
            player.freeMana = manaGrant.freeMana
            player.totalManaObtained = totalManaObtained
            userInfo['free_mana'] = manaGrant.freeMana
            break
        }
        case MailType.EXP_POOL: {
            const newExp = adjustPlayerExpPoolSync(playerId, mail.number, 'mail_reward')
            if (newExp === null) throw new Error(`Failed to grant EXP mail ${mail.id} to player ${playerId}`)
            player.expPool = newExp
            userInfo['exp_pool'] = newExp
            break
        }
        case MailType.BOND_TOKEN: {
            const newBond = player.bondToken + mail.number
            updatePlayerSync({ id: playerId, bondToken: newBond })
            player.bondToken = newBond
            userInfo['bond_token'] = newBond
            break
        }
        case MailType.BOSS_BOOST_POINT: {
            const newBoss = player.bossBoostPoint + mail.number
            updatePlayerSync({ id: playerId, bossBoostPoint: newBoss })
            player.bossBoostPoint = newBoss
            userInfo['boss_boost_point'] = newBoss
            break
        }
        case MailType.BOOST_POINT: {
            const newBoost = player.boostPoint + mail.number
            updatePlayerSync({ id: playerId, boostPoint: newBoost })
            player.boostPoint = newBoost
            userInfo['boost_point'] = newBoost
            break
        }
        case MailType.DEGREE: {
            if (mail.type_id === null) break
            if (grantPlayerDegreeSync(playerId, mail.type_id)) {
                degreeIds.push(mail.type_id)
            }
            break
        }
        case MailType.RANK_POINT: {
            const newRank = player.rankPoint + mail.number
            updatePlayerSync({ id: playerId, rankPoint: newRank })
            player.rankPoint = newRank
            userInfo['rank_point'] = newRank
            break
        }
    }

    insertReceiveHistorySync(playerId, { type: mail.type, type_id: mail.type_id, number: mail.number })

    return { characterList, equipmentList, itemList, userInfo, degreeIds }
}

/**
 * Claims the exact requested mails and applies all rewards in one short write transaction.
 * The per-player queue prevents duplicate grants between concurrent requests in this process;
 * BEGIN IMMEDIATE also protects the read/mark/reward sequence from other writers.
 */
export async function claimPlayerMailRewards(
    playerId: number,
    requestedMailIds: readonly number[],
): Promise<ClaimedMailRewards> {
    if (requestedMailIds.length > MAX_MAIL_CLAIM_IDS) {
        throw new RangeError(`A mail claim may contain at most ${MAX_MAIL_CLAIM_IDS} IDs.`)
    }
    return withPlayerWriteQueue(playerId, async () => runImmediateTransactionWithRetry(() => {
        const uniqueMailIds = [...new Set(requestedMailIds.filter(
            mailId => Number.isSafeInteger(mailId) && mailId > 0,
        ))]
        const mails = getUnreceivedPlayerMailsByIdsSync(playerId, uniqueMailIds)
        const mailById = new Map(mails.map(mail => [mail.id, mail]))
        const player = getPlayerSync(playerId)
        if (!player) throw new Error(`Player ${playerId} does not exist.`)

        // Mark first inside the transaction. Any reward failure rolls this update back.
        const claimedMailIds = receiveAllMailsSync(
            playerId,
            uniqueMailIds.filter(mailId => mailById.has(mailId)),
        )
        const characterList: any[] = []
        const equipmentList: any[] = []
        const itemList: Record<string, number> = {}
        const userInfo: Record<string, any> = {}
        const degreeIds = new Set<number>()

        for (const mailId of claimedMailIds) {
            const mail = mailById.get(mailId)
            if (!mail) continue
            const reward = applyMailReward(playerId, player, mail)
            characterList.push(...reward.characterList)
            equipmentList.push(...reward.equipmentList)
            Object.assign(itemList, reward.itemList)
            Object.assign(userInfo, reward.userInfo)
            for (const degreeId of reward.degreeIds) degreeIds.add(degreeId)
        }

        return {
            claimedMailIds,
            alreadyCount: requestedMailIds.length - claimedMailIds.length,
            characterList,
            equipmentList,
            itemList,
            userInfo,
            degreeIds: [...degreeIds],
        }
    }))
}

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/index", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as IndexBody
        const viewerId = body.viewer_id
        if (!viewerId || isNaN(viewerId)) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid viewer_id"
        })

        const session = await getSession(viewerId.toString())
        if (!session) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid viewer_id"
        })

        const playerId = resolvePlayerIdSync(session.accountId)!
        if (playerId === null) return reply.status(400).send({
            error: "Bad Request",
            message: "No player bound to account"
        })

        const page = body.current_page || 1
        const mails = getPlayerMailsSync(playerId, page, 100)
        const totalCount = getPlayerMailCountSync(playerId)

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: viewerId }),
            data: {
                mail: mails.map(formatMailResponse),
                total_count: totalCount,
            }
        })
    })

    fastify.post("/receive", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as ReceiveBody
        const viewerId = body.viewer_id
        const mailId = body.mail_id
        if (!viewerId || isNaN(viewerId) || !mailId || isNaN(mailId)) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid request body"
        })

        const session = await getSession(viewerId.toString())
        if (!session) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid viewer_id"
        })

        const playerId = resolvePlayerIdSync(session.accountId)!
        if (playerId === null) return reply.status(400).send({
            error: "Bad Request",
            message: "No player bound to account"
        })

        const claim = await claimPlayerMailRewards(playerId, [mailId])
        if (claim.claimedMailIds.length === 0) return reply.status(400).send({
            error: "Bad Request",
            message: "Mail not found or already received"
        })

        const { characterList, equipmentList, itemList, userInfo, degreeIds } = claim
        const reconciledCharacterList = reconcileAwakeUnlockCharacterList(playerId, characterList)

        const totalCount = getPlayerMailCountSync(playerId)

        const responseData: Record<string, any> = {
            auto_sale_expired_mail: false,
            dispose_expired_mail: false,
            total_count: totalCount,
            mail_arrived: getPlayerMailCountSync(playerId, true) > 0,
        }

        if (reconciledCharacterList.length > 0) responseData.character_list = reconciledCharacterList
        if (equipmentList.length > 0) responseData.equipment_list = equipmentList
        if (Object.keys(itemList).length > 0) responseData.item_list = itemList
        if (Object.keys(userInfo).length > 0) responseData.user_info = userInfo
        if (degreeIds.length > 0) {
            responseData.degree_list = degreeIds.map(degreeId => ({
                viewer_id: viewerId,
                degree_id: degreeId,
            }))
        }

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: viewerId }),
            data: responseData
        })
    })

    fastify.post("/receive_all", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as ReceiveAllBody
        const viewerId = body.viewer_id
        const mailIds = body.mail_ids
        if (!viewerId || isNaN(viewerId) || !mailIds || !Array.isArray(mailIds) || mailIds.length > MAX_MAIL_CLAIM_IDS) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid request body"
        })

        const session = await getSession(viewerId.toString())
        if (!session) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid viewer_id"
        })

        const playerId = resolvePlayerIdSync(session.accountId)!
        if (playerId === null) return reply.status(400).send({
            error: "Bad Request",
            message: "No player bound to account"
        })

        const claim = await claimPlayerMailRewards(playerId, mailIds)
        const {
            alreadyCount,
            characterList,
            equipmentList,
            itemList,
            userInfo,
            degreeIds,
            claimedMailIds: claimed,
        } = claim
        const reconciledCharacterList = reconcileAwakeUnlockCharacterList(playerId, characterList)

        const responseData: Record<string, any> = {
            already_mail_count: alreadyCount,
            auto_sale_expired_mail_count: 0,
            deleted_mail_count: 0,
            dispose_expired_mail_count: 0,
            ex_boost_item_list: [],
            mail_ids: claimed,
            max_overed_mail_count: 0,
            outdated_mail_count: 0,
            total_count: getPlayerMailCountSync(playerId),
            mail_arrived: getPlayerMailCountSync(playerId, true) > 0,
        }

        if (reconciledCharacterList.length > 0) responseData.character_list = reconciledCharacterList
        if (equipmentList.length > 0) responseData.equipment_list = equipmentList
        if (Object.keys(itemList).length > 0) responseData.item_list = itemList
        if (Object.keys(userInfo).length > 0) responseData.user_info = userInfo
        if (degreeIds.length > 0) {
            responseData.degree_list = degreeIds.map(degreeId => ({
                viewer_id: viewerId,
                degree_id: degreeId,
            }))
        }

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: viewerId }),
            data: responseData
        })
    })
}

export default routes
