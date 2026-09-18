import type Database from "better-sqlite3"
import { registerMemoryCounters } from "./memory-diagnostics"

const caches = new WeakMap<Database.Database, Map<string, Database.Statement>>()
const stats = { hits: 0, misses: 0, evictions: 0, busyBypasses: 0 }
const LIMIT = 128
const enabled = !/^(0|false|no|off)$/i.test(process.env.SQL_STATEMENT_CACHE ?? "true")
registerMemoryCounters("sqlStatements", () => ({ ...stats, perConnectionLimit: LIMIT }))

/** For audited get/all/run callers only; do not mutate a shared statement's bind/raw/pluck mode. */
export function cachedStatement(db: Database.Database, sql: string): Database.Statement {
    if (!enabled) return db.prepare(sql)
    let cache = caches.get(db)
    if (!cache) { cache = new Map(); caches.set(db, cache) }
    const previous = cache.get(sql)
    if (previous && !previous.busy) {
        stats.hits++
        cache.delete(sql); cache.set(sql, previous)
        return previous
    }
    if (previous?.busy) { stats.busyBypasses++; return db.prepare(sql) }
    stats.misses++
    const statement = db.prepare(sql)
    cache.set(sql, statement)
    if (cache.size > LIMIT) { cache.delete(cache.keys().next().value!); stats.evictions++ }
    return statement
}
