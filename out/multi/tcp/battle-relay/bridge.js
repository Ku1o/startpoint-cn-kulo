"use strict";
// Main-process side of the battle relay child (opt-in: MULTI_BATTLE_RELAY_PROCESS=1).
//
// A battle socket is handed to the child right after its handshake frame is
// read. The main process keeps a RelayProxySocket in its place, so handshake,
// barriers, leases, Leave/BattleStart and settlement code keep working on a
// socket-like object: writes become IPC messages, and the child forwards the
// frames the main process must see as `data` events.
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.isRelayProxySocket = exports.battleRelayBridge = exports.BattleRelayBridge = exports.RelayProxySocket = exports.battleRelayProcessEnabled = void 0;
const events_1 = require("events");
const child_process_1 = require("child_process");
const path = __importStar(require("path"));
function positiveInteger(name, fallback, minimum) {
    var _a;
    const value = Number.parseInt((_a = process.env[name]) !== null && _a !== void 0 ? _a : "", 10);
    return Number.isFinite(value) ? Math.max(minimum, value) : fallback;
}
function battleRelayProcessEnabled(environment = process.env) {
    var _a;
    return /^(1|true|yes|on)$/i.test((_a = environment.MULTI_BATTLE_RELAY_PROCESS) !== null && _a !== void 0 ? _a : "");
}
exports.battleRelayProcessEnabled = battleRelayProcessEnabled;
/** Restarts allowed per server process; after that battle sockets stay in-process. */
const MAX_RESTARTS = positiveInteger("MULTI_BATTLE_RELAY_MAX_RESTARTS", 5, 0);
/**
 * Stands in for a battle `net.Socket` whose file descriptor now lives in the
 * relay child. Implements the subset of the socket API the multi code uses.
 */
class RelayProxySocket extends events_1.EventEmitter {
    constructor(sid, bridge, remoteAddress, remotePort) {
        super();
        this.sid = sid;
        this.bridge = bridge;
        this.remoteAddress = remoteAddress;
        this.remotePort = remotePort;
        this.destroyed = false;
        this.writableEnded = false;
        this.readable = true;
        this.writableLength = 0;
        this.closeEmitted = false;
    }
    get writable() {
        return !this.destroyed && !this.writableEnded;
    }
    write(data) {
        if (!this.writable)
            return false;
        this.bridge.post({ t: "write", sid: this.sid, data: typeof data === "string" ? data : Buffer.from(data).toString("utf8") });
        return true;
    }
    end(data) {
        if (this.destroyed || this.writableEnded)
            return this;
        if (data !== undefined)
            this.write(data);
        this.writableEnded = true;
        this.bridge.post({ t: "end", sid: this.sid });
        return this;
    }
    destroy() {
        if (this.destroyed)
            return this;
        this.destroyed = true;
        this.readable = false;
        this.bridge.post({ t: "destroy", sid: this.sid });
        process.nextTick(() => this.emitClose(false));
        return this;
    }
    setNoDelay() { return this; }
    setKeepAlive() { return this; }
    setEncoding() { return this; }
    setTimeout() { return this; }
    pause() { return this; }
    resume() { return this; }
    ref() { return this; }
    unref() { return this; }
    /** The child reported that the real socket closed. */
    remoteClosed(reason, hadError, detail) {
        if (this.closeEmitted)
            return;
        this.readable = false;
        if (reason === "peer_fin") {
            this.emit("end");
        }
        else if (reason === "socket_error") {
            const error = new Error(detail !== null && detail !== void 0 ? detail : "battle relay socket error");
            error.code = detail;
            this.emit("error", error);
        }
        else if (reason !== "parent_request") {
            this.emit("relay-close-reason", reason, detail);
        }
        this.destroyed = true;
        this.emitClose(hadError);
    }
    emitClose(hadError) {
        if (this.closeEmitted)
            return;
        this.closeEmitted = true;
        this.bridge.forget(this.sid);
        this.emit("close", hadError);
    }
}
exports.RelayProxySocket = RelayProxySocket;
class BattleRelayBridge {
    constructor(childPath = path.join(__dirname, "child.js")) {
        this.childPath = childPath;
        this.child = null;
        this.ready = false;
        this.stopping = false;
        this.restarts = 0;
        this.nextSid = 1;
        this.proxies = new Map();
        this.pendingMembership = new Map();
        this.membershipFlushQueued = false;
        this.readyWaiters = [];
    }
    get isReady() {
        return this.ready && this.child !== null && this.child.connected;
    }
    get activeSockets() {
        return this.proxies.size;
    }
    start() {
        if (this.child)
            return this.waitReady();
        this.stopping = false;
        const child = (0, child_process_1.fork)(this.childPath, [], {
            // Inspector or profiler flags of the main process must not be inherited.
            execArgv: [],
            serialization: "json",
            stdio: ["ignore", "inherit", "inherit", "ipc"],
        });
        this.child = child;
        child.on("message", (message) => this.handleChildMessage(message));
        child.on("exit", (code, signal) => this.handleChildExit(child, code, signal));
        child.on("error", (error) => console.error("[BATTLE-RELAY] child process error:", error));
        return this.waitReady();
    }
    waitReady() {
        if (this.isReady)
            return Promise.resolve();
        return new Promise(resolve => this.readyWaiters.push(resolve));
    }
    stop() {
        const child = this.child;
        this.stopping = true;
        if (!child)
            return Promise.resolve();
        return new Promise(resolve => {
            const timer = setTimeout(() => child.kill(), 2000);
            timer.unref();
            child.once("exit", () => {
                clearTimeout(timer);
                resolve();
            });
            this.post({ t: "shutdown" });
        });
    }
    post(message) {
        const child = this.child;
        if (!child || !child.connected)
            return;
        try {
            child.send(message);
        }
        catch (error) {
            console.error("[BATTLE-RELAY] IPC send failed:", error.message);
        }
    }
    forget(sid) {
        this.proxies.delete(sid);
    }
    /**
     * Moves a freshly accepted socket into the child. Returns the proxy that
     * replaces it, plus any bytes the main process had already buffered, or
     * null when the child cannot take it (the caller keeps the socket).
     */
    adopt(socket) {
        const child = this.child;
        if (!this.isReady || !child)
            return null;
        const handle = socket._handle;
        if (!(handle === null || handle === void 0 ? void 0 : handle.readStop))
            return null;
        for (const event of ["data", "end", "close", "error", "drain", "timeout"])
            socket.removeAllListeners(event);
        // The parent copy is closed after transfer; a late error must not crash.
        socket.on("error", () => { });
        socket.pause();
        handle.reading = false;
        handle.readStop();
        // Bytes libuv already read but the stream has not emitted yet.
        let pending = "";
        let chunk;
        while ((chunk = socket.read()) !== null)
            pending += String(chunk);
        socket.server = null;
        const sid = this.nextSid++;
        const proxy = new RelayProxySocket(sid, this, socket.remoteAddress, socket.remotePort);
        this.proxies.set(sid, proxy);
        try {
            child.send({ t: "adopt", sid }, socket, { keepOpen: false }, (error) => {
                // The parent's handle is already closed; this releases the
                // JS socket and the server's connection count.
                socket.destroy();
                if (error) {
                    console.error(`[BATTLE-RELAY] socket handoff failed: sid=${sid}`, error.message);
                    proxy.remoteClosed("socket_error", true, "handoff_failed");
                }
            });
        }
        catch (error) {
            console.error(`[BATTLE-RELAY] socket handoff threw: sid=${sid}`, error.message);
            process.nextTick(() => proxy.remoteClosed("socket_error", true, "handoff_failed"));
        }
        return { proxy, pending };
    }
    /**
     * Publishes a room's relay membership. Several changes in one turn of the
     * event loop collapse into one IPC message carrying the final state.
     */
    scheduleMembership(roomNumber, compute) {
        if (!this.child)
            return;
        this.pendingMembership.set(roomNumber, compute);
        if (this.membershipFlushQueued)
            return;
        this.membershipFlushQueued = true;
        queueMicrotask(() => {
            this.membershipFlushQueued = false;
            const pending = [...this.pendingMembership];
            this.pendingMembership.clear();
            for (const [room, computeMembers] of pending) {
                this.post({ t: "members", room, members: computeMembers() });
            }
        });
    }
    handleChildMessage(message) {
        var _a, _b, _c, _d;
        switch (message.t) {
            case "ready":
                this.ready = true;
                for (const resolve of this.readyWaiters.splice(0))
                    resolve();
                console.log("[BATTLE-RELAY] relay process ready");
                break;
            case "adopted":
                if (!message.ok)
                    (_a = this.proxies.get(message.sid)) === null || _a === void 0 ? void 0 : _a.remoteClosed("socket_error", true, "adopt_rejected");
                break;
            case "frames":
                (_b = this.proxies.get(message.sid)) === null || _b === void 0 ? void 0 : _b.emit("data", message.data);
                break;
            case "activity":
                for (const item of message.items)
                    (_c = this.proxies.get(item.sid)) === null || _c === void 0 ? void 0 : _c.emit("relay-activity", item);
                break;
            case "closed":
                (_d = this.proxies.get(message.sid)) === null || _d === void 0 ? void 0 : _d.remoteClosed(message.reason, message.hadError, message.detail);
                break;
        }
    }
    handleChildExit(child, code, signal) {
        if (this.child !== child)
            return;
        this.child = null;
        this.ready = false;
        // Every adopted socket died with the child. Report them so rooms run
        // their normal departure path (Leave, absent-seat grace, AI takeover).
        for (const proxy of [...this.proxies.values()])
            proxy.remoteClosed("relay_exit", true);
        this.proxies.clear();
        if (this.stopping)
            return;
        console.error(`[BATTLE-RELAY] relay process exited: code=${code} signal=${signal}`);
        if (this.restarts >= MAX_RESTARTS) {
            console.error("[BATTLE-RELAY] restart limit reached; battle sockets stay in the main process");
            for (const resolve of this.readyWaiters.splice(0))
                resolve();
            return;
        }
        this.restarts++;
        // New battle sockets stay in-process until the replacement is ready.
        void this.start();
    }
}
exports.BattleRelayBridge = BattleRelayBridge;
exports.battleRelayBridge = new BattleRelayBridge();
function isRelayProxySocket(socket) {
    return socket instanceof RelayProxySocket;
}
exports.isRelayProxySocket = isRelayProxySocket;
