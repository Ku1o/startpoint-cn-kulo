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

            socket.setEncoding("utf8")
            let buffer = ""
            let handshakeDone = false
            let isBattleSocket = false
            let socketRemoved = false

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
                buffer += chunk
                while (buffer.includes("\0")) {
                    const idx = buffer.indexOf("\0")
                    const raw = buffer.substring(0, idx)
                    buffer = buffer.substring(idx + 1)
                    if (raw.trim().length === 0) continue

                    try {
                        const data = JSON.parse(raw)
                        if (!handshakeDone && data.socklet) {
                            handshakeDone = true
                            isBattleSocket = data.socklet === "cooperation_battle"
                            handleHandshake(socket, data).catch((err) => {
                                console.error(`[TCP] handshake failed:`, err)
                                socket.destroy()
                            })
                        } else if (handshakeDone) {
                            if (isBattleSocket) {
                                handleBattleMessage(socket, data)
                            } else {
                                const lobby = require("./lobby")
                                lobby.handleMessage(socket, data)
                            }
                        }
                    } catch (e) {
                        console.warn(`[TCP] parse error from ${remoteAddr}:`, (e as Error).message)
                    }
                }
            })

            socket.on("close", () => {
                gameVerboseLog(() => `[TCP] connection closed: ${remoteAddr}`)
                removeSocketClient()
            })

            socket.on("error", (err) => {
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
