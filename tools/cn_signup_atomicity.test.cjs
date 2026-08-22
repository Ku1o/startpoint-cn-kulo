const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const useCompiledServer = process.env.CN_SIGNUP_COMPILED === "1"
if (!useCompiledServer) require("ts-node/register/transpile-only")
const serverModuleRoot = useCompiledServer ? "../out" : "../src"

const dataDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "sp-cn-signup-"))
process.env.DATA_DIR = dataDirectory

async function main() {
    const Fastify = require("fastify")
    const { getDb } = require(`${serverModuleRoot}/data/db`)
    const signupRoutes = require(`${serverModuleRoot}/routes/cn/tool`).default

    const database = getDb()
    assert.equal(
        database.pragma("temp_store", { simple: true }),
        1,
        "SQLite temporary data must use the stable disk-backed temp directory",
    )

    const app = Fastify()
    await app.register(signupRoutes, { prefix: "/api/index.php/tool" })
    await app.ready()

    database.exec(`
        CREATE TRIGGER fail_default_player_materialization
        BEFORE INSERT ON daily_challenge_point_list_entries
        BEGIN
            SELECT RAISE(ABORT, 'forced default-player materialization failure');
        END;
    `)

    const response = await app.inject({
        method: "POST",
        url: "/api/index.php/tool/signup",
        headers: { udid: "atomic-signup-test" },
        payload: {
            device_id: 880000001,
            channelNo: "test",
        },
    })

    assert.equal(response.statusCode, 500)
    assert.match(response.body, /forced default-player materialization failure/)
    assert.equal(database.prepare("SELECT COUNT(*) AS count FROM accounts").get().count, 0)
    assert.equal(database.prepare("SELECT COUNT(*) AS count FROM players").get().count, 0)
    assert.equal(database.prepare("SELECT COUNT(*) AS count FROM device_bindings").get().count, 0)

    await app.close()
    database.close()
    console.log("CN signup atomicity and disk-backed SQLite temp-store test passed")
}

main()
    .finally(() => {
        const resolved = path.resolve(dataDirectory)
        if (resolved.startsWith(path.resolve(os.tmpdir()) + path.sep)) {
            fs.rmSync(resolved, { recursive: true, force: true })
        }
    })
    .catch(error => {
        console.error(error)
        process.exitCode = 1
    })
