const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const test = require("node:test")
const ts = require("typescript")

// Run with tools/run-isolated-check.cjs: refuse to open the ordinary database.
const sandbox = path.resolve(__dirname, "../tmp") + path.sep
for (const name of ["DATA_DIR", "GACHA_SEED_DIR"]) {
    assert.ok(process.env[name] && path.resolve(process.env[name]).startsWith(sandbox), `${name} must use the isolated check directory`)
}
require.extensions[".ts"] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText, filename)

const Fastify = require("fastify")
const version = require("../src/lib/version.ts")
const readManifest = version.getPatchManifest
const revision = "c".repeat(64)
version.getPatchManifest = () => ({ patches: [{ id: "synthetic-section-fixture", type: "patch", enabled: true,
    version: "1.4.900", quest_time_revisions: { "rush:700099": revision, "rush:700100": revision } }] })
const { getDb } = require("../src/data/db.ts")
const { insertAccountSync } = require("../src/data/domains/account.ts")
const { insertDefaultPlayerSync } = require("../src/data/domains/player.ts")
const playerRoutes = require("../src/routes/web_api/player.ts").default
const lookupModule = require("../src/routes/web_api/lookup.ts")
const { degreeDefinitions } = require("../src/lib/content-master.ts")
const db = getDb()
const app = Fastify()
app.register(playerRoutes, { prefix: "/api/player" })
app.register(lookupModule.default, { prefix: "/api/lookup" })
test.after(async () => { await app.close(); version.getPatchManifest = readManifest; db.close() })

function player() {
    const account = insertAccountSync({ appId: "wf_cn", idpAlias: "", idpCode: "fixture", idpId: "", status: "normal" })
    return insertDefaultPlayerSync(account.id)
}
function seed(playerId, section, questId) {
    db.prepare(`INSERT OR REPLACE INTO players_quest_progress
        (player_id, section, quest_id, finished, host_finished, unlocked, high_score,
         clear_rank, best_elapsed_time_ms, leader_character_id, multi_clear_count,
         s_plus_reward_received, best_time_revision)
        VALUES (?, ?, ?, 1, 1, 1, 12345, 5, 1000, 1, 7, 1, NULL)`).run(playerId, section, questId)
}
const snapshot = () => db.prepare("SELECT * FROM players_quest_progress ORDER BY player_id,section,quest_id").all()

test("partial detail only reads its requested collection; quest maintenance stays scoped and legacy full detail remains", async () => {
    const p = player(), other = player()
    const quests = [[24, 700099001], [24, 700099098], [24, 700100030], [24, 700100031], [24, 700099099], [24, 700007001], [2, 700099001]]
    for (const [section, id] of quests) { seed(p.id, section, id); seed(other.id, section, id) }
    db.prepare("INSERT OR REPLACE INTO players_items(id,amount,player_id) VALUES(100,7,?)").run(p.id)
    db.prepare("INSERT OR REPLACE INTO players_equipment(id,level,enhancement_level,protection,stack,player_id) VALUES(1,12,2,0,1,?)").run(p.id)
    db.prepare("INSERT OR REPLACE INTO players_drawn_quests(category_id,quest_id,odds_id,player_id) VALUES(24,700099001,1,?)").run(p.id)
    const before = snapshot()
    for (const section of ["player", "characters", "items", "equipment", "drawnQuests"]) {
        const response = await app.inject(`/api/player/${p.id}/detail?section=${section}`)
        assert.equal(response.statusCode, 200)
        const body = response.json()
        assert.deepEqual(Object.keys(body), [section])
        if (section !== "player") assert.ok(body[section].length > 0, `${section} fixture must be nonempty`)
        assert.deepEqual(snapshot(), before, `${section} must not run quest maintenance`)
    }
    for (const query of ["section=unknown", "section=", "section=player&section=questProgress"]) {
        assert.equal((await app.inject(`/api/player/${p.id}/detail?${query}`)).statusCode, 400)
        assert.deepEqual(snapshot(), before)
    }
    const response = await app.inject(`/api/player/${p.id}/detail?section=questProgress`)
    assert.equal(response.statusCode, 200)
    assert.deepEqual(Object.keys(response.json()), ["questProgress"])
    const finite = row => row.player_id === p.id && row.section === 24 && (
        row.quest_id >= 700099001 && row.quest_id <= 700099098 || row.quest_id >= 700100001 && row.quest_id <= 700100030)
    const expected = before.map(row => finite(row) ? { ...row, best_elapsed_time_ms: null, best_time_revision: revision } : row)
    assert.deepEqual(snapshot(), expected, "only target player's stale finite-tower times/revision may change")
    assert.deepEqual((await app.inject(`/api/player/${p.id}/detail?section=questProgress`)).json(), response.json())
    assert.deepEqual(snapshot(), expected, "repeated quest reads are idempotent")
    seed(p.id, 24, 700099001)
    const legacy = await app.inject(`/api/player/${p.id}/detail`)
    assert.equal(legacy.statusCode, 200)
    assert.deepEqual(Object.keys(legacy.json()), ["player", "characters", "items", "equipment", "questProgress", "drawnQuests"])
    assert.deepEqual(snapshot(), expected, "unqualified legacy GET retains original maintenance")
    assert.equal((await app.inject("/api/player/999999999/detail?section=items")).statusCode, 404)
})

test("lookup objects retain compatibility, degrees follow actual definitions, private ETags validate conditionally", async () => {
    const expected = lookupModule.buildDegreeLookup(degreeDefinitions)
    const response = await app.inject("/api/lookup/degrees")
    assert.equal(response.statusCode, 200)
    assert.deepEqual(response.json(), expected)
    assert.equal(Object.keys(expected).length, Object.keys(degreeDefinitions).length)
    assert.ok(Object.keys(expected).length > 0)
    for (const [id, row] of Object.entries(degreeDefinitions)) {
        assert.ok(typeof row.string_id === "string" && row.string_id.length > 0, `degree ${id} must have a real image identity`)
        assert.deepEqual(expected[id], { name: row.name, image: `dynamic/degree/${row.string_id}.png` })
    }
    for (const kind of ["characters", "items", "equipment", "quests", "degrees"]) {
        const first = await app.inject(`/api/lookup/${kind}`)
        assert.equal(first.statusCode, 200)
        assert.equal(typeof first.json(), "object")
        assert.ok(Object.keys(first.json()).length > 0)
        assert.equal(first.headers["cache-control"], "private, no-cache")
        assert.match(first.headers.etag, /^"[a-f0-9]{64}"$/)
        for (const condition of [first.headers.etag, `"other", W/${first.headers.etag}`, "*"]) {
            const cached = await app.inject({ url: `/api/lookup/${kind}`, headers: { "if-none-match": condition } })
            assert.equal(cached.statusCode, 304)
            assert.equal(cached.body, "")
        }
        assert.equal((await app.inject({ url: `/api/lookup/${kind}`, headers: { "if-none-match": '"not-current"' } })).statusCode, 200)
    }
})

test("item assignment preserves allowed zero and rejects fractional/nonfinite/out-of-range amounts without changing rows", async () => {
    const p = player()
    db.prepare("INSERT OR REPLACE INTO players_items(id,amount,player_id) VALUES(100,7,?)").run(p.id)
    const read = () => db.prepare("SELECT * FROM players_items WHERE player_id=? AND id=100").get(p.id)
    const zero = await app.inject({ method: "POST", url: `/api/player/${p.id}/item`, payload: { id: 100, count: 0 } })
    assert.equal(zero.statusCode, 200)
    assert.equal(zero.json().count, 0)
    assert.equal(read()?.amount ?? 0, 0)
    for (const count of [1.5, "NaN", "Infinity", -1, 2147483648]) {
        const before = read()
        const response = await app.inject({ method: "POST", url: `/api/player/${p.id}/item`, payload: { id: 100, count } })
        assert.equal(response.statusCode, 400, String(count))
        assert.deepEqual(read(), before)
    }
})
