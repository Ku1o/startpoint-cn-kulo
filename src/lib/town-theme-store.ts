import type { Database } from "better-sqlite3"
import { TownThemeCatalog, townThemeRecord, type TownThemeListing } from "./town-theme-catalog"
import { bindAnnualSchedules, resolveAnnualSchedules, validStoredAnnualSchedules, TownThemeCalendarError,
    type StoredTownAnnualSchedule, type TownAnnualSchedule, type TownAnnualWarning } from "./town-theme-calendar"

export const TOWN_THEME_CONFIRMATION = "APPLY_TOWN_THEME"
interface TownThemeState {
    schemaVersion: 1; revision: number; mode: "auto" | "manual"; themeId: string | null
    catalogDigest: string; updatedAtMs: number | null
}
interface PersistedTownThemeState extends TownThemeState { themeDigest: string | null; annualSchedules?: StoredTownAnnualSchedule[] }
export interface TownThemeStatus extends TownThemeState {
    themes: TownThemeListing[]; degradedReason: string | null; annualSchedules: TownAnnualSchedule[]
    annualWarnings: TownAnnualWarning[]; activeAnnualThemeId: string | null
}
export interface TownPresentationSnapshot {
    schema_version: 1; revision: number; mode: "auto" | "manual"; theme_id: string | null
    town_content_id: number | null; catalog_digest: string
}
export interface TownThemeUpdate {
    expectedRevision: number; catalogDigest: string; mode: "auto" | "manual"; themeId: string | null; confirmation: typeof TOWN_THEME_CONFIRMATION
    annualSchedules?: TownAnnualSchedule[]
}
export class TownThemeError extends Error {
    constructor(message: string, readonly statusCode = 400) { super(message) }
}
export class TownThemeConflict extends TownThemeError {
    constructor(readonly current: TownThemeStatus) { super("主城外观或目录已更新，请刷新后重试。", 409) }
}
function integer(value: unknown): value is number { return Number.isSafeInteger(value) && (value as number) >= 0 }
function validState(value: unknown, revision: number): value is PersistedTownThemeState {
    return townThemeRecord(value) && Object.keys(value).length === (Object.prototype.hasOwnProperty.call(value, "annualSchedules") ? 8 : 7)
        && (value.annualSchedules === undefined || validStoredAnnualSchedules(value.annualSchedules)) && value.schemaVersion === 1 && value.revision === revision
        && (value.mode === "auto" ? value.themeId === null && value.themeDigest === null : value.mode === "manual"
            && typeof value.themeId === "string" && /^[a-z][a-z0-9_]{0,63}$/.test(value.themeId)
            && typeof value.themeDigest === "string" && /^[a-f0-9]{64}$/.test(value.themeDigest))
        && typeof value.catalogDigest === "string" && /^[a-f0-9]{64}$/.test(value.catalogDigest)
        && integer(value.updatedAtMs)
}
export function validateTownThemeUpdate(value: unknown): TownThemeUpdate {
    if (!townThemeRecord(value) || Object.keys(value).length !== (Object.prototype.hasOwnProperty.call(value, "annualSchedules") ? 6 : 5)
        || !["expectedRevision", "catalogDigest", "mode", "themeId", "confirmation"].every(key => Object.prototype.hasOwnProperty.call(value, key))
        || (Object.prototype.hasOwnProperty.call(value, "annualSchedules") && (!Array.isArray(value.annualSchedules) || value.annualSchedules.length > 100))
        || !integer(value.expectedRevision) || value.expectedRevision >= Number.MAX_SAFE_INTEGER
        || typeof value.catalogDigest !== "string" || !/^[a-f0-9]{64}$/.test(value.catalogDigest)
        || value.confirmation !== TOWN_THEME_CONFIRMATION
        || !(value.mode === "auto" ? value.themeId === null : value.mode === "manual" && typeof value.themeId === "string" && /^[a-z][a-z0-9_]{0,63}$/.test(value.themeId)))
        throw new TownThemeError("主城外观请求无效，请刷新页面后确认选择。")
    return value as unknown as TownThemeUpdate
}
/** Only called by an explicit admin write, under the persistence coordinator. */
export function initializeTownThemeSchema(db: Database): void {
    db.exec(`CREATE TABLE IF NOT EXISTS town_presentation_state (
        id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL CHECK(revision>=0), value_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS town_presentation_audit (
        revision INTEGER PRIMARY KEY CHECK(revision>0), changed_at_ms INTEGER NOT NULL,
        before_json TEXT, after_json TEXT NOT NULL, operation TEXT NOT NULL CHECK(operation='APPLY_TOWN_THEME')
    );`)
}

/** Server singleton data only: no player/account FK and no activity, epoch or clock writes. */
export class TownThemeStore {
    constructor(readonly db: Database, readonly catalog: TownThemeCatalog) {}
    private read(): { state: PersistedTownThemeState; raw: string | null; error: string | null } {
        const fallback: PersistedTownThemeState = { schemaVersion: 1, revision: 0, mode: "auto", themeId: null, themeDigest: null, catalogDigest: this.catalog.digest, updatedAtMs: null }
        try {
            const missing = () => {
                const audit = this.db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='town_presentation_audit'").get()
                return { state: fallback, raw: null, error: audit && this.db.prepare("SELECT 1 FROM town_presentation_audit LIMIT 1").get() ? "town_theme_state_missing" : null }
            }
            if (!this.db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='town_presentation_state'").get()) return missing()
            const row = this.db.prepare("SELECT revision,value_json FROM town_presentation_state WHERE id=1").get() as { revision: number; value_json: string } | undefined
            if (!row) {
                if (this.db.prepare("SELECT 1 FROM town_presentation_state LIMIT 1").get()) return { state: fallback, raw: null, error: "town_theme_state_invalid" }
                return missing()
            }
            if (integer(row.revision)) fallback.revision = row.revision
            if (!integer(row.revision) || typeof row.value_json !== "string" || row.value_json.length > 65536) throw new Error("invalid_state")
            let value: unknown
            try { value = JSON.parse(row.value_json) } catch { value = null }
            if (!validState(value, row.revision)) return { state: fallback, raw: row.value_json, error: "town_theme_state_invalid" }
            return { state: value, raw: row.value_json, error: null }
        } catch { return { state: fallback, raw: null, error: "town_theme_state_unavailable_or_invalid" } }
    }
    private effective(nowMs: number): PersistedTownThemeState & { degradedReason: string | null; annualWarnings: TownAnnualWarning[]; activeAnnualThemeId: string | null } {
        const { state, error } = this.read()
        const degradedReason = error ?? this.catalog.degradedReason
            ?? (state.mode === "manual" && (!this.catalog.find(state.themeId!) || state.themeDigest !== this.catalog.themeDigest(state.themeId!)) ? "town_theme_state_theme_mismatch" : null)
        const annual = resolveAnnualSchedules(state.annualSchedules ?? [], this.catalog, nowMs)
        return { ...state, ...(degradedReason ? { mode: "auto" as const, themeId: null } : {}),
            catalogDigest: this.catalog.digest, degradedReason, annualWarnings: annual.warnings,
            activeAnnualThemeId: !degradedReason && state.mode === "auto" ? annual.activeThemeId : null }
    }
    status(nowMs = Date.now()): TownThemeStatus {
        const { themeDigest: _themeDigest, annualSchedules, ...state } = this.effective(nowMs)
        return { ...state, annualSchedules: (annualSchedules ?? []).map(({ themeId, start, end }) => ({ themeId, start, end })), themes: this.catalog.listing() }
    }
    snapshot(nowMs = Date.now()): TownPresentationSnapshot {
        const current = this.effective(nowMs), selected = current.mode === "manual" ? this.catalog.find(current.themeId!)
            : current.activeAnnualThemeId ? this.catalog.find(current.activeAnnualThemeId) : undefined
        return { schema_version: 1, revision: current.revision, mode: selected ? "manual" : "auto",
            theme_id: selected?.id ?? null, town_content_id: selected?.nativeTownContentId ?? null, catalog_digest: current.catalogDigest }
    }
    update(input: unknown, nowMs = Date.now()): TownThemeStatus {
        const body = validateTownThemeUpdate(input)
        if (!integer(nowMs)) throw new TownThemeError("审计时间无效。")
        // A nested transaction is a savepoint, so an audit failure never leaks the state write.
        return this.db.transaction(() => {
            const current = this.read()
            if (current.error) throw new TownThemeError("主城外观持久状态不可用，请先核查。", 503)
            if (body.expectedRevision !== current.state.revision || body.catalogDigest !== this.catalog.digest) throw new TownThemeConflict(this.status(nowMs))
            if (this.catalog.degradedReason) throw new TownThemeError("主城外观目录或资源证据不可用。", 503)
            const themeDigest = body.mode === "manual" ? this.catalog.themeDigest(body.themeId!) : null
            if (body.mode === "manual" && (!this.catalog.find(body.themeId!) || !themeDigest)) throw new TownThemeError("未登记或未验证的主城主题。")
            let annualSchedules = current.state.annualSchedules ?? []
            if (body.annualSchedules !== undefined) {
                try { annualSchedules = bindAnnualSchedules(body.annualSchedules, this.catalog) }
                catch (error) { if (error instanceof TownThemeCalendarError) throw new TownThemeError(error.message); throw error }
            }
            if (current.state.mode === body.mode && current.state.themeId === body.themeId && current.state.themeDigest === themeDigest
                && current.state.catalogDigest === this.catalog.digest && JSON.stringify(current.state.annualSchedules ?? []) === JSON.stringify(annualSchedules)) return this.status(nowMs)
            initializeTownThemeSchema(this.db)
            const next: PersistedTownThemeState = { schemaVersion: 1, revision: current.state.revision + 1,
                mode: body.mode, themeId: body.themeId, themeDigest: themeDigest ?? null, catalogDigest: this.catalog.digest, updatedAtMs: nowMs, annualSchedules }
            const after = JSON.stringify(next)
            this.db.prepare(`INSERT INTO town_presentation_state(id,revision,value_json) VALUES(1,?,?)
                ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,value_json=excluded.value_json`).run(next.revision, after)
            this.db.prepare("INSERT INTO town_presentation_audit(revision,changed_at_ms,before_json,after_json,operation) VALUES(?,?,?,?,?)")
                .run(next.revision, nowMs, current.raw, after, TOWN_THEME_CONFIRMATION)
            return this.status(nowMs)
        }).immediate()
    }
}
