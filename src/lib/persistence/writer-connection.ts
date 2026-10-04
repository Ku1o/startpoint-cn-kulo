import Database, { type Database as SqliteDatabase } from "better-sqlite3"
import { observeSqliteDatabase } from "../sqlite-diagnostics"
import { applySqliteSettings } from "../sqlite-settings"

export interface WriterConnectionOptions {
    databasePath: string
    busyTimeoutMs: number
}

/**
 * Open the writer thread's own connection to the business database.
 *
 * The main process stays the schema owner: this factory deliberately skips the
 * initializer/update pipeline in `src/data/index.ts` so a worker restart can
 * never re-run migrations, rewrite the version file or race storage
 * maintenance. Only pragmas and instrumentation are applied, mirroring the
 * main connection so both sides observe the same durability settings.
 *
 * Checkpoint ownership starts on the automatic owner (1000) and is handed to
 * the external checkpoint worker through the `checkpoint_owner` protocol
 * message once that worker reports a successful checkpoint.
 */
export function openWriterConnection(options: WriterConnectionOptions): SqliteDatabase {
    const db = new Database(options.databasePath)
    db.pragma("temp_store = FILE")
    db.pragma("journal_mode = WAL")
    applySqliteSettings(db)
    db.pragma(`busy_timeout = ${Math.max(0, options.busyTimeoutMs)}`)
    db.pragma("wal_autocheckpoint = 1000")
    db.pragma("foreign_keys = ON")
    observeSqliteDatabase(db, "writer")
    return db
}
