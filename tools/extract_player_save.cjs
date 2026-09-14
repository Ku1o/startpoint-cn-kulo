#!/usr/bin/env node
const fs = require('node:fs')
const path = require('node:path')
const Database = require('better-sqlite3')

const MAX_BYTES = 64 * 1024 * 1024

function positiveId(value, label) {
    const text = String(value ?? '').trim()
    if (!/^[1-9]\d*$/.test(text) || !Number.isSafeInteger(Number(text))) {
        throw new Error(`${label} 必须是有效的正整数`)
    }
    return Number(text)
}

function parseArgs(argv) {
    const args = {}
    const names = new Map([
        ['--database', 'database'], ['--viewer-id', 'viewerId'],
        ['--player-id', 'playerId'], ['--output', 'output'],
    ])
    for (let index = 0; index < argv.length; index++) {
        const flag = argv[index]
        if (flag === '--help' || flag === '-h') { args.help = true; continue }
        if (flag === '--list') { args.list = true; continue }
        const name = names.get(flag)
        if (!name) throw new Error(`未知参数：${flag}`)
        if (Object.hasOwn(args, name)) throw new Error(`重复参数：${flag}`)
        const value = argv[++index]
        if (!value || value.startsWith('--')) throw new Error(`${flag} 缺少值`)
        args[name] = value
    }
    return args
}

function printHelp() {
    console.log(`从备份数据库按 viewer id 提取单人存档（只读）

  node tools/extract_player_save.cjs --database "F:/backup/wdfp_data.db" --viewer-id 123456789 --output "F:/recovery/save.json"

--database   必填：SQLite 数据库文件，或含 wdfp_data.db 的备份目录
--viewer-id  必填：游戏内玩家序号，通过 sessions 的 viewer 记录定位账号
--list       仅列出该账号下的存档，不导出文件
--player-id  该账号有多个存档时，明确选择其中一个内部玩家 ID
--output     JSON 输出路径；省略时写入当前目录，文件名含 viewer id / 玩家 ID / 时间

不会初始化、升级或覆盖备份数据库，也不会连接正在运行的服务。
输出为后台可导入的 V2 单人存档，不包含账号密码、设备绑定或登录令牌。
已有输出文件不会覆盖；旧库缺表或出现未分类玩家表时拒绝导出。
请先解压数据库备份。若备份带有 -wal / -shm 文件，请保留同目录同名配套文件。
恢复误删进度：先让玩家创建目标存档，再在后台该存档页面导入 JSON；目标 UID 保留。`)
}

function resolveDatabase(input) {
    if (!input) throw new Error('必须指定 --database，不能隐式使用在线数据库')
    let filename = path.resolve(input)
    if (fs.statSync(filename).isDirectory()) filename = path.join(filename, 'wdfp_data.db')
    filename = fs.realpathSync(filename)
    if (!fs.statSync(filename).isFile()) throw new Error('数据库路径必须是文件或备份目录')
    return filename
}

function outputPath(input, viewerId, playerId) {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-')
    const requested = path.resolve(input || `save_${viewerId}_${playerId}_${stamp}.json`)
    if (path.extname(requested).toLowerCase() !== '.json') throw new Error('输出文件必须使用 .json 扩展名')
    // Resolve existing parents before any writes, including Windows junctions.
    const parent = fs.realpathSync(path.dirname(requested))
    const resolved = path.join(parent, path.basename(requested))
    if ([requested, resolved].some(name => name.split(/[\\/]/).some(part => part.toLowerCase() === '.cdn'))) {
        throw new Error('不能将提取结果写入只读 .cdn 资源目录')
    }
    if (fs.existsSync(resolved)) throw new Error(`输出文件已存在，拒绝覆盖：${resolved}`)
    return resolved
}

function loadSnapshotApi() {
    // Never import data/db or player domains: they initialize a writable DB.
    const built = path.resolve(__dirname, '../out/data/snapshots/player-snapshot.js')
    if (!fs.existsSync(built)) throw new Error('缺少 out/data/snapshots/player-snapshot.js，请先在项目目录运行 npm run build')
    return require(built)
}

function extractPlayerSave(options) {
    const viewerId = positiveId(options.viewerId, 'viewer id')
    const selectedPlayerId = options.playerId === undefined ? undefined : positiveId(options.playerId, 'player id')
    const databasePath = resolveDatabase(options.database)
    const db = new Database(databasePath, { readonly: true, fileMustExist: true })
    let result
    try {
        db.pragma('query_only = ON')
        db.pragma('busy_timeout = 5000')
        // The viewer lookup and every portable table share a consistent read transaction.
        result = db.transaction(() => {
            const accounts = db.prepare('SELECT DISTINCT account_id FROM sessions WHERE token = ? AND type = 2').all(String(viewerId))
            if (accounts.length === 0) throw new Error(`备份中找不到 viewer id ${viewerId} 的账号映射；请确认备份日期及玩家序号`)
            if (accounts.length !== 1) throw new Error('viewer id 对应多个账号，拒绝猜测归属')
            const candidates = db.prepare('SELECT id, name FROM players WHERE account_id = ? ORDER BY id').all(accounts[0].account_id)
            if (candidates.length === 0) throw new Error(`viewer id ${viewerId} 的账号在此备份中已没有存档，请使用误删前的备份`)
            if (options.list) return { viewerId, candidates }
            if (selectedPlayerId === undefined && candidates.length > 1) {
                throw new Error(`该账号有多个存档，请用 --player-id 明确选择：${JSON.stringify(candidates)}`)
            }
            const player = selectedPlayerId === undefined ? candidates[0] : candidates.find(row => row.id === selectedPlayerId)
            if (!player) throw new Error(`player id ${selectedPlayerId} 不属于 viewer id ${viewerId}，拒绝提取`)
            const { createPlayerSaveSnapshotV2Sync } = loadSnapshotApi()
            let snapshot
            try {
                snapshot = createPlayerSaveSnapshotV2Sync(player.id, db)
            } catch (error) {
                throw new Error(`备份存档校验失败：${error.message}；请使用匹配数据库结构的工具版本，或先在独立副本上完成受支持的迁移`)
            }
            return { viewerId, playerId: player.id, snapshot }
        })()
    } finally {
        db.close()
    }
    if (options.list) return result
    const payload = Buffer.from(JSON.stringify(result.snapshot), 'utf8')
    if (payload.length > MAX_BYTES) throw new Error('存档超过后台导入的 64 MB 上限，未生成输出文件')
    const filename = outputPath(options.output, viewerId, result.playerId)
    // Exclusive creation also protects existing files/hardlinks if another process races us.
    const fd = fs.openSync(filename, 'wx', 0o600)
    try {
        fs.writeFileSync(fd, payload)
        fs.fsyncSync(fd)
    } catch (error) {
        fs.closeSync(fd)
        fs.unlinkSync(filename)
        throw error
    }
    fs.closeSync(fd)
    return {
        viewerId, playerId: result.playerId, playerName: result.snapshot.summary.playerName,
        output: filename, byteLength: payload.length, rowCount: result.snapshot.summary.rowCount,
        schemaFingerprint: result.snapshot.schemaFingerprint,
    }
}

if (require.main === module) {
    try {
        const args = parseArgs(process.argv.slice(2))
        if (args.help) printHelp()
        else console.log(JSON.stringify(extractPlayerSave(args), null, 2))
    } catch (error) {
        console.error(`提取失败：${error.message}`)
        process.exitCode = 1
    }
}

module.exports = { extractPlayerSave, parseArgs }
