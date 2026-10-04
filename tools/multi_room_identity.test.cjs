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
const { getPlayerItemSync, setPlayerItemSync } = require("../src/data/domains/item")
const { insertDefaultPlayerSync, updatePlayerSync } = require("../src/data/domains/player")
const { insertPlayerQuestProgressSync } = require("../src/data/domains/quest")
const {
    getPlayerActiveQuestSync,
    insertPlayerActiveQuestSync,
} = require("../src/data/domains/quest_active")
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
const { encodeRoomShareOptions, FOLLOWER_SHARE_TYPE } = require("../src/multi/room/sharing")
const { registerLobbyRoutes } = require("../src/multi/http/lobby")
const { registerRoomRoutes } = require("../src/multi/http/room")
const { registerSocialRoutes } = require("../src/multi/http/social")
const { registerBattleRoutes } = require("../src/multi/http/battle")
const { activeQuests } = require("../src/routes/api/singleBattleQuest")
const registerAttentionRoutes = require("../src/routes/api/attention").default
const { handleHandshake } = require("../src/multi/tcp/handshake")
const { handleMessage: handleLobbyMessage } = require("../src/multi/tcp/lobby")
const { sessionManager } = require("../src/multi/state/SessionManager")
const { roomAdmissionRegistry } = require("../src/multi/room/admission")
const playerRankTable = require("../assets/cdndata/player_rank_full.json")

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
        const latecomer = await createIdentity("multi-identity-latecomer", ["晚到者"])

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

        // Lobby emotions: Client2Server.Broadcast([MeetingBroadcastMessage.Emotion])
        // must reach the other room members as MeetingServer2Client.Messages
        // (never echoed back to the sender, which renders its own balloon).
        hostSocket.messages.length = 0
        guestSocket.messages.length = 0
        handleLobbyMessage(guestSocket, [1, [[0, 3]]])
        await new Promise(resolve => setTimeout(resolve, 20))
        const relayedEmotions = hostSocket.messages
            .filter(message => Array.isArray(message) && message[0] === 2)
        assert.equal(relayedEmotions.length, 1)
        assert.equal(relayedEmotions[0][1], guestClient.connectionId)
        assert.deepEqual(relayedEmotions[0][2], [[0, 3]])
        assert.equal(
            guestSocket.messages.filter(message => Array.isArray(message) && message[0] === 2).length,
            0,
        )

        fastify = await createServer()
        const unavailableCreate = await fastify.inject({
            method: "POST",
            url: "/create_room",
            payload: {
                viewer_id: host.viewerId,
                category: 1,
                quest_id: 999999999,
                party_id: 1,
                api_count: 0,
            },
        })
        assert.equal(unavailableCreate.statusCode, 200, unavailableCreate.body)
        assert.equal(decode(unavailableCreate).data_headers.result_code, 4507)

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

        const staleQuestSelection = await fastify.inject({
            method: "POST",
            url: "/select_room",
            payload: {
                viewer_id: latecomer.viewerId,
                room_number: firstRoom.room_number,
                category: 1,
                quest_id: 9001002,
                party_id: 1,
                accepted_type: 0,
                api_count: 4,
            },
        })
        assert.equal(staleQuestSelection.statusCode, 200, staleQuestSelection.body)
        assert.equal(decode(staleQuestSelection).data.raising_state, 9)

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
        firstRoom.share_room_options = encodeRoomShareOptions([FOLLOWER_SHARE_TYPE])

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

        // COM mates occupy their seats: a seat-complete room rejects a new
        // entrant with the client's native filled state (3) instead of the
        // stale-room state, and AI-filled rooms do not advertise recruitment.
        const savedNpcCount = firstRoom.npc_count
        firstRoom.is_npc_mode = true
        firstRoom.npc_count = 1
        const fullRoomAttention = await fastify.inject({
            method: "POST",
            url: "/check",
            payload: { viewer_id: latecomer.viewerId, holding_number: 0, request_number: 3 },
        })
        assert.equal(decode(fullRoomAttention).data.multi, null)
        const fullRoomSelect = await fastify.inject({
            method: "POST",
            url: "/select_room",
            payload: {
                viewer_id: latecomer.viewerId,
                room_number: firstRoom.room_number,
                category: 1,
                quest_id: 9001001,
                party_id: 1,
                accepted_type: 2,
                api_count: 12,
            },
        })
        assert.equal(decode(fullRoomSelect).data.raising_state, 3)
        // A follower still sees the room, but the list entry itself reports
        // the native filled state so the client does not attempt the entry.
        assert.equal(addFollowSync(latecomer.selectedPlayerId, host.selectedPlayerId), "added")
        const latecomerRooms = await fastify.inject({
            method: "POST",
            url: "/get_rooms",
            payload: { viewer_id: latecomer.viewerId, category_id: 1 },
        })
        const latecomerEntry = decode(latecomerRooms).data.rooms
            .find(room => room.room_number === firstRoom.room_number)
        assert.ok(latecomerEntry, "follower still sees the seat-complete room")
        assert.equal(latecomerEntry.raising_state, 3)
        firstRoom.npc_count = savedNpcCount
        firstRoom.is_npc_mode = false

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

        // Every new guest follows the hard-multi client-master conditions:
        // rank 120 plus the exact linked boss/advent prerequisite, regardless
        // of whether entry came from a bell, room code, or follow listing.
        const hardRoom = createRoom(
            host.viewerId,
            host.selectedPlayerId,
            1,
            26,
            1001001,
            0,
            1,
        )
        roomNumbers.push(hardRoom.room_number)
        const hardHostSocket = new FakeSocket()
        await handleHandshake(hardHostSocket, {
            socklet: "cooperation_room",
            viewerId: host.viewerId,
            roomNumber: hardRoom.room_number,
            questCategory: 26,
            questId: 1001001,
            connectionId: "hard-rescue-host",
        })
        const hardHostClient = sessionManager.getClient(host.viewerId, hardRoom.room_number)
        hardHostClient.enterData = {}
        connectedClients.push(hardHostClient)
        connectedSockets.push(hardHostSocket)
        const hardRecruitment = publishRandomRecruitment(hardRoom.room_number)
        hardRoom.share_room_options = encodeRoomShareOptions([FOLLOWER_SHARE_TYPE])

        const lowRankAttention = await fastify.inject({
            method: "POST",
            url: "/check",
            payload: { viewer_id: stranger.viewerId, holding_number: 0, request_number: 3 },
        })
        assert.equal(decode(lowRankAttention).data.multi, null)
        const lowRankFriendRooms = await fastify.inject({
            method: "POST",
            url: "/get_rooms",
            payload: { viewer_id: latecomer.viewerId, category_id: 26 },
        })
        assert.deepEqual(decode(lowRankFriendRooms).data.rooms, [])

        const rank120Threshold = Number(playerRankTable["120"][0][1])
        updatePlayerSync({ id: stranger.selectedPlayerId, rankPoint: rank120Threshold })
        const missingPrerequisiteAttention = await fastify.inject({
            method: "POST",
            url: "/check",
            payload: { viewer_id: stranger.viewerId, holding_number: 0, request_number: 3 },
        })
        assert.equal(decode(missingPrerequisiteAttention).data.multi, null)

        insertPlayerQuestProgressSync(stranger.selectedPlayerId, 2, {
            questId: 1061004,
            finished: true,
        })
        const eligibleAttention = await fastify.inject({
            method: "POST",
            url: "/check",
            payload: { viewer_id: stranger.viewerId, holding_number: 0, request_number: 3 },
        })
        assert.equal(
            decode(eligibleAttention).data.multi[0].attention_key,
            hardRecruitment.attentionKey,
        )

        const forgedLowRankRescue = await fastify.inject({
            method: "POST",
            url: "/select_room",
            payload: {
                viewer_id: latecomer.viewerId,
                room_number: hardRoom.room_number,
                category: 26,
                quest_id: 1001001,
                party_id: 1,
                accepted_type: 2,
                api_count: 13,
            },
        })
        assert.equal(decode(forgedLowRankRescue).data.raising_state, 9)

        const blockedDirectRoomEntry = await fastify.inject({
            method: "POST",
            url: "/select_room",
            payload: {
                viewer_id: latecomer.viewerId,
                room_number: hardRoom.room_number,
                category: 26,
                quest_id: 1001001,
                party_id: 1,
                accepted_type: 0,
                api_count: 14,
            },
        })
        assert.equal(decode(blockedDirectRoomEntry).data.raising_state, 9)

        updatePlayerSync({ id: latecomer.selectedPlayerId, rankPoint: rank120Threshold })
        insertPlayerQuestProgressSync(latecomer.selectedPlayerId, 2, {
            questId: 1061004,
            finished: true,
        })
        const eligibleFriendRooms = await fastify.inject({
            method: "POST",
            url: "/get_rooms",
            payload: { viewer_id: latecomer.viewerId, category_id: 26 },
        })
        assert.ok(decode(eligibleFriendRooms).data.rooms.some(
            room => room.room_number === hardRoom.room_number,
        ))
        const eligibleDirectRoomEntry = await fastify.inject({
            method: "POST",
            url: "/select_room",
            payload: {
                viewer_id: latecomer.viewerId,
                room_number: hardRoom.room_number,
                category: 26,
                quest_id: 1001001,
                party_id: 1,
                accepted_type: 0,
                api_count: 15,
            },
        })
        assert.notEqual(decode(eligibleDirectRoomEntry).data.raising_state, 9)
        roomAdmissionRegistry.release(hardRoom.room_number, latecomer.viewerId)

        const eligibleRescue = await fastify.inject({
            method: "POST",
            url: "/select_room",
            payload: {
                viewer_id: stranger.viewerId,
                room_number: hardRoom.room_number,
                category: 26,
                quest_id: 1001001,
                party_id: 1,
                accepted_type: 2,
                api_count: 16,
            },
        })
        assert.notEqual(decode(eligibleRescue).data.raising_state, 9)
        assert.equal(wasRandomRecruitmentAcceptedBy(hardRoom.room_number, stranger.viewerId), true)

        // HTTP selection and TCP admission are separate. If the authoritative
        // prerequisite changes between them, the handshake must fail closed.
        getDb().prepare(`DELETE FROM players_quest_progress
            WHERE player_id = ? AND section = ? AND quest_id = ?`)
            .run(stranger.selectedPlayerId, 2, 1061004)
        const ineligibleRescueSocket = new FakeSocket()
        await handleHandshake(ineligibleRescueSocket, {
            socklet: "cooperation_room",
            viewerId: stranger.viewerId,
            roomNumber: hardRoom.room_number,
            questCategory: 26,
            questId: 1001001,
            connectionId: "hard-rescue-ineligible",
        })
        assert.deepEqual(ineligibleRescueSocket.messages, [[3, "HANDSHAKE_DENIED"]])
        assert.equal(ineligibleRescueSocket.writable, false)

        // Every new five-boss guest must be Rank 130 and own one entry ticket.
        // Bell delivery, room-code/follow entry, and TCP admission only read
        // that inventory; the battle runtime still charges only the host.
        const fiveBossRoom = createRoom(
            host.viewerId,
            host.selectedPlayerId,
            1,
            2,
            1099001,
            0,
            1,
        )
        roomNumbers.push(fiveBossRoom.room_number)
        const fiveBossHostSocket = new FakeSocket()
        await handleHandshake(fiveBossHostSocket, {
            socklet: "cooperation_room",
            viewerId: host.viewerId,
            roomNumber: fiveBossRoom.room_number,
            questCategory: 2,
            questId: 1099001,
            connectionId: "five-boss-rescue-host",
        })
        const fiveBossHostClient = sessionManager.getClient(
            host.viewerId,
            fiveBossRoom.room_number,
        )
        fiveBossHostClient.enterData = {}
        connectedClients.push(fiveBossHostClient)
        connectedSockets.push(fiveBossHostSocket)
        const fiveBossRecruitment = publishRandomRecruitment(fiveBossRoom.room_number)
        fiveBossRoom.share_room_options = encodeRoomShareOptions([FOLLOWER_SHARE_TYPE])

        const rank130Threshold = Number(playerRankTable["130"][0][1])
        updatePlayerSync({
            id: latecomer.selectedPlayerId,
            rankPoint: rank130Threshold - 1,
        })
        setPlayerItemSync(latecomer.selectedPlayerId, 10000143, 1)
        const lowRankFiveBossFriendRooms = await fastify.inject({
            method: "POST",
            url: "/get_rooms",
            payload: { viewer_id: latecomer.viewerId, category_id: 2 },
        })
        assert.equal(
            decode(lowRankFiveBossFriendRooms).data.rooms.some(
                room => room.room_number === fiveBossRoom.room_number,
            ),
            false,
        )
        const lowRankFiveBossSearch = await fastify.inject({
            method: "POST",
            url: "/search_room",
            payload: {
                viewer_id: latecomer.viewerId,
                room_number: fiveBossRoom.room_number,
                api_count: 17,
            },
        })
        assert.equal(decode(lowRankFiveBossSearch).data.room_exists, false)
        const lowRankFiveBossDirectSelect = await fastify.inject({
            method: "POST",
            url: "/select_room",
            payload: {
                viewer_id: latecomer.viewerId,
                room_number: fiveBossRoom.room_number,
                category: 2,
                quest_id: 1099001,
                party_id: 1,
                accepted_type: 0,
                api_count: 18,
            },
        })
        assert.equal(decode(lowRankFiveBossDirectSelect).data.raising_state, 9)
        const lowRankFiveBossAttention = await fastify.inject({
            method: "POST",
            url: "/check",
            payload: { viewer_id: latecomer.viewerId, holding_number: 0, request_number: 3 },
        })
        assert.equal(
            decode(lowRankFiveBossAttention).data.multi?.some(
                item => item.quest_info.room_number === fiveBossRoom.room_number,
            ) ?? false,
            false,
        )

        updatePlayerSync({
            id: latecomer.selectedPlayerId,
            rankPoint: rank130Threshold,
        })
        setPlayerItemSync(latecomer.selectedPlayerId, 10000143, 0)
        const noTicketFriendRooms = await fastify.inject({
            method: "POST",
            url: "/get_rooms",
            payload: { viewer_id: latecomer.viewerId, category_id: 2 },
        })
        assert.equal(
            decode(noTicketFriendRooms).data.rooms.some(
                room => room.room_number === fiveBossRoom.room_number,
            ),
            false,
        )
        const noTicketSearch = await fastify.inject({
            method: "POST",
            url: "/search_room",
            payload: {
                viewer_id: latecomer.viewerId,
                room_number: fiveBossRoom.room_number,
                api_count: 19,
            },
        })
        assert.equal(decode(noTicketSearch).data.room_exists, false)
        const noTicketDirectSelect = await fastify.inject({
            method: "POST",
            url: "/select_room",
            payload: {
                viewer_id: latecomer.viewerId,
                room_number: fiveBossRoom.room_number,
                category: 2,
                quest_id: 1099001,
                party_id: 1,
                accepted_type: 0,
                api_count: 20,
            },
        })
        assert.equal(decode(noTicketDirectSelect).data.raising_state, 9)
        const noTicketAttention = await fastify.inject({
            method: "POST",
            url: "/check",
            payload: { viewer_id: latecomer.viewerId, holding_number: 0, request_number: 3 },
        })
        assert.equal(
            decode(noTicketAttention).data.multi?.some(
                item => item.quest_info.room_number === fiveBossRoom.room_number,
            ) ?? false,
            false,
        )

        setPlayerItemSync(latecomer.selectedPlayerId, 10000143, 1)
        const ticketSearch = await fastify.inject({
            method: "POST",
            url: "/search_room",
            payload: {
                viewer_id: latecomer.viewerId,
                room_number: fiveBossRoom.room_number,
                api_count: 21,
            },
        })
        assert.equal(decode(ticketSearch).data.room_exists, true)
        const ticketBeforeDirectSelect = getPlayerItemSync(
            latecomer.selectedPlayerId,
            10000143,
        )
        const fiveBossDirectSelect = await fastify.inject({
            method: "POST",
            url: "/select_room",
            payload: {
                viewer_id: latecomer.viewerId,
                room_number: fiveBossRoom.room_number,
                category: 2,
                quest_id: 1099001,
                party_id: 1,
                accepted_type: 0,
                api_count: 22,
            },
        })
        assert.notEqual(decode(fiveBossDirectSelect).data.raising_state, 9)
        assert.equal(
            getPlayerItemSync(latecomer.selectedPlayerId, 10000143),
            ticketBeforeDirectSelect,
        )
        roomAdmissionRegistry.release(fiveBossRoom.room_number, latecomer.viewerId)
        const ticketAttention = await fastify.inject({
            method: "POST",
            url: "/check",
            payload: { viewer_id: latecomer.viewerId, holding_number: 0, request_number: 3 },
        })
        const fiveBossAttention = decode(ticketAttention).data.multi.find(
            item => item.quest_info.room_number === fiveBossRoom.room_number,
        )
        assert.equal(fiveBossAttention.attention_key, fiveBossRecruitment.attentionKey)
        const ticketBeforeSelect = getPlayerItemSync(latecomer.selectedPlayerId, 10000143)
        const fiveBossRescueSelect = await fastify.inject({
            method: "POST",
            url: "/select_room",
            payload: {
                viewer_id: latecomer.viewerId,
                room_number: fiveBossRoom.room_number,
                category: 2,
                quest_id: 1099001,
                party_id: 1,
                accepted_type: 2,
                api_count: 23,
            },
        })
        assert.notEqual(decode(fiveBossRescueSelect).data.raising_state, 9)
        assert.equal(
            getPlayerItemSync(latecomer.selectedPlayerId, 10000143),
            ticketBeforeSelect,
        )
        updatePlayerSync({
            id: latecomer.selectedPlayerId,
            rankPoint: rank130Threshold - 1,
        })
        const fiveBossLowRankGuestSocket = new FakeSocket()
        await handleHandshake(fiveBossLowRankGuestSocket, {
            socklet: "cooperation_room",
            viewerId: latecomer.viewerId,
            roomNumber: fiveBossRoom.room_number,
            questCategory: 2,
            questId: 1099001,
            connectionId: "five-boss-low-rank-guest",
        })
        assert.deepEqual(fiveBossLowRankGuestSocket.messages, [[3, "HANDSHAKE_DENIED"]])
        assert.equal(fiveBossLowRankGuestSocket.writable, false)

        updatePlayerSync({
            id: latecomer.selectedPlayerId,
            rankPoint: rank130Threshold,
        })
        const fiveBossDirectReselect = await fastify.inject({
            method: "POST",
            url: "/select_room",
            payload: {
                viewer_id: latecomer.viewerId,
                room_number: fiveBossRoom.room_number,
                category: 2,
                quest_id: 1099001,
                party_id: 1,
                accepted_type: 0,
                api_count: 24,
            },
        })
        assert.notEqual(decode(fiveBossDirectReselect).data.raising_state, 9)
        const fiveBossGuestSocket = new FakeSocket()
        await handleHandshake(fiveBossGuestSocket, {
            socklet: "cooperation_room",
            viewerId: latecomer.viewerId,
            roomNumber: fiveBossRoom.room_number,
            questCategory: 2,
            questId: 1099001,
            connectionId: "five-boss-rescue-guest",
        })
        const fiveBossGuestClient = sessionManager.getClient(
            latecomer.viewerId,
            fiveBossRoom.room_number,
        )
        fiveBossGuestClient.enterData = {}
        connectedClients.push(fiveBossGuestClient)
        connectedSockets.push(fiveBossGuestSocket)
        assert.equal(
            getPlayerItemSync(latecomer.selectedPlayerId, 10000143),
            ticketBeforeSelect,
        )

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

        const currentPlayId = "identity-current-play"
        const delayedPlayId = "identity-delayed-play"
        const currentQuest = {
            playerId: host.selectedPlayerId,
            playId: currentPlayId,
            questId: 9001001,
            category: 1,
            useBossBoostPoint: false,
            useBoostPoint: false,
            isAutoStartMode: false,
            isMulti: true,
            isMultiHost: true,
            roomNumber: firstRoom.room_number,
            continueCount: 0,
            startedAtMs: Date.now(),
        }
        insertPlayerActiveQuestSync(host.selectedPlayerId, currentQuest)
        activeQuests[host.selectedPlayerId] = {
            ...currentQuest,
            roomNumber: firstRoom.room_number,
        }
        const delayedBase = {
            viewer_id: host.viewerId,
            play_id: delayedPlayId,
            quest_id: 9001001,
            category: 1,
            room_number: firstRoom.room_number,
            api_count: 30,
        }
        const delayedFinish = await fastify.inject({
            method: "POST",
            url: "/finish",
            payload: {
                ...delayedBase,
                is_accomplished: true,
                elapsed_time_ms: 1000,
                score: 1,
                contribution_score: 0,
                mate_player_result: [],
            },
        })
        assert.equal(delayedFinish.statusCode, 200, delayedFinish.body)
        assert.equal(decode(delayedFinish).data.clear_rank, 0)
        assert.deepEqual(decode(delayedFinish).data.item_list, {})

        const delayedAbort = await fastify.inject({
            method: "POST",
            url: "/abort",
            payload: { ...delayedBase, api_count: 31 },
        })
        assert.equal(delayedAbort.statusCode, 200, delayedAbort.body)
        const delayedContinue = await fastify.inject({
            method: "POST",
            url: "/play_continue",
            payload: { ...delayedBase, api_count: 32 },
        })
        assert.equal(delayedContinue.statusCode, 200, delayedContinue.body)
        assert.equal(decode(delayedContinue).data.continue_count, 0)
        assert.equal(getPlayerActiveQuestSync(host.selectedPlayerId).playId, currentPlayId)
        assert.equal(activeQuests[host.selectedPlayerId].playId, currentPlayId)

        const staleRoom = createRoom(
            host.viewerId,
            host.selectedPlayerId,
            1,
            1,
            9001001,
            0,
            1,
        )
        roomNumbers.push(staleRoom.room_number)
        disbandRoom(staleRoom.room_number, "identity_stale_request")
        const staleShare = await fastify.inject({
            method: "POST",
            url: "/share_room",
            payload: {
                viewer_id: host.viewerId,
                room_number: staleRoom.room_number,
                category: 1,
                quest_id: 9001001,
                share_type_list: [1],
                api_count: 33,
            },
        })
        assert.equal(staleShare.statusCode, 200, staleShare.body)
        assert.equal(decode(staleShare).data.config.return_attention_max_num, 3)
        const stalePrepare = await fastify.inject({
            method: "POST",
            url: "/prepare",
            payload: {
                viewer_id: host.viewerId,
                room_number: staleRoom.room_number,
                category: 1,
                quest_id: 9001001,
                api_count: 34,
            },
        })
        assert.equal(stalePrepare.statusCode, 200, stalePrepare.body)
        assert.equal(decode(stalePrepare).data.raising_state, 9)
        const staleSummon = await fastify.inject({
            method: "POST",
            url: "/summon",
            payload: {
                viewer_id: host.viewerId,
                room_number: staleRoom.room_number,
                category_id: 1,
                quest_id: 9001001,
                api_count: 35,
            },
        })
        assert.equal(staleSummon.statusCode, 200, staleSummon.body)
        assert.equal(decode(staleSummon).data.mate1, null)
        assert.equal(decode(staleSummon).data.mate2, null)
        const staleStart = await fastify.inject({
            method: "POST",
            url: "/start",
            payload: {
                viewer_id: host.viewerId,
                play_id: "stale-room-start",
                quest_id: 9001001,
                category: 1,
                party_id: 1,
                use_boost_point: false,
                use_boss_boost_point: false,
                is_auto_start_mode: false,
                room_number: staleRoom.room_number,
                mate_player_ids: [],
                mate_party_ids: [],
                combat_power: 0,
                api_count: 36,
            },
        })
        assert.equal(staleStart.statusCode, 200, staleStart.body)
        assert.equal(decode(staleStart).data_headers.result_code, 4050)
        assert.equal(getPlayerActiveQuestSync(host.selectedPlayerId).playId, currentPlayId)

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
