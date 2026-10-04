"use strict";
// Multi battle TCP session server
// Protocol: JSON messages delimited by null byte (\0)
// Post-handshake messages use typepacker format with useEnumIndex=true:
//   [index, param1, param2, ...]
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
exports.stopSessionServer = exports.startSessionServer = exports.SESSION_MAX_FRAMES_PER_TICK = exports.SESSION_TCP_KEEPALIVE_MS = exports.SESSION_MAX_BUFFER_BYTES = exports.SESSION_MAX_FRAME_BYTES = exports.SESSION_HANDSHAKE_TIMEOUT_MS = exports.SESSION_HOST = exports.SESSION_PORT = void 0;
const net = __importStar(require("net"));
const memory_diagnostics_1 = require("../../lib/memory-diagnostics");
const client_admission_1 = require("../../lib/client-admission");
const handshake_1 = require("./handshake");
const battle_1 = require("./battle");
const SessionManager_1 = require("../state/SessionManager");
const game_logging_1 = require("../../lib/game-logging");
const reliable_send_1 = require("./reliable-send");
const disconnect_diagnostics_1 = require("./disconnect-diagnostics");
const embedded_1 = require("../coordinator/embedded");
const connection_diagnostic_1 = require("../five-boss/connection-diagnostic");
const tcp_1 = require("../../lounge/tcp");
exports.SESSION_PORT = parseInt(process.env.SESSION_PORT || "8003");
exports.SESSION_HOST = process.env.SESSION_HOST || "0.0.0.0";
function positiveInteger(name, fallback, minimum) {
    var _a;
    const value = Number.parseInt((_a = process.env[name]) !== null && _a !== void 0 ? _a : "", 10);
    return Number.isFinite(value) ? Math.max(minimum, value) : fallback;
}
exports.SESSION_HANDSHAKE_TIMEOUT_MS = positiveInteger("SESSION_HANDSHAKE_TIMEOUT_MS", 15000, 1000);
exports.SESSION_MAX_FRAME_BYTES = positiveInteger("SESSION_MAX_FRAME_BYTES", 262144, 1024);
exports.SESSION_MAX_BUFFER_BYTES = positiveInteger("SESSION_MAX_BUFFER_BYTES", 1048576, exports.SESSION_MAX_FRAME_BYTES);
exports.SESSION_TCP_KEEPALIVE_MS = positiveInteger("SESSION_TCP_KEEPALIVE_MS", 10000, 1000);
// A client can deliver many complete frames in one `data` callback. Keep one
// noisy socket from monopolizing the Node event loop while another player's
// heartbeat or room broadcast is waiting to run. Frames for one socket remain
// ordered; the remainder is resumed with setImmediate below.
exports.SESSION_MAX_FRAMES_PER_TICK = positiveInteger("SESSION_MAX_FRAMES_PER_TICK", 128, 1);
let server = null;
const activeSockets = new Set();
function startSessionServer() {
    return new Promise((resolve, reject) => {
        if (server) {
            resolve();
            return;
        }
        server = net.createServer((socket) => {
            activeSockets.add(socket);
            socket.once("close", () => activeSockets.delete(socket));
            const remoteAddr = `${socket.remoteAddress}:${socket.remotePort}`;
            (0, game_logging_1.gameVerboseLog)(() => `[TCP] new connection from ${remoteAddr}`);
            socket.setNoDelay(true);
            socket.setKeepAlive(true, exports.SESSION_TCP_KEEPALIVE_MS);
            socket.setEncoding("utf8");
            let buffer = "";
            let handshakeDone = false;
            let isBattleSocket = false;
            let isLoungeSocket = false;
            let socketRemoved = false;
            let protocolClosed = false;
            let processingFrames = false;
            let processFramesScheduled = false;
            let handshakePending = null;
            let admissionToken, admissionSession;
            const closeForProtocolViolation = (reason) => {
                if (protocolClosed)
                    return;
                protocolClosed = true;
                buffer = "";
                (0, disconnect_diagnostics_1.markTcpDisconnectReason)(socket, reason === "client build no longer admitted"
                    ? "admission" : "protocol");
                console.warn(`[TCP] protocol violation from ${remoteAddr}: ${reason}`);
                connection_diagnostic_1.fiveBossConnectionDiagnostics.socketEvent(socket, "protocol_close", reason.split(":", 1)[0]);
                socket.destroy();
            };
            const handshakeTimer = setTimeout(() => {
                if (!handshakeDone)
                    closeForProtocolViolation(`handshake timeout after ${exports.SESSION_HANDSHAKE_TIMEOUT_MS}ms`);
            }, exports.SESSION_HANDSHAKE_TIMEOUT_MS);
            handshakeTimer.unref();
            const clearHandshakeTimer = () => clearTimeout(handshakeTimer);
            const removeSocketClient = () => {
                (0, reliable_send_1.clearReliableSendState)(socket);
                (0, tcp_1.detachLoungeSocket)(socket);
                if (socketRemoved)
                    return;
                try {
                    const client = SessionManager_1.sessionManager.findClientBySocket(socket);
                    if (client) {
                        socketRemoved = true;
                        void embedded_1.embeddedMultiCoordinator.enqueueRoomCommand(client.roomNumber, () => SessionManager_1.sessionManager.removeClient(client)).catch(error => {
                            console.error(`[TCP] queued socket cleanup failed: room=${client.roomNumber}`, error);
                        });
                    }
                }
                catch (_a) {
                    // Socket shutdown is best-effort. The room lease cleanup is
                    // still able to remove an already detached connection.
                }
            };
            const processFrames = () => {
                if (protocolClosed || processingFrames || processFramesScheduled || handshakePending)
                    return;
                processingFrames = true;
                let processed = 0;
                try {
                    while (!protocolClosed && processed < exports.SESSION_MAX_FRAMES_PER_TICK) {
                        const idx = buffer.indexOf("\0");
                        if (idx < 0)
                            break;
                        const raw = buffer.substring(0, idx);
                        buffer = buffer.substring(idx + 1);
                        processed++;
                        if (raw.trim().length === 0)
                            continue;
                        const frameBytes = Buffer.byteLength(raw, "utf8");
                        if (frameBytes > exports.SESSION_MAX_FRAME_BYTES) {
                            closeForProtocolViolation(`frame exceeded ${exports.SESSION_MAX_FRAME_BYTES} bytes`);
                            return;
                        }
                        let data;
                        try {
                            data = JSON.parse(raw);
                        }
                        catch (e) {
                            closeForProtocolViolation(`invalid JSON frame: ${e.message}`);
                            return;
                        }
                        try {
                            if (!handshakeDone) {
                                if (!data || typeof data !== "object" || typeof data.socklet !== "string") {
                                    closeForProtocolViolation("first frame was not a valid handshake");
                                    return;
                                }
                                admissionToken = data.sp_admission;
                                admissionSession = data.sp_session;
                                if (!(0, client_admission_1.clientAdmission)().checkActivity(admissionToken, admissionSession).ok) {
                                    (0, disconnect_diagnostics_1.markTcpDisconnectReason)(socket, "admission");
                                    socket.end(JSON.stringify([1, "CLIENT_ADMISSION_REQUIRED"]) + "\0");
                                    protocolClosed = true;
                                    clearHandshakeTimer();
                                    return;
                                }
                                isBattleSocket = data.socklet === "cooperation_battle";
                                isLoungeSocket = data.socklet === "multi_special_exchange_socklet";
                                const handshake = isLoungeSocket
                                    ? (0, tcp_1.handleLoungeHandshake)(socket, data)
                                    : (0, handshake_1.handleHandshake)(socket, data);
                                handshakePending = Promise.resolve(handshake).then(() => {
                                    handshakePending = null;
                                    clearHandshakeTimer();
                                    if (protocolClosed || socket.destroyed || socket.writableEnded) {
                                        // The peer can close while an uncached
                                        // handshake is still resolving. If the
                                        // handler indexed the socket after the
                                        // close callback ran, clean it now.
                                        removeSocketClient();
                                        return;
                                    }
                                    handshakeDone = true;
                                    processFrames();
                                }, (err) => {
                                    handshakePending = null;
                                    (0, disconnect_diagnostics_1.markTcpDisconnectReason)(socket, "handshake_error");
                                    console.error(`[TCP] handshake failed:`, err);
                                    removeSocketClient();
                                    socket.destroy();
                                });
                                // A client may coalesce Enter/heartbeat with its
                                // handshake in one TCP chunk. Do not dispatch
                                // those frames before the async handshake has
                                // indexed this socket in SessionManager.
                                return;
                            }
                            else if (!(0, client_admission_1.clientAdmission)().checkActivity(admissionToken, admissionSession).ok) {
                                closeForProtocolViolation("client build no longer admitted");
                                return;
                            }
                            else if (isBattleSocket) {
                                (0, battle_1.handleBattleMessage)(socket, data);
                            }
                            else if (isLoungeSocket) {
                                (0, tcp_1.handleLoungeMessage)(socket, data);
                            }
                            else {
                                const lobby = require("./lobby");
                                lobby.handleMessage(socket, data);
                            }
                        }
                        catch (e) {
                            (0, disconnect_diagnostics_1.markTcpDisconnectReason)(socket, "message_error");
                            console.warn(`[TCP] message rejected from ${remoteAddr}:`, e.message);
                            socket.destroy();
                            return;
                        }
                    }
                }
                finally {
                    processingFrames = false;
                    if (!protocolClosed && !handshakePending
                        && buffer.includes("\0") && !processFramesScheduled) {
                        processFramesScheduled = true;
                        setImmediate(() => {
                            processFramesScheduled = false;
                            processFrames();
                        });
                    }
                }
                if (!protocolClosed && Buffer.byteLength(buffer, "utf8") > exports.SESSION_MAX_FRAME_BYTES) {
                    closeForProtocolViolation(`unterminated frame exceeded ${exports.SESSION_MAX_FRAME_BYTES} bytes`);
                }
            };
            socket.on("data", (chunk) => {
                if (protocolClosed)
                    return;
                buffer += chunk;
                if (Buffer.byteLength(buffer, "utf8") > exports.SESSION_MAX_BUFFER_BYTES) {
                    closeForProtocolViolation(`receive buffer exceeded ${exports.SESSION_MAX_BUFFER_BYTES} bytes`);
                    return;
                }
                processFrames();
            });
            socket.on("end", () => {
                (0, disconnect_diagnostics_1.markTcpDisconnectReason)(socket, "peer_fin");
                connection_diagnostic_1.fiveBossConnectionDiagnostics.socketEvent(socket, "socket_end", "peer_fin");
            });
            socket.on("close", (hadError) => {
                const reason = (0, disconnect_diagnostics_1.finishTcpDisconnect)(socket, hadError);
                connection_diagnostic_1.fiveBossConnectionDiagnostics.socketEvent(socket, "socket_close", hadError ? "with_error" : "without_error");
                clearHandshakeTimer();
                (0, game_logging_1.gameVerboseLog)(() => `[TCP] connection closed: ${remoteAddr} reason=${reason}`);
                removeSocketClient();
            });
            socket.on("error", (err) => {
                var _a;
                (0, disconnect_diagnostics_1.markTcpDisconnectReason)(socket, "socket_error");
                connection_diagnostic_1.fiveBossConnectionDiagnostics.socketEvent(socket, "socket_error", (_a = err.code) !== null && _a !== void 0 ? _a : "unknown");
                clearHandshakeTimer();
                console.warn(`[TCP] socket error from ${remoteAddr}:`, err.message);
                removeSocketClient();
            });
        });
        (0, memory_diagnostics_1.observeServerConnections)("tcp", server);
        const handleListenError = (error) => {
            if (server) {
                try {
                    server.close();
                }
                catch (_a) { }
                server = null;
            }
            reject(error);
        };
        server.once("error", handleListenError);
        server.listen(exports.SESSION_PORT, exports.SESSION_HOST, () => {
            server === null || server === void 0 ? void 0 : server.off("error", handleListenError);
            console.log(`[TCP] session server listening on ${exports.SESSION_HOST}:${exports.SESSION_PORT}`);
            resolve();
        });
    });
}
exports.startSessionServer = startSessionServer;
function stopSessionServer() {
    return new Promise((resolve) => {
        const current = server;
        if (!current) {
            resolve();
            return;
        }
        // net.Server.close() stops accepts but waits forever for established
        // clients. Shutdown is already an explicit service stop, so release
        // those sockets now and let their normal cleanup enqueue room leases.
        for (const socket of activeSockets) {
            (0, disconnect_diagnostics_1.markTcpDisconnectReason)(socket, "server_shutdown");
            socket.destroy();
        }
        current.close(() => {
            server = null;
            resolve();
        });
    });
}
exports.stopSessionServer = stopSessionServer;
