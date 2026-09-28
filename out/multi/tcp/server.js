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
exports.stopSessionServer = exports.startSessionServer = exports.SESSION_TCP_KEEPALIVE_MS = exports.SESSION_MAX_BUFFER_BYTES = exports.SESSION_MAX_FRAME_BYTES = exports.SESSION_HANDSHAKE_TIMEOUT_MS = exports.SESSION_HOST = exports.SESSION_PORT = void 0;
const net = __importStar(require("net"));
const memory_diagnostics_1 = require("../../lib/memory-diagnostics");
const client_admission_1 = require("../../lib/client-admission");
const handshake_1 = require("./handshake");
const battle_1 = require("./battle");
const SessionManager_1 = require("../state/SessionManager");
const game_logging_1 = require("../../lib/game-logging");
const reliable_send_1 = require("./reliable-send");
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
let server = null;
const activeSockets = new Set();
function startSessionServer() {
    return new Promise((resolve) => {
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
            let admissionToken, admissionSession;
            const closeForProtocolViolation = (reason) => {
                if (protocolClosed)
                    return;
                protocolClosed = true;
                buffer = "";
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
                socketRemoved = true;
                try {
                    const client = SessionManager_1.sessionManager.findClientBySocket(socket);
                    if (client) {
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
            socket.on("data", (chunk) => {
                if (protocolClosed)
                    return;
                buffer += chunk;
                if (Buffer.byteLength(buffer, "utf8") > exports.SESSION_MAX_BUFFER_BYTES) {
                    closeForProtocolViolation(`receive buffer exceeded ${exports.SESSION_MAX_BUFFER_BYTES} bytes`);
                    return;
                }
                while (buffer.includes("\0")) {
                    const idx = buffer.indexOf("\0");
                    const raw = buffer.substring(0, idx);
                    buffer = buffer.substring(idx + 1);
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
                                socket.end(JSON.stringify([1, "CLIENT_ADMISSION_REQUIRED"]) + "\0");
                                protocolClosed = true;
                                clearHandshakeTimer();
                                return;
                            }
                            handshakeDone = true;
                            clearHandshakeTimer();
                            isBattleSocket = data.socklet === "cooperation_battle";
                            isLoungeSocket = data.socklet === "multi_special_exchange_socklet";
                            const handshake = isLoungeSocket
                                ? (0, tcp_1.handleLoungeHandshake)(socket, data)
                                : (0, handshake_1.handleHandshake)(socket, data);
                            handshake.catch((err) => {
                                console.error(`[TCP] handshake failed:`, err);
                                socket.destroy();
                            });
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
                        console.warn(`[TCP] message rejected from ${remoteAddr}:`, e.message);
                        socket.destroy();
                        return;
                    }
                }
                if (Buffer.byteLength(buffer, "utf8") > exports.SESSION_MAX_FRAME_BYTES) {
                    closeForProtocolViolation(`unterminated frame exceeded ${exports.SESSION_MAX_FRAME_BYTES} bytes`);
                }
            });
            socket.on("end", () => connection_diagnostic_1.fiveBossConnectionDiagnostics.socketEvent(socket, "socket_end", "peer_fin"));
            socket.on("close", (hadError) => {
                connection_diagnostic_1.fiveBossConnectionDiagnostics.socketEvent(socket, "socket_close", hadError ? "with_error" : "without_error");
                clearHandshakeTimer();
                (0, game_logging_1.gameVerboseLog)(() => `[TCP] connection closed: ${remoteAddr}`);
                removeSocketClient();
            });
            socket.on("error", (err) => {
                var _a;
                connection_diagnostic_1.fiveBossConnectionDiagnostics.socketEvent(socket, "socket_error", (_a = err.code) !== null && _a !== void 0 ? _a : "unknown");
                clearHandshakeTimer();
                console.warn(`[TCP] socket error from ${remoteAddr}:`, err.message);
                removeSocketClient();
            });
        });
        (0, memory_diagnostics_1.observeServerConnections)("tcp", server);
        server.listen(exports.SESSION_PORT, exports.SESSION_HOST, () => {
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
        for (const socket of activeSockets)
            socket.destroy();
        current.close(() => {
            server = null;
            resolve();
        });
    });
}
exports.stopSessionServer = stopSessionServer;
