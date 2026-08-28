"use strict";
// Multi battle session manager
// Atomic indexing of room clients, battle clients and per-room state machines.
// Protocol arrays follow typepacker useEnumIndex=true format (see sessionServer.ts).
Object.defineProperty(exports, "__esModule", { value: true });
exports.sessionManager = exports.SessionManager = void 0;
const types_1 = require("../types");
const ClientStateMachine_1 = require("./ClientStateMachine");
const game_logging_1 = require("../../lib/game-logging");
const reliable_send_1 = require("../tcp/reliable-send");
const chain_diagnostic_1 = require("../tcp/chain-diagnostic");
const embedded_1 = require("../coordinator/embedded");
const admission_1 = require("../room/admission");
class SessionManager {
    constructor() {
        this.clients = new Map();
        this.roomClients = new Map();
        this.battleClients = new Map();
        this.cidToBattleClient = new Map();
        this.socketClients = new WeakMap();
        this.sceneReadyClients = new Map();
        this.battleLevelNextClients = new Map();
        this.battleExpectedCount = new Map();
        this.battleHeartbeatTimers = new Map();
        this.battleLastActivityAt = new Map();
        this.battleConnectionPhase = new Map();
        this.battleSceneStartedRooms = new Set();
        this.pendingBattleLeaves = new Map();
        this.battleBarrierLogState = new Map();
        this.supersededBattleClients = new WeakSet();
        this.supersededSockets = new WeakSet();
        this.retiredLobbySockets = new WeakSet();
        this.supersededSocketBuckets = new Map();
        this.abandonedBattleTimers = new Map();
        this.settlementReturnTimers = new Map();
        this.rescueGuests = new Map();
        this.newbieRescueGuests = new Map();
        this.rescueFragmentEligibleGuests = new Map();
        this.rescueGuestWaits = new Map();
        this.rescueGuestReconnectTimers = new Map();
        this.blockedRoomRestores = new Map();
        this.hostReconnectTimers = new Map();
        this.roomConnectionGenerations = new Map();
    }
    addr(viewerId, roomNumber) {
        return `${viewerId}@${roomNumber}`;
    }
    parsePositiveDuration(name, fallback, minimum = 1000) {
        const parsed = parseInt(process.env[name] || "", 10);
        return Number.isFinite(parsed) ? Math.max(minimum, parsed) : fallback;
    }
    maxSupersededSocketsPerViewer() {
        const parsed = parseInt(process.env.MULTI_MAX_SUPERSEDED_CONNECTIONS_PER_VIEWER || "", 10);
        return Number.isFinite(parsed) ? Math.max(1, Math.min(32, parsed)) : 2;
    }
    deferSupersededSocketClose(socket, replacementIsLive) {
        const checkMs = this.parsePositiveDuration("MULTI_SUPERSEDED_SOCKET_CLOSE_MS", 60000);
        const closeWhenSafe = () => {
            if (socket.destroyed)
                return;
            // Closing the old socket while its replacement owns the room can
            // make the client show a false communication-loss dialog. Keep it
            // quarantined until the replacement/room is gone; it is no longer
            // indexed and cannot issue commands or receive broadcasts.
            if (replacementIsLive()) {
                const retry = setTimeout(closeWhenSafe, checkMs);
                retry.unref();
                return;
            }
            socket.destroy();
        };
        const timer = setTimeout(closeWhenSafe, checkMs);
        timer.unref();
        return checkMs;
    }
    quarantineSupersededSocket(ownerKey, roomNumber, socket, replacementIsLive) {
        this.supersededSockets.add(socket);
        let bucket = this.supersededSocketBuckets.get(ownerKey);
        if (!bucket) {
            bucket = { roomNumber, sockets: new Set() };
            this.supersededSocketBuckets.set(ownerKey, bucket);
        }
        bucket.sockets.add(socket);
        socket.once("close", () => {
            const current = this.supersededSocketBuckets.get(ownerKey);
            current === null || current === void 0 ? void 0 : current.sockets.delete(socket);
            if ((current === null || current === void 0 ? void 0 : current.sockets.size) === 0)
                this.supersededSocketBuckets.delete(ownerKey);
        });
        const maximum = this.maxSupersededSocketsPerViewer();
        while (bucket.sockets.size > maximum) {
            const oldest = bucket.sockets.values().next().value;
            if (!oldest)
                break;
            bucket.sockets.delete(oldest);
            if (!oldest.destroyed)
                oldest.destroy();
        }
        return this.deferSupersededSocketClose(socket, replacementIsLive);
    }
    closeSupersededSocketsForRoom(roomNumber) {
        for (const [ownerKey, bucket] of this.supersededSocketBuckets) {
            if (bucket.roomNumber !== roomNumber)
                continue;
            this.supersededSocketBuckets.delete(ownerKey);
            for (const socket of bucket.sockets) {
                if (!socket.destroyed)
                    socket.destroy();
            }
        }
    }
    retireDisbandedLobbySocket(socket, roomNumber) {
        this.retiredLobbySockets.add(socket);
        if (socket.destroyed)
            return;
        // The CN client handles Disbanded by sending Bye and closing this
        // socket itself.  A server FIN queued immediately after Disbanded can
        // be processed as SocketError after the client has already cleared its
        // cooperationRoomStatus, which makes the client throw C5805.  Keep the
        // socket quarantined long enough for both the final frame and the
        // client's intentional close, then reclaim an unresponsive peer.
        const sendQueueMaxAgeMs = this.parsePositiveDuration("MULTI_SEND_QUEUE_MAX_AGE_MS", 15000);
        const fallbackGraceMs = sendQueueMaxAgeMs + 5000;
        const graceMs = this.parsePositiveDuration("MULTI_DISBAND_SOCKET_GRACE_MS", fallbackGraceMs);
        const timer = setTimeout(() => {
            if (socket.destroyed)
                return;
            (0, game_logging_1.gameVerboseLog)(() => `[MULTI] forcing retired lobby socket closed: room=${roomNumber}`
                + ` graceMs=${graceMs}`);
            socket.destroy();
        }, graceMs);
        timer.unref();
        socket.once("close", () => clearTimeout(timer));
    }
    clearBattleHeartbeatLease(connectionId) {
        const timer = this.battleHeartbeatTimers.get(connectionId);
        if (timer)
            clearTimeout(timer);
        this.battleHeartbeatTimers.delete(connectionId);
        this.battleLastActivityAt.delete(connectionId);
        this.battleConnectionPhase.delete(connectionId);
    }
    armBattleLoadingLease(connectionId) {
        const client = this.cidToBattleClient.get(connectionId);
        if (!client || client.socket.destroyed)
            return;
        const leaseMs = this.parsePositiveDuration("BATTLE_LOADING_LEASE_MS", 60000, 10000);
        const previous = this.battleHeartbeatTimers.get(connectionId);
        if (previous)
            clearTimeout(previous);
        this.battleConnectionPhase.set(connectionId, "loading");
        this.battleLastActivityAt.set(connectionId, Date.now());
        const timer = setTimeout(() => {
            this.battleHeartbeatTimers.delete(connectionId);
            const current = this.cidToBattleClient.get(connectionId);
            if (!current || current.socket.destroyed
                || this.battleConnectionPhase.get(connectionId) !== "loading")
                return;
            console.warn(`[MULTI] battle loading timed out: room=${current.roomNumber}`
                + ` viewer=${current.viewerId} connection=${connectionId} timeoutMs=${leaseMs}`);
            current.socket.destroy();
        }, leaseMs);
        timer.unref();
        this.battleHeartbeatTimers.set(connectionId, timer);
    }
    scheduleBattleActivityLease(connectionId, delayMs) {
        const client = this.cidToBattleClient.get(connectionId);
        if (!client || client.socket.destroyed)
            return;
        const leaseMs = this.parsePositiveDuration("BATTLE_HEARTBEAT_LEASE_MS", 25000, 5000);
        const previous = this.battleHeartbeatTimers.get(connectionId);
        if (previous)
            clearTimeout(previous);
        const timer = setTimeout(() => {
            var _a;
            this.battleHeartbeatTimers.delete(connectionId);
            const current = this.cidToBattleClient.get(connectionId);
            if (!current || current.socket.destroyed) {
                this.battleLastActivityAt.delete(connectionId);
                return;
            }
            const inactiveMs = Date.now() - ((_a = this.battleLastActivityAt.get(connectionId)) !== null && _a !== void 0 ? _a : 0);
            if (inactiveMs < leaseMs) {
                this.scheduleBattleActivityLease(connectionId, Math.max(1, leaseMs - inactiveMs));
                return;
            }
            console.warn(`[MULTI] real battle connection heartbeat expired: room=${current.roomNumber}`
                + ` viewer=${current.viewerId} connection=${connectionId} inactiveMs=${inactiveMs}`);
            // Destroy only a battle socket that completed the real handshake.
            // Its normal close handler performs the native Leave path using the
            // connection id already known by every remaining client.
            current.socket.destroy();
        }, delayMs);
        timer.unref();
        this.battleHeartbeatTimers.set(connectionId, timer);
    }
    armActiveBattleHeartbeatLease(connectionId) {
        const client = this.cidToBattleClient.get(connectionId);
        if (!client || client.socket.destroyed)
            return;
        const leaseMs = this.parsePositiveDuration("BATTLE_HEARTBEAT_LEASE_MS", 25000, 5000);
        this.battleConnectionPhase.set(connectionId, "active");
        this.battleLastActivityAt.set(connectionId, Date.now());
        this.scheduleBattleActivityLease(connectionId, leaseMs);
    }
    armBattleReadyHeartbeatLease(connectionId) {
        const client = this.cidToBattleClient.get(connectionId);
        if (!client || client.socket.destroyed)
            return;
        const leaseMs = this.parsePositiveDuration("BATTLE_HEARTBEAT_LEASE_MS", 25000, 5000);
        this.battleConnectionPhase.set(connectionId, "ready");
        this.battleLastActivityAt.set(connectionId, Date.now());
        this.scheduleBattleActivityLease(connectionId, leaseMs);
    }
    noteBattleActivity(connectionId) {
        if (!this.cidToBattleClient.has(connectionId))
            return;
        // Loading has a fixed upper bound and is deliberately not governed by
        // the activity heartbeat. SceneReady switches the connection to the
        // renewable ready lease; barrier release promotes it to active.
        const phase = this.battleConnectionPhase.get(connectionId);
        if (phase === "ready" || phase === "active") {
            // One timer per ready/active connection is enough. Per-packet traffic
            // only advances the deadline timestamp; the timer reschedules for
            // the exact remaining lease when it wakes up.
            this.battleLastActivityAt.set(connectionId, Date.now());
        }
    }
    indexClientSocket(client) {
        this.socketClients.set(client.socket, client);
    }
    unindexClientSocket(client) {
        if (this.socketClients.get(client.socket) === client) {
            this.socketClients.delete(client.socket);
        }
    }
    logBattleBarrierState(roomNumber, reason) {
        var _a, _b, _c, _d, _e;
        const expected = (_a = this.battleExpectedCount.get(roomNumber)) !== null && _a !== void 0 ? _a : 0;
        const connected = (_c = (_b = this.battleClients.get(roomNumber)) === null || _b === void 0 ? void 0 : _b.size) !== null && _c !== void 0 ? _c : 0;
        const ready = (_e = (_d = this.sceneReadyClients.get(roomNumber)) === null || _d === void 0 ? void 0 : _d.size) !== null && _e !== void 0 ? _e : 0;
        const generation = (() => {
            var _a, _b;
            try {
                return Number((_b = (_a = require("../room/manager").getRoom(roomNumber)) === null || _a === void 0 ? void 0 : _a.lobby_generation) !== null && _b !== void 0 ? _b : 0);
            }
            catch (_c) {
                return 0;
            }
        })();
        const signature = `${generation}:${expected}:${connected}:${ready}:${reason}`;
        if (this.battleBarrierLogState.get(roomNumber) === signature)
            return;
        this.battleBarrierLogState.set(roomNumber, signature);
        console.log(`[MULTI-BARRIER] room=${roomNumber} generation=${generation}`
            + ` expected=${expected} connected=${connected} ready=${ready} reason=${reason}`);
    }
    releaseSceneReadyBarrierIfSatisfied(roomNumber, reason) {
        var _a, _b, _c, _d, _e;
        const expected = (_a = this.battleExpectedCount.get(roomNumber)) !== null && _a !== void 0 ? _a : 0;
        if (expected <= 0)
            return false;
        const connected = (_c = (_b = this.battleClients.get(roomNumber)) === null || _b === void 0 ? void 0 : _b.size) !== null && _c !== void 0 ? _c : 0;
        const ready = (_e = (_d = this.sceneReadyClients.get(roomNumber)) === null || _d === void 0 ? void 0 : _d.size) !== null && _e !== void 0 ? _e : 0;
        this.logBattleBarrierState(roomNumber, reason);
        if (connected <= 0 || ready < expected || ready < connected)
            return false;
        this.battleExpectedCount.set(roomNumber, 0);
        this.battleLevelNextClients.delete(roomNumber);
        this.logBattleBarrierState(roomNumber, `${reason}:released`);
        return true;
    }
    queueBattleLeave(roomNumber, connectionId) {
        let pending = this.pendingBattleLeaves.get(roomNumber);
        if (!pending) {
            pending = new Set();
            this.pendingBattleLeaves.set(roomNumber, pending);
        }
        pending.add(connectionId);
    }
    broadcastBattleLeave(roomNumber, connectionId) {
        for (const client of this.getConnectedBattleClients(roomNumber)) {
            if (client.connectionId === connectionId)
                continue;
            this.sendJson(client.socket, [1, [0, connectionId]]);
        }
    }
    activateBattleScene(roomNumber) {
        const clients = this.getConnectedBattleClients(roomNumber);
        this.battleSceneStartedRooms.add(roomNumber);
        // Promote the entire room together. SceneReady means only that one
        // client finished loading; treating it as active before this point can
        // publish Leave to peers that are still constructing their battle.
        for (const client of clients) {
            this.armActiveBattleHeartbeatLease(client.connectionId);
        }
        for (const client of clients) {
            this.sendJson(client.socket, [1, [1]]);
        }
        // Every survivor must observe BattleStart before AI takeover. Sending
        // Leave earlier lets differently loaded clients build divergent local
        // battle/chain state and can stall subsequent chain activations.
        const pending = this.pendingBattleLeaves.get(roomNumber);
        this.pendingBattleLeaves.delete(roomNumber);
        for (const connectionId of pending !== null && pending !== void 0 ? pending : []) {
            this.broadcastBattleLeave(roomNumber, connectionId);
        }
    }
    getConnectedBattleClients(roomNumber) {
        var _a;
        const result = [];
        for (const connectionId of (_a = this.battleClients.get(roomNumber)) !== null && _a !== void 0 ? _a : []) {
            const client = this.cidToBattleClient.get(connectionId);
            if (client && !client.socket.destroyed)
                result.push(client);
        }
        return result;
    }
    clearBattleHeartbeatLeasesForRoom(roomNumber) {
        for (const [connectionId, client] of this.cidToBattleClient) {
            if (client.roomNumber === roomNumber)
                this.clearBattleHeartbeatLease(connectionId);
        }
    }
    clearRescueGuestWait(roomNumber, viewerId) {
        const key = this.addr(viewerId, roomNumber);
        const wait = this.rescueGuestWaits.get(key);
        if (!wait)
            return;
        clearTimeout(wait.warningTimer);
        clearTimeout(wait.ejectTimer);
        this.rescueGuestWaits.delete(key);
    }
    clearRescueGuestReconnect(roomNumber, viewerId) {
        const key = this.addr(viewerId, roomNumber);
        const timer = this.rescueGuestReconnectTimers.get(key);
        if (timer)
            clearTimeout(timer);
        this.rescueGuestReconnectTimers.delete(key);
    }
    markRescueGuest(roomNumber, viewerId, isNewbieRescue = false, isFragmentRewardEligible = false) {
        var _a, _b, _c;
        let viewers = this.rescueGuests.get(roomNumber);
        if (!viewers) {
            viewers = new Set();
            this.rescueGuests.set(roomNumber, viewers);
        }
        viewers.add(viewerId);
        if (isNewbieRescue) {
            let newbieViewers = this.newbieRescueGuests.get(roomNumber);
            if (!newbieViewers) {
                newbieViewers = new Set();
                this.newbieRescueGuests.set(roomNumber, newbieViewers);
            }
            newbieViewers.add(viewerId);
        }
        else {
            (_a = this.newbieRescueGuests.get(roomNumber)) === null || _a === void 0 ? void 0 : _a.delete(viewerId);
        }
        if (isFragmentRewardEligible) {
            let eligibleViewers = this.rescueFragmentEligibleGuests.get(roomNumber);
            if (!eligibleViewers) {
                eligibleViewers = new Set();
                this.rescueFragmentEligibleGuests.set(roomNumber, eligibleViewers);
            }
            eligibleViewers.add(viewerId);
        }
        else {
            (_b = this.rescueFragmentEligibleGuests.get(roomNumber)) === null || _b === void 0 ? void 0 : _b.delete(viewerId);
        }
        (_c = this.blockedRoomRestores.get(roomNumber)) === null || _c === void 0 ? void 0 : _c.delete(viewerId);
        this.clearRescueGuestReconnect(roomNumber, viewerId);
    }
    isRescueGuest(roomNumber, viewerId) {
        var _a, _b;
        return (_b = (_a = this.rescueGuests.get(roomNumber)) === null || _a === void 0 ? void 0 : _a.has(viewerId)) !== null && _b !== void 0 ? _b : false;
    }
    isNewbieRescueGuest(roomNumber, viewerId) {
        var _a, _b;
        return (_b = (_a = this.newbieRescueGuests.get(roomNumber)) === null || _a === void 0 ? void 0 : _a.has(viewerId)) !== null && _b !== void 0 ? _b : false;
    }
    isRescueFragmentEligibleGuest(roomNumber, viewerId) {
        var _a, _b;
        return (_b = (_a = this.rescueFragmentEligibleGuests.get(roomNumber)) === null || _a === void 0 ? void 0 : _a.has(viewerId)) !== null && _b !== void 0 ? _b : false;
    }
    isRoomRestoreBlocked(roomNumber, viewerId) {
        var _a, _b;
        return (_b = (_a = this.blockedRoomRestores.get(roomNumber)) === null || _a === void 0 ? void 0 : _a.has(viewerId)) !== null && _b !== void 0 ? _b : false;
    }
    beginRescueGuestWait(client) {
        var _a;
        if (!this.isRescueGuest(client.roomNumber, client.viewerId))
            return;
        const key = this.addr(client.viewerId, client.roomNumber);
        this.clearRescueGuestReconnect(client.roomNumber, client.viewerId);
        (_a = this.blockedRoomRestores.get(client.roomNumber)) === null || _a === void 0 ? void 0 : _a.delete(client.viewerId);
        const existing = this.rescueGuestWaits.get(key);
        if (existing && existing.ready === client.isReady) {
            const remainingSeconds = Math.max(1, Math.ceil((existing.deadline - Date.now()) / 1000));
            if (remainingSeconds <= 30)
                this.sendJson(client.socket, [1, [7, remainingSeconds]]);
            return;
        }
        if (existing)
            this.clearRescueGuestWait(client.roomNumber, client.viewerId);
        // A ready rescue guest is actively waiting for the host to start and
        // must not be mistaken for an abandoned visitor by the short idle
        // timeout. Keep an eventual release path because the official client
        // has no Leave button, but give prepared guests a much longer window.
        const waitMs = client.isReady
            ? this.parsePositiveDuration("RESCUE_GUEST_READY_WAIT_MS", 600000, 10000)
            : this.parsePositiveDuration("RESCUE_GUEST_WAIT_MS", 180000, 2000);
        const ready = client.isReady;
        const warningMs = Math.min(waitMs, this.parsePositiveDuration("RESCUE_GUEST_WARNING_MS", 30000, 1000));
        const deadline = Date.now() + waitMs;
        const warningTimer = setTimeout(() => {
            const current = this.getClient(client.viewerId, client.roomNumber);
            if (!current || current.enterData === null || current.isBattle)
                return;
            if (current.isReady !== ready) {
                this.clearRescueGuestWait(client.roomNumber, client.viewerId);
                this.beginRescueGuestWait(current);
                return;
            }
            this.sendJson(current.socket, [1, [7, Math.max(1, Math.ceil(warningMs / 1000))]]);
            console.warn(`[MULTI] rescue guest timeout warning: viewer=${client.viewerId} room=${client.roomNumber} seconds=${Math.ceil(warningMs / 1000)}`);
        }, Math.max(0, waitMs - warningMs));
        warningTimer.unref();
        const ejectTimer = setTimeout(() => {
            void embedded_1.embeddedMultiCoordinator.enqueueRoomCommand(client.roomNumber, () => {
                const current = this.getClient(client.viewerId, client.roomNumber);
                if (current && !current.isBattle && current.isReady !== ready) {
                    this.clearRescueGuestWait(client.roomNumber, client.viewerId);
                    this.beginRescueGuestWait(current);
                    return;
                }
                this.ejectRescueGuest(client.roomNumber, client.viewerId, "rescue_wait_timeout");
            }).catch(error => console.error(`[MULTI] rescue wait timeout failed: room=${client.roomNumber} viewer=${client.viewerId}`, error));
        }, waitMs);
        ejectTimer.unref();
        this.rescueGuestWaits.set(key, { deadline, ready, warningTimer, ejectTimer });
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] rescue guest wait started: viewer=${client.viewerId} room=${client.roomNumber} ready=${ready} waitMs=${waitMs}`);
    }
    clearRescueGuestLobbyWait(roomNumber, viewerId) {
        this.clearRescueGuestWait(roomNumber, viewerId);
    }
    beginRescueGuestReconnectGrace(client) {
        if (client.isBattle || !this.isRescueGuest(client.roomNumber, client.viewerId))
            return;
        const key = this.addr(client.viewerId, client.roomNumber);
        if (this.rescueGuestReconnectTimers.has(key))
            return;
        const reconnectMs = this.parsePositiveDuration("RESCUE_GUEST_RECONNECT_GRACE_MS", 25000);
        const timer = setTimeout(() => {
            void embedded_1.embeddedMultiCoordinator.enqueueRoomCommand(client.roomNumber, () => {
                if (this.rescueGuestReconnectTimers.get(key) !== timer)
                    return;
                this.rescueGuestReconnectTimers.delete(key);
                const current = this.getClient(client.viewerId, client.roomNumber);
                if (current && !current.isBattle)
                    return;
                this.ejectRescueGuest(client.roomNumber, client.viewerId, "rescue_reconnect_timeout");
            }).catch(error => console.error(`[MULTI] rescue reconnect timeout failed: room=${client.roomNumber} viewer=${client.viewerId}`, error));
        }, reconnectMs);
        timer.unref();
        this.rescueGuestReconnectTimers.set(key, timer);
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] rescue guest reconnect grace started: viewer=${client.viewerId} room=${client.roomNumber} graceMs=${reconnectMs}`);
    }
    ejectRescueGuest(roomNumber, viewerId, reason) {
        var _a, _b, _c, _d, _e;
        this.clearRescueGuestWait(roomNumber, viewerId);
        this.clearRescueGuestReconnect(roomNumber, viewerId);
        (_a = this.rescueGuests.get(roomNumber)) === null || _a === void 0 ? void 0 : _a.delete(viewerId);
        (_b = this.newbieRescueGuests.get(roomNumber)) === null || _b === void 0 ? void 0 : _b.delete(viewerId);
        (_c = this.rescueFragmentEligibleGuests.get(roomNumber)) === null || _c === void 0 ? void 0 : _c.delete(viewerId);
        let blocked = this.blockedRoomRestores.get(roomNumber);
        if (!blocked) {
            blocked = new Set();
            this.blockedRoomRestores.set(roomNumber, blocked);
        }
        blocked.add(viewerId);
        try {
            const { removeRoomMember } = require("../room/manager");
            removeRoomMember(roomNumber, viewerId);
        }
        catch (e) { }
        try {
            const { suppressRandomRecruitmentForViewer } = require("../recruitment");
            suppressRandomRecruitmentForViewer(roomNumber, viewerId);
        }
        catch (e) { }
        const current = this.getClient(viewerId, roomNumber);
        if (current && !current.isBattle) {
            this.removeClient(current);
            try {
                current.socket.end();
            }
            catch (e) { }
            setTimeout(() => {
                try {
                    current.socket.destroy();
                }
                catch (e) { }
            }, 250).unref();
        }
        try {
            const lobby = require("../tcp/lobby");
            (_d = lobby.scheduleRematchDisconnectCleanup) === null || _d === void 0 ? void 0 : _d.call(lobby, roomNumber);
            (_e = lobby.scheduleNpcReconcile) === null || _e === void 0 ? void 0 : _e.call(lobby, roomNumber);
        }
        catch (e) { }
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] rescue guest released: viewer=${viewerId} room=${roomNumber} reason=${reason}`);
    }
    beginHostReconnectGrace(roomNumber) {
        if (this.hostReconnectTimers.has(roomNumber))
            return;
        let roomInstanceId;
        let roomGeneration;
        try {
            const { getRoom } = require("../room/manager");
            const room = getRoom(roomNumber);
            if (!room)
                return;
            roomInstanceId = embedded_1.embeddedMultiCoordinator.ensureLifecycle(room).instanceId;
            roomGeneration = room.lobby_generation;
        }
        catch (e) {
            return;
        }
        const reconnectMs = this.parsePositiveDuration("MULTI_HOST_RECONNECT_GRACE_MS", 25000);
        const timer = setTimeout(() => {
            void embedded_1.embeddedMultiCoordinator.enqueueRoomCommand(roomNumber, () => {
                if (this.hostReconnectTimers.get(roomNumber) !== timer)
                    return;
                this.hostReconnectTimers.delete(roomNumber);
                try {
                    const { getRoom } = require("../room/manager");
                    const room = getRoom(roomNumber);
                    if (!embedded_1.embeddedMultiCoordinator.isCurrentInstance(room, roomInstanceId)
                        || room.lobby_generation !== roomGeneration
                        || room.lifecycle.phase === "BATTLE")
                        return;
                    if (this.isHostOnline(room.host_viewer_id, roomNumber, roomGeneration))
                        return;
                    this.commitRoomDisband(roomNumber, "host_reconnect_timeout");
                }
                catch (e) { }
            }).catch(error => console.error(`[MULTI] host reconnect timeout failed: room=${roomNumber}`, error));
        }, reconnectMs);
        timer.unref();
        this.hostReconnectTimers.set(roomNumber, timer);
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] host reconnect grace started: room=${roomNumber} graceMs=${reconnectMs}`);
    }
    cancelHostReconnectGrace(roomNumber) {
        const timer = this.hostReconnectTimers.get(roomNumber);
        if (timer)
            clearTimeout(timer);
        this.hostReconnectTimers.delete(roomNumber);
    }
    clearRescueGuestStateForRoom(roomNumber) {
        var _a, _b;
        const viewers = new Set([
            ...((_a = this.rescueGuests.get(roomNumber)) !== null && _a !== void 0 ? _a : []),
            ...((_b = this.blockedRoomRestores.get(roomNumber)) !== null && _b !== void 0 ? _b : []),
        ]);
        for (const viewerId of viewers) {
            this.clearRescueGuestWait(roomNumber, viewerId);
            this.clearRescueGuestReconnect(roomNumber, viewerId);
        }
        this.rescueGuests.delete(roomNumber);
        this.newbieRescueGuests.delete(roomNumber);
        this.rescueFragmentEligibleGuests.delete(roomNumber);
        this.blockedRoomRestores.delete(roomNumber);
    }
    commitRoomDisband(roomNumber, reason) {
        const roomClients = this.getClientsInRoom(roomNumber);
        const lobbyClients = roomClients.filter(client => !client.isBattle);
        const battleClients = this.getConnectedBattleClients(roomNumber);
        const allClients = [...new Set([...roomClients, ...battleClients])];
        this.clearBattleHeartbeatLeasesForRoom(roomNumber);
        let deleted = false;
        try {
            const { disbandRoom } = require("../room/manager");
            // Commit the room as non-joinable before telling clients that it
            // was dismissed.  This makes the protocol message truthful even
            // when a client immediately tries restore_room/select_room.
            deleted = disbandRoom(roomNumber, reason);
        }
        catch (e) {
            this.removeRoomState(roomNumber);
        }
        if (!deleted)
            return false;
        // MeetingServerMessage.Disbanded is valid only on cooperation_room.
        // Sending its enum index (6) to cooperation_battle makes the battle
        // unserializer dereference a missing enum entry and crash with C5602.
        const notifiedLobbySockets = new Set();
        for (const client of lobbyClients) {
            const sendResult = this.sendJson(client.socket, [1, [6, "multibattle_room_dismissed"]], {
                roomNumber,
                connectionId: client.connectionId,
                viewerId: client.viewerId,
                roomGeneration: client.roomGeneration,
                channel: "room_disband",
            });
            if (sendResult !== "closed")
                notifiedLobbySockets.add(client.socket);
        }
        for (const client of allClients) {
            const addr = this.addr(client.viewerId, roomNumber);
            if (this.clients.get(addr) === client)
                this.clients.delete(addr);
            if (client.isBattle)
                this.cidToBattleClient.delete(client.connectionId);
            this.unindexClientSocket(client);
            if (!client.isBattle && notifiedLobbySockets.has(client.socket)) {
                this.retireDisbandedLobbySocket(client.socket, roomNumber);
            }
            else {
                try {
                    client.socket.end();
                }
                catch (e) { }
                setTimeout(() => {
                    try {
                        client.socket.destroy();
                    }
                    catch (e) { }
                }, 250).unref();
            }
        }
        this.closeSupersededSocketsForRoom(roomNumber);
        this.roomClients.delete(roomNumber);
        this.battleClients.delete(roomNumber);
        this.sceneReadyClients.delete(roomNumber);
        this.battleLevelNextClients.delete(roomNumber);
        this.battleExpectedCount.delete(roomNumber);
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] room disbanded: room=${roomNumber} reason=${reason}`);
        return true;
    }
    disbandRoomIfNoRealConnections(roomNumber, battleRoomTimeoutExpired = false) {
        var _a, _b, _c, _d;
        const lobbyConnectionCount = (_b = (_a = this.roomClients.get(roomNumber)) === null || _a === void 0 ? void 0 : _a.size) !== null && _b !== void 0 ? _b : 0;
        const battleConnectionCount = (_d = (_c = this.battleClients.get(roomNumber)) === null || _c === void 0 ? void 0 : _c.size) !== null && _d !== void 0 ? _d : 0;
        if (lobbyConnectionCount > 0 || battleConnectionCount > 0)
            return;
        if (this.hostReconnectTimers.has(roomNumber))
            return;
        try {
            const { getRoom } = require("../room/manager");
            const room = getRoom(roomNumber);
            if (!room)
                return;
            // The CN client closes the battle TCP socket as soon as the battle
            // scene has been initialized. The actual fight can then continue
            // client-side for minutes, so the 25-second reconnect grace must not
            // start here or the room can disappear before /finish is sent.
            // Keep only a long abandoned-battle watchdog for clients that never
            // send either /finish or /abort.
            if (room.lifecycle.phase === "BATTLE" && !battleRoomTimeoutExpired) {
                if (!this.abandonedBattleTimers.has(roomNumber)) {
                    const battleRoomTimeoutMs = parseInt(process.env.BATTLE_ROOM_TIMEOUT_MS || "900000");
                    const lifecycle = embedded_1.embeddedMultiCoordinator.ensureLifecycle(room);
                    const roomInstanceId = lifecycle.instanceId;
                    const battleSessionId = lifecycle.battleSessionId;
                    const timer = setTimeout(() => {
                        void embedded_1.embeddedMultiCoordinator.enqueueRoomCommand(roomNumber, () => {
                            if (this.abandonedBattleTimers.get(roomNumber) !== timer)
                                return;
                            this.abandonedBattleTimers.delete(roomNumber);
                            const currentRoom = getRoom(roomNumber);
                            if (!embedded_1.embeddedMultiCoordinator.isCurrentInstance(currentRoom, roomInstanceId)
                                || currentRoom.lifecycle.battleSessionId !== battleSessionId
                                || currentRoom.lifecycle.phase !== "BATTLE")
                                return;
                            this.disbandRoomIfNoRealConnections(roomNumber, true);
                        }).catch(error => console.error(`[MULTI] abandoned battle timeout failed: room=${roomNumber}`, error));
                    }, battleRoomTimeoutMs);
                    timer.unref();
                    this.abandonedBattleTimers.set(roomNumber, timer);
                    (0, game_logging_1.gameVerboseLog)(() => `[MULTI] waiting for battle finish: room=${roomNumber} timeoutMs=${battleRoomTimeoutMs}`);
                }
                return;
            }
            // Successful settlement has its own timer, deliberately separate
            // from REMATCH_RECONNECT_GRACE_MS. The latter starts only after the
            // return lobby exists and is used to wait for missing real players.
            if (room.settlement_return_pending)
                return;
            const pendingTimer = this.abandonedBattleTimers.get(roomNumber);
            if (pendingTimer)
                clearTimeout(pendingTimer);
            this.abandonedBattleTimers.delete(roomNumber);
            this.roomClients.delete(roomNumber);
            this.battleClients.delete(roomNumber);
            this.sceneReadyClients.delete(roomNumber);
            this.battleLevelNextClients.delete(roomNumber);
            this.battleExpectedCount.delete(roomNumber);
            try {
                const { stopRandomRecruitment } = require("../recruitment");
                stopRandomRecruitment(roomNumber);
            }
            catch (e) { }
            this.commitRoomDisband(roomNumber, "all_real_connections_closed");
            (0, game_logging_1.gameVerboseLog)(() => `[MULTI] room disbanded: all real connections closed room=${roomNumber}`);
        }
        catch (e) { }
    }
    beginSettlementReturnGrace(roomNumber) {
        const existingTimer = this.settlementReturnTimers.get(roomNumber);
        if (existingTimer)
            clearTimeout(existingTimer);
        this.settlementReturnTimers.delete(roomNumber);
        const abandonedTimer = this.abandonedBattleTimers.get(roomNumber);
        if (abandonedTimer)
            clearTimeout(abandonedTimer);
        this.abandonedBattleTimers.delete(roomNumber);
        let roomInstanceId;
        let lifecycleVersion;
        try {
            const { getRoom } = require("../room/manager");
            const room = getRoom(roomNumber);
            if (!room || room.lifecycle.phase !== "RETURNING")
                return;
            const lifecycle = embedded_1.embeddedMultiCoordinator.ensureLifecycle(room);
            roomInstanceId = lifecycle.instanceId;
            lifecycleVersion = lifecycle.version;
        }
        catch (e) {
            return;
        }
        const settlementReturnGraceMs = parseInt(process.env.SETTLEMENT_RETURN_GRACE_MS || "60000");
        const timer = setTimeout(() => {
            void embedded_1.embeddedMultiCoordinator.enqueueRoomCommand(roomNumber, () => {
                if (this.settlementReturnTimers.get(roomNumber) !== timer)
                    return;
                this.settlementReturnTimers.delete(roomNumber);
                try {
                    const { getRoom } = require("../room/manager");
                    const room = getRoom(roomNumber);
                    if (!embedded_1.embeddedMultiCoordinator.isCurrentInstance(room, roomInstanceId)
                        || room.lifecycle.version !== lifecycleVersion
                        || room.lifecycle.phase !== "RETURNING"
                        || !room.settlement_return_pending)
                        return;
                    // Only the host completing the lobby Enter flow counts as a
                    // successful room return. Guests may wait during the grace
                    // period, but they must not keep a hostless room alive.
                    this.commitRoomDisband(roomNumber, "settlement_host_return_timeout");
                    console.warn(`[MULTI] room disbanded: host did not return after settlement room=${roomNumber}`);
                }
                catch (e) { }
            }).catch(error => console.error(`[MULTI] settlement return timeout failed: room=${roomNumber}`, error));
        }, settlementReturnGraceMs);
        timer.unref();
        this.settlementReturnTimers.set(roomNumber, timer);
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] waiting for settlement lobby return: room=${roomNumber} graceMs=${settlementReturnGraceMs}`);
    }
    completeSettlementReturn(roomNumber) {
        const pendingTimer = this.settlementReturnTimers.get(roomNumber);
        if (pendingTimer)
            clearTimeout(pendingTimer);
        this.settlementReturnTimers.delete(roomNumber);
        let roomGeneration;
        try {
            const { getRoom } = require("../room/manager");
            const room = getRoom(roomNumber);
            if (room) {
                embedded_1.embeddedMultiCoordinator.completeSettlementReturn(room);
                roomGeneration = room.lobby_generation;
            }
        }
        catch (e) { }
        try {
            // Keep room lifetime and settlement eligibility independent.  A
            // successful host return advances retained finish snapshots to
            // LOBBY, but they remain replayable for their short TTL.
            const { transitionRoomSettlementSnapshots } = require("../settlement-snapshot");
            if (roomGeneration !== undefined) {
                transitionRoomSettlementSnapshots(roomNumber, "LOBBY", roomGeneration);
            }
        }
        catch (e) { }
        (0, game_logging_1.gameVerboseLog)(() => `[MULTI] settlement host returned: room=${roomNumber}`);
    }
    createClient(socket, viewerId, roomNumber, connectionId, playerId) {
        return {
            socket,
            viewerId,
            roomNumber,
            connectionId,
            playerId,
            isBattle: false,
            isReady: false,
            buffer: "",
            mates: [],
            enterData: null,
            roomGeneration: 0,
            connectionGeneration: 0,
            superseded: false,
            connectedAt: Date.now(),
            admissionClaimed: false,
            clientState: new ClientStateMachine_1.ClientStateMachine(types_1.ClientState.Connecting),
            battleState: types_1.BattleState.Initializing,
        };
    }
    getClient(viewerId, roomNumber) {
        return this.clients.get(this.addr(viewerId, roomNumber));
    }
    getRoomClientByConnectionId(roomNumber, connectionId) {
        for (const client of this.getClientsInRoom(roomNumber)) {
            if (!client.isBattle && client.connectionId === connectionId)
                return client;
        }
        return undefined;
    }
    addClientToRoom(client) {
        var _a;
        const addr = this.addr(client.viewerId, client.roomNumber);
        const previous = this.clients.get(addr);
        const nextConnectionGeneration = ((_a = this.roomConnectionGenerations.get(addr)) !== null && _a !== void 0 ? _a : 0) + 1;
        this.roomConnectionGenerations.set(addr, nextConnectionGeneration);
        client.connectionGeneration = nextConnectionGeneration;
        client.superseded = false;
        this.clients.set(addr, client);
        if (previous && previous !== client && previous.socket !== client.socket) {
            previous.superseded = true;
            this.unindexClientSocket(previous);
            (0, reliable_send_1.clearReliableSendState)(previous.socket);
            const closeCheckMs = this.quarantineSupersededSocket(`lobby:${addr}`, client.roomNumber, previous.socket, () => {
                const current = this.clients.get(addr);
                return !!current && current !== previous && !current.socket.destroyed;
            });
            (0, game_logging_1.gameVerboseLog)(() => `[MULTI] room connection superseded: viewer=${client.viewerId}`
                + ` room=${client.roomNumber} oldGeneration=${previous.connectionGeneration}`
                + ` newGeneration=${client.connectionGeneration} closeCheckMs=${closeCheckMs}`);
        }
        this.indexClientSocket(client);
        let set = this.roomClients.get(client.roomNumber);
        if (!set) {
            set = new Set();
            this.roomClients.set(client.roomNumber, set);
        }
        set.add(addr);
        if (this.isRescueGuest(client.roomNumber, client.viewerId)) {
            this.clearRescueGuestReconnect(client.roomNumber, client.viewerId);
        }
        return { ok: true, value: undefined };
    }
    removeClient(client) {
        var _a, _b, _c, _d, _e, _f, _g;
        this.unindexClientSocket(client);
        if (!client.isBattle && client.admissionClaimed) {
            admission_1.roomAdmissionRegistry.releaseClaim(client.roomNumber, (_a = client.admissionGeneration) !== null && _a !== void 0 ? _a : client.roomGeneration, client.viewerId, client.connectionId);
            client.admissionClaimed = false;
        }
        const addr = this.addr(client.viewerId, client.roomNumber);
        const isCurrentConnection = this.clients.get(addr) === client;
        if (!client.isBattle && (!isCurrentConnection || client.superseded)) {
            return { ok: true, value: undefined };
        }
        if (isCurrentConnection)
            this.clients.delete(addr);
        if (client.isBattle) {
            const superseded = this.supersededBattleClients.delete(client);
            const isCurrentBattleConnection = this.cidToBattleClient.get(client.connectionId) === client;
            if (isCurrentBattleConnection)
                this.clearBattleHeartbeatLease(client.connectionId);
            const bSet = this.battleClients.get(client.roomNumber);
            if (bSet && !superseded) {
                if (this.battleSceneStartedRooms.has(client.roomNumber)) {
                    this.broadcastBattleLeave(client.roomNumber, client.connectionId);
                }
                else {
                    this.queueBattleLeave(client.roomNumber, client.connectionId);
                }
            }
            if (isCurrentBattleConnection) {
                (_b = this.battleClients.get(client.roomNumber)) === null || _b === void 0 ? void 0 : _b.delete(client.connectionId);
                if (((_c = this.battleClients.get(client.roomNumber)) === null || _c === void 0 ? void 0 : _c.size) === 0) {
                    this.battleClients.delete(client.roomNumber);
                }
                this.cidToBattleClient.delete(client.connectionId);
                (_d = this.sceneReadyClients.get(client.roomNumber)) === null || _d === void 0 ? void 0 : _d.delete(client.connectionId);
                (_e = this.battleLevelNextClients.get(client.roomNumber)) === null || _e === void 0 ? void 0 : _e.delete(client.connectionId);
            }
            const exp = this.battleExpectedCount.get(client.roomNumber);
            // A three-person loading barrier may safely fall back to the two
            // clients that actually reached the scene.  Never turn a two-real-
            // player battle into two independent one-player battles.
            if (!superseded && exp && exp > 2)
                this.battleExpectedCount.set(client.roomNumber, exp - 1);
            if (!superseded && this.releaseSceneReadyBarrierIfSatisfied(client.roomNumber, "disconnect")) {
                this.activateBattleScene(client.roomNumber);
            }
        }
        const set = this.roomClients.get(client.roomNumber);
        if (set && isCurrentConnection) {
            set.delete(addr);
            if (!client.isBattle) {
                try {
                    const { getRoom } = require("../room/manager");
                    const room = getRoom(client.roomNumber);
                    if (room
                        && room.lifecycle.phase === "LOBBY"
                        && client.roomGeneration === room.lobby_generation) {
                        const remaining = this.getClientsInRoom(client.roomNumber, room.lobby_generation);
                        for (const other of remaining) {
                            other.mates = other.mates.filter(mate => mate.viewerId !== client.viewerId);
                        }
                        const host = remaining.find(other => other.viewerId === room.host_viewer_id);
                        room.mates = ((_f = host === null || host === void 0 ? void 0 : host.mates) !== null && _f !== void 0 ? _f : remaining.map(other => other.yourself).filter(Boolean))
                            .map((mate) => {
                            var _a, _b, _c;
                            return ({
                                viewer_id: (_a = mate.viewerId) !== null && _a !== void 0 ? _a : null,
                                com_id: (_b = mate.comId) !== null && _b !== void 0 ? _b : 0,
                                player_id: (_c = mate.playerId) !== null && _c !== void 0 ? _c : undefined,
                            });
                        });
                        if (host) {
                            this.broadcastToRoom(client.roomNumber, [1, [1, host.mates]]);
                            try {
                                const lobby = require("../tcp/lobby");
                                (_g = lobby.scheduleRematchDisconnectCleanup) === null || _g === void 0 ? void 0 : _g.call(lobby, client.roomNumber);
                            }
                            catch (e) { }
                        }
                    }
                }
                catch (e) { }
            }
            if (set.size === 0) {
                this.roomClients.delete(client.roomNumber);
            }
            else {
                // OLD: if room still has clients, re-evaluate host auto-ready
                if (!client.isBattle) {
                    try {
                        const lobby = require("../tcp/lobby");
                        if (lobby.checkHostAutoReady)
                            lobby.checkHostAutoReady(client.roomNumber);
                    }
                    catch (e) { }
                }
            }
        }
        if (!client.isBattle && isCurrentConnection) {
            try {
                const { getRoom } = require("../room/manager");
                const room = getRoom(client.roomNumber);
                if (room && room.lifecycle.phase === "LOBBY") {
                    if (room.host_viewer_id === client.viewerId) {
                        this.beginHostReconnectGrace(client.roomNumber);
                    }
                    else {
                        this.beginRescueGuestReconnectGrace(client);
                    }
                }
            }
            catch (e) { }
        }
        this.disbandRoomIfNoRealConnections(client.roomNumber);
        return { ok: true, value: undefined };
    }
    getClientsInRoom(roomNumber, roomGeneration) {
        const set = this.roomClients.get(roomNumber);
        if (!set)
            return [];
        const out = [];
        for (const addr of set) {
            const c = this.clients.get(addr);
            if (c && (roomGeneration === undefined || c.roomGeneration === roomGeneration))
                out.push(c);
        }
        return out;
    }
    hasRoomClients(roomNumber) {
        const set = this.roomClients.get(roomNumber);
        return !!set && set.size > 0;
    }
    isHostOnline(hostViewerId, roomNumber, roomGeneration) {
        const set = this.roomClients.get(roomNumber);
        if (!set)
            return false;
        for (const addr of set) {
            const c = this.clients.get(addr);
            if (c
                && !c.isBattle
                && !c.superseded
                && c.enterData !== null
                && !c.socket.destroyed
                && c.viewerId === hostViewerId
                && (roomGeneration === undefined || c.roomGeneration === roomGeneration))
                return true;
        }
        return false;
    }
    addBattleClient(connectionId, client) {
        var _a, _b;
        const pendingTimer = this.abandonedBattleTimers.get(client.roomNumber);
        if (pendingTimer)
            clearTimeout(pendingTimer);
        this.abandonedBattleTimers.delete(client.roomNumber);
        let set = this.battleClients.get(client.roomNumber);
        if (!set) {
            set = new Set();
            this.battleClients.set(client.roomNumber, set);
        }
        // A reconnect may establish a replacement socket before the old one
        // emits close.  Keep one battle connection per real viewer so the
        // SceneReady barrier cannot count a stale socket as a missing player.
        for (const existingConnectionId of [...set]) {
            const existing = this.cidToBattleClient.get(existingConnectionId);
            if (!existing)
                continue;
            const sameSocketIdentity = existingConnectionId === connectionId;
            const sameKnownViewer = client.viewerId > 0
                && existing.viewerId > 0
                && existing.viewerId === client.viewerId;
            if (!sameSocketIdentity && !sameKnownViewer)
                continue;
            this.clearBattleHeartbeatLease(existingConnectionId);
            set.delete(existingConnectionId);
            (_a = this.sceneReadyClients.get(client.roomNumber)) === null || _a === void 0 ? void 0 : _a.delete(existingConnectionId);
            (_b = this.battleLevelNextClients.get(client.roomNumber)) === null || _b === void 0 ? void 0 : _b.delete(existingConnectionId);
            this.cidToBattleClient.delete(existingConnectionId);
            this.supersededBattleClients.add(existing);
            existing.superseded = true;
            this.unindexClientSocket(existing);
            (0, reliable_send_1.clearReliableSendState)(existing.socket);
            const ownerIdentity = client.viewerId > 0 ? `viewer:${client.viewerId}` : `connection:${connectionId}`;
            this.quarantineSupersededSocket(`battle:${ownerIdentity}@${client.roomNumber}`, client.roomNumber, existing.socket, () => {
                const current = this.cidToBattleClient.get(connectionId);
                if (current === client && !current.socket.destroyed)
                    return true;
                if (client.viewerId <= 0)
                    return false;
                return [...this.cidToBattleClient.values()].some(candidate => candidate !== existing
                    && candidate.roomNumber === client.roomNumber
                    && candidate.viewerId === client.viewerId
                    && !candidate.socket.destroyed);
            });
            this.logBattleBarrierState(client.roomNumber, "connection_replaced");
        }
        const pendingLeaves = this.pendingBattleLeaves.get(client.roomNumber);
        pendingLeaves === null || pendingLeaves === void 0 ? void 0 : pendingLeaves.delete(connectionId);
        if ((pendingLeaves === null || pendingLeaves === void 0 ? void 0 : pendingLeaves.size) === 0)
            this.pendingBattleLeaves.delete(client.roomNumber);
        set.add(connectionId);
        this.cidToBattleClient.set(connectionId, client);
        this.indexClientSocket(client);
        this.armBattleLoadingLease(connectionId);
        this.logBattleBarrierState(client.roomNumber, "connected");
    }
    removeBattleClient(connectionId) {
        var _a, _b, _c;
        this.clearBattleHeartbeatLease(connectionId);
        const client = this.cidToBattleClient.get(connectionId);
        if (client) {
            if (this.battleSceneStartedRooms.has(client.roomNumber)) {
                this.broadcastBattleLeave(client.roomNumber, connectionId);
            }
            else {
                this.queueBattleLeave(client.roomNumber, connectionId);
            }
            this.unindexClientSocket(client);
            (_a = this.battleClients.get(client.roomNumber)) === null || _a === void 0 ? void 0 : _a.delete(connectionId);
            (_b = this.sceneReadyClients.get(client.roomNumber)) === null || _b === void 0 ? void 0 : _b.delete(connectionId);
            (_c = this.battleLevelNextClients.get(client.roomNumber)) === null || _c === void 0 ? void 0 : _c.delete(connectionId);
        }
        this.cidToBattleClient.delete(connectionId);
        if (client && this.releaseSceneReadyBarrierIfSatisfied(client.roomNumber, "removed")) {
            this.activateBattleScene(client.roomNumber);
        }
    }
    getBattleClient(connectionId) {
        return this.cidToBattleClient.get(connectionId);
    }
    findClientBySocket(socket) {
        return this.socketClients.get(socket);
    }
    isSupersededSocket(socket) {
        return this.supersededSockets.has(socket);
    }
    isRetiredLobbySocket(socket) {
        return this.retiredLobbySockets.has(socket);
    }
    isCurrentBattleClient(client) {
        return this.cidToBattleClient.get(client.connectionId) === client;
    }
    snapshotBattleRelayRecipients(source, includeSource = false) {
        if (!this.isCurrentBattleClient(source))
            return [];
        const set = this.battleClients.get(source.roomNumber);
        if (!set)
            return [];
        const recipients = [];
        // Snapshot both ids and resolved clients before forwarding. A reconnect
        // during the loop must not replace or remove one receiver halfway through
        // this logical broadcast.
        for (const connectionId of [...set]) {
            if (!includeSource && connectionId === source.connectionId)
                continue;
            const client = this.cidToBattleClient.get(connectionId);
            if (!client
                || client.roomGeneration !== source.roomGeneration
                || client.socket.destroyed
                || !client.socket.writable)
                continue;
            recipients.push(client);
        }
        return recipients;
    }
    markSceneReady(connectionId, roomNumber) {
        var _a;
        const expected = (_a = this.battleExpectedCount.get(roomNumber)) !== null && _a !== void 0 ? _a : 0;
        if (expected <= 0)
            return false;
        let readySet = this.sceneReadyClients.get(roomNumber);
        if (!readySet) {
            readySet = new Set();
            this.sceneReadyClients.set(roomNumber, readySet);
        }
        readySet.add(connectionId);
        this.armBattleReadyHeartbeatLease(connectionId);
        const released = this.releaseSceneReadyBarrierIfSatisfied(roomNumber, "scene_ready");
        if (released)
            this.activateBattleScene(roomNumber);
        return released;
    }
    beginBattleLevelNext(connectionId, roomNumber) {
        var _a, _b, _c;
        let levelNextSet = this.battleLevelNextClients.get(roomNumber);
        if (!levelNextSet) {
            levelNextSet = new Set();
            this.battleLevelNextClients.set(roomNumber, levelNextSet);
            // CN's dual-boss battles keep the same TCP battle connection.
            // LevelNext starts a new SceneReady barrier for the next boss;
            // reusing the previous ready set would start the next scene before
            // every real player has finished loading it.
            this.sceneReadyClients.set(roomNumber, new Set());
            const connected = (_b = (_a = this.battleClients.get(roomNumber)) === null || _a === void 0 ? void 0 : _a.size) !== null && _b !== void 0 ? _b : 0;
            this.battleExpectedCount.set(roomNumber, connected);
            this.battleSceneStartedRooms.delete(roomNumber);
            for (const battleConnectionId of (_c = this.battleClients.get(roomNumber)) !== null && _c !== void 0 ? _c : []) {
                this.armBattleLoadingLease(battleConnectionId);
            }
            this.logBattleBarrierState(roomNumber, "level_next");
        }
        levelNextSet.add(connectionId);
    }
    clearSceneReady(roomNumber) {
        this.sceneReadyClients.delete(roomNumber);
        this.battleLevelNextClients.delete(roomNumber);
        this.battleSceneStartedRooms.delete(roomNumber);
        this.pendingBattleLeaves.delete(roomNumber);
    }
    setBattleExpectedCount(roomNumber, count) {
        this.sceneReadyClients.set(roomNumber, new Set());
        this.battleLevelNextClients.delete(roomNumber);
        this.battleExpectedCount.set(roomNumber, count);
        this.battleSceneStartedRooms.delete(roomNumber);
        this.pendingBattleLeaves.delete(roomNumber);
        this.logBattleBarrierState(roomNumber, "expected_changed");
        if (this.releaseSceneReadyBarrierIfSatisfied(roomNumber, "expected_recheck")) {
            this.activateBattleScene(roomNumber);
        }
    }
    clearBattleExpectedCount(roomNumber) {
        this.sceneReadyClients.delete(roomNumber);
        this.battleLevelNextClients.delete(roomNumber);
        this.battleExpectedCount.delete(roomNumber);
        this.battleBarrierLogState.delete(roomNumber);
        this.battleSceneStartedRooms.delete(roomNumber);
        this.pendingBattleLeaves.delete(roomNumber);
    }
    removeRoomState(roomNumber) {
        (0, chain_diagnostic_1.clearChainDiagnosticRoom)(roomNumber);
        const abandonedTimer = this.abandonedBattleTimers.get(roomNumber);
        if (abandonedTimer)
            clearTimeout(abandonedTimer);
        this.abandonedBattleTimers.delete(roomNumber);
        const settlementTimer = this.settlementReturnTimers.get(roomNumber);
        if (settlementTimer)
            clearTimeout(settlementTimer);
        this.settlementReturnTimers.delete(roomNumber);
        this.cancelHostReconnectGrace(roomNumber);
        this.clearRescueGuestStateForRoom(roomNumber);
        this.clearBattleHeartbeatLeasesForRoom(roomNumber);
        this.battleBarrierLogState.delete(roomNumber);
        this.battleSceneStartedRooms.delete(roomNumber);
        this.pendingBattleLeaves.delete(roomNumber);
        for (const key of this.roomConnectionGenerations.keys()) {
            if (key.endsWith(`@${roomNumber}`))
                this.roomConnectionGenerations.delete(key);
        }
    }
    sendJson(socket, data, context) {
        return this.sendFrame(socket, JSON.stringify(data) + "\0", context);
    }
    sendFrame(socket, frame, context) {
        return (0, reliable_send_1.sendFrameReliably)(socket, frame, context);
    }
    broadcastToRoom(roomNumber, data, excludeAddr, roomGeneration) {
        var _a;
        const set = this.roomClients.get(roomNumber);
        if (!set)
            return;
        let expectedGeneration = roomGeneration;
        if (expectedGeneration === undefined) {
            try {
                const { getRoom } = require("../room/manager");
                expectedGeneration = (_a = getRoom(roomNumber)) === null || _a === void 0 ? void 0 : _a.lobby_generation;
            }
            catch (e) { }
        }
        for (const addr of set) {
            if (excludeAddr !== undefined && addr === excludeAddr)
                continue;
            const c = this.clients.get(addr);
            // A socket is indexed immediately after its handshake, but the
            // client does not have a local "yourself" room object until Enter
            // has been answered with Welcome.  Sending Mates/State/Start during
            // that gap can make the CN client raise C15202 because it cannot
            // find itself in the meeting roster.
            if (c
                && !c.superseded
                && c.enterData !== null
                && (expectedGeneration === undefined || c.roomGeneration === expectedGeneration)) {
                this.sendJson(c.socket, data, {
                    roomNumber,
                    connectionId: c.connectionId,
                    viewerId: c.viewerId,
                    roomGeneration: c.roomGeneration,
                    channel: "lobby",
                });
            }
        }
    }
    getRoomClientCount(roomNumber, roomGeneration) {
        var _a, _b;
        if (roomGeneration === undefined)
            return (_b = (_a = this.roomClients.get(roomNumber)) === null || _a === void 0 ? void 0 : _a.size) !== null && _b !== void 0 ? _b : 0;
        return this.getClientsInRoom(roomNumber, roomGeneration).length;
    }
}
exports.SessionManager = SessionManager;
exports.sessionManager = new SessionManager();
