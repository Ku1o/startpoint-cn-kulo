const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const { spawnSync } = require("node:child_process")
const Database = require("better-sqlite3")

const outDir = process.env.STARPOINT_TEST_OUT_DIR
    ? path.resolve(process.env.STARPOINT_TEST_OUT_DIR)
    : path.resolve(__dirname, "../out")

const TABLES = [
    "leaderboard_seasons",
    "leaderboard_runs",
    "leaderboard_run_rounds",
    "leaderboard_settlement_configs",
    "leaderboard_availability",
    "leaderboard_settlements",
    "leaderboard_settlement_results",
]

test("版本号已是 9 的旧库启动时仍会补齐排行榜表", () => {
    const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-leaderboard-upgrade-"))
    const databasePath = path.join(dataDir, "wdfp_data.db")
    const database = new Database(databasePath)
    database.pragma("foreign_keys = OFF")
    require(path.join(outDir, "data/initializers/wdfpData")).default(database, false)
    for (const table of [...TABLES].reverse()) {
        database.prepare(`DROP TABLE ${table}`).run()
    }
    database.close()
    fs.writeFileSync(`${databasePath}.version`, "9", "utf8")

    const dbModule = path.join(outDir, "data/db")
    const script = `
        const { getDb } = require(${JSON.stringify(dbModule)});
        const db = getDb();
        const expected = ${JSON.stringify(TABLES)};
        const found = new Set(db.prepare(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).all().map(row => row.name));
        if (!expected.every(name => found.has(name))) process.exit(3);
    `
    const child = spawnSync(process.execPath, ["-e", script], {
        cwd: path.resolve(__dirname, ".."),
        env: { ...process.env, DATA_DIR: dataDir },
        encoding: "utf8",
    })
    assert.equal(child.status, 0, `${child.stdout}\n${child.stderr}`)
})

test("已有排行榜赛季表升级时补齐内容版本且保留原赛季", () => {
    const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-leaderboard-season-upgrade-"))
    const databasePath = path.join(dataDir, "wdfp_data.db")
    const database = new Database(databasePath)
    database.pragma("foreign_keys = OFF")
    require(path.join(outDir, "data/initializers/wdfpData")).default(database, false)
    database.prepare("DROP TABLE leaderboard_seasons").run()
    database.prepare(`
        CREATE TABLE leaderboard_seasons (
            competition_key TEXT PRIMARY KEY,
            season INTEGER NOT NULL DEFAULT 1,
            started_at_ms INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'initial'
        )
    `).run()
    database.prepare(`
        INSERT INTO leaderboard_seasons
            (competition_key, season, started_at_ms, source)
        VALUES ('rush:700099:1', 7, 1234, 'legacy')
    `).run()
    database.close()
    fs.writeFileSync(`${databasePath}.version`, "9", "utf8")

    const dbModule = path.join(outDir, "data/db")
    const script = `
        const { getDb } = require(${JSON.stringify(dbModule)});
        const db = getDb();
        const columns = db.prepare("PRAGMA table_info('leaderboard_seasons')").all();
        if (!columns.some(row => row.name === "content_revision")) process.exit(4);
        const row = db.prepare(
            "SELECT season, started_at_ms, source, content_revision "
            + "FROM leaderboard_seasons WHERE competition_key = 'rush:700099:1'"
        ).get();
        if (JSON.stringify(row) !== JSON.stringify({
            season: 7, started_at_ms: 1234, source: "legacy", content_revision: null,
        })) process.exit(5);
    `
    const child = spawnSync(process.execPath, ["-e", script], {
        cwd: path.resolve(__dirname, ".."),
        env: { ...process.env, DATA_DIR: dataDir },
        encoding: "utf8",
    })
    assert.equal(child.status, 0, `${child.stdout}\n${child.stderr}`)
})
