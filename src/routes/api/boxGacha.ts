// Handles the insertion of mana into characters.

import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { getAccountPlayers } from "../../data/domains/account"
import { getPlayerBoxGachaDrawnRewardsSync, getPlayerBoxGachaSync, insertPlayerBoxGachaDrawnRewardSync, insertPlayerBoxGachaSync, resetPlayerBoxGachaSync, updatePlayerBoxGachaDrawnRewardSync, updatePlayerBoxGachaSync } from "../../data/domains/boxGacha"
import { getPlayerItemSync, updatePlayerItemSync } from "../../data/domains/item"
import { getPlayerSync } from "../../data/domains/player"
import { getSession } from "../../data/domains/session"
import { playerOwnsEquipmentSync, updatePlayerEquipmentSync } from "../../data/domains/equipment"
import { updatePlayerPartyGroupSync } from "../../data/domains/party"
import { resolvePlayerIdSync } from "../../data/activeAccount";
import { generateDataHeaders, getServerTime } from "../../utils";
import { getBoxGachaSync } from "../../lib/assets";
import { drawBoxGachaSync, rewardPlayerBoxGachaResultSync } from "../../lib/gacha";
import { reconcileAwakeUnlockCharacterList } from "../../lib/mission";
import { BoxGachaBox, BoxGachaBoxes } from "../../lib/types";
import { PlayerBoxGacha, PlayerBoxGachaDrawnReward } from "../../data/types";
import { runPersistenceTransaction } from "../../lib/persistence-coordinator";

interface GetBoxListBody {
    box_gacha_id: number
    viewer_id: number
    api_count: number
}

interface ExecBody {
    stop_on_featured_rewards: boolean,
    box_gacha_id: number,
    box_id: number,
    api_count: number,
    viewer_id: number,
    number: number
}

interface CloseBody {
    box_gacha_id: number,
    box_id: number,
    viewer_id: number,
    api_count: number
}

interface ResetBody {
    box_gacha_id: number,
    box_id: number,
    viewer_id: number,
    api_count: number
}

/**
 * Calculates the remaining stock from the current reward master and the
 * player's per-reward draw history. This remains correct when a patch expands
 * an existing box after the player has already emptied the previous version.
 */
function getCurrentRemainingNumber(
    rewards: BoxGachaBox,
    drawnRewards: PlayerBoxGachaDrawnReward[]
): number {
    const drawnMap = new Map(drawnRewards.map(reward => [reward.id, reward.number]))
    return Object.entries(rewards).reduce((remaining, [rewardId, reward]) => {
        return remaining + Math.max(0, reward.available - (drawnMap.get(Number(rewardId)) ?? 0))
    }, 0)
}

/**
 * Legacy players can have remaining_number=0/is_closed=true for a box that was
 * empty before its master-data stock was increased. Reopen only the newly
 * added difference; boxes closed early retain a positive stored remainder and
 * are deliberately left closed.
 */
function reconcileExpandedEmptyBox(
    playerId: number,
    boxGachaId: number,
    boxId: number,
    rewards: BoxGachaBox,
    drawnRewards: PlayerBoxGachaDrawnReward[],
    playerBoxData: PlayerBoxGacha | null
): PlayerBoxGacha | null {
    if (playerBoxData === null || playerBoxData.remainingNumber !== 0) return playerBoxData

    const currentRemainingNumber = getCurrentRemainingNumber(rewards, drawnRewards)
    if (currentRemainingNumber <= 0) return playerBoxData

    updatePlayerBoxGachaSync(playerId, boxGachaId, {
        boxId,
        remainingNumber: currentRemainingNumber,
        isClosed: false
    })
    console.log(
        `[BOX] reopened expanded empty box: player=${playerId} gacha=${boxGachaId} box=${boxId} added=${currentRemainingNumber}`
    )
    return {
        ...playerBoxData,
        remainingNumber: currentRemainingNumber,
        isClosed: false
    }
}

/**
 * Returns all of a box gacha's box statuses serialized for the client.
 * 
 * @param playerId The ID of the player.
 * @param boxGachaId The ID of the box gacha.
 * @param boxes A record of boxes to get the data of.
 * @param skipBoxId The ID of the box id to skip.
 */
function getAllBoxList(
    playerId: number,
    boxGachaId: number,
    boxes: BoxGachaBoxes,
    skipBoxId?: number
): Object[] {
    const boxInfo: Object[] = []
    for (const [boxId, rewards] of Object.entries(boxes)) {
        // get drawn rewards
        const parsedBoxId = Number(boxId)
        if (parsedBoxId !== skipBoxId) {
            const playerDrawnRewards = getPlayerBoxGachaDrawnRewardsSync(playerId, boxGachaId, parsedBoxId)
            const playerBoxData = reconcileExpandedEmptyBox(
                playerId,
                boxGachaId,
                parsedBoxId,
                rewards,
                playerDrawnRewards,
                getPlayerBoxGachaSync(playerId, boxGachaId, parsedBoxId)
            )

            boxInfo.push({
                "box_id": parsedBoxId,
                "reset_times": playerBoxData?.resetTimes ?? 0,
                "all_drawn_reward_list": playerDrawnRewards.map(reward => {
                    return {
                        "reward_id": reward.id,
                        "number": reward.number
                    }
                }),
                "coming_next_reward_list": [],
                "is_closed": playerBoxData?.isClosed ?? false
            })
        }
    }
    return boxInfo
}

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/reset", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as ResetBody

        const viewerId = Number(body.viewer_id)
        const boxGachaId = Number(body.box_gacha_id)
        const boxId = Number(body.box_id)
        console.log(`[BOX] reset: boxGachaId=${boxGachaId} boxId=${boxId}`)

        if (!Number.isFinite(viewerId) || !Number.isFinite(boxGachaId) || !Number.isFinite(boxId)) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid request body."
        })

        const viewerIdSession = await getSession(viewerId.toString())
        if (!viewerIdSession) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid viewer id."
        })

        const playerId = resolvePlayerIdSync(viewerIdSession.accountId)
        if (playerId === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No players bound to account."
        })

        const boxGachaData = getBoxGachaSync(boxGachaId)
        const boxRewards = boxGachaData?.boxes[boxId]
        const availableCount = boxGachaData?.availableCounts[boxId]
        if (boxGachaData === null || boxRewards === undefined || availableCount === undefined) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid box gacha or box id."
        })

        const resetResult = await runPersistenceTransaction({
            domain: "gacha", playerId, operation: "box_reset",
        }, () => {
            const playerDrawnRewards = getPlayerBoxGachaDrawnRewardsSync(playerId, boxGachaId, boxId)
            const playerBoxData = reconcileExpandedEmptyBox(
                playerId,
                boxGachaId,
                boxId,
                boxRewards,
                playerDrawnRewards,
                getPlayerBoxGachaSync(playerId, boxGachaId, boxId)
            )
            if (playerBoxData === null) return { allBoxInfo: null, errorMessage: "Box doesn't exist." }
            if (!playerBoxData.isClosed && playerBoxData.remainingNumber > 0) {
                return { allBoxInfo: null, errorMessage: "Box still has remaining rewards." }
            }
            if (!resetPlayerBoxGachaSync(playerId, boxGachaId, boxId, availableCount)) {
                return { allBoxInfo: null, errorMessage: "Failed to reset box." }
            }
            return { allBoxInfo: getAllBoxList(playerId, boxGachaId, boxGachaData.boxes) }
        })
        if (resetResult.allBoxInfo === null) return reply.status(
            resetResult.errorMessage === "Failed to reset box." ? 500 : 400
        ).send({
            "error": resetResult.errorMessage === "Failed to reset box." ? "Internal Server Error" : "Bad Request",
            "message": resetResult.errorMessage,
        })

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: viewerId
            }),
            "data": {
                "all_box_info": resetResult.allBoxInfo
            }
        })
    })

    fastify.post("/close", async (request: FastifyRequest, reply: FastifyReply) => {

        const body = request.body as CloseBody

        const viewerId = body.viewer_id
        const boxGachaId = body.box_gacha_id
        const boxId = body.box_id
        if (isNaN(viewerId) || isNaN(boxGachaId) || isNaN(boxId)) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid request body."
        })

        const viewerIdSession = await getSession(viewerId.toString())
        if (!viewerIdSession) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid viewer id."
        })

        // get player
        const playerId = resolvePlayerIdSync(viewerIdSession.accountId)!

        if (playerId === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No players bound to account."
        })

        // get box asset data.
        const boxGachaData = getBoxGachaSync(boxGachaId)
        if (boxGachaData === null) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid box gacha id."
        })

        const closeResult = await runPersistenceTransaction({
            domain: "gacha", playerId, operation: "box_close",
        }, () => {
            const playerBoxData = getPlayerBoxGachaSync(playerId, boxGachaId, boxId)
            if (playerBoxData === null) return { allBoxInfo: null, errorMessage: "Box doesn't exist" }
            if (playerBoxData.isClosed) return { allBoxInfo: null, errorMessage: "Box is already closed." }
            updatePlayerBoxGachaSync(playerId, boxGachaId, { boxId, isClosed: true })
            return { allBoxInfo: getAllBoxList(playerId, boxGachaId, boxGachaData.boxes) }
        })
        if (closeResult.allBoxInfo === null) return reply.status(400).send({
            "error": "Bad Request",
            "message": closeResult.errorMessage,
        })

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: viewerId
            }),
            "data": {
                "all_box_info": closeResult.allBoxInfo
            }
        })
    })

    fastify.post("/exec", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as ExecBody

        const viewerId = body.viewer_id
        const boxGachaId = body.box_gacha_id
        const boxId = body.box_id
        const pullCount = body.number
        const stopOnFeaturedRewards = body.stop_on_featured_rewards
        console.log(`[BOX] exec: boxGachaId=${boxGachaId} boxId=${boxId} pullCount=${pullCount}`)
        if (isNaN(viewerId) || isNaN(boxGachaId) || isNaN(boxId) || isNaN(pullCount) || stopOnFeaturedRewards === undefined) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid request body."
        })

        const viewerIdSession = await getSession(viewerId.toString())
        if (!viewerIdSession) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid viewer id."
        })

        // get player
        const playerId = resolvePlayerIdSync(viewerIdSession.accountId)!
        const player = playerId !== null ? getPlayerSync(playerId) : null

        if (player === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No players bound to account."
        })

        // get box gacha data
        const boxGachaData = getBoxGachaSync(boxGachaId)
        if (boxGachaData === null) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid box gacha id."
        })

        // make sure the player has enough currency
        const pullCurrencyId = boxGachaData.redeemItemId
        const playerPullCurrency = getPlayerItemSync(playerId, pullCurrencyId)
        if (playerPullCurrency === null) return reply.status(400).send({
            "error": "Bad Request",
            "message": "No pull currency."
        })
        const maximumPullCost = Math.abs(pullCount) * boxGachaData.redeemItemCount
        if (playerPullCurrency < maximumPullCost) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Not enough pull currency."
        })

        // get the current box
        const boxRewards = boxGachaData.boxes[boxId]
        if (boxRewards === undefined) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid box ID."
        })

        const playerDrawnRewards = getPlayerBoxGachaDrawnRewardsSync(playerId, boxGachaId, boxId)
        const playerBoxData = reconcileExpandedEmptyBox(
            playerId,
            boxGachaId,
            boxId,
            boxRewards,
            playerDrawnRewards,
            getPlayerBoxGachaSync(playerId, boxGachaId, boxId)
        )
        if (playerBoxData !== null && playerBoxData.isClosed) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Box is closed."
        })

        const settlement = await runPersistenceTransaction({
            domain: "gacha", playerId, operation: "box_exec",
        }, () => {
            const currentDrawnRewards = getPlayerBoxGachaDrawnRewardsSync(playerId, boxGachaId, boxId)
            const currentBoxData = reconcileExpandedEmptyBox(
                playerId, boxGachaId, boxId, boxRewards, currentDrawnRewards,
                getPlayerBoxGachaSync(playerId, boxGachaId, boxId),
            )
            if (currentBoxData?.isClosed) throw new Error("Box is closed.")
            const currentCurrency = getPlayerItemSync(playerId, pullCurrencyId)
            if (currentCurrency === null) throw new Error("No pull currency.")

            const drawResult = drawBoxGachaSync(boxRewards, currentDrawnRewards, pullCount, stopOnFeaturedRewards)
            const actualPullCost = drawResult.drawCount * boxGachaData.redeemItemCount
            const newPullCurrency = currentCurrency - actualPullCost
            if (newPullCurrency < 0) throw new Error("Not enough pull currency.")
            console.log(
                `[BOX] exec result: boxGachaId=${boxGachaId} boxId=${boxId} requested=${pullCount} actual=${drawResult.drawCount} cost=${actualPullCost} stopOnFeatured=${stopOnFeaturedRewards}`
            )

            const rewardResult = rewardPlayerBoxGachaResultSync(playerId, drawResult)
            const playerDrawnRewardMap = new Map(currentDrawnRewards.map(reward => [reward.id, reward.number]))
            const totalDrawCount = currentDrawnRewards.reduce((total, reward) => total + reward.number, 0)
                + drawResult.rewards.reduce((total, reward) => total + reward.number, 0)
            const remainingDrawsNumber = (boxGachaData.availableCounts[boxId] ?? totalDrawCount) - totalDrawCount
            const shouldClose = remainingDrawsNumber === 0
            if (currentBoxData === null) {
                insertPlayerBoxGachaSync(playerId, boxGachaId, {
                    boxId, isClosed: shouldClose, remainingNumber: remainingDrawsNumber, resetTimes: 0,
                })
            } else {
                updatePlayerBoxGachaSync(playerId, boxGachaId, {
                    boxId, isClosed: shouldClose, remainingNumber: remainingDrawsNumber,
                })
            }
            for (const drawnReward of drawResult.rewards) {
                const existing = playerDrawnRewardMap.get(drawnReward.id)
                if (existing === undefined) {
                    insertPlayerBoxGachaDrawnRewardSync(playerId, boxGachaId, boxId, {
                        id: drawnReward.id, number: drawnReward.number,
                    })
                } else {
                    updatePlayerBoxGachaDrawnRewardSync(
                        playerId, boxGachaId, boxId, drawnReward.id, existing + drawnReward.number,
                    )
                }
            }
            updatePlayerItemSync(playerId, pullCurrencyId, newPullCurrency)
            return {
                drawResult, rewardResult, newPullCurrency,
                playerBoxData: currentBoxData ?? {
                    boxId, resetTimes: 0, remainingNumber: remainingDrawsNumber, isClosed: shouldClose,
                },
                currentDrawnRewards,
            }
        })
        const { drawResult, rewardResult, newPullCurrency, currentDrawnRewards } = settlement
        const drawnRewards = drawResult.rewards
        const allDrawResultMap: Map<number, number> = new Map()
        let totalDrawCount = 0
        for (const drawnReward of drawnRewards) {
            totalDrawCount += drawnReward.number
            allDrawResultMap.set(drawnReward.id, drawnReward.number)
        }
        for (const playerDrawnReward of currentDrawnRewards) {
            totalDrawCount += playerDrawnReward.number
            allDrawResultMap.set(playerDrawnReward.id, (allDrawResultMap.get(playerDrawnReward.id) ?? 0) + playerDrawnReward.number)
        }
        const remainingDrawsNumber = (boxGachaData.availableCounts[boxId] ?? totalDrawCount) - totalDrawCount
        const shouldClose = remainingDrawsNumber === 0
        const responsePlayerBoxData = settlement.playerBoxData

        // generate totalDrawnRewards array
        const allBoxInfo: Object[] = await runPersistenceTransaction({
            domain: "gacha", playerId, operation: "box_response_reconcile",
        }, () => getAllBoxList(playerId, boxGachaId, boxGachaData.boxes, boxId))

        // add current box to allBoxInfo
        {
            // build all drawn reward list
            const allDrawnRewardList: Object[] = []
            for (const [rewardId, number] of allDrawResultMap) {
                allDrawnRewardList.push({
                    "reward_id": rewardId,
                    "number": number
                })
            }

            allBoxInfo.push({
                "box_id": boxId,
                "reset_times": responsePlayerBoxData?.resetTimes ?? 0,
                "all_drawn_reward_list": allDrawnRewardList,
                "coming_next_reward_list": [],
                "is_closed": shouldClose ? true : responsePlayerBoxData?.isClosed ?? false
            })
        }

        const existingCharacterList = (rewardResult?.character_list ?? []) as Record<string, unknown>[]
        const characterList = drawnRewards.length > 0
            ? reconcileAwakeUnlockCharacterList(playerId, existingCharacterList)
            : existingCharacterList

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: viewerId
            }),
            "data": {
                "user_info": {
                    "free_mana": player.freeMana + (rewardResult?.user_info.free_mana ?? 0),
                    "exp_pool": player.expPool + (rewardResult?.user_info.exp_pool ?? 0),
                    "exp_pooled_time": getServerTime(player.expPooledTime),
                },
                "drawn_reward_list": drawnRewards.map(reward => {
                    return {
                        "reward_id": reward.id,
                        "number": reward.number
                    }
                }),
                "all_box_info": allBoxInfo,
                "joined_character_id_list": rewardResult?.joined_character_id_list ?? [],
                "character_list": characterList,
                "equipment_list": rewardResult?.equipment_list ?? [],
                "item_list": {
                    [pullCurrencyId]: newPullCurrency,
                    ...(rewardResult?.items ?? {})
                },
                "mail_arrived": false
            }
        })
    })

    fastify.post("/get_box_list", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as GetBoxListBody

        const viewerId = body.viewer_id
        const boxGachaId = body.box_gacha_id
        console.log(`[BOX] get_box_list: boxGachaId=${boxGachaId}`)
        if (isNaN(viewerId) || isNaN(boxGachaId)) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid request body."
        })

        const viewerIdSession = await getSession(viewerId.toString())
        if (!viewerIdSession) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid viewer id."
        })

        // get player
        const playerId = resolvePlayerIdSync(viewerIdSession.accountId)!
        const player = playerId !== null ? getPlayerSync(playerId) : null

        if (player === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No players bound to account."
        })

        // get box gacha data
        const boxGachaData = getBoxGachaSync(boxGachaId)
        if (boxGachaData === null) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid box gacha id."
        })

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: viewerId
            }),
            "data": {
                "all_box_info": getAllBoxList(playerId, boxGachaId, boxGachaData.boxes)
            }
        })
    })
}

export default routes;
