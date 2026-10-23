import { createHash } from "node:crypto"
import type { Database } from "better-sqlite3"
import { isFixedJulyCandidate } from "./content-july-reference"

export const CONTENT_ACTIONS = ["visible", "enter", "claim", "exchange"] as const
export type ContentAction = typeof CONTENT_ACTIONS[number]
export type ContentReadiness = "unverified" | "current_baseline" | "verified" | "blocked"
export interface ContentCatalogRow {
    key: string; type: string; id: number; name: string
    originalStartMs: number | null; originalEndMs: number | null; originalExchangeEndMs: number | null
    windowCandidate: boolean; browseCandidate: boolean; source: string
    personalWindow?: boolean
    definitionDigest?: string
    questSources?: string[]
    definitionSources?: string[]
    missionKeys?: string[]
    parentKey?: string
    boxRules?: unknown
    serverDefinitionDigest?: string
    definitionEvidence?: { status: string; serverSources: string[]; clientQuestMappings: number; serverQuestMatches: number; missingQuestKeys: string[]; issues: string[] }
}
export interface ContentCatalog {
    schemaVersion: number; source: { assetVersion: string; manifestSha256: string }
    baselineTimeMs: number; baselineEvidence: string; rows: ContentCatalogRow[]
    questMap: Record<string, string>; missing: string[]; resources: Record<string, unknown>
    missionMap?: Record<string, string>
    serverResources?: Record<string, { sha256: string }>
}
export interface ContentActionOverride {
    enabled: boolean; endsAtMs: number | null; readiness: ContentReadiness; evidence: string
    questKeys?: string[] | null; missionKeys?: string[] | null
    /** Store-captured identities, never accepted from the operator. */
    catalogDigest?: string; contentDigest?: string
}
export interface ContentControl {
    key: string; instanceId: string; readiness: ContentReadiness; evidence: string
    flags: Record<ContentAction, boolean>; endsAtMs: number | null
    revision: number; catalogDigest: string; contentDigest: string
    integrityError?: string
    controlled?: boolean
    /** False suspends new entry without erasing the reviewed action configuration. */
    published?: boolean
    actionOverrides?: Partial<Record<ContentAction, ContentActionOverride>>
    questKeys?: string[] | null
    missionKeys?: string[] | null
}
export interface ContentCatalogListing {
    revision: number; catalogDigest: string; source: ContentCatalog["source"]
    clientIntegration: { android: string; ios: string }; baselineTimeMs: number; baselineEvidence: string
    missing: string[]; types: string[]; total: number
    rows: Array<ContentCatalogRow & { state: ContentControl | null; capabilities: readonly ContentAction[]; clientCapabilities: readonly ContentAction[]; readiness: string; stale: boolean; definitionReady: boolean; publishable: boolean; effectiveFlags: Partial<Record<ContentAction, boolean>> | null }>
}
export interface ContentManagementQuery {
    search?: string; type?: string; readiness?: string; candidatesOnly?: boolean
    referenceWindow?: readonly [number, number]; offset?: number; limit?: number
}
/** A single read request, never an authorization token for a later write. */
export interface ContentManagementSnapshot {
    readonly nowMs: number
    /** First possible expiry among states read by this snapshot; never a write authority. */
    readonly nextChangeAtMs: number
    readonly revision: number
    state(key: string): ContentControl | null
    row(key: string): ContentCatalogListing["rows"][number] | undefined
    list(query?: ContentManagementQuery, include?: (row: ContentCatalogRow) => boolean): ContentCatalogListing
    all(query?: ContentManagementQuery, include?: (row: ContentCatalogRow) => boolean): ContentCatalogListing
}
/** Native owner/box pairs are supplied by the verified production catalog reader.
 * Direct unit stores may omit this optional lifecycle without guessing globals. */
export interface ContentBoxLifecycle {
    associations: readonly { parentKey: string; boxKey: string; relationshipMatches: boolean }[]
    available: boolean
    requiredKeys?: readonly string[]
}
export class ContentOperationError extends Error {
    constructor(message: string, public statusCode = 400) { super(message) }
}

/** Server-global only. No player foreign keys, clocks, claims or progress writes. */
export function initializeContentOperationsSchema(db: Database): void {
    db.exec(`
        CREATE TABLE IF NOT EXISTS content_operations_meta (
            id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO content_operations_meta(id,revision) VALUES(1,0);
        CREATE TABLE IF NOT EXISTS content_operations_state (
            content_key TEXT PRIMARY KEY, value_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS content_operations_audit (
            revision INTEGER PRIMARY KEY, content_key TEXT NOT NULL, changed_at_ms INTEGER NOT NULL,
            before_json TEXT, after_json TEXT NOT NULL, reason TEXT NOT NULL
        );
    `)
}

function record(v: unknown): v is Record<string, unknown> {
    return typeof v === "object" && v !== null && !Array.isArray(v)
}
function boundedText(v: unknown, label: string): string {
    if (typeof v !== "string" || !v.trim() || v.length > 2000) throw new ContentOperationError(`${label}必须为 1 至 2000 字的说明`)
    return v.trim()
}

const SWITCHABLE_TYPES = new Set([
    "gacha", "pass_card_event", "active_mission_event", "collect_item_event", "box_gacha",
    "daily_week_event", "advent_event", "story_event", "ranking_event", "challenge_dungeon_event",
    "daily_exp_mana_event", "world_story_event", "tower_dungeon_event", "expert_single_event",
    "carnival_event", "raid_event", "rush_event", "solo_time_attack_event", "hard_multi_event",
    "score_attack_event", "multi_special_exchange_campaign",
])

export class ContentOperationsStore {
    readonly digest: string
    readonly rows: Map<string, ContentCatalogRow>
    readonly contentDigests: Map<string, string>
    readonly runtimeDefinitions: Map<string, { digest: string; matchesCatalog: boolean }>
    readonly passKeys: readonly string[]
    readonly shopSaleParents: ReadonlySet<string>
    readonly boxParents = new Set<string>()
    private readonly boxPeers = new Map<string, ContentBoxLifecycle["associations"][number]>()
    private readonly boxRequiredKeys = new Set<string>()
    readonly questMembers = new Map<string, Set<string>>()
    readonly missionMembers = new Map<string, Set<string>>()
    constructor(readonly db: Database, readonly catalog: ContentCatalog,
        readonly capabilities: (row: ContentCatalogRow) => readonly ContentAction[],
        runtimeDefinition?: (row: ContentCatalogRow) => { digest: string; matchesCatalog: boolean },
        readonly clientEntry?: (row: ContentCatalogRow) => { kind: string; id: number } | null,
        readonly clientCapabilities?: (row: ContentCatalogRow) => readonly ContentAction[],
        readonly clientIntegration = { android: "pending", ios: "pending" },
        readonly defaultPolicy?: (row: ContentCatalogRow, action: ContentAction) => boolean | null,
        readonly boxLifecycle?: ContentBoxLifecycle) {
        this.digest = createHash("sha256").update(JSON.stringify(catalog)).digest("hex")
        this.rows = new Map(catalog.rows.map(row => [row.key, row]))
        this.passKeys = catalog.rows.filter(row => row.type === "pass_card_event").map(row => row.key)
        this.shopSaleParents = new Set(catalog.rows.filter(row => row.type === "event_item_shop" && row.parentKey).map(row => row.parentKey!))
        for (const key of boxLifecycle?.requiredKeys ?? []) this.boxRequiredKeys.add(key)
        for (const link of boxLifecycle?.associations ?? []) {
            if (this.boxPeers.has(link.parentKey) || this.boxPeers.has(link.boxKey)) throw new Error("Invalid native box lifecycle association")
            const reviewedLink = this.rows.has(link.parentKey) && this.rows.has(link.boxKey)
                ? link : { ...link, relationshipMatches: false }
            this.boxParents.add(link.parentKey)
            for (const key of [link.parentKey, link.boxKey]) { this.boxPeers.set(key, reviewedLink); this.boxRequiredKeys.add(key) }
        }
        if (this.rows.size !== catalog.rows.length) throw new Error("Duplicate content catalog keys")
        for (const [member, key] of Object.entries(catalog.questMap)) {
            if (!this.questMembers.has(key)) this.questMembers.set(key, new Set())
            this.questMembers.get(key)!.add(member)
        }
        for (const [member, key] of Object.entries(catalog.missionMap ?? {})) {
            if (!this.missionMembers.has(key)) this.missionMembers.set(key, new Set())
            this.missionMembers.get(key)!.add(member)
        }
        for (const row of catalog.rows) for (const member of row.missionKeys ?? []) {
            if (!this.missionMembers.has(row.key)) this.missionMembers.set(row.key, new Set())
            this.missionMembers.get(row.key)!.add(member)
        }
        this.runtimeDefinitions = new Map(catalog.rows.map(row => [row.key,
            runtimeDefinition?.(row) ?? { digest: "", matchesCatalog: true }]))
        this.contentDigests = new Map(catalog.rows.map(row => {
            const sources = (row.definitionSources ?? [row.source, ...(row.questSources ?? [`master/quest/event/${row.type}_quest.orderedmap`])])
                .map(key => { const resource = catalog.resources[key]; return record(resource) ? resource.sha256 ?? null : null })
            return [row.key, createHash("sha256").update(JSON.stringify({ key: row.key,
                definition: row.definitionDigest ?? [row.name, row.originalStartMs, row.originalEndMs, row.originalExchangeEndMs],
                serverDefinition: row.serverDefinitionDigest ?? null, runtimeDefinition: this.runtimeDefinitions.get(row.key)!.digest, sources })).digest("hex")]
        }))
    }
    revision(): number {
        return (this.db.prepare("SELECT revision FROM content_operations_meta WHERE id=1").get() as { revision: number }).revision
    }
    state(key: string): ContentControl | null {
        const result = this.db.prepare("SELECT value_json FROM content_operations_state WHERE content_key=?").get(key) as { value_json: string } | undefined
        return result ? this.decodeState(key, result.value_json) : null
    }
    private decodeState(key: string, json: string): ContentControl {
        let parsed: unknown
        try { parsed = JSON.parse(json) } catch { parsed = null }
        if (record(parsed) && parsed.key === key && parsed.instanceId === `${key}:original`
            && ["unverified", "current_baseline", "verified", "blocked"].includes(String(parsed.readiness))
            && typeof parsed.evidence === "string" && record(parsed.flags)
            && CONTENT_ACTIONS.every(action => typeof (parsed.flags as Record<string, unknown>)[action] === "boolean")
            && (parsed.endsAtMs === null || (Number.isSafeInteger(parsed.endsAtMs) && (parsed.endsAtMs as number) >= 0))
            && Number.isSafeInteger(parsed.revision) && (parsed.revision as number) >= 0
            && (parsed.controlled === undefined || typeof parsed.controlled === "boolean")
            && (parsed.published === undefined || typeof parsed.published === "boolean")
            && [parsed.questKeys, parsed.missionKeys].every((keys, index) => keys === undefined || keys === null
                || (Array.isArray(keys) && keys.length <= 5000 && new Set(keys).size === keys.length
                    && keys.every(member => typeof member === "string" && /^\d+:\d+$/.test(member)
                        && (!this.rows.has(key) || (index === 0 ? this.questMembers : this.missionMembers).get(key)?.has(member)))))
            && (parsed.actionOverrides === undefined || (record(parsed.actionOverrides)
                && Object.entries(parsed.actionOverrides).every(([action, override]) => CONTENT_ACTIONS.includes(action as ContentAction)
                    && this.validOverride(key, override))))
            && typeof parsed.catalogDigest === "string" && typeof parsed.contentDigest === "string") {
            return parsed as unknown as ContentControl
        }
        // Keep the claimed key closed, with a visible diagnostic, until an explicit recheck repairs it.
        return { key, instanceId: `${key}:original`, readiness: "blocked", evidence: "持久运营状态格式损坏，需重新核查",
            flags: { visible: false, enter: false, claim: false, exchange: false }, endsAtMs: null,
            revision: 0, catalogDigest: "", contentDigest: "", integrityError: "invalid_persisted_state",
            controlled: true }
    }
    private validOverride(key: string, value: unknown): value is ContentActionOverride {
        return record(value) && Object.keys(value).every(field => ["enabled", "endsAtMs", "readiness", "evidence", "questKeys", "missionKeys", "catalogDigest", "contentDigest"].includes(field))
            && typeof value.enabled === "boolean" && typeof value.evidence === "string" && !!value.evidence.trim() && value.evidence.length <= 2000
            && ["unverified", "current_baseline", "verified", "blocked"].includes(String(value.readiness))
            && (value.endsAtMs === null || (Number.isSafeInteger(value.endsAtMs) && (value.endsAtMs as number) >= 0))
            && typeof value.catalogDigest === "string" && typeof value.contentDigest === "string"
            && [value.questKeys, value.missionKeys].every((keys, index) => keys === undefined || keys === null
                || (Array.isArray(keys) && keys.length <= 5000 && new Set(keys).size === keys.length
                    && keys.every(member => typeof member === "string" && /^\d+:\d+$/.test(member)
                        && (!this.rows.has(key) || (index === 0 ? this.questMembers : this.missionMembers).get(key)?.has(member)))))
    }
    private actionControl(state: ContentControl, action: ContentAction): ContentActionOverride | null {
        if (state.controlled === false) return null
        if (state.actionOverrides !== undefined) return state.actionOverrides[action] ?? null
        return { enabled: state.flags[action], endsAtMs: state.endsAtMs, readiness: state.readiness, evidence: state.evidence,
            questKeys: state.questKeys, missionKeys: state.missionKeys, catalogDigest: state.catalogDigest, contentDigest: state.contentDigest }
    }
    private defaultAllowed(key: string, action: ContentAction): boolean | null {
        const row = this.rows.get(key)
        if (!row) return null
        const decision = this.defaultPolicy?.(row, action) ?? null
        return decision === true ? this.definitionReady(row) && this.capabilities(row).includes(action) : decision
    }
    private publishable(row: ContentCatalogRow): boolean {
        return SWITCHABLE_TYPES.has(row.type) && this.capabilities(row).includes("visible")
    }
    supportsPublicationSwitch(key: string): boolean {
        const row = this.rows.get(key)
        return !!row && this.publishable(row)
    }
    private deadlineActions(row: ContentCatalogRow, state: ContentControl): ContentAction[] {
        if (["special_exchange_campaign", "start_dash_exchange_campaign"].includes(row.type)) return ["exchange"]
        if (!this.publishable(row)) return []
        return ["visible" as const, "enter" as const, ...(this.boxParents.has(row.key) ? ["exchange" as const] : [])].filter(action => this.capabilities(row).includes(action)
            && !!this.actionControl(state, action))
    }
    /** Editing a deadline never repairs or broadens the underlying action review. Expiry alone is editable. */
    deadlineControl(key: string, saved?: ContentControl | null): {
        canEdit: boolean; reason: string; endsAtMs: number | null; hasMixedDeadlines: boolean; actionLabels: string[]
    } {
        const row = this.rows.get(key), state = saved === undefined ? this.state(key) : saved
        const denied = (reason: string) => ({ canEdit: false, reason, endsAtMs: null, hasMixedDeadlines: false, actionLabels: [] })
        if (!row || !state || state.controlled === false || state.integrityError) return denied("尚无有效的已核查开放设置")
        const actions = this.deadlineActions(row, state)
        if (!actions.length || (this.publishable(row) && !actions.includes("visible"))) return denied("该内容尚无可配置截止时间的开放动作")
        if (!this.definitionReady(row)) return denied("内容定义已变化或未完成核查")
        if (actions.some(action => {
            const review = this.actionControl(state, action)
            return !review || !this.capabilities(row).includes(action) || !["verified", "current_baseline"].includes(review.readiness)
                || !review.evidence.trim() || review.contentDigest !== this.contentDigests.get(key)
        })) return denied("开放动作尚未核查或核查已过时，不能只修改截止时间")
        const ends = actions.map(action => this.actionControl(state, action)!.endsAtMs)
        return { canEdit: true, reason: "保存不会自动开启已关闭内容；原有领奖、兑换资格与进度保留",
            endsAtMs: ends[0], hasMixedDeadlines: ends.some(end => end !== ends[0]),
            actionLabels: actions.map(action => action === "visible" ? "入口显示" : action === "enter" ? "参与玩法" : "已有资格兑换") }
    }
    private suspended(state: ContentControl, action: ContentAction): boolean {
        return state.published === false && (action === "visible" || action === "enter"
            || (action === "exchange" && (this.shopSaleParents.has(state.key) || this.boxParents.has(state.key))))
    }
    /** null means a core permanent action retains its original business rule. */
    allowed(key: string, action: ContentAction, nowMs: number): boolean | null {
        const state = this.state(key)
        return this.allowedWithLookup(key, action, nowMs, candidate => candidate === key ? state : this.state(candidate))
    }
    private localAllowed(key: string, action: ContentAction, nowMs: number, lookup: (key: string) => ContentControl | null | undefined): boolean | null {
        const state = lookup(key)
        if (state && this.suspended(state, action)) return false
        if (!state || !this.actionControl(state, action)) return this.defaultAllowed(key, action)
        return this.stateAllows(state, action, nowMs)
    }
    private allowedWithLookup(key: string, action: ContentAction, nowMs: number, lookup: (key: string) => ContentControl | null | undefined): boolean | null {
        const local = this.localAllowed(key, action, nowMs, lookup)
        if (local === false || !this.boxRequiredKeys.has(key)) return local
        const link = this.boxPeers.get(key)
        const participating = action === "visible" || action === "enter"
            || action === "exchange" && (link?.parentKey === key || this.rows.get(key)?.type !== "box_gacha")
            || action === "claim" && this.rows.get(key)?.type === "box_gacha"
        if (!participating) return local
        if (!this.boxLifecycle?.available || !link?.relationshipMatches) return false
        const parentState = lookup(link.parentKey), boxState = lookup(link.boxKey)
        const linkedState = (candidate: string) => candidate === link.parentKey ? parentState : boxState
        // Use local decisions here, rather than recursive allowed calls: both
        // sides may be published sequentially inside one atomic admin batch.
        if (["visible", "enter", "exchange"].some(action => this.localAllowed(link.parentKey, action as ContentAction, nowMs, linkedState) !== true)
            || ["visible", "enter"].some(action => this.localAllowed(link.boxKey, action as ContentAction, nowMs, linkedState) !== true)) return false
        return local
    }
    scopedAllowed(key: string, kind: "quest" | "mission", member: string, action: ContentAction, nowMs: number): boolean | null {
        const state = this.state(key)
        const effective = () => this.allowedWithLookup(key, action, nowMs, candidate => candidate === key ? state : this.state(candidate))
        if (!state) return effective()
        if (this.suspended(state, action)) return false
        const override = this.actionControl(state, action)
        if (!override) return effective()
        if (effective() !== true) return false
        const scope = override[kind === "quest" ? "questKeys" : "missionKeys"]
        return scope === undefined || scope === null || scope.includes(member)
    }
    activeManagedPass(nowMs: number): string | null {
        for (const key of this.passKeys) {
            if (this.allowed(key, "visible", nowMs) === true) return key
        }
        return null
    }
    private definitionReady(row: ContentCatalogRow): boolean {
        if (!this.runtimeDefinitions.get(row.key)?.matchesCatalog) return false
        const evidence = row.definitionEvidence
        if (!evidence || evidence.status === "matched") return true
        // Operator time replaces these two legacy calendar fields; identity/mapping defects still block activation.
        return row.type === "gacha" && evidence.status === "mismatch" && evidence.issues.length > 0
            && evidence.issues.every(issue => issue === "startDate differs" || issue === "endDate differs")
    }
    private actionReviewReady(state: ContentControl, action: ContentAction): boolean {
        const key = state.key, override = this.actionControl(state, action)
        if (!override || !this.rows.has(key) || override.contentDigest !== this.contentDigests.get(key)) return false
        const row = this.rows.get(key)!
        if (!this.definitionReady(row)) return false
        if (override.readiness !== "verified" && override.readiness !== "current_baseline") return false
        return this.capabilities(row).includes(action)
    }
    private stateAllows(state: ContentControl, action: ContentAction, nowMs: number): boolean {
        if (this.suspended(state, action) || !Number.isFinite(nowMs) || !this.actionReviewReady(state, action)) return false
        const override = this.actionControl(state, action)!
        return override.enabled === true && (override.endsAtMs === null || nowMs <= override.endsAtMs)
    }
    /** Capture controls with their revision; decode only requested keys, at most once per request. */
    managementSnapshot(): ContentManagementSnapshot {
        if (!this.db.inTransaction) return this.db.transaction(() => this.managementSnapshot())()
        const nowMs = Date.now(), revision = this.revision()
        const encoded = new Map((this.db.prepare("SELECT content_key,value_json FROM content_operations_state").all() as Array<{ content_key: string; value_json: string }>)
            .map(row => [row.content_key, row.value_json]))
        const states = new Map<string, ContentControl>()
        let nextChangeAtMs = Infinity
        const trackDeadline = (state: ContentControl) => {
            for (const value of [state, ...Object.values(state.actionOverrides ?? {})]) {
                const end = value?.endsAtMs
                if (typeof end === "number" && Number.isSafeInteger(end) && end >= nowMs)
                    nextChangeAtMs = Math.min(nextChangeAtMs, end + 1)
            }
        }
        const savedState = (key: string) => {
            let state = states.get(key)
            const json = encoded.get(key)
            if (!state && json !== undefined) {
                state = this.decodeState(key, json); states.set(key, state); trackDeadline(state)
            }
            return state
        }
        const listed = (row: ContentCatalogRow): ContentCatalogListing["rows"][number] => {
            const state = savedState(row.key)
            return { ...row, state: state ?? null, capabilities: this.capabilities(row), clientCapabilities: this.clientCapabilities?.(row) ?? [],
                publishable: this.publishable(row), effectiveFlags: this.effectiveFlags(row.key, state, nowMs, savedState),
                readiness: state?.readiness ?? "unverified", definitionReady: this.definitionReady(row),
                stale: !this.runtimeDefinitions.get(row.key)?.matchesCatalog || (!!state && (state.actionOverrides === undefined
                    ? state.contentDigest !== this.contentDigests.get(row.key)
                    : CONTENT_ACTIONS.some(action => { const override = this.actionControl(state, action); return !!override && override.contentDigest !== this.contentDigests.get(row.key) }))) }
        }
        const select = (query: ContentManagementQuery = {}, include: (row: ContentCatalogRow) => boolean = () => true, paginate = true) => {
            const search = (query.search ?? "").trim().toLocaleLowerCase()
            const rows = this.catalog.rows.filter(row => include(row) && (!query.type || row.type === query.type)
                && (!query.candidatesOnly || isFixedJulyCandidate(row))
                && (!query.referenceWindow || (!row.personalWindow
                    && (row.originalStartMs === null || row.originalStartMs <= query.referenceWindow[0])
                    && (row.originalEndMs === null || row.originalEndMs >= query.referenceWindow[1] - 1000)))
                && (!search || `${row.key} ${row.name}`.toLocaleLowerCase().includes(search))
                && (!query.readiness || (savedState(row.key)?.readiness ?? "unverified") === query.readiness))
            const offset = Number.isFinite(query.offset) ? Math.max(0, Math.trunc(query.offset!)) : 0
            const limit = Number.isFinite(query.limit) ? Math.max(1, Math.min(200, Math.trunc(query.limit!))) : 50
            return { revision, catalogDigest: this.digest, source: this.catalog.source,
                clientIntegration: this.clientIntegration,
                baselineTimeMs: this.catalog.baselineTimeMs, baselineEvidence: this.catalog.baselineEvidence,
                missing: this.catalog.missing, types: [...new Set(this.catalog.rows.map(row => row.type))],
                total: rows.length, rows: (paginate ? rows.slice(offset, offset + limit) : rows).map(listed) }
        }
        return { nowMs, revision, get nextChangeAtMs() { return nextChangeAtMs }, state: key => savedState(key) ?? null,
            row: key => { const row = this.rows.get(key); return row ? listed(row) : undefined },
            list: select, all: (query, include) => select(query, include, false) }
    }
    list(query: ContentManagementQuery = {}): ContentCatalogListing {
        if (!this.db.inTransaction) return this.db.transaction(() => this.list(query))()
        return this.managementSnapshot().list(query)
    }
    private effectiveFlags(key: string, state: ContentControl | undefined, nowMs: number,
        lookup: (key: string) => ContentControl | null | undefined = candidate => this.state(candidate)): Partial<Record<ContentAction, boolean>> | null {
        const flags: Partial<Record<ContentAction, boolean>> = {}
        for (const action of CONTENT_ACTIONS) {
            const result = this.allowedWithLookup(key, action, nowMs, candidate => candidate === key ? state : lookup(candidate))
            if (result !== null) flags[action] = result
        }
        return Object.keys(flags).length ? flags : null
    }
    snapshot(nowMs: number): { schema_version: number; full_snapshot: boolean; revision: number; catalog_digest: string; server_time_ms: number; states: Array<Record<string, unknown>>; catalog: Array<Record<string, unknown>>; default_policy?: unknown } {
        if (!this.db.inTransaction) return this.db.transaction(() => this.snapshot(nowMs))()
        // Explicit full snapshot. Includes closed states, not just currently visible rows.
        const states = this.db.prepare("SELECT content_key,value_json FROM content_operations_state ORDER BY content_key").all() as Array<{ content_key: string; value_json: string }>
        const controlled = states.map(({ content_key, value_json }) => this.decodeState(content_key, value_json))
            .filter(s => s.controlled !== false && (s.controlled === true || !this.rows.has(s.key) || this.capabilities(this.rows.get(s.key)!).length > 0))
        const savedStates = new Map(controlled.map(state => [state.key, state]))
        const effective = (key: string, action: ContentAction) => this.allowedWithLookup(key, action, nowMs, candidate => savedStates.get(candidate))
        // Closed/default entries are included in compact key lists. Omitting a stored state is never an implicit open.
        const defaults = this.defaultPolicy ? Object.fromEntries(CONTENT_ACTIONS.map(action => {
            const closed: string[] = [], qualifiedRights: string[] = [], legacy: string[] = []
            for (const row of this.catalog.rows) {
                const decision = this.defaultAllowed(row.key, action)
                if (decision === false) closed.push(row.key)
                if (decision === true) qualifiedRights.push(row.key)
                if (decision === null) legacy.push(row.key)
            }
            return [action, { closed_keys: closed, qualified_rights_keys: qualifiedRights, legacy_keys: legacy }]
        })) : undefined
        return { schema_version: 2, full_snapshot: true, revision: this.revision(), catalog_digest: this.digest,
            ...(defaults ? { default_policy: { version: 1, explicit_actions_override_defaults: true, actions: defaults } } : {}),
            server_time_ms: nowMs, states: controlled.map(s => {
                const reportedActions = CONTENT_ACTIONS.filter(action => this.actionControl(s, action) || this.suspended(s, action))
                return { key: s.key, instance_id: s.instanceId, permanent: s.endsAtMs === null, ends_at_ms: s.endsAtMs,
                    quest_keys: s.questKeys ?? null, mission_keys: s.missionKeys ?? null,
                    actions: Object.fromEntries(reportedActions.map(action => {
                        const override = this.actionControl(s, action)
                        return [action, { enabled: effective(s.key, action) === true, ends_at_ms: override?.endsAtMs ?? null,
                            quest_keys: override?.questKeys ?? null, mission_keys: override?.missionKeys ?? null }]
                    })),
                    ...Object.fromEntries(reportedActions.map(action => [action, effective(s.key, action) === true])) }
            }), catalog: controlled.filter(s => this.rows.has(s.key)).map(s => {
                const row = this.rows.get(s.key)!
                return { key: row.key, type: row.type, id: row.id, entry: this.clientEntry?.(row) ?? null,
                    server_actions: this.capabilities(row), client_actions: this.clientCapabilities?.(row) ?? [], parent_key: row.parentKey ?? null,
                    quest_keys: [...this.questMembers.get(row.key) ?? []], mission_keys: [...this.missionMembers.get(row.key) ?? []] }
            }) }
    }
    audit(query: { key?: string; beforeRevision?: number; limit?: number } = {}): {
        revision: number; rows: Array<{ revision: number; key: string; changedAtMs: number; before: ContentControl | null; after: ContentControl; reason: string }>
    } {
        if (!this.db.inTransaction) return this.db.transaction(() => this.audit(query))()
        const limit = Number.isFinite(query.limit) ? Math.max(1, Math.min(200, Math.trunc(query.limit!))) : 50
        const before = Number.isSafeInteger(query.beforeRevision) ? query.beforeRevision! : Number.MAX_SAFE_INTEGER
        const rows = this.db.prepare(`SELECT * FROM content_operations_audit
            WHERE revision < ? AND (? IS NULL OR content_key=?) ORDER BY revision DESC LIMIT ?`)
            .all(before, query.key ?? null, query.key ?? null, limit) as Array<{ revision: number; content_key: string; changed_at_ms: number; before_json: string | null; after_json: string; reason: string }>
        return { revision: this.revision(), rows: rows.map(row => ({ revision: row.revision, key: row.content_key,
            changedAtMs: row.changed_at_ms, before: row.before_json === null ? null : this.decodeState(row.content_key, row.before_json),
            after: this.decodeState(row.content_key, row.after_json), reason: row.reason })) }
    }
    /** One atomic publication switch; action reviews, scopes and player progress remain untouched. */
    setPublished(key: string, input: unknown, nowMs: number): ContentControl {
        const row = this.rows.get(key)
        if (!row) throw new ContentOperationError("内容不存在", 404)
        if (!this.publishable(row)) throw new ContentOperationError("该内容不是可发布的活动或卡池", 409)
        if (!record(input) || Object.keys(input).some(field => !["published", "expectedRevision", "catalogDigest", "reason"].includes(field))
            || typeof input.published !== "boolean" || !Number.isSafeInteger(input.expectedRevision)
            || (input.expectedRevision as number) < 0) throw new ContentOperationError("发布请求参数无效")
        if (input.catalogDigest !== this.digest) throw new ContentOperationError("内容目录已变化，请重新核对资源", 409)
        if (!Number.isSafeInteger(nowMs) || nowMs < 0) throw new ContentOperationError("无效的服务器时间")
        const reason = boundedText(input.reason, "变更原因")
        const apply = () => {
            const revision = this.revision()
            if (revision !== input.expectedRevision) throw new ContentOperationError("状态已被其他操作更新，请刷新后重试", 409)
            const before = this.state(key)
            if (!before || before.controlled === false || before.integrityError)
                throw new ContentOperationError("尚无有效的已核查运营状态，不能一键发布", 409)
            if ((before.published !== false) === input.published)
                throw new ContentOperationError("发布状态已变化，请刷新后重试", 409)
            const next: ContentControl = JSON.parse(JSON.stringify(before))
            next.published = input.published as boolean
            if (next.published) {
                if (!this.stateAllows(next, "visible", nowMs))
                    throw new ContentOperationError("入口未完成核查、已过期或定义已变化，不能一键上线", 409)
                if (this.boxParents.has(key) && !this.stateAllows(next, "exchange", nowMs))
                    throw new ContentOperationError("关联奖励箱的兑换入口尚未核查或已过期，不能一键上线", 409)
                for (const action of CONTENT_ACTIONS) {
                    const review = this.actionControl(next, action)
                    // An independently expired right stays closed; it must not prevent a reviewed entrance reopening.
                    if ((action === "claim" || action === "exchange" && !this.boxParents.has(key)) && review?.enabled && review.endsAtMs !== null
                        && nowMs > review.endsAtMs && this.actionReviewReady(next, action)) continue
                    if (review?.enabled && !this.stateAllows(next, action, nowMs))
                        throw new ContentOperationError(`已配置的${action}动作失效，需重新核查后上线`, 409)
                }
                if (row.type === "pass_card_event") {
                    const other = this.passKeys.some(otherKey => otherKey !== key && this.allowed(otherKey, "visible", nowMs) === true)
                    if (other) throw new ContentOperationError("当前客户端同一时间只支持一个通行证入口", 409)
                }
            }
            next.revision = revision + 1
            const json = JSON.stringify(next)
            this.db.prepare("UPDATE content_operations_state SET value_json=? WHERE content_key=?").run(json, key)
            this.db.prepare("UPDATE content_operations_meta SET revision=? WHERE id=1").run(next.revision)
            this.db.prepare("INSERT INTO content_operations_audit VALUES(?,?,?,?,?,?)").run(next.revision, key, nowMs,
                JSON.stringify(before), json, reason)
            return next
        }
        return this.db.inTransaction ? apply() : this.db.transaction(apply).immediate()
    }
    /** Deadline-only edit, with a close marker when extending a naturally expired entrance. */
    setDeadline(key: string, input: unknown, nowMs: number): ContentControl {
        if (!this.rows.has(key)) throw new ContentOperationError("内容不存在", 404)
        if (!record(input) || Object.keys(input).some(field => !["expectedRevision", "catalogDigest", "endsAtMs", "reason"].includes(field))
            || !Number.isSafeInteger(input.expectedRevision) || (input.expectedRevision as number) < 0)
            throw new ContentOperationError("截止设置请求参数无效")
        if (input.catalogDigest !== this.digest) throw new ContentOperationError("内容目录已变化，请重新核对资源", 409)
        if (!Number.isSafeInteger(nowMs) || nowMs < 0) throw new ContentOperationError("无效的服务器时间")
        if (input.endsAtMs !== null && (!Number.isSafeInteger(input.endsAtMs) || (input.endsAtMs as number) <= nowMs))
            throw new ContentOperationError("截止时间必须为空或晚于当前真实时间")
        const reason = boundedText(input.reason, "变更原因")
        const apply = () => {
            const revision = this.revision()
            if (revision !== input.expectedRevision) throw new ContentOperationError("状态已被其他操作更新，请刷新后重试", 409)
            const before = this.state(key), control = this.deadlineControl(key, before)
            if (!before || !control.canEdit) throw new ContentOperationError(control.reason, 409)
            const row = this.rows.get(key)!, actions = this.deadlineActions(row, before)
            const next: ContentControl = JSON.parse(JSON.stringify(before))
            // Split legacy shared deadlines before editing participation, retaining every other exact review and scope.
            if (next.actionOverrides === undefined) next.actionOverrides = Object.fromEntries(CONTENT_ACTIONS.map(action =>
                [action, this.actionControl(before, action)!]))
            const expired = actions.some(action => {
                const review = this.actionControl(before, action)!
                return review.enabled && review.endsAtMs !== null && nowMs > review.endsAtMs
            })
            for (const action of actions) next.actionOverrides[action]!.endsAtMs = input.endsAtMs as number | null
            if (expired) {
                if (this.publishable(row)) next.published = false
                else next.actionOverrides.exchange!.enabled = false
            }
            // Extending an active pass must not revive an overlapping pass entrance.
            if (row.type === "pass_card_event" && this.stateAllows(next, "visible", nowMs)
                && this.passKeys.some(other => other !== key && this.allowed(other, "visible", nowMs) === true))
                throw new ContentOperationError("当前客户端同一时间只支持一个通行证入口", 409)
            next.revision = revision + 1
            const json = JSON.stringify(next)
            this.db.prepare("UPDATE content_operations_state SET value_json=? WHERE content_key=?").run(json, key)
            this.db.prepare("UPDATE content_operations_meta SET revision=? WHERE id=1").run(next.revision)
            this.db.prepare("INSERT INTO content_operations_audit VALUES(?,?,?,?,?,?)").run(next.revision, key, nowMs, JSON.stringify(before), json, reason)
            return next
        }
        return this.db.inTransaction ? apply() : this.db.transaction(apply).immediate()
    }
    update(key: string, input: unknown, nowMs: number): ContentControl {
        if (!this.rows.has(key)) throw new ContentOperationError("内容不存在", 404)
        if (!record(input)) throw new ContentOperationError("请求正文必须是对象")
        if (Object.keys(input).some(k => !["expectedRevision","catalogDigest","readiness","evidence","flags","endsAtMs","reason","questKeys","missionKeys","actionOverrides"].includes(k))) {
            throw new ContentOperationError("包含不支持的字段；重开沿用同一实例，不提供进度重置")
        }
        if (!Number.isSafeInteger(input.expectedRevision) || (input.expectedRevision as number) < 0) throw new ContentOperationError("缺少有效版本号")
        if (input.catalogDigest !== this.digest) throw new ContentOperationError("内容目录已变化，请重新核对资源", 409)
        const reason = boundedText(input.reason, "变更原因")
        if (!Number.isSafeInteger(nowMs) || nowMs < 0) throw new ContentOperationError("无效的服务器时间")
        // BEGIN IMMEDIATE makes compare + state + audit atomic even with a second SQLite writer.
        const apply = () => {
            const revision = this.revision()
            if (revision !== input.expectedRevision) throw new ContentOperationError("状态已被其他操作更新，请刷新后重试", 409)
            const row = this.rows.get(key)!
            const before = this.state(key)
            const next: ContentControl = before ? JSON.parse(JSON.stringify(before)) : {
                key, instanceId: `${key}:original`, readiness: "unverified", evidence: "",
                flags: { visible: false, enter: false, claim: false, exchange: false }, endsAtMs: null,
                revision, catalogDigest: this.digest, contentDigest: this.contentDigests.get(key)!,
            }
            const partial = input.actionOverrides !== undefined
            if (partial && ["flags", "endsAtMs", "questKeys", "missionKeys"].some(field => input[field] !== undefined))
                throw new ContentOperationError("动作覆盖不能与整行权限、期限或范围混合")
            if (!partial && before?.actionOverrides !== undefined && ["flags", "endsAtMs", "questKeys", "missionKeys"].some(field => input[field] !== undefined))
                throw new ContentOperationError("已使用动作权限，请分别修改动作覆盖")
            const wired = this.capabilities(row).length > 0
            next.controlled = next.controlled === true || (wired && ((!!before && before.controlled === undefined) || input.flags !== undefined || partial))
            for (const kind of ["quest", "mission"] as const) {
                const field = kind === "quest" ? "questKeys" : "missionKeys"
                if (input[field] === undefined) continue
                const values = input[field]
                const available = (kind === "quest" ? this.questMembers : this.missionMembers).get(key) ?? new Set<string>()
                if (values !== null && (!Array.isArray(values) || values.length > 5000
                    || values.some(value => typeof value !== "string" || !available.has(value)) || new Set(values).size !== values.length)) {
                    throw new ContentOperationError(`${kind}范围必须为本内容已定义的唯一键列表或空值`)
                }
                if (!available.size) throw new ContentOperationError(`本内容不支持${kind}范围`)
                next[field] = values === null ? null : [...values as string[]].sort()
            }
            if (input.readiness !== undefined) {
                if (!["unverified","current_baseline","verified","blocked"].includes(input.readiness as string)) throw new ContentOperationError("无效的就绪状态")
                next.readiness = input.readiness as ContentReadiness
                next.evidence = boundedText(input.evidence, "核查依据")
                if (next.readiness === "current_baseline" && !isFixedJulyCandidate(row)) throw new ContentOperationError("历史内容不能标为当前基线")
                next.catalogDigest = this.digest
                next.contentDigest = this.contentDigests.get(key)!
                delete next.integrityError
            } else if (input.evidence !== undefined) throw new ContentOperationError("核查依据必须与就绪状态一起更新")
            if (input.flags !== undefined) {
                if (!record(input.flags) || Object.keys(input.flags).some(k => !CONTENT_ACTIONS.includes(k as ContentAction))) throw new ContentOperationError("无效的操作开关")
                for (const action of CONTENT_ACTIONS) if (action in input.flags) {
                    if (typeof input.flags[action] !== "boolean") throw new ContentOperationError("开关必须是布尔值")
                    next.flags[action] = input.flags[action] as boolean
                }
            }
            if (input.endsAtMs !== undefined) {
                if (input.endsAtMs !== null && (!Number.isSafeInteger(input.endsAtMs) || (input.endsAtMs as number) <= nowMs)) throw new ContentOperationError("截止时间必须为空或晚于当前真实时间")
                next.endsAtMs = input.endsAtMs as number | null
            }
            if (next.readiness === "unverified" || next.readiness === "blocked") {
                if (input.flags && Object.values(input.flags).some(v => v === true)) throw new ContentOperationError("未验证或已知故障的内容禁止开启", 409)
                next.flags = { visible: false, enter: false, claim: false, exchange: false }
            }
            if (partial) {
                if (!record(input.actionOverrides) || !Object.keys(input.actionOverrides).length
                    || Object.keys(input.actionOverrides).some(action => !CONTENT_ACTIONS.includes(action as ContentAction)))
                    throw new ContentOperationError("动作覆盖必须包含已定义的动作")
                if (next.actionOverrides === undefined) {
                    next.actionOverrides = {}
                    // Legacy takeover owns the whole row; conversion retains every original decision and scope.
                    if (before && before.controlled !== false) for (const action of CONTENT_ACTIONS)
                        next.actionOverrides[action] = this.actionControl(before, action)!
                }
                for (const [actionName, value] of Object.entries(input.actionOverrides)) {
                    const action = actionName as ContentAction
                    if (!record(value) || Object.keys(value).some(field => !["enabled", "endsAtMs", "readiness", "evidence", "questKeys", "missionKeys"].includes(field))
                        || typeof value.enabled !== "boolean" || !["unverified", "current_baseline", "verified", "blocked"].includes(String(value.readiness)))
                        throw new ContentOperationError("无效的动作覆盖")
                    if (value.endsAtMs !== null && (!Number.isSafeInteger(value.endsAtMs) || (value.endsAtMs as number) <= nowMs))
                        throw new ContentOperationError("动作截止时间必须为空或晚于当前真实时间")
                    const override: ContentActionOverride = { enabled: value.enabled, endsAtMs: value.endsAtMs as number | null,
                        readiness: value.readiness as ContentReadiness, evidence: boundedText(value.evidence, "动作核查依据"),
                        catalogDigest: this.digest, contentDigest: this.contentDigests.get(key)! }
                    const previous = next.actionOverrides[action]
                    // Optional member fields retain the prior exact scope; only explicit null selects all.
                    for (const field of ["questKeys", "missionKeys"] as const) if (previous?.[field] !== undefined)
                        override[field] = previous[field] === null ? null : [...previous[field]!]
                    if (override.readiness === "current_baseline" && !isFixedJulyCandidate(row))
                        throw new ContentOperationError("历史内容不能标为当前基线")
                    for (const kind of ["quest", "mission"] as const) {
                        const field = kind === "quest" ? "questKeys" : "missionKeys"
                        const members = value[field], available = (kind === "quest" ? this.questMembers : this.missionMembers).get(key) ?? new Set<string>()
                        if (members === undefined) continue
                        if (!available.size || (members !== null && (!Array.isArray(members) || members.length > 5000
                            || new Set(members).size !== members.length || members.some(member => typeof member !== "string" || !available.has(member)))))
                            throw new ContentOperationError(`${kind}动作范围必须为本内容已定义的唯一键列表或空值`)
                        override[field] = members === null ? null : [...members as string[]].sort()
                    }
                    if (override.enabled) {
                        if (!["verified", "current_baseline"].includes(override.readiness)) throw new ContentOperationError("未验证或已知故障的动作禁止开启", 409)
                        if (!this.capabilities(row).includes(action)) throw new ContentOperationError(`该类型尚未接通服务端校验：${action}`, 409)
                        if (!this.definitionReady(row)) throw new ContentOperationError("客户端与服务端定义缺失、冲突或目录已过时，需要先重导出并核对资源和规则", 409)
                        if ((action === "enter" || action === "claim") && (override.questKeys?.length === 0 || override.missionKeys?.length === 0))
                            throw new ContentOperationError("动作开启时核查范围不能为空")
                        if ((action === "enter" || action === "claim") && ["quest", "mission"].some(kind => {
                            const members = (kind === "quest" ? this.questMembers : this.missionMembers).get(key)
                            return !!members?.size && override[kind === "quest" ? "questKeys" : "missionKeys"] === undefined
                        })) throw new ContentOperationError("有成员的动作必须明确选择精确范围或整范围")
                    }
                    next.actionOverrides[action] = override
                }
                next.controlled = true
                if (next.actionOverrides.enter?.enabled && next.actionOverrides.visible?.enabled === false)
                    throw new ContentOperationError("参与开启时受控入口必须可见")
                if (row.type === "pass_card_event" && this.stateAllows(next, "visible", nowMs)) {
                    const other = (this.db.prepare("SELECT content_key FROM content_operations_state WHERE content_key<>?").all(key) as Array<{ content_key: string }>)
                        .some(s => s.content_key.startsWith("pass_card_event:") && this.allowed(s.content_key, "visible", nowMs))
                    if (other) throw new ContentOperationError("当前客户端同一时间只支持一个通行证入口", 409)
                }
                delete next.integrityError
            }
            if (!partial && next.actionOverrides === undefined && CONTENT_ACTIONS.some(action => next.flags[action])) {
                if (next.contentDigest !== this.contentDigests.get(key)) throw new ContentOperationError("资源发生变化，需要重新核查", 409)
                if (!this.definitionReady(row)) throw new ContentOperationError("客户端与服务端定义缺失、冲突或目录已过时，需要先重导出并核对资源和规则", 409)
                const unsupported = CONTENT_ACTIONS.filter(action => next.flags[action] && !this.capabilities(row).includes(action))
                if (unsupported.length) throw new ContentOperationError(`该类型尚未接通服务端校验：${unsupported.join("、")}`, 409)
                if (next.flags.enter && !next.flags.visible) throw new ContentOperationError("参与开启时入口必须可见")
                if (next.flags.enter && (next.questKeys?.length === 0 || next.missionKeys?.length === 0)) throw new ContentOperationError("参与开启时核查范围不能为空")
                if (row.type === "pass_card_event" && next.flags.visible) {
                    const other = (this.db.prepare("SELECT content_key,value_json FROM content_operations_state WHERE content_key<>?").all(key) as Array<{ content_key: string; value_json: string }>)
                        .some(s => s.content_key.startsWith("pass_card_event:") && this.allowed(s.content_key,"visible",nowMs))
                    if (other) throw new ContentOperationError("当前客户端同一时间只支持一个通行证入口", 409)
                }
            }
            next.revision = revision + 1
            const json = JSON.stringify(next)
            this.db.prepare("INSERT INTO content_operations_state(content_key,value_json) VALUES(?,?) ON CONFLICT(content_key) DO UPDATE SET value_json=excluded.value_json").run(key,json)
            this.db.prepare("UPDATE content_operations_meta SET revision=? WHERE id=1").run(next.revision)
            this.db.prepare("INSERT INTO content_operations_audit VALUES(?,?,?,?,?,?)").run(next.revision,key,nowMs,before ? JSON.stringify(before) : null,json,reason)
            return next
        }
        return this.db.inTransaction ? apply() : this.db.transaction(apply).immediate()
    }
}
