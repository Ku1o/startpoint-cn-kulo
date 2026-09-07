const assert = require("node:assert/strict")
const Database = require("better-sqlite3")

const useCompiledServer = process.env.DAILY_VMONEY_MAIL_COMPILED === "1"
if (!useCompiledServer) require("ts-node/register/transpile-only")
const serverModuleRoot = useCompiledServer ? "../out" : "../src"
const {
    createDailyVmoneyMailScheduler,
    dispatchDailyVmoneyMailSync,
    ensureDailyVmoneyMailForPlayerSync,
    getDailyVmoneyMailConfigSync,
    getDailyVmoneyMailOverviewSync,
    updateDailyVmoneyMailConfigSync,
    validateDailyVmoneyMailConfigUpdate,
} = require(`${serverModuleRoot}/lib/daily-vmoney-mail`)

function createDatabase() {
    const db = new Database(":memory:")
    db.pragma("foreign_keys = ON")
    db.exec(`
        CREATE TABLE players (id INTEGER PRIMARY KEY);
        CREATE TABLE players_mails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            reason_id INTEGER NOT NULL DEFAULT 0,
            subject TEXT,
            description TEXT,
            type INTEGER NOT NULL,
            type_id INTEGER,
            number INTEGER NOT NULL DEFAULT 1,
            receive_time TEXT NOT NULL DEFAULT '0000-00-00 00:00:00',
            create_time TEXT NOT NULL,
            reward_period_limited INTEGER NOT NULL DEFAULT 0,
            reward_limit_time TEXT,
            FOREIGN KEY (player_id) REFERENCES players (id) ON DELETE CASCADE
        );
        CREATE TABLE daily_vmoney_mail_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            enabled INTEGER NOT NULL DEFAULT 0,
            amount INTEGER NOT NULL DEFAULT 150000,
            send_hour INTEGER NOT NULL DEFAULT 5,
            send_minute INTEGER NOT NULL DEFAULT 0,
            subject TEXT NOT NULL DEFAULT '每日千抽',
            description TEXT NOT NULL DEFAULT '每日星导石奖励，请查收。',
            updated_at_ms INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE daily_vmoney_mail_runs (
            bucket TEXT PRIMARY KEY,
            scheduled_at_ms INTEGER NOT NULL,
            executed_at_ms INTEGER NOT NULL,
            source TEXT NOT NULL,
            amount INTEGER NOT NULL,
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            sent_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE daily_vmoney_mail_grants (
            bucket TEXT NOT NULL,
            player_id INTEGER NOT NULL,
            mail_id INTEGER NOT NULL,
            created_at_ms INTEGER NOT NULL,
            PRIMARY KEY (bucket, player_id),
            FOREIGN KEY (player_id) REFERENCES players (id) ON DELETE CASCADE
        );
    `)
    return db
}

function chinaTime(year, month, day, hour, minute = 0) {
    return Date.UTC(year, month - 1, day, hour - 8, minute)
}

function mailCount(db, playerId) {
    return db.prepare("SELECT COUNT(*) AS count FROM players_mails WHERE player_id = ?").get(playerId).count
}

function testScheduledDispatchAndLatePlayer() {
    const db = createDatabase()
    try {
        db.exec("INSERT INTO players (id) VALUES (1), (2)")
        const defaults = getDailyVmoneyMailConfigSync(db)
        assert.equal(defaults.enabled, false)
        assert.equal(defaults.amount, 150000)
        assert.equal(defaults.sendHour, 5)

        updateDailyVmoneyMailConfigSync({ enabled: true }, chinaTime(2026, 8, 31, 4), db)
        assert.equal(
            dispatchDailyVmoneyMailSync(chinaTime(2026, 8, 31, 4, 59), "scheduler", false, db).status,
            "not_due",
        )

        const first = dispatchDailyVmoneyMailSync(chinaTime(2026, 8, 31, 5), "scheduler", false, db)
        assert.equal(first.status, "sent")
        assert.equal(first.run.bucket, "2026-08-31")
        assert.equal(first.run.sentCount, 2)
        assert.deepEqual(
            db.prepare("SELECT DISTINCT type, number, subject FROM players_mails").all(),
            [{ type: 4, number: 150000, subject: "每日千抽" }],
        )
        assert.equal(
            dispatchDailyVmoneyMailSync(chinaTime(2026, 8, 31, 6), "scheduler", false, db).status,
            "already_sent",
        )
        assert.equal(db.prepare("SELECT COUNT(*) AS count FROM players_mails").get().count, 2)

        db.exec("INSERT INTO players (id) VALUES (3)")
        assert.equal(ensureDailyVmoneyMailForPlayerSync(3, chinaTime(2026, 8, 31, 7), db), true)
        assert.equal(ensureDailyVmoneyMailForPlayerSync(3, chinaTime(2026, 8, 31, 7), db), false)
        assert.equal(mailCount(db, 3), 1)
        assert.equal(getDailyVmoneyMailOverviewSync(chinaTime(2026, 8, 31, 7), db).lastRun.sentCount, 3)

        const second = dispatchDailyVmoneyMailSync(chinaTime(2026, 9, 1, 5), "scheduler", false, db)
        assert.equal(second.status, "sent")
        assert.equal(second.run.bucket, "2026-09-01")
        assert.equal(second.run.sentCount, 3)
        assert.equal(db.prepare("SELECT COUNT(*) AS count FROM players_mails").get().count, 6)
    } finally {
        db.close()
    }
}

function testEnableAfterTimeAndManualIdempotency() {
    const db = createDatabase()
    try {
        db.exec("INSERT INTO players (id) VALUES (10)")
        const enabledAtNoon = chinaTime(2026, 8, 31, 12)
        updateDailyVmoneyMailConfigSync(
            { enabled: true, amount: 321, subject: "测试每日奖励", description: "测试正文" },
            enabledAtNoon,
            db,
        )
        assert.equal(dispatchDailyVmoneyMailSync(enabledAtNoon, "scheduler", false, db).status, "not_due")

        const forced = dispatchDailyVmoneyMailSync(enabledAtNoon, "manual", true, db)
        assert.equal(forced.status, "sent")
        assert.equal(forced.run.bucket, "2026-08-31")
        assert.equal(forced.run.amount, 321)
        assert.equal(dispatchDailyVmoneyMailSync(enabledAtNoon, "manual", true, db).status, "already_sent")
        assert.equal(mailCount(db, 10), 1)
    } finally {
        db.close()
    }
}

function testLatePlayerDoesNotReceiveStaleCycle() {
    const db = createDatabase()
    try {
        db.exec("INSERT INTO players (id) VALUES (1)")
        updateDailyVmoneyMailConfigSync({ enabled: true }, chinaTime(2026, 8, 1, 4), db)
        assert.equal(
            dispatchDailyVmoneyMailSync(chinaTime(2026, 8, 1, 5), "scheduler", false, db).status,
            "sent",
        )
        db.exec("INSERT INTO players (id) VALUES (2)")
        assert.equal(ensureDailyVmoneyMailForPlayerSync(2, chinaTime(2026, 8, 10, 6), db), false)
        assert.equal(mailCount(db, 2), 0)
    } finally {
        db.close()
    }
}

function testValidationAndSchedulerLifecycle() {
    assert.throws(() => validateDailyVmoneyMailConfigUpdate({}), /没有可更新/)
    assert.throws(() => validateDailyVmoneyMailConfigUpdate({ amount: 0 }), /星导石数量无效/)
    assert.throws(() => validateDailyVmoneyMailConfigUpdate({ sendHour: 24 }), /发送小时无效/)
    assert.throws(() => validateDailyVmoneyMailConfigUpdate({ subject: "" }), /邮件标题/)
    assert.deepEqual(
        validateDailyVmoneyMailConfigUpdate({ enabled: true, sendHour: 0, sendMinute: 0 }),
        { enabled: true, sendHour: 0, sendMinute: 0 },
    )

    const db = createDatabase()
    try {
        db.exec("INSERT INTO players (id) VALUES (20)")
        updateDailyVmoneyMailConfigSync(
            { enabled: true, sendHour: 0, sendMinute: 0 },
            0,
            db,
        )
        const logs = []
        const scheduler = createDailyVmoneyMailScheduler(db, {
            intervalMs: 60_000,
            logger: { log(message) { logs.push(message) }, warn(message) { logs.push(message) } },
        })
        scheduler.start()
        scheduler.stop()
        assert.equal(mailCount(db, 20), 1)
        assert.ok(logs.some(message => message.includes("sent=1")))
    } finally {
        db.close()
    }
}

testScheduledDispatchAndLatePlayer()
testEnableAfterTimeAndManualIdempotency()
testLatePlayerDoesNotReceiveStaleCycle()
testValidationAndSchedulerLifecycle()
console.log("daily vmoney mail tests passed")
