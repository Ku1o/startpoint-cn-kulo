// Multi battle TCP session server
// Protocol: JSON messages delimited by null byte (\0)
// Post-handshake messages use typepacker format with useEnumIndex=true:
//   [index, param1, param2, ...]

import * as net from "net"
import { handleHandshake } from "./handshake"
import { handleBattleMessage } from "./battle"
import { sessionManager } from "../state/SessionManager"
import { gameVerboseLog } from "../../lib/game-logging"
import { clearReliableSendState } from "./reliable-send"

export const SESSION_PORT = parseInt(process.env.SESSION_PORT || "8003")
export const SESSION_HOST = process.env.SESSION_HOST || "0.0.0.0"

function positiveInteger(name: string, fallback: number, minimum: number): number {
    const value = Number.parseInt(process.env[name] ?? "", 10)
    return Number.isFinite(value) ? Math.max(minimum, value) : fallback
}

export const SESSION_HANDSHAKE_TIMEOUT_MS = positiveInteger("SESSION_HANDSHAKE_TIMEOUT_MS", 15_000, 1_000)
export const SESSION_MAX_FRAME_BYTES = positiveInteger("SESSION_MAX_FRAME_BYTES", 262_144, 1_024)
export const SESSION_MAX_BUFFER_BYTES = positiveInteger("SESSION_MAX_BUFFER_BYTES", 1_048_576, SESSION_MAX_FRAME_BYTES)
export const SESSION_TCP_KEEPALIVE_MS = positiveInteger("SESSION_TCP_KEEPALIVE_MS", 10_000, 1_000)

let server: net.Server | null = null

export function startSessionServer(): Promise<void> {
    return new Promise((resolve) => {
        if (server) {
            resolve()
            return
        }
        server = net.createServer((socket) => {
            const remoteAddr = `${socket.remoteAddress}:${socket.remotePort}`
            gameVerboseLog(() => `[TCP] new connection from ${remoteAddr}`)

            socket.setNoDelay(true)
            socket.setKeepAlive(true, SESSION_TCP_KEEPALIVE_MS)
            socket.setEncoding("utf8")
            let buffer = ""
            let handshakeDone = false
            let isBattleSocket = false
            let socketRemoved = false
            let protocolClosed = false

            const closeForProtocolViolation = (reason: string) => {
                if (protocolClosed) return
                protocolClosed = true
                buffer = ""
                console.warn(`[TCP] protocol violation from ${remoteAddr}: ${reason}`)
                socket.destroy()
            }

            const handshakeTimer = setTimeout(() => {
                if (!handshakeDone) closeForProtocolViolation(`handshake timeout after ${SESSION_HANDSHAKE_TIMEOUT_MS}ms`)
            }, SESSION_HANDSHAKE_TIMEOUT_MS)
            handshakeTimer.unref()

            const clearHandshakeTimer = () => clearTimeout(handshakeTimer)

            const removeSocketClient = () => {
                clearReliableSendState(socket)
                if (socketRemoved) return
                socketRemoved = true
                try {
                    const client = sessionManager.findClientBySocket(socket)
                    if (client) sessionManager.removeClient(client)
                } catch {
                    // Socket shutdown is best-effort. The room lease cleanup is
                    // still able to remove an already detached connection.
                }
            }

            socket.on("data", (chunk: string) => {
                if (protocolClosed) return
                buffer += chunk
                if (Buffer.byteLength(buffer, "utf8") > SESSION_MAX_BUFFER_BYTES) {
                    closeForProtocolViolation(`receive buffer exceeded ${SESSION_MAX_BUFFER_BYTES} bytes`)
                    return
                }
                while (buffer.includes("\0")) {
                    const idx = buffer.indexOf("\0")
                    const raw = buffer.substring(0, idx)
                    buffer = buffer.substring(idx + 1)
                    if (raw.trim().length === 0) continue
                    const frameBytes = Buffer.byteLength(raw, "utf8")
                    if (frameBytes > SESSION_MAX_FRAME_BYTES) {
                        closeForProtocolViolation(`frame exceeded ${SESSION_MAX_FRAME_BYTES} bytes`)
                        return
                    }

                    let data: any
                    try {
                        data = JSON.parse(raw)
                    } catch (e) {
                        closeForProtocolViolation(`invalid JSON frame: ${(e as Error).message}`)
                        return
                    }
                    try {
                        if (!handshakeDone) {
                            if (!data || typeof data !== "object" || typeof data.socklet !== "string") {
                                closeForProtocolViolation("first frame was not a valid handshake")
                                return
                            }
                            handshakeDone = true
                            clearHandshakeTimer()
                            isBattleSocket = data.socklet === "cooperation_battle"
                            handleHandshake(socket, data).catch((err) => {
                                console.error(`[TCP] handshake failed:`, err)
                                socket.destroy()
                            })
                        } else if (isBattleSocket) {
                            handleBattleMessage(socket, data)
                        } else {
                            const lobby = require("./lobby")
                            lobby.handleMessage(socket, data)
                        }
                    } catch (e) {
                        console.warn(`[TCP] message rejected from ${remoteAddr}:`, (e as Error).message)
                        socket.destroy()
                        return
                    }
                }
                if (Buffer.byteLength(buffer, "utf8") > SESSION_MAX_FRAME_BYTES) {
                    closeForProtocolViolation(`unterminated frame exceeded ${SESSION_MAX_FRAME_BYTES} bytes`)
                }
            })

            socket.on("close", () => {
                clearHandshakeTimer()
                gameVerboseLog(() => `[TCP] connection closed: ${remoteAddr}`)
                removeSocketClient()
            })

            socket.on("error", (err) => {
                clearHandshakeTimer()
                console.warn(`[TCP] socket error from ${remoteAddr}:`, err.message)
                removeSocketClient()
            })
        })

        server.listen(SESSION_PORT, SESSION_HOST, () => {
            console.log(`[TCP] session server listening on ${SESSION_HOST}:${SESSION_PORT}`)
            resolve()
        })
    })
}

export function stopSessionServer(): Promise<void> {
    return new Promise((resolve) => {
        if (!server) {
            resolve()
            return
        }
        server.close(() => {
            server = null
            resolve()
        })
    })
}
