const assert = require("assert")
const { spawn } = require("child_process")
const fs = require("fs")
const http = require("http")
const net = require("net")
const os = require("os")
const path = require("path")
const Database = require("better-sqlite3")
const { pack, unpack } = require("msgpackr")

const projectRoot = path.resolve(__dirname, "..")
const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-takeover-http-"))

function allocatePort() {
    return new Promise((resolve, reject) => {
        const probe = net.createServer()
        probe.once("error", reject)
        probe.listen(0, "127.0.0.1", () => {
            const address = probe.address()
            const port = typeof address === "object" && address ? address.port : 0
            probe.close(error => error ? reject(error) : resolve(port))
        })
    })
}

function postMsgpack(port, endpoint, body, udid) {
    const payload = pack(body).toString("base64")
    return new Promise((resolve, reject) => {
        const request = http.request({
            host: "127.0.0.1",
            port,
            path: `/api/index.php/${endpoint}`,
            method: "POST",
            headers: {
                "content-type": "application/x-www-form-urlencoded",
                "content-length": Buffer.byteLength(payload),
                udid,
            },
        }, response => {
            const chunks = []
            response.on("data", chunk => chunks.push(chunk))
            response.on("end", () => {
                try {
                    const raw = Buffer.concat(chunks).toString("utf8")
                    assert.strictEqual(response.statusCode, 200, raw)
                    resolve(unpack(Buffer.from(raw, "base64")))
                } catch (error) {
                    reject(error)
                }
            })
        })
        request.once("error", reject)
        request.end(payload)
    })
}

async function waitForServer(child, timeoutMs = 30_000) {
    return new Promise((resolve, reject) => {
        let output = ""
        const timeout = setTimeout(() => reject(new Error(`server startup timed out\n${output}`)), timeoutMs)
        const consume = chunk => {
            output += chunk.toString()
            if (output.includes("CN StarPoint listening")) {
                clearTimeout(timeout)
                resolve()
            }
        }
        child.stdout.on("data", consume)
        child.stderr.on("data", consume)
        child.once("exit", code => {
            clearTimeout(timeout)
            reject(new Error(`server exited before startup (code ${code})\n${output}`))
        })
    })
}

async function stopChild(child) {
    if (child.exitCode !== null) return
    child.kill()
    await Promise.race([
        new Promise(resolve => child.once("exit", resolve)),
        new Promise(resolve => setTimeout(resolve, 5_000)),
    ])
    if (child.exitCode === null) child.kill("SIGKILL")
}

async function main() {
    const [httpPort, sessionPort] = await Promise.all([allocatePort(), allocatePort()])
    const child = spawn(process.execPath, ["out/cn-server.js"], {
        cwd: projectRoot,
        env: {
            ...process.env,
            DATA_DIR: temporaryDataDir,
            CN_LISTEN_HOST: "127.0.0.1",
            CN_LISTEN_PORT: String(httpPort),
            SESSION_HOST: "127.0.0.1",
            SESSION_PORT: String(sessionPort),
            LOG_LEVEL: "fatal",
        },
        stdio: ["ignore", "pipe", "pipe"],
    })

    try {
        await waitForServer(child)
        const signup = await postMsgpack(httpPort, "tool/signup", {
            device_id: 700000001,
            channelNo: "test",
        }, "http-old-udid")
        assert.strictEqual(signup.data_headers.result_code, 1)
        const viewerId = signup.data_headers.viewer_id
        assert.ok(Number.isSafeInteger(viewerId) && viewerId > 0)

        const registered = await postMsgpack(httpPort, "take_over_register/register_take_over_data", {
            viewer_id: viewerId,
            input_password: "Abcdefg1",
        }, "http-old-udid")
        assert.strictEqual(registered.data_headers.result_code, 1)
        assert.strictEqual(registered.data.registered_viewer_id, viewerId)

        const transferred = await postMsgpack(httpPort, "take_over/take_over_by_take_over_data", {
            input_viewer_id: String(viewerId),
            input_password: "Abcdefg1",
            device_id: 700000002,
        }, "http-new-udid")
        assert.strictEqual(transferred.data_headers.result_code, 1)
        assert.strictEqual(transferred.data.abolished_viewer_id, 0)
        assert.strictEqual(transferred.data.linked_viewer_id, viewerId)

        const oldAccess = await postMsgpack(httpPort, "take_over_register/get_take_over_setting", {
            viewer_id: viewerId,
        }, "http-old-udid")
        assert.strictEqual(oldAccess.data_headers.result_code, 516)

        const newAccess = await postMsgpack(httpPort, "take_over_register/get_take_over_setting", {
            viewer_id: viewerId,
        }, "http-new-udid")
        assert.strictEqual(newAccess.data_headers.result_code, 1)
        assert.strictEqual(newAccess.data.exists_user_take_over_data, true)
    } finally {
        await stopChild(child)
    }

    const database = new Database(path.join(temporaryDataDir, "wdfp_data.db"), { readonly: true })
    try {
        assert.strictEqual(database.prepare(`SELECT COUNT(*) AS count FROM accounts`).get().count, 1)
        assert.deepEqual(database.prepare(`SELECT device_id FROM device_bindings`).all(), [{ device_id: 700000002 }])
        assert.strictEqual(database.prepare(`SELECT COUNT(*) AS count FROM account_transfer_audit`).get().count, 1)
    } finally {
        database.close()
    }
    console.log("account takeover full HTTP/MsgPack smoke test passed")
}

main()
    .finally(() => {
        const resolved = path.resolve(temporaryDataDir)
        if (resolved.startsWith(path.resolve(os.tmpdir()) + path.sep)) {
            fs.rmSync(resolved, { recursive: true, force: true })
        }
    })
    .catch(error => {
        console.error(error)
        process.exitCode = 1
    })
