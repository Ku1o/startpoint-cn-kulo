const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const { EventEmitter } = require("node:events")

require("ts-node/register/transpile-only")

const dataDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "sp-multi-identity-"))
process.env.DATA_DIR = dataDirectory

const Fastify = require("fastify")
const { pack, unpack } = require("msgpackr")
const { getDb } = require("../src/data/db")
const { insertAccountSync } = require("../src/data/domains/account")
const { insertDefaultPlayerSync, updatePlayerSync } = require("../src/data/domains/player")
const { generateViewerIdSession } = require("../src/data/domains/session")
const { addFollowSync, getPlayerIdByViewerIdSync } = require("../src/data/domains/follow")
const { saveAccountDefaultPlayer } = require("../src/data/activeAccount")
const { resolveMultiPlayerContext } = require("../src/multi/player-context")
const {
    addRoomMember,
    createRoom,
    disbandRoom,
    getRoom,
    getRoomByToken,
    getRoomMemberPlayerId,
    getRooms,
    isRoomMember,
} = require("../src/multi/room/manager")
const {
    acceptRandomRecruitmentForViewer,
    publishRandomRecruitment,
    stopRandomRecruitment,
    takeRandomRecruitments,
    validateRandomRecruitmentAttention,
    wasRandomRecruitmentAcceptedBy,
} = require("../src/multi/recruitment")
const { encodeRoomShareOptions, MUTUAL_FOLLOW_SHARE_TYPE } = require("../src/multi/room/sharing")
const { registerLobbyRoutes } = require("../src/multi/http/lobby")
const { registerRoomRoutes } = require("../src/multi/http/room")
const { registerSocialRoutes } = require("../src/multi/http/social")
const { registerBattleRoutes } = require("../src/multi/http/battle")
const registerAttentionRoutes = require("../src/routes/api/attention").default
const { handleHandshake } = require("../src/multi/tcp/handshake")
const { sessionManager } = require("../src/multi/state/SessionManager")
const { roomAdmissionRegistry } = require("../src/multi/room/admission")

class FakeSocket extends EventEmitter {
    constructor() {
        super()
        this.destroyed = false
        this.readable = true
        this.writable = true
        this.remoteAddress = "127.0.0.1"
        this.remotePort = 12345
        this.messages = []
    }

    write(raw) {
        this.messages.push(JSON.parse(String(raw).replace(/\0$/, "")))
        return true
    }

    end() {
        this.writable = false
    }

    destroy() {
        this.destroyed = true
        this.readable = false
        this.writable = false
    }
}

async function createIdentity(idpId, names, selectedIndex = 0) {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "leiting",
        idpId,
        status: "normal",
    })
    const players = names.map(name => {
        const player = insertDefaultPlayerSync(account.id)
        updatePlayerSync({ id: player.id, name })
        return player.id
    })
    saveAccountDefaultPlayer(account.id, players[selectedIndex])
    const viewerSession = await generateViewerIdSession(account.id)
    return {
        accountId: account.id,
        playerIds: players,
        selectedPlayerId: players[selectedIndex],
        viewerId: Number(viewerSession.token),
    }
}

async function createServer() {
    const fastify = Fastify()
    fastify.addHook("onSend", (_request, reply, payload, done) => {
        if (String(reply.getHeader("content-type") || "").startsWith("application/x-msgpack")) {
            done(null, pack(payload).toString("base64"))
            return
        }
        done(null, payload)
    })
    registerRoomRoutes(fastify)
    registerLobbyRoutes(fastify)
    registerSocialRoutes(fastify)
    registerBattleRoutes(fastify)
    await registerAttentionRoutes(fastify)
    await fastify.ready()
    return fastify
}

function decode(response) {
    return unpack(Buffer.from(response.body, "base64"))
}

async function main() {
    let fastify
    const roomNumbers = []
    const connectedClients = []
    const connectedSockets = []
    try {
        const host = await createIdentity("multi-identity-host", ["旧存档", "当前房主"], 1)
        const guest = await createIdentity("multi-identity-guest", ["访客"])
        const stranger = await createIdentity("multi-identity-stranger", ["陌生人"])

        const hostContext = await resolveMultiPlayerContext(host.viewerId)
        assert.equal(hostContext.playerId, host.selectedPlayerId)
        assert.equal(hostContext.player.name, "当前房主")
        assert.equal(getPlayerIdByViewerIdSync(host.viewerId), host.selectedPlayerId)

        const firstRoom = createRoom(
            host.viewerId,
            host.selectedPlayerId,
            1,
            1,
            9001001,
            0,
            1,
        )
        const secondRoom = createRoom(
            guest.viewerId,
            guest.selectedPlayerId,
            1,
            1,
            9001001,
            0,
            1,
        )
        roomNumbers.push(firstRoom.room_number, secondRoom.room_number)
        assert.notEqual(firstRoom.room_number, secondRoom.room_number)
        assert.notEqual(firstRoom.access_token, secondRoom.access_token)
        assert.match(firstRoom.access_token, /^[A-Za-z0-9_-]{32,}$/)
        assert.equal(getRoomByToken(firstRoom.access_token), firstRoom)
        assert.equal(getRoomByToken("multi_battle_quest_access_token"), undefined)

        const firstEventRoom = createRoom(
            host.viewerId,
            host.selectedPlayerId,
            1,
            8,
            1001,
            0,
            1,
        )
        const otherEventRoom = createRoom(
            host.viewerId,
            host.selectedPlayerId,
            1,
            8,
            17001,
            0,
            1,
        )
        roomNumbers.push(firstEventRoom.room_number, otherEventRoom.room_number)
        assert.deepEqual(
            getRooms(8, 1).map(room => room.room_number),
            [firstEventRoom.room_number],
        )
        assert.deepEqual(
            getRooms(8, 17).map(room => room.room_number),
            [otherEventRoom.room_number],
        )

        const hostSocket = new FakeSocket()
        await handleHandshake(hostSocket, {
            socklet: "cooperation_room",
            viewerId: host.viewerId,
            roomNumber: firstRoom.room_number,
            questCategory: 1,
            questId: 9001001,
            connectionId: "identity-host",
        })
        const hostClient = sessionManager.getClient(host.viewerId, firstRoom.room_number)
        assert.equal(hostClient.playerId, host.selectedPlayerId)
        assert.equal(hostClient.yourself.isHost, true)
        hostClient.enterData = {}
        connectedClients.push(hostClient)
        connectedSockets.push(hostSocket)

        assert.equal(roomAdmissionRegistry.reserve(
            firstRoom.room_number,
            firstRoom.lobby_generation,
            guest.viewerId,
            [host.viewerId],
            3,
        ), true)
        const guestSocket = new FakeSocket()
        await handleHandshake(guestSocket, {
            socklet: "cooperation_room",
            viewerId: guest.viewerId,
            roomNumber: firstRoom.room_number,
            questCategory: 1,
            questId: 9001001,
            connectionId: "identity-guest",
        })
        const guestClient = sessionManager.getClient(guest.viewerId, firstRoom.room_number)
        assert.equal(guestClient.playerId, guest.selectedPlayerId)
        assert.equal(guestClient.yourself.isHost, false)
        guestClient.enterData = {}
        connectedClients.push(guestClient)
        connectedSockets.push(guestSocket)

        fastify = await createServer()

        const guestShare = await fastify.inject({
            method: "POST",
            url: "/share_room",
            payload: {
                viewer_id: guest.viewerId,
                room_number: firstRoom.room_number,
                category: 1,
                quest_id: 9001001,
                share_type_list: [1],
                api_count: 1,
            },
        })
        assert.equal(guestShare.statusCode, 403)

        const guestDisband = await fastify.inject({
            method: "POST",
            url: "/disband_room",
            payload: { viewer_id: guest.viewerId, room_number: firstRoom.room_number, api_count: 2 },
        })
        assert.equal(guestDisband.statusCode, 403)
        assert.equal(getRoom(firstRoom.room_number), firstRoom)

        const strangerRestore = await fastify.inject({
            method: "POST",
            url: "/restore_room",
            payload: { viewer_id: stranger.viewerId, room_number: firstRoom.room_number, api_count: 3 },
        })
        assert.equal(strangerRestore.statusCode, 200)
        assert.equal(decode(strangerRestore).data.raising_state, 13)

        assert.equal(addRoomMember(
            firstRoom.room_number,
            guest.viewerId,
            guest.selectedPlayerId,
        ), true)
        assert.equal(isRoomMember(firstRoom, guest.viewerId), true)
        assert.equal(getRoomMemberPlayerId(firstRoom, guest.viewerId), guest.selectedPlayerId)
        assert.equal(isRoomMember(firstRoom, stranger.viewerId), false)

        const memberRestore = await fastify.inject({
            method: "POST",
            url: "/restore_room",
            payload: { viewer_id: guest.viewerId, room_number: firstRoom.room_number, api_count: 4 },
        })
        assert.equal(memberRestore.statusCode, 200)
        assert.notEqual(decode(memberRestore).data.raising_state, 13)

        saveAccountDefaultPlayer(host.accountId, host.playerIds[0])
        const switchedHostStart = await fastify.inject({
            method: "POST",
            url: "/start",
            payload: {
                viewer_id: host.viewerId,
                quest_id: 9001001,
                category: 1,
                party_id: 1,
                use_boost_point: false,
                use_boss_boost_point: false,
                is_auto_start_mode: false,
                room_number: firstRoom.room_number,
                mate_player_ids: [],
                mate_party_ids: [],
                play_id: "player-mismatch",
                combat_power: 0,
                api_count: 5,
            },
        })
        assert.equal(switchedHostStart.statusCode, 400)
        assert.equal(firstRoom.lifecycle.phase, "LOBBY")
        saveAccountDefaultPlayer(host.accountId, host.selectedPlayerId)

        const strangerStart = await fastify.inject({
            method: "POST",
            url: "/start",
            payload: {
                viewer_id: stranger.viewerId,
                quest_id: 9001001,
                category: 1,
                party_id: 1,
                use_boost_point: false,
                use_boss_boost_point: false,
                is_auto_start_mode: false,
                room_number: firstRoom.room_number,
                mate_player_ids: [],
                mate_party_ids: [],
                play_id: "identity-boundary",
                combat_power: 0,
                api_count: 6,
            },
        })
        assert.equal(strangerStart.statusCode, 403)

        const invalidToken = await fastify.inject({
            method: "POST",
            url: "/verify_access_token",
            payload: { viewer_id: guest.viewerId, access_token: "invalid", api_count: 6 },
        })
        assert.deepEqual(decode(invalidToken).data, { room_exists: false })

        const validToken = await fastify.inject({
            method: "POST",
            url: "/verify_access_token",
            payload: { viewer_id: guest.viewerId, access_token: firstRoom.access_token, api_count: 7 },
        })
        const tokenData = decode(validToken).data
        assert.equal(tokenData.room_exists, true)
        assert.equal(tokenData.room_number, firstRoom.room_number)
        assert.equal(tokenData.establisher_name, "当前房主")

        assert.equal(addFollowSync(guest.selectedPlayerId, host.selectedPlayerId), "added")
        firstRoom.share_room_options = encodeRoomShareOptions([MUTUAL_FOLLOW_SHARE_TYPE])

        const searched = await fastify.inject({
            method: "POST",
            url: "/search_room",
            payload: { viewer_id: guest.viewerId, room_number: firstRoom.room_number, api_count: 8 },
        })
        assert.equal(decode(searched).data.establisher_follow, 2)

        const followedRooms = await fastify.inject({
            method: "POST",
            url: "/get_rooms",
            payload: { viewer_id: guest.viewerId, category_id: 1 },
        })
        assert.equal(decode(followedRooms).data.rooms.length, 1)

        const strangerRooms = await fastify.inject({
            method: "POST",
            url: "/get_rooms",
            payload: { viewer_id: stranger.viewerId, category_id: 1 },
        })
        assert.deepEqual(decode(strangerRooms).data.rooms, [])

        const noAttention = await fastify.inject({
            method: "POST",
            url: "/check",
            payload: { viewer_id: stranger.viewerId, holding_number: 0, request_number: 3 },
        })
        assert.equal(decode(noAttention).data.multi, null)

        const recruitment = publishRandomRecruitment(firstRoom.room_number)
        const strangerRoomsWhileRecruiting = await fastify.inject({
            method: "POST",
            url: "/get_rooms",
            payload: { viewer_id: stranger.viewerId, category_id: 1 },
        })
        assert.deepEqual(decode(strangerRoomsWhileRecruiting).data.rooms, [])

        const strangerAttention = await fastify.inject({
            method: "POST",
            url: "/check",
            payload: { viewer_id: stranger.viewerId, holding_number: 0, request_number: 3 },
        })
        assert.equal(decode(strangerAttention).data.multi[0].attention_key, recruitment.attentionKey)

        const delivered = takeRandomRecruitments(guest.viewerId, 1, () => true)
        assert.equal(delivered.length, 1)
        assert.equal(delivered[0].attentionKey, recruitment.attentionKey)
        assert.equal(acceptRandomRecruitmentForViewer(firstRoom.room_number, guest.viewerId), true)
        assert.equal(wasRandomRecruitmentAcceptedBy(firstRoom.room_number, guest.viewerId), true)
        assert.deepEqual(takeRandomRecruitments(guest.viewerId, 1, () => true), [])
        assert.equal(validateRandomRecruitmentAttention(
            firstRoom.room_number,
            host.viewerId,
            recruitment.attentionKey,
        ), false)
        assert.equal(validateRandomRecruitmentAttention(
            firstRoom.room_number,
            guest.viewerId,
            recruitment.attentionKey,
        ), true)
        stopRandomRecruitment(firstRoom.room_number)
        assert.equal(validateRandomRecruitmentAttention(
            firstRoom.room_number,
            guest.viewerId,
            recruitment.attentionKey,
        ), true)
        assert.equal(wasRandomRecruitmentAcceptedBy(firstRoom.room_number, guest.viewerId), true)

        const hostShare = await fastify.inject({
            method: "POST",
            url: "/share_room",
            payload: {
                viewer_id: host.viewerId,
                room_number: firstRoom.room_number,
                category: 1,
                quest_id: 9001001,
                share_type_list: [1],
                api_count: 9,
            },
        })
        assert.equal(hostShare.statusCode, 200)
        assert.equal(decode(hostShare).data.config.return_attention_max_num, 3)

        console.log("multi room identity tests passed")
    } finally {
        if (fastify) await fastify.close()
        for (const client of connectedClients) sessionManager.removeClient(client)
        for (const socket of connectedSockets) socket.destroy()
        for (const roomNumber of roomNumbers) disbandRoom(roomNumber, "identity_test_cleanup")
        getDb().close()
        fs.rmSync(dataDirectory, { recursive: true, force: true })
    }
}

main().then(
    () => process.exit(0),
    error => {
        console.error(error)
        process.exit(1)
    },
)
