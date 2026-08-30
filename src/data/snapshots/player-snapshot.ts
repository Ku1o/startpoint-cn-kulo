import { createHash } from "crypto"
import type { Database as BetterSqlite3Database } from "better-sqlite3"
import { getServerDate, getTimeOffset } from "../../utils"

type SnapshotScalar = string | number | null

interface SnapshotTableData {
    columns: string[]
    rows: SnapshotScalar[][]
}

export interface PlayerSaveSnapshotV2 {
    schema: "starpoint-cn-save"
    version: 2
    scope: "player-archive"
    exportedAt: string
    playerId: number
    schemaFingerprint: string
    summary: {
        playerName: string
        includedTableCount: number
        rowCount: number
        excludedState: Array<{
            tables: string[]
            policy: "preserve-target" | "reset"
            reason: string
        }>
    }
    data: {
        tables: Record<string, SnapshotTableData>
    }
}

export interface RestorePlayerSnapshotOptions {
    includeArchiveHistory?: boolean
}

export interface RestorePlayerSnapshotResult {
    restoredTables: number
    restoredRows: number
    skippedTables: string[]
    resetTables: string[]
}

interface TableInfoRow {
    cid: number
    name: string
    type: string
    notnull: number
    dflt_value: string | null
    pk: number
}

const ARCHIVE_HISTORY_TABLES = new Set([
    "players_mails",
    "players_receive_history",
    "players_practice_battle_history",
])

// Dependency order. Every durable table directly owned by a player must be
// listed here. The coverage audit below intentionally makes future exports
// fail closed when a new player-owned table is added without a snapshot policy.
export const PLAYER_SNAPSHOT_V2_TABLES = Object.freeze([
    "players",
    "players_degrees",
    "players_options",
    "players_encyclopedia_keywords",
    "players_player_history_settings",
    "players_triggered_tutorials",
    "players_mails",
    "players_receive_history",
    "players_practice_battle_history",
    "players_cleared_regular_missions",
    "players_items",
    "players_collected_items",
    "daily_challenge_point_list_entries",
    "daily_challenge_point_list_campaigns",
    "players_characters",
    "players_characters_bond_tokens",
    "players_characters_mana_nodes",
    "players_character_awake_unlocks",
    "players_party_groups",
    "players_parties",
    "players_equipment",
    "players_quest_progress",
    "players_character_quest_clears",
    "players_party_member_co_clears",
    "players_party_race_clears",
    "players_periodic_snapshots",
    "players_mission_battle_counters",
    "players_gacha_info",
    "players_gacha_campaigns",
    "players_drawn_quests",
    "players_periodic_reward_points",
    "players_active_missions",
    "players_active_missions_stages",
    "players_active_mission_counters",
    "players_active_mission_battle_condition_facts",
    "players_active_mission_battle_facts",
    "players_category_missions",
    "players_category_mission_stages",
    "players_mission_counters",
    "players_mission_counter_snapshots",
    "players_pass_cards",
    "players_pass_card_rewards",
    "players_box_gacha",
    "players_box_gacha_drawn_rewards",
    "players_start_dash_exchange_campaigns",
    "players_multi_special_exchange_campaigns",
    "players_rush_events",
    "players_rush_events_cleared_folders",
    "players_rush_events_played_parties",
    "players_raid_event_overall_rewards",
    "players_carnival_event_records",
    "players_carnival_event_rewards",
    "players_carnival_event_reward_claims",
    "players_shop_purchases",
] as const)

const EXCLUDED_PLAYER_STATE = Object.freeze([
    {
        tables: ["players_active_quests"],
        policy: "reset" as const,
        reason: "未完成战斗恢复数据不能跨存档恢复，导入时清除。",
    },
    {
        tables: ["players_repair_versions"],
        policy: "reset" as const,
        reason: "永久修复版本标记属于服务器派生状态，导入时清除并按当前版本重新校验。",
    },
    {
        tables: ["players_follows", "published_parties", "quest_npc_party_pool", "raid_event_global_kill_ledger"],
        policy: "preserve-target" as const,
        reason: "跨玩家关系、公开副本和全局幂等账本不属于便携玩家存档，覆盖既有存档时保留目标侧数据。",
    },
    {
        tables: ["leaderboard_runs", "leaderboard_run_rounds", "leaderboard_settlement_results"],
        policy: "preserve-target" as const,
        reason: "排行榜对局、轮次明细和结算结果属于服务器公共竞赛记录，不随玩家存档迁移，覆盖时保留目标侧数据。",
    },
])

const REMAPPED_AUTOINCREMENT_IDS = new Map<string, ReadonlySet<string>>([
    ["players_mails", new Set(["id"])],
    ["players_receive_history", new Set(["id"])],
    ["players_practice_battle_history", new Set(["id"])],
])

const MAX_TOTAL_ROWS = 500_000
const MAX_STRING_LENGTH = 8 * 1024 * 1024
const TEXT_STORED_IN_INTEGER_COLUMNS = new Set([
    "players.stamina_heal_time",
    "players.exp_pooled_time",
])

function getDefaultDatabase(): BetterSqlite3Database {
    // Keep the default connection lazy. Read-only worker threads pass their
    // own connection and must not initialize the main writable database.
    return require("../db").getDb() as BetterSqlite3Database
}

function quoteIdentifier(value: string): string {
    return `"${value.replace(/"/g, '""')}"`
}

function getTableInfo(db: BetterSqlite3Database, table: string): TableInfoRow[] {
    const rows = db.prepare(`PRAGMA table_info(${quoteIdentifier(table)})`).all() as TableInfoRow[]
    if (rows.length === 0) throw new Error(`存档表不存在：${table}`)
    return rows
}

function getTableColumns(db: BetterSqlite3Database, table: string): string[] {
    return getTableInfo(db, table).map(column => column.name)
}

function getPrimaryKeyColumns(db: BetterSqlite3Database, table: string): string[] {
    return getTableInfo(db, table)
        .filter(column => column.pk > 0)
        .sort((left, right) => left.pk - right.pk)
        .map(column => column.name)
}

function getSchemaFingerprint(db: BetterSqlite3Database): string {
    const schema = PLAYER_SNAPSHOT_V2_TABLES.map(table => ({
        table,
        columns: getTableInfo(db, table).map(column => ({
            name: column.name,
            type: column.type,
            notnull: column.notnull,
            defaultValue: column.dflt_value,
            pk: column.pk,
        })),
    }))
    return createHash("sha256").update(JSON.stringify(schema)).digest("hex")
}

function getPlayerReferencingTables(db: BetterSqlite3Database): Set<string> {
    const tableRows = db.prepare(`
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
    `).all() as Array<{ name: string }>
    const result = new Set<string>()
    for (const { name } of tableRows) {
        const foreignKeys = db.prepare(`PRAGMA foreign_key_list(${quoteIdentifier(name)})`).all() as Array<{ table: string }>
        if (foreignKeys.some(foreignKey => foreignKey.table === "players")) result.add(name)
    }
    return result
}

export function assertPlayerSnapshotCoverageSync(
    db: BetterSqlite3Database = getDefaultDatabase(),
): void {
    const classified = new Set<string>(PLAYER_SNAPSHOT_V2_TABLES.slice(1))
    for (const exclusion of EXCLUDED_PLAYER_STATE) {
        for (const table of exclusion.tables) classified.add(table)
    }
    const referencing = getPlayerReferencingTables(db)
    const unknown = [...referencing].filter(table => !classified.has(table)).sort()
    if (unknown.length > 0) {
        throw new Error(`发现尚未登记存档策略的玩家表：${unknown.join(", ")}`)
    }
}

function assertSnapshotScalar(value: unknown, context: string): asserts value is SnapshotScalar {
    if (value === null) return
    if (typeof value === "number") {
        if (!Number.isFinite(value)) throw new Error(`${context}: 数字不是有限值`)
        return
    }
    if (typeof value === "string") {
        if (value.length > MAX_STRING_LENGTH) throw new Error(`${context}: 字符串过长`)
        return
    }
    throw new Error(`${context}: 只允许字符串、数字或 null`)
}

function assertSnapshotColumnValue(
    value: unknown,
    table: string,
    column: TableInfoRow,
    context: string,
): asserts value is SnapshotScalar {
    assertSnapshotScalar(value, context)
    if (value === null) {
        if (column.notnull === 1 || column.pk > 0) throw new Error(`${context}: 必填列不能为 null`)
        return
    }
    const declaredType = TEXT_STORED_IN_INTEGER_COLUMNS.has(`${table}.${column.name}`)
        ? "TEXT"
        : column.type.trim().toUpperCase()
    if (declaredType === "INTEGER" && (typeof value !== "number" || !Number.isSafeInteger(value))) {
        throw new Error(`${context}: INTEGER 列必须是安全整数`)
    }
    if ((declaredType === "TEXT" || declaredType === "DATE") && typeof value !== "string") {
        throw new Error(`${context}: ${declaredType} 列必须是字符串`)
    }
}

function readSnapshotTable(
    db: BetterSqlite3Database,
    table: string,
    playerId: number,
): SnapshotTableData {
    const columns = getTableColumns(db, table)
    const primaryKey = getPrimaryKeyColumns(db, table)
    const selectedColumns = columns.map(quoteIdentifier).join(", ")
    const whereColumn = table === "players" ? "id" : "player_id"
    const orderBy = primaryKey.length > 0
        ? ` ORDER BY ${primaryKey.map(quoteIdentifier).join(", ")}`
        : ""
    const rows = db.prepare(`
        SELECT ${selectedColumns}
        FROM ${quoteIdentifier(table)}
        WHERE ${quoteIdentifier(whereColumn)} = ?${orderBy}
    `).all(playerId) as Array<Record<string, unknown>>
    return {
        columns,
        rows: rows.map((row, rowIndex) => columns.map(column => {
            const value = row[column]
            assertSnapshotScalar(value, `${table}[${rowIndex}].${column}`)
            return value
        })),
    }
}

export function createPlayerSaveSnapshotV2Sync(
    playerId: number,
    db: BetterSqlite3Database = getDefaultDatabase(),
): PlayerSaveSnapshotV2 {
    if (!Number.isSafeInteger(playerId) || playerId < 1) throw new Error("玩家 ID 无效")
    assertPlayerSnapshotCoverageSync(db)

    const tables: Record<string, SnapshotTableData> = {}
    let rowCount = 0
    for (const table of PLAYER_SNAPSHOT_V2_TABLES) {
        const tableData = readSnapshotTable(db, table, playerId)
        tables[table] = tableData
        rowCount += tableData.rows.length
    }
    if (tables.players.rows.length !== 1) throw new Error(`玩家 ${playerId} 不存在或数据不唯一`)

    const playerNameIndex = tables.players.columns.indexOf("name")
    const playerName = tables.players.rows[0][playerNameIndex]
    if (typeof playerName !== "string") throw new Error("玩家名称无效")

    const snapshot: PlayerSaveSnapshotV2 = {
        schema: "starpoint-cn-save",
        version: 2,
        scope: "player-archive",
        exportedAt: new Date().toISOString(),
        playerId,
        schemaFingerprint: getSchemaFingerprint(db),
        summary: {
            playerName,
            includedTableCount: PLAYER_SNAPSHOT_V2_TABLES.length,
            rowCount,
            excludedState: EXCLUDED_PLAYER_STATE.map(entry => ({
                tables: [...entry.tables],
                policy: entry.policy,
                reason: entry.reason,
            })),
        },
        data: { tables },
    }
    return validatePlayerSaveSnapshotV2Sync(snapshot, db)
}

export function isPlayerSaveSnapshotV2(value: unknown): value is PlayerSaveSnapshotV2 {
    if (value === null || typeof value !== "object") return false
    const candidate = value as Partial<PlayerSaveSnapshotV2>
    return candidate.schema === "starpoint-cn-save" && candidate.version === 2
}

export function validatePlayerSaveSnapshotV2Sync(
    value: unknown,
    db: BetterSqlite3Database = getDefaultDatabase(),
): PlayerSaveSnapshotV2 {
    if (!isPlayerSaveSnapshotV2(value)) throw new Error("不是有效的 V2 玩家存档")
    const snapshot = value as PlayerSaveSnapshotV2
    if (snapshot.scope !== "player-archive") throw new Error(`不支持的存档范围：${String(snapshot.scope)}`)
    if (!Number.isSafeInteger(snapshot.playerId) || snapshot.playerId < 1) throw new Error("存档来源玩家 ID 无效")
    if (typeof snapshot.exportedAt !== "string" || !Number.isFinite(Date.parse(snapshot.exportedAt))) {
        throw new Error("存档导出时间无效")
    }

    assertPlayerSnapshotCoverageSync(db)
    const expectedFingerprint = getSchemaFingerprint(db)
    if (snapshot.schemaFingerprint !== expectedFingerprint) {
        throw new Error("存档数据库结构与当前服务器不一致，拒绝执行覆盖；请先使用匹配版本迁移")
    }
    if (!snapshot.data || typeof snapshot.data !== "object" || !snapshot.data.tables || typeof snapshot.data.tables !== "object") {
        throw new Error("存档缺少 data.tables")
    }

    const expectedTables = new Set<string>(PLAYER_SNAPSHOT_V2_TABLES)
    const actualTables = Object.keys(snapshot.data.tables)
    const missing = [...expectedTables].filter(table => !Object.prototype.hasOwnProperty.call(snapshot.data.tables, table))
    const extra = actualTables.filter(table => !expectedTables.has(table))
    if (missing.length > 0 || extra.length > 0) {
        throw new Error(`存档表集合不完整；缺少：${missing.join(", ") || "无"}；未知：${extra.join(", ") || "无"}`)
    }

    let totalRows = 0
    for (const table of PLAYER_SNAPSHOT_V2_TABLES) {
        const tableData = snapshot.data.tables[table]
        if (!tableData || typeof tableData !== "object") throw new Error(`${table}: 表数据无效`)
        const tableInfo = getTableInfo(db, table)
        const expectedColumns = tableInfo.map(column => column.name)
        if (!Array.isArray(tableData.columns) || JSON.stringify(tableData.columns) !== JSON.stringify(expectedColumns)) {
            throw new Error(`${table}: 列定义与当前服务器不一致`)
        }
        if (!Array.isArray(tableData.rows)) throw new Error(`${table}: rows 不是数组`)
        totalRows += tableData.rows.length
        if (totalRows > MAX_TOTAL_ROWS) throw new Error(`存档行数超过安全上限 ${MAX_TOTAL_ROWS}`)

        const playerIdColumn = table === "players" ? "id" : "player_id"
        const playerIdIndex = expectedColumns.indexOf(playerIdColumn)
        for (let rowIndex = 0; rowIndex < tableData.rows.length; rowIndex++) {
            const row = tableData.rows[rowIndex]
            if (!Array.isArray(row) || row.length !== expectedColumns.length) {
                throw new Error(`${table}[${rowIndex}]: 列数不正确`)
            }
            for (let columnIndex = 0; columnIndex < row.length; columnIndex++) {
                assertSnapshotColumnValue(
                    row[columnIndex],
                    table,
                    tableInfo[columnIndex],
                    `${table}[${rowIndex}].${expectedColumns[columnIndex]}`,
                )
            }
            if (row[playerIdIndex] !== snapshot.playerId) {
                throw new Error(`${table}[${rowIndex}]: 混入了其他玩家的数据`)
            }
        }
    }
    if (snapshot.data.tables.players.rows.length !== 1) throw new Error("存档必须且只能包含一条 players 主记录")
    const playerTable = snapshot.data.tables.players
    const playerName = playerTable.rows[0][playerTable.columns.indexOf("name")]
    if (!snapshot.summary || typeof snapshot.summary !== "object") throw new Error("存档缺少 summary")
    if (snapshot.summary.playerName !== playerName) throw new Error("存档摘要中的玩家名称不一致")
    if (snapshot.summary.includedTableCount !== PLAYER_SNAPSHOT_V2_TABLES.length) {
        throw new Error("存档摘要中的表数量不一致")
    }
    if (snapshot.summary.rowCount !== totalRows) throw new Error("存档摘要中的行数量不一致")
    return snapshot
}

function canonicalRows(
    table: string,
    columns: string[],
    rows: SnapshotScalar[][],
    targetPlayerId: number,
): string[] {
    const omitted = REMAPPED_AUTOINCREMENT_IDS.get(table) ?? new Set<string>()
    const playerIdIndex = columns.indexOf("player_id")
    return rows.map(row => {
        const canonical: Record<string, SnapshotScalar> = {}
        for (let index = 0; index < columns.length; index++) {
            const column = columns[index]
            if (omitted.has(column)) continue
            canonical[column] = index === playerIdIndex ? targetPlayerId : row[index]
        }
        return JSON.stringify(canonical)
    }).sort()
}

function assertRestoredTable(
    db: BetterSqlite3Database,
    table: string,
    source: SnapshotTableData,
    targetPlayerId: number,
): void {
    const actual = readSnapshotTable(db, table, targetPlayerId)
    const expectedRows = canonicalRows(table, source.columns, source.rows, targetPlayerId)
    const actualRows = canonicalRows(table, actual.columns, actual.rows, targetPlayerId)
    if (JSON.stringify(actualRows) !== JSON.stringify(expectedRows)) {
        throw new Error(`${table}: 写入后校验不一致`)
    }
}

export function restorePlayerSaveSnapshotV2Sync(
    snapshotValue: unknown,
    targetPlayerId: number,
    options: RestorePlayerSnapshotOptions = {},
    db: BetterSqlite3Database = getDefaultDatabase(),
): RestorePlayerSnapshotResult {
    if (!Number.isSafeInteger(targetPlayerId) || targetPlayerId < 1) throw new Error("目标玩家 ID 无效")
    const snapshot = validatePlayerSaveSnapshotV2Sync(snapshotValue, db)
    const target = db.prepare(`SELECT account_id FROM players WHERE id = ?`).get(targetPlayerId) as { account_id: number } | undefined
    if (!target) throw new Error(`目标玩家 ${targetPlayerId} 不存在`)

    const includeArchiveHistory = options.includeArchiveHistory !== false
    const skippedTables = [...ARCHIVE_HISTORY_TABLES].filter(() => !includeArchiveHistory)
    const restoredTables = PLAYER_SNAPSHOT_V2_TABLES
        .filter(table => table !== "players")
        .filter(table => includeArchiveHistory || !ARCHIVE_HISTORY_TABLES.has(table))
    const resetTables = EXCLUDED_PLAYER_STATE
        .filter(entry => entry.policy === "reset")
        .flatMap(entry => [...entry.tables])
    const currentPoolTime = getServerDate().toISOString()
    const currentOffset = getTimeOffset() ?? 0

    let restoredRows = 1
    const restore = db.transaction(() => {
        for (const table of [...restoredTables].reverse()) {
            db.prepare(`DELETE FROM ${quoteIdentifier(table)} WHERE player_id = ?`).run(targetPlayerId)
        }
        for (const table of resetTables) {
            db.prepare(`DELETE FROM ${quoteIdentifier(table)} WHERE player_id = ?`).run(targetPlayerId)
        }

        const playerTable = snapshot.data.tables.players
        const sourcePlayer = playerTable.rows[0]
        const updateColumns = playerTable.columns.filter(column => column !== "id" && column !== "account_id")
        const updateValues = updateColumns.map(column => {
            if (column === "exp_pooled_time") return currentPoolTime
            if (column === "time_offset") return currentOffset
            return sourcePlayer[playerTable.columns.indexOf(column)]
        })
        const playerUpdate = db.prepare(`
            UPDATE players
            SET ${updateColumns.map(column => `${quoteIdentifier(column)} = ?`).join(", ")}
            WHERE id = ?
        `).run(...updateValues, targetPlayerId)
        if (playerUpdate.changes !== 1) throw new Error("目标玩家主记录更新失败")

        for (const table of restoredTables) {
            const tableData = snapshot.data.tables[table]
            const omitted = REMAPPED_AUTOINCREMENT_IDS.get(table) ?? new Set<string>()
            const insertColumns = tableData.columns.filter(column => !omitted.has(column))
            if (tableData.rows.length === 0) continue
            const placeholders = insertColumns.map(() => "?").join(", ")
            const insert = db.prepare(`
                INSERT INTO ${quoteIdentifier(table)} (${insertColumns.map(quoteIdentifier).join(", ")})
                VALUES (${placeholders})
            `)
            const playerIdIndex = tableData.columns.indexOf("player_id")
            for (const row of tableData.rows) {
                const values = insertColumns.map(column => {
                    const sourceIndex = tableData.columns.indexOf(column)
                    return sourceIndex === playerIdIndex ? targetPlayerId : row[sourceIndex]
                })
                insert.run(...values)
                restoredRows++
            }
        }

        const restoredPlayer = readSnapshotTable(db, "players", targetPlayerId)
        if (restoredPlayer.rows.length !== 1) throw new Error("恢复后玩家主记录不唯一")
        const restoredPlayerRow = restoredPlayer.rows[0]
        for (let index = 0; index < playerTable.columns.length; index++) {
            const column = playerTable.columns[index]
            const expected = column === "id"
                ? targetPlayerId
                : column === "account_id"
                    ? target.account_id
                    : column === "exp_pooled_time"
                        ? currentPoolTime
                        : column === "time_offset"
                            ? currentOffset
                            : sourcePlayer[index]
            if (restoredPlayerRow[index] !== expected) {
                throw new Error(`players.${column}: 写入后校验不一致`)
            }
        }

        for (const table of restoredTables) {
            assertRestoredTable(db, table, snapshot.data.tables[table], targetPlayerId)
        }
    })

    restore()
    return {
        restoredTables: restoredTables.length + 1,
        restoredRows,
        skippedTables,
        resetTables,
    }
}
