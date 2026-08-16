const assert = require("node:assert/strict")
const net = require("node:net")

async function reservePort() {
    const probe = net.createServer()
    await new Promise((resolve, reject) => {
        probe.once("error", reject)
        probe.listen(0, "127.0.0.1", resolve)
    })
    const address = probe.address()
    assert.ok(address && typeof address === "object")
    const port = address.port
    await new Promise(resolve => probe.close(resolve))
    return port
}

async function expectServerClose(port, payload) {
    await new Promise((resolve, reject) => {
        const socket = net.createConnection({ host: "127.0.0.1", port })
        const timeout = setTimeout(() => {
            socket.destroy()
            reject(new Error("guardrail did not close the socket in time"))
        }, 3_000)
        socket.once("connect", () => {
            if (payload !== undefined) socket.write(payload)
        })
        socket.on("error", () => {})
        socket.once("close", () => {
            clearTimeout(timeout)
            resolve()
        })
    })
}

async function main() {
    const port = await reservePort()
    process.env.SESSION_HOST = "127.0.0.1"
    process.env.SESSION_PORT = String(port)
    process.env.SESSION_HANDSHAKE_TIMEOUT_MS = "1000"
    process.env.SESSION_MAX_FRAME_BYTES = "1024"

    const { startSessionServer, stopSessionServer } = require("../out/multi/tcp/server.js")
    await startSessionServer()
    await expectServerClose(port, "not-json\0")
    await expectServerClose(port, "x".repeat(1_500))
    await expectServerClose(port, undefined)
    await stopSessionServer()
    console.log("multi_tcp_guardrails.test: ok")
}

main().then(
    () => process.exit(0),
    error => {
        console.error(error)
        process.exit(1)
    },
)
