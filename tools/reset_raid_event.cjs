#!/usr/bin/env node

const fs = require("node:fs")
const path = require("node:path")
const sqlite3 = require("better-sqlite3")

function fail(message) {
    console.error(`错误：${message}`)
    process.exitCode = 1
}

function parseArgs(argv) {
    const result = { apply: false, serverStopped: false }
    for (let index = 0; index < argv.length; index++) {
        const arg = argv[index]
        if (arg === "--apply") result.apply = true
        else if (arg === "--server-stopped") result.serverStopped = true
        else if (arg === "--data-dir") result.dataDir = argv[++index]
        else if (arg === "--event-id") result.eventId = Number(argv[++index])
        else if (arg === "--confirm") result.confirm = argv[++index]
        else if (arg === "--help" || arg === "-h") result.help = true
        else throw new Error(`未知参数：${arg}`)
    }
    return result
}

function printHelp() {
    console.log(`战阵之宴离线重置工具

预览（不会写入）：
  npm run raid:reset -- --data-dir <数据库目录> --event-id 7

执行（必须先停止游戏服务）：
  npm run raid:reset -- --data-dir <数据库目录> --event-id 7 \\
    --apply --server-stopped --confirm RESET-RAID-7

执行时会先备份 wdfp_data.db 和版本文件。`)
}

function makeBackupStamp() {
    const now = new Date()
    const pad = (value, width = 2) => String(value).padStart(width, "0")
    return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-` +
        `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}-` +
        pad(now.getMilliseconds(), 3)
}

async function main() {
    let args
    try {
        args = parseArgs(process.argv.slice(2))
    } catch (error) {
        fail(error.message)
        return
    }
    if (args.help) {
        printHelp()
        return
    }
    if (!Number.isSafeInteger(args.eventId) || args.eventId < 1) {
        fail("必须显式提供有效的 --event-id")
        return
    }

    const rawDataDir = args.dataDir || process.env.DATA_DIR
    if (!rawDataDir) {
        fail("必须提供 --data-dir，或在环境中设置 DATA_DIR")
        return
    }
    const dataDir = path.resolve(rawDataDir)
    const databasePath = path.resolve(dataDir, "wdfp_data.db")
    if (path.dirname(databasePath) !== dataDir || !fs.existsSync(databasePath)) {
        fail(`数据库不存在：${databasePath}`)
        return
    }

    if (args.apply) {
        const expected = `RESET-RAID-${args.eventId}`
        if (!args.serverStopped || args.confirm !== expected) {
            fail(`执行重置必须确认服务已停止，并提供 --confirm ${expected}`)
            return
        }
    }

    const builtResetModule = path.resolve(__dirname, "../out/lib/raid-event-reset.js")
    if (!fs.existsSync(builtResetModule)) {
        require("ts-node/register/transpile-only")
    }
    const {
        previewRaidEventResetSync,
        resetRaidEventSync,
    } = require(fs.existsSync(builtResetModule)
        ? builtResetModule
        : "../src/lib/raid-event-reset")

    const database = new sqlite3(databasePath, {
        readonly: !args.apply,
        fileMustExist: true,
    })
    database.pragma("busy_timeout = 1000")
    database.pragma("foreign_keys = ON")

    try {
        const preview = previewRaidEventResetSync(database, args.eventId)
        console.log(JSON.stringify({
            mode: args.apply ? "apply" : "dry-run",
            eventId: args.eventId,
            database: databasePath,
            rowsToDelete: preview,
            preserved: ["玩家背包与货币", "已经发放的奖励", "账号与存档", "Raid 三套编队"],
        }, null, 2))

        if (!args.apply) {
            console.log("预览完成；数据库未写入。")
            return
        }

        const backupName = `raid-event-reset-${args.eventId}-${makeBackupStamp()}`
        const backupDirectory = path.resolve(dataDir, "admin-backups", backupName)
        const backupRoot = path.resolve(dataDir, "admin-backups")
        if (path.dirname(backupDirectory) !== backupRoot) {
            throw new Error("备份路径校验失败")
        }
        fs.mkdirSync(backupDirectory, { recursive: true })
        await database.backup(path.join(backupDirectory, "wdfp_data.db"))

        const versionPath = path.join(dataDir, "wdfp_data.db.version")
        if (fs.existsSync(versionPath)) {
            fs.copyFileSync(versionPath, path.join(backupDirectory, "wdfp_data.db.version"))
        }
        fs.writeFileSync(
            path.join(backupDirectory, "backup-info.json"),
            JSON.stringify({
                createdAt: new Date().toISOString(),
                type: "raid-event-reset",
                eventId: args.eventId,
                sourceDatabase: databasePath,
                rowsBeforeReset: preview,
            }, null, 2),
            "utf8",
        )

        const deleted = resetRaidEventSync(database, args.eventId)
        const after = previewRaidEventResetSync(database, args.eventId)
        const remaining = Object.values(after).reduce((sum, value) => sum + value, 0)
        if (remaining !== 0) throw new Error(`重置后仍有 ${remaining} 条活动状态残留`)

        console.log(JSON.stringify({
            reset: "completed",
            eventId: args.eventId,
            deleted,
            backupDirectory,
        }, null, 2))
        console.log("重置完成；现在可以重新启动游戏服务。")
    } finally {
        database.close()
    }
}

main().catch(error => fail(error instanceof Error ? error.message : String(error)))
