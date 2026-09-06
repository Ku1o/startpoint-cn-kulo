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

test("旧结算配置增加独立冻结开关，仅继承原来已启用的自动结算", () => {
    const database = new Database(":memory:")
    const init = require(path.join(outDir, "data/initializers/wdfpData")).default
    try {
        init(database, false)
        database.exec(`DROP TABLE leaderboard_settlement_configs;
            CREATE TABLE leaderboard_settlement_configs (
                competition_key TEXT PRIMARY KEY, auto_enabled INTEGER NOT NULL DEFAULT 0,
                settle_at_ms INTEGER, repeat_interval_ms INTEGER, reward_tiers_json TEXT NOT NULL,
                mail_subject TEXT NOT NULL, mail_body TEXT NOT NULL, exclude_bots INTEGER NOT NULL DEFAULT 1,
                updated_at_ms INTEGER NOT NULL
            )`)
        for (const auto of [0, 1]) database.prepare(`INSERT INTO leaderboard_settlement_configs
            VALUES (?, ?, 123456789, 3600000, '[]', 'custom title', 'custom body', 0, 42)`)
            .run(`legacy-${auto}`, auto)
        init(database, true)
        const rows = database.prepare("SELECT * FROM leaderboard_settlement_configs ORDER BY competition_key").all()
        assert.deepEqual(rows.map(row => [row.auto_enabled, row.freeze_enabled]), [[0, 0], [1, 1]])
        for (const row of rows) {
            assert.equal(row.settle_at_ms, 123456789)
            assert.equal(row.repeat_interval_ms, 3600000)
            assert.equal(row.mail_subject, "custom title")
            assert.equal(row.mail_body, "custom body")
            assert.equal(row.exclude_bots, 0)
            assert.equal(row.updated_at_ms, 42)
        }
        database.prepare("UPDATE leaderboard_settlement_configs SET freeze_enabled = 1 WHERE competition_key = 'legacy-0'").run()
        init(database, true)
        assert.equal(database.prepare("SELECT freeze_enabled FROM leaderboard_settlement_configs WHERE competition_key = 'legacy-0'").get().freeze_enabled, 1)
    } finally { database.close() }
})

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
