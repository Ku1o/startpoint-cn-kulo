/**
 * Profile API — get_my_profile.
 * Returns player profile info, settings, and party groups.
 */
import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { getPlayerSync, updatePlayerSync } from "../../data/domains/player"
import { getSession } from "../../data/domains/session"
import { resolvePlayerIdSync } from "../../data/activeAccount";
// removed getAccountPlayers "../../data/wdfpData";
import { generateDataHeaders } from "../../utils";
import { getPlayerIdByViewerIdSync } from "../../data/domains/follow";
import { buildTargetProfileSync } from "../../lib/follow";
import { fromProfileTargetId } from "../../lib/leaderboard/presentation";
import { getFavoritePartyGroupListSync } from "../../lib/profileFavorite";
import {
    ensurePlayerLegacyDegreesSync,
    ensurePlayerSoloTimeAttackDegreesSync,
    getPlayerDegreeIdsSync,
    hasPlayerDegreeSync,
} from "../../data/domains/degree";
import { ensurePlayerClaimedCarnivalDegreesSync } from "../../lib/quest/finish/carnival-reward-handler";
import { gameVerboseLog } from "../../lib/game-logging";
import {
    getPlayerProfileSettingsSync,
    updatePlayerProfileSettingsSync,
} from "../../data/domains/option";
import { getPlayerProfileStatsSync } from "../../lib/profile-stats";
import { getConfigSync } from "../../lib/assets";
import { ensurePlayerActivityDegreesSync } from "../../lib/activity-degree-rewards";

const PROFILE_SETTING_FIELDS = [
    "show_opened_mana_board_second_count",
    "show_owned_character_count",
    "show_owned_degree_count",
] as const

function serializeProfileSettings(
    settings: ReturnType<typeof getPlayerProfileSettingsSync>,
) {
    return {
        show_opened_mana_board_second_count: settings.showOpenedManaBoardSecondCount,
        show_owned_character_count: settings.showOwnedCharacterCount,
        show_owned_degree_count: settings.showOwnedDegreeCount,
    }
}

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/get_my_profile", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as any
        const viewerId = body.viewer_id
        if (!viewerId || isNaN(viewerId)) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid request body."
        })

        const session = await getSession(viewerId.toString())
        if (!session) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid viewer id."
        })

        const playerId = resolvePlayerIdSync(session.accountId)!
        if (playerId === null) return reply.status(400).send({
            error: "Bad Request",
            message: "No player bound to account."
        })

        const player = getPlayerSync(playerId)
        if (!player) return reply.status(400).send({ error: "Bad Request", message: "Player not found." })

        ensurePlayerLegacyDegreesSync(playerId, player.degreeId || 1)
        ensurePlayerSoloTimeAttackDegreesSync(playerId)
        ensurePlayerClaimedCarnivalDegreesSync(playerId)
        ensurePlayerActivityDegreesSync(playerId)
        const stats = getPlayerProfileStatsSync(playerId)
        const profileSettings = getPlayerProfileSettingsSync(playerId)

        const partyGroupList = getFavoritePartyGroupListSync(
            playerId,
            player.leaderCharacterId,
        )

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: viewerId }),
            data: {
                profile_info: {
                    max_opened_mana_board_second_count: stats.maxOpenedManaBoardSecondCount,
                    max_owned_character_count: stats.maxOwnedCharacterCount,
                    max_owned_degree_count: stats.maxOwnedDegreeCount,
                    opened_mana_board_second_count: stats.openedManaBoardSecondCount,
                    owned_character_count: stats.ownedCharacterCount,
                    owned_degree_count: stats.ownedDegreeCount,
                },
                profile_settings: serializeProfileSettings(profileSettings),
                user_party_group_list: partyGroupList,
            }
        })
    })

    // Public profile opened from the follow/follower list.
    fastify.post("/get_profile", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as any
        const viewerId = Number(body.viewer_id)
        const targetViewerId = Number(body.target_viewer_id)
        if (!Number.isFinite(viewerId) || !Number.isFinite(targetViewerId)) {
            return reply.status(400).send({ error: "Bad Request", message: "Invalid request body." })
        }

        const session = await getSession(String(viewerId))
        if (!session) return reply.status(400).send({ error: "Bad Request", message: "Invalid viewer id." })
        const playerId = resolvePlayerIdSync(session.accountId)
        // Rush leaderboard rows carry an encoded saved-player id because a
        // single account can have multiple player archives sharing one viewer
        // session. Keep the normal viewer-id lookup for every other caller.
        const targetPlayerId = fromProfileTargetId(targetViewerId)
            ?? getPlayerIdByViewerIdSync(targetViewerId)
        if (playerId === null || targetPlayerId === null) {
            reply.header("content-type", "application/x-msgpack")
            return reply.status(200).send({
                data_headers: generateDataHeaders({ viewer_id: viewerId, result_code: 1457 }),
                data: {},
            })
        }

        const profile = buildTargetProfileSync(playerId, targetPlayerId)
        if (!profile) {
            reply.header("content-type", "application/x-msgpack")
            return reply.status(200).send({
                data_headers: generateDataHeaders({ viewer_id: viewerId, result_code: 1457 }),
                data: {},
            })
        }

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: viewerId }),
            data: profile,
        })
    })

    // Returns the player's last login region (CN-specific)
    fastify.post("/get_last_login_region", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as any
        const viewerId = body.viewer_id
        if (!viewerId || isNaN(viewerId)) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid request body."
        })

        const session = await getSession(viewerId.toString())
        if (!session) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid viewer id."
        })

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: viewerId }),
            data: {
                region: "CN",
            }
        })
    })

    // Returns owned degree IDs for title selection
    fastify.post("/get_degree_list", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as any
        const viewerId = body.viewer_id
        if (!viewerId || isNaN(viewerId)) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid request body."
        })

        const session = await getSession(viewerId.toString())
        if (!session) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid viewer id."
        })

        const playerId = resolvePlayerIdSync(session.accountId)!
        const player = playerId !== null ? getPlayerSync(playerId) : null
        if (playerId === null || !player) return reply.status(500).send({
            error: "Internal Server Error",
            message: "No player bound to account."
        })

        ensurePlayerLegacyDegreesSync(playerId, player.degreeId || 1)
        ensurePlayerSoloTimeAttackDegreesSync(playerId)
        ensurePlayerClaimedCarnivalDegreesSync(playerId)
        ensurePlayerActivityDegreesSync(playerId)
        const degreeIds = getPlayerDegreeIdsSync(playerId)

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: viewerId }),
            data: {
                degree_ids: degreeIds,
            }
        })
    })

    // Set the player's displayed degree title
    fastify.post("/update_degree", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as any
        const viewerId = body.viewer_id
        const degreeId = body.degree_id
        if (!viewerId || isNaN(viewerId) || degreeId === undefined || isNaN(degreeId)) {
            return reply.status(400).send({
                error: "Bad Request",
                message: "Invalid request body."
            })
        }

        const session = await getSession(viewerId.toString())
        if (!session) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid viewer id."
        })

        const playerId = resolvePlayerIdSync(session.accountId)!
        if (playerId === null) return reply.status(500).send({
            error: "Internal Server Error",
            message: "No player bound to account."
        })

        const player = getPlayerSync(playerId)
        if (!player) return reply.status(500).send({
            error: "Internal Server Error",
            message: "Player not found."
        })

        ensurePlayerLegacyDegreesSync(playerId, player.degreeId || 1)
        ensurePlayerSoloTimeAttackDegreesSync(playerId)
        ensurePlayerClaimedCarnivalDegreesSync(playerId)
        ensurePlayerActivityDegreesSync(playerId)
        if (!hasPlayerDegreeSync(playerId, Number(degreeId))) {
            return reply.status(400).send({
                error: "Bad Request",
                message: "Degree is not owned."
            })
        }

        updatePlayerSync({ id: playerId, degreeId: Number(degreeId) })

        gameVerboseLog(() => `[PROFILE] update_degree viewer=${viewerId} degree=${degreeId}`)

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: viewerId }),
            data: {
                user_info: { degree_id: Number(degreeId) }
            }
        })
    })

    // Update profile visibility settings.
    fastify.post("/update_profile_settings", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as any
        const viewerId = body.viewer_id
        if (!viewerId || isNaN(viewerId)) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid request body."
        })

        const session = await getSession(viewerId.toString())
        if (!session) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid viewer id."
        })

        const settings = body.profile_settings
        if (settings === null || typeof settings !== "object" || Array.isArray(settings)
            || !PROFILE_SETTING_FIELDS.some(field => Object.prototype.hasOwnProperty.call(settings, field))
            || PROFILE_SETTING_FIELDS.some(field => (
                Object.prototype.hasOwnProperty.call(settings, field)
                && typeof settings[field] !== "boolean"
            ))) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid profile settings.",
        })

        const playerId = resolvePlayerIdSync(session.accountId)
        if (playerId === null || !getPlayerSync(playerId)) return reply.status(400).send({
            error: "Bad Request",
            message: "No player bound to account.",
        })
        const updated = updatePlayerProfileSettingsSync(playerId, {
            ...(typeof settings.show_opened_mana_board_second_count === "boolean"
                ? { showOpenedManaBoardSecondCount: settings.show_opened_mana_board_second_count }
                : {}),
            ...(typeof settings.show_owned_character_count === "boolean"
                ? { showOwnedCharacterCount: settings.show_owned_character_count }
                : {}),
            ...(typeof settings.show_owned_degree_count === "boolean"
                ? { showOwnedDegreeCount: settings.show_owned_degree_count }
                : {}),
        })
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: viewerId }),
            data: {
                profile_settings: serializeProfileSettings(updated),
            }
        })
    })

    // Update profile comment
    fastify.post("/update_comment", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as any
        const viewerId = body.viewer_id
        if (!viewerId || isNaN(viewerId)) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid request body."
        })

        const session = await getSession(viewerId.toString())
        if (!session) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid viewer id."
        })

        const playerId = resolvePlayerIdSync(session.accountId)!
        if (playerId === null) return reply.status(400).send({
            error: "Bad Request",
            message: "No player bound to account."
        })

        if (typeof body.comment !== "string") return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid comment.",
        })
        const comment = body.comment.substring(0, getConfigSync().max_player_comment_length)
        updatePlayerSync({ id: playerId, comment })

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: viewerId }),
            data: { comment },
        })
    })

    // Rename player
    fastify.post("/rename", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as any
        const viewerId = body.viewer_id
        if (!viewerId || isNaN(viewerId)) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid request body."
        })

        const session = await getSession(viewerId.toString())
        if (!session) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid viewer id."
        })

        const playerId = resolvePlayerIdSync(session.accountId)!
        if (playerId === null) return reply.status(400).send({
            error: "Bad Request",
            message: "No player bound to account."
        })

        if (typeof body.name !== "string") return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid name.",
        })
        const name = body.name.substring(0, getConfigSync().max_player_name_length)
        updatePlayerSync({ id: playerId, name })

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: viewerId }),
            data: { name },
        })
    })
}

export default routes
