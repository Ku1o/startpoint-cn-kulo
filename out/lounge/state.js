"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.resetLoungesForTests = exports.detachLoungeSocket = exports.disbandLounge = exports.broadcastLoungeFrame = exports.sendLoungeFrame = exports.loungeCanStart = exports.touchLoungeActivity = exports.setLoungeMemberReady = exports.serializeLoungeMates = exports.getLoungeSocketContext = exports.enterLounge = exports.attachLoungeSocket = exports.canAttachLoungeViewer = exports.setLoungeShareTypes = exports.prepareLounge = exports.matchesLoungeAccess = exports.listLounges = exports.getLoungeByNumber = exports.getLounge = exports.createLounge = exports.cleanupExpiredLounges = exports.getLoungeOccupancy = void 0;
const LOUNGE_CAPACITY = 3;
const LOUNGE_TTL_MS = 30 * 60 * 1000;
const MAX_LOUNGES = 1024;
const rooms = new Map();
const roomIdsByNumber = new Map();
const socketContexts = new WeakMap();
let loungeSequence = 0;
function nextLoungeId() {
    loungeSequence = (loungeSequence + 1) % 1000;
    return Date.now() * 1000 + loungeSequence;
}
function nextLoungeNumber() {
    for (let attempt = 0; attempt < 1000; attempt++) {
        const value = String(100000 + Math.floor(Math.random() * 900000));
        if (!roomIdsByNumber.has(value))
            return value;
    }
    return String(nextLoungeId()).slice(-6).padStart(6, "0");
}
function removeRoom(room) {
    rooms.delete(room.id);
    if (roomIdsByNumber.get(room.number) === room.id) {
        roomIdsByNumber.delete(room.number);
    }
}
function clearDisconnectedPendingSockets(room) {
    for (const [viewerId, socket] of room.pendingSockets) {
        if (socket.destroyed || !socket.writable)
            room.pendingSockets.delete(viewerId);
    }
}
function getLoungeOccupancy(room) {
    clearDisconnectedPendingSockets(room);
    let occupancy = room.members.size;
    for (const viewerId of room.pendingSockets.keys()) {
        if (!room.members.has(viewerId))
            occupancy += 1;
    }
    return occupancy;
}
exports.getLoungeOccupancy = getLoungeOccupancy;
function cleanupExpiredLounges(now = Date.now()) {
    for (const room of rooms.values()) {
        if (now - room.lastActivityAt >= LOUNGE_TTL_MS)
            disbandLounge(room);
    }
    if (rooms.size <= MAX_LOUNGES)
        return;
    const oldest = [...rooms.values()].sort((a, b) => a.lastActivityAt - b.lastActivityAt);
    for (let index = 0; rooms.size > MAX_LOUNGES && index < oldest.length; index++) {
        disbandLounge(oldest[index]);
    }
}
exports.cleanupExpiredLounges = cleanupExpiredLounges;
const cleanupTimer = setInterval(cleanupExpiredLounges, 60000);
cleanupTimer.unref();
function createLounge(input) {
    cleanupExpiredLounges();
    for (const existing of rooms.values()) {
        if (existing.hostViewerId === input.hostViewerId && existing.useCase === input.useCase) {
            removeRoom(existing);
        }
    }
    const now = Date.now();
    const room = {
        id: nextLoungeId(),
        number: nextLoungeNumber(),
        advice: input.advice,
        useCase: input.useCase,
        campaignId: input.campaignId,
        hostViewerId: input.hostViewerId,
        hostPlayerId: input.hostPlayerId,
        hostProfile: input.hostProfile,
        raisingState: 1,
        createdAt: now,
        lastActivityAt: now,
        members: new Map(),
        pendingSockets: new Map(),
        shareTypes: new Set(),
    };
    rooms.set(room.id, room);
    roomIdsByNumber.set(room.number, room.id);
    return room;
}
exports.createLounge = createLounge;
function getLounge(id) {
    cleanupExpiredLounges();
    return rooms.get(id);
}
exports.getLounge = getLounge;
function getLoungeByNumber(number) {
    cleanupExpiredLounges();
    const id = roomIdsByNumber.get(number);
    return id === undefined ? undefined : rooms.get(id);
}
exports.getLoungeByNumber = getLoungeByNumber;
function listLounges(useCase) {
    cleanupExpiredLounges();
    return [...rooms.values()]
        .filter(room => room.useCase === useCase && room.raisingState === 2 && getLoungeOccupancy(room) < LOUNGE_CAPACITY)
        .sort((a, b) => b.createdAt - a.createdAt);
}
exports.listLounges = listLounges;
function matchesLoungeAccess(room, input) {
    return room.useCase === input.useCase
        && room.advice === input.advice
        && room.hostViewerId === input.establisherViewerId;
}
exports.matchesLoungeAccess = matchesLoungeAccess;
function prepareLounge(room) {
    room.raisingState = 2;
    room.lastActivityAt = Date.now();
}
exports.prepareLounge = prepareLounge;
function setLoungeShareTypes(room, values) {
    room.shareTypes = new Set(values);
    room.lastActivityAt = Date.now();
}
exports.setLoungeShareTypes = setLoungeShareTypes;
function canAttachLoungeViewer(room, viewerId) {
    return room.raisingState === 2
        && (room.members.has(viewerId)
            || room.pendingSockets.has(viewerId)
            || getLoungeOccupancy(room) < LOUNGE_CAPACITY);
}
exports.canAttachLoungeViewer = canAttachLoungeViewer;
function attachLoungeSocket(room, viewerId, socket) {
    const existing = room.members.get(viewerId);
    const pending = room.pendingSockets.get(viewerId);
    socketContexts.set(socket, { roomId: room.id, viewerId });
    room.lastActivityAt = Date.now();
    room.pendingSockets.set(viewerId, socket);
    if (pending && pending !== socket && !pending.destroyed)
        pending.destroy();
    if (existing && existing.socket !== socket && !existing.socket.destroyed) {
        existing.socket.destroy();
    }
}
exports.attachLoungeSocket = attachLoungeSocket;
function enterLounge(socket, profile) {
    var _a, _b, _c, _d, _e;
    const context = socketContexts.get(socket);
    if (!context)
        return null;
    const room = rooms.get(context.roomId);
    if (!room || room.pendingSockets.get(context.viewerId) !== socket
        || !canAttachLoungeViewer(room, context.viewerId))
        return null;
    room.pendingSockets.delete(context.viewerId);
    const member = {
        viewerId: context.viewerId,
        profile: {
            name: String((_a = profile.name) !== null && _a !== void 0 ? _a : ""),
            characterId: Number((_b = profile.characterId) !== null && _b !== void 0 ? _b : 1),
            evolutionLevel: Number((_c = profile.evolutionLevel) !== null && _c !== void 0 ? _c : 0),
            rank: Number((_d = profile.rank) !== null && _d !== void 0 ? _d : 1),
            degreeId: Number((_e = profile.degreeId) !== null && _e !== void 0 ? _e : 1),
        },
        readyState: [1],
        socket,
    };
    room.members.set(context.viewerId, member);
    room.lastActivityAt = Date.now();
    return { room, member };
}
exports.enterLounge = enterLounge;
function getLoungeSocketContext(socket) {
    const context = socketContexts.get(socket);
    if (!context)
        return null;
    const room = rooms.get(context.roomId);
    if (!room)
        return null;
    return { room, viewerId: context.viewerId, member: room.members.get(context.viewerId) };
}
exports.getLoungeSocketContext = getLoungeSocketContext;
function serializeLoungeMates(room) {
    return [...room.members.values()].map(member => (Object.assign(Object.assign({ viewerId: member.viewerId }, member.profile), { readyState: member.readyState })));
}
exports.serializeLoungeMates = serializeLoungeMates;
function setLoungeMemberReady(room, viewerId, readyState) {
    const member = room.members.get(viewerId);
    if (!member)
        return false;
    member.readyState = readyState;
    room.lastActivityAt = Date.now();
    return true;
}
exports.setLoungeMemberReady = setLoungeMemberReady;
function touchLoungeActivity(room) {
    if (rooms.get(room.id) === room)
        room.lastActivityAt = Date.now();
}
exports.touchLoungeActivity = touchLoungeActivity;
function loungeCanStart(room) {
    return room.members.size === LOUNGE_CAPACITY
        && [...room.members.values()].every(member => Number(member.readyState[0]) === 1);
}
exports.loungeCanStart = loungeCanStart;
function sendLoungeFrame(socket, value) {
    if (socket.destroyed || !socket.writable)
        return false;
    try {
        socket.write(`${JSON.stringify(value)}\0`);
        return true;
    }
    catch (_a) {
        socket.destroy();
        return false;
    }
}
exports.sendLoungeFrame = sendLoungeFrame;
function broadcastLoungeFrame(room, value) {
    for (const member of room.members.values())
        sendLoungeFrame(member.socket, value);
}
exports.broadcastLoungeFrame = broadcastLoungeFrame;
function disbandLounge(room, message = "multibattle_room_dismissed") {
    const frame = [1, [1, message]];
    const sentSockets = new Set();
    for (const member of room.members.values()) {
        sentSockets.add(member.socket);
        sendLoungeFrame(member.socket, frame);
    }
    for (const socket of room.pendingSockets.values()) {
        if (!sentSockets.has(socket))
            sendLoungeFrame(socket, frame);
    }
    room.raisingState = 99;
    removeRoom(room);
}
exports.disbandLounge = disbandLounge;
function detachLoungeSocket(socket, explicitBye = false) {
    const context = socketContexts.get(socket);
    if (!context)
        return;
    socketContexts.delete(socket);
    const room = rooms.get(context.roomId);
    if (!room)
        return;
    const pending = room.pendingSockets.get(context.viewerId);
    if (pending === socket)
        room.pendingSockets.delete(context.viewerId);
    const member = room.members.get(context.viewerId);
    // A reconnecting viewer keeps the existing member slot while the new
    // socket completes its Enter message. The old socket must not remove it.
    if (pending && pending !== socket)
        return;
    if ((member === null || member === void 0 ? void 0 : member.socket) !== socket)
        return;
    room.members.delete(context.viewerId);
    room.lastActivityAt = Date.now();
    if (explicitBye && context.viewerId === room.hostViewerId) {
        disbandLounge(room);
        return;
    }
    if (explicitBye) {
        broadcastLoungeFrame(room, [1, [4, serializeLoungeMates(room)]]);
    }
}
exports.detachLoungeSocket = detachLoungeSocket;
function resetLoungesForTests() {
    rooms.clear();
    roomIdsByNumber.clear();
    loungeSequence = 0;
}
exports.resetLoungesForTests = resetLoungesForTests;
