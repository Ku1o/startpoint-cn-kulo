import { createHash } from "node:crypto"
import { Buffer } from "node:buffer"
import { closeSync, openSync, readFileSync, readSync, statSync } from "node:fs"
import path from "node:path"

export interface DiscoveryCharacter { id: number; name: string; relation: "up" | "pool" | "exchange" | "reward"; aliases?: string[] }
export interface DiscoveryReward { kind: string; id: number; name: string; relation: string; aliases?: string[] }
export interface DiscoveryRecord {
    characters: DiscoveryCharacter[]; rewards: DiscoveryReward[]; aliases: string[]; editionLabel?: string
    notes: string[]; publicNotes?: string[]; status: "verified" | "unavailable" | "not_applicable"; evidence?: unknown[]
}
interface DiscoveryIndex {
    schemaVersion: 1
    source: { manifestSha256: string; presentationSha256: string; catalogSha256: string }
    sourceInputs: Record<string, string>; rows: Record<string, DiscoveryRecord>
}
interface SearchField { text: string; reason: string; weight: number }
interface RuntimeRecord {
    characters: number[]; rewards: number[]; aliases: string[]; editionLabel?: string; publicNotes: string[]
    status: DiscoveryRecord["status"]; highlights: DiscoveryView["highlights"]
}
interface RuntimeIndex {
    schemaVersion: 2; canonicalSha256: string; source: DiscoveryIndex["source"]; sourceInputs: Record<string, string>
    rows: Record<string, RuntimeRecord>
    characters: Array<{ entity: DiscoveryCharacter; fields: SearchField[] }>
    rewards: Array<{ entity: DiscoveryReward; fields: SearchField[] }>
}
type Index = DiscoveryIndex | RuntimeIndex
export interface DiscoveryParent {
    key: string; type: string; name: string; originalStartMs: number | null; originalEndMs: number | null
    presentation: { title: string; originalTitle?: string; subtitle?: string; group: string; typeLabel: string }
}
export interface DiscoveryView {
    seriesKey: string; seriesTitle: string; editionLabel?: string
    highlights: { label: string; names: string[]; total: number }[]; notes: string[]; matchReasons: string[]
}
/** Summarise the full filtered set before group pagination; child operations stay independent. */
export function groupContentSeries<T extends { discovery: Pick<DiscoveryView, "seriesKey" | "seriesTitle">; originalStartMs: number | null; primaryControl: { status: string } }>(rows: T[]) {
    const groups = new Map<string, { key: string; title: string; total: number; enabled: number; disabled: number; pending: number; blocked: number;
        firstStartMs: number | null; lastStartMs: number | null; preview: T }>()
    for (const row of rows) {
        const key = row.discovery.seriesKey
        if (!groups.has(key)) groups.set(key, { key, title: row.discovery.seriesTitle, total: 0, enabled: 0, disabled: 0, pending: 0, blocked: 0,
            firstStartMs: null, lastStartMs: null, preview: row })
        const group = groups.get(key)!
        group.total++
        if (row.primaryControl.status === "enabled") group.enabled++
        else if (row.primaryControl.status === "disabled") group.disabled++
        else if (row.primaryControl.status === "pending") group.pending++
        else group.blocked++
        if (row.originalStartMs !== null) {
            group.firstStartMs = group.firstStartMs === null ? row.originalStartMs : Math.min(group.firstStartMs, row.originalStartMs)
            group.lastStartMs = group.lastStartMs === null ? row.originalStartMs : Math.max(group.lastStartMs, row.originalStartMs)
        }
    }
    return [...groups.values()]
}
const root = path.resolve(__dirname, "../.."), canonicalPath = path.join(root, "assets/content_discovery.json")
const runtimePath = path.join(root, "assets/content_discovery_runtime.json")
const shaPattern = /^[a-f0-9]{64}$/
const hashes = new Map<string, { signature: string; digest: string }>()
let cached: { signature: string; value: Index } | undefined
const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value)
const texts = (value: unknown): value is string[] => Array.isArray(value) && value.every(text => typeof text === "string" && text.length <= 2000)
function validRecord(value: unknown): value is DiscoveryRecord {
    if (!object(value) || !Array.isArray(value.characters) || !Array.isArray(value.rewards) || !texts(value.aliases) || !texts(value.notes)
        || (value.publicNotes !== undefined && !texts(value.publicNotes))
        || (value.editionLabel !== undefined && (typeof value.editionLabel !== "string" || value.editionLabel.length > 2000))
        || !["verified", "unavailable", "not_applicable"].includes(value.status as string)) return false
    const entity = (item: unknown) => object(item) && Number.isSafeInteger(item.id) && Number(item.id) >= 0
        && typeof item.name === "string" && item.name.trim().length > 0 && item.name.length <= 2000
        && (item.aliases === undefined || texts(item.aliases))
    return value.characters.every(item => entity(item) && ["up", "pool", "exchange", "reward"].includes(item.relation))
        && value.rewards.every(item => entity(item) && typeof item.kind === "string" && item.kind.length > 0 && item.kind.length <= 200
            && ["up", "pool", "drop", "firstClear", "mission", "box", "exchange", "ranking", "overall", "pass"].includes(item.relation))
}
const signature = (file: string) => { const stat = statSync(file, { bigint: true }); return `${stat.dev}:${stat.ino}:${stat.size}:${stat.mtimeNs}:${stat.ctimeNs}` }
function digest(file: string): string {
    const current = signature(file), old = hashes.get(file)
    if (old?.signature === current) return old.digest
    const hash = createHash("sha256"), buffer = Buffer.allocUnsafe(64 * 1024), fd = openSync(file, "r")
    try { let count: number; while ((count = readSync(fd, buffer, 0, buffer.length, null))) hash.update(buffer.subarray(0, count)) }
    finally { closeSync(fd) }
    if (signature(file) !== current) throw new Error("Discovery source changed during verification")
    const value = hash.digest("hex")
    hashes.set(file, { signature: current, digest: value })
    return value
}
function validRuntime(value: RuntimeIndex): boolean {
    if (!Array.isArray(value.characters) || !Array.isArray(value.rewards)) return false
    const fieldsValid = (fields: unknown) => Array.isArray(fields) && fields.every(field => object(field)
        && typeof field.text === "string" && typeof field.reason === "string" && Number.isFinite(field.weight))
    if (!value.characters.every(item => object(item) && fieldsValid(item.fields)
        && validRecord({ characters: [item.entity], rewards: [], aliases: [], notes: [], status: "verified" }))
        || !value.rewards.every(item => object(item) && fieldsValid(item.fields)
            && validRecord({ characters: [], rewards: [item.entity], aliases: [], notes: [], status: "verified" }))) return false
    const references = (refs: unknown, size: number) => Array.isArray(refs) && refs.every(ref => Number.isSafeInteger(ref) && ref >= 0 && ref < size)
    return Object.values(value.rows).every(row => object(row) && references(row.characters, value.characters.length)
        && references(row.rewards, value.rewards.length) && texts(row.aliases) && texts(row.publicNotes)
        && (row.editionLabel === undefined || typeof row.editionLabel === "string")
        && ["verified", "unavailable", "not_applicable"].includes(row.status as string)
        && Array.isArray(row.highlights) && row.highlights.every(item => object(item) && typeof item.label === "string"
            && texts(item.names) && Number.isSafeInteger(item.total) && Number(item.total) > 0))
}
function readIndex(): Index | null {
    try {
        // Small schema-1 installations remain compatible. The production full
        // document is never parsed when the offline projection is unavailable.
        let indexPath: string
        try { statSync(runtimePath); indexPath = runtimePath }
        catch { if (statSync(canonicalPath).size > 1024 * 1024) return null; indexPath = canonicalPath }
        if (statSync(indexPath).size > 8 * 1024 * 1024) return null
        const current = signature(indexPath)
        const fresh = cached?.signature !== current
        const value = fresh ? JSON.parse(readFileSync(indexPath, "utf8")) as Index : cached!.value
        if (![1, 2].includes(value.schemaVersion) || !object(value.source) || !object(value.rows) || !object(value.sourceInputs)
            || !Object.keys(value.sourceInputs).length) return null
        if (indexPath === runtimePath && value.schemaVersion !== 2) return null
        if (fresh) {
            if (!Object.keys(value.rows).every(key => /^[a-z_]+:\d+$/.test(key))) return null
            if (value.schemaVersion === 2 ? !validRuntime(value as RuntimeIndex)
                : !Object.values(value.rows).every(validRecord)) return null
            const parents = JSON.parse(readFileSync(path.join(root, "assets/content_presentation.json"), "utf8")).rows
            if (!object(parents) || JSON.stringify(Object.keys(parents).sort()) !== JSON.stringify(Object.keys(value.rows).sort())) return null
        }
        if (value.schemaVersion === 2 && (!shaPattern.test((value as RuntimeIndex).canonicalSha256 || "")
            || digest(canonicalPath) !== (value as RuntimeIndex).canonicalSha256)) return null
        const expected = [["assets/asset-patch/manifest.json", value.source.manifestSha256],
            ["assets/content_presentation.json", value.source.presentationSha256], ["assets/content_catalog.json", value.source.catalogSha256]]
        for (const [relative, sha] of [...expected, ...Object.entries(value.sourceInputs)]) {
            if (!shaPattern.test(sha || "") || !/^(?:assets|src|tools|docs)\/[a-zA-Z0-9_./-]+$/.test(relative)
                || relative.split("/").some(part => part === ".." || part === "." || !part)
                || digest(path.join(root, relative)) !== sha) return null
        }
        if (signature(indexPath) !== current) return null
        cached = { signature: current, value }
        return value
    } catch { return null }
}
export const normalizeDiscoveryText = (value: string) => value.normalize("NFKC").toLocaleLowerCase().replace(/[\p{P}\p{S}\s]/gu, "")
export function discoveryTerms(query: string): string[] {
    return [...new Set(query.normalize("NFKC").trim().split(/[\s,，;；、]+/u).map(normalizeDiscoveryText).filter(Boolean))]
}
const dateStrings = (milliseconds: number | null) => {
    if (milliseconds === null || !Number.isFinite(milliseconds)) return []
    const date = new Date(milliseconds + 8 * 3600_000), y = date.getUTCFullYear(), m = date.getUTCMonth() + 1, d = date.getUTCDate()
    return [`${y}年${m}月${d}日`, `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`,
        `${y}-${m}-${d}`, `${y}年${m}月`, `${y}-${String(m).padStart(2, "0")}`]
}
const characterLabels: Record<string, string> = { up: "UP角色", pool: "池内可获得角色", exchange: "可兑换角色", reward: "奖励角色" }
const rewardLabels: Record<string, string> = { up: "UP装备", pool: "池内可获得装备", drop: "关卡掉落", firstClear: "首次通关奖励", mission: "任务奖励", box: "箱池奖励", exchange: "兑换奖励", ranking: "排行奖励", overall: "全体奖励", pass: "通行证奖励" }
const names = (entities: Array<{ name: string; aliases?: string[] }>) => entities.flatMap(entity => [entity.name, ...(entity.aliases || [])])
type Prepared = { identity: string; view: DiscoveryView; fields: SearchField[] }
// Each captured source owns its prepared cards. Concurrent requests may hold
// different versions (including a degraded reader) without exchanging views.
const preparedBySource = new WeakMap<Index, Map<string, Prepared>>()
const fallbackPrepared = new Map<string, Prepared>()
function safeRecord(index: Index | null, key: string): DiscoveryRecord | RuntimeRecord | undefined {
    const row = index && Object.prototype.hasOwnProperty.call(index.rows, key) ? index.rows[key] : undefined
    return row && Array.isArray(row.characters) && Array.isArray(row.rewards) && Array.isArray(row.aliases)
        && (index?.schemaVersion === 2 || Array.isArray((row as DiscoveryRecord).notes)) ? row : undefined
}
/** A request-local reader validates source identities once; no database/player state is accessed. */
export function contentDiscoveryReader() {
    const index = readIndex()
    const preparedRows = index ? preparedBySource.get(index) || new Map<string, Prepared>() : fallbackPrepared
    if (index && !preparedBySource.has(index)) preparedBySource.set(index, preparedRows)
    const notes = (row: DiscoveryRecord | RuntimeRecord | undefined) => !index ? ["关联资料已变化，暂只按内容名称和原始档期检索。"]
        : [...(row?.publicNotes || []), ...(row?.status === "unavailable" && !row.publicNotes?.length
            ? ["部分关联资料尚未确认，下方仅列出已核实的角色和奖励。"] : [])]
    const details = (key: string) => {
        const row = safeRecord(index, key)
        return { characters: index?.schemaVersion === 2 ? ((row as RuntimeRecord | undefined)?.characters || []).map(ref => index.characters[ref].entity)
                : (row as DiscoveryRecord | undefined)?.characters || [],
            rewards: index?.schemaVersion === 2 ? ((row as RuntimeRecord | undefined)?.rewards || []).map(ref => index.rewards[ref].entity)
                : (row as DiscoveryRecord | undefined)?.rewards || [], aliases: row?.aliases || [], notes: notes(row) }
    }
    function prepared(parent: DiscoveryParent) {
        const identity = JSON.stringify([parent.type, parent.name, parent.originalStartMs, parent.originalEndMs, parent.presentation])
        const old = preparedRows.get(parent.key)
        if (old?.identity === identity) return old
        const row = safeRecord(index, parent.key), p = parent.presentation
        // Display grouping is based on the same native name and type; it does not merge operations or imply shared eligibility.
        const seriesName = p.originalTitle || p.title
        const seriesKey = createHash("sha256").update(`${parent.type}\n${seriesName}`).digest("hex").slice(0, 24)
        const fields: Array<{ text: string; reason: string; weight: number }> = []
        const add = (text: string | undefined, reason: string, weight: number) => { if (text) fields.push({ text: normalizeDiscoveryText(text), reason, weight }) }
        add(p.title, "内容名称", 100); add(p.originalTitle, "原始名称", 95); add(parent.name, "原始名称", 90)
        add(parent.key, "内容编号", 80); add(p.subtitle, "内容说明", 45); add(p.typeLabel, "玩法类型", 35)
        add(row?.editionLabel, "活动期次", 75)
        for (const alias of row?.aliases || []) add(alias, "名称别称", 85)
        for (const date of [...dateStrings(parent.originalStartMs), ...dateStrings(parent.originalEndMs)]) add(date, "原始档期", 65)
        const highlights: DiscoveryView["highlights"] = index?.schemaVersion === 2 ? (row as RuntimeRecord | undefined)?.highlights || [] : []
        // Legacy records are bounded to 1 MiB. Production relations remain
        // dictionary references; neither cards nor matches hydrate full details.
        const legacy = index?.schemaVersion === 1 ? row as DiscoveryRecord | undefined : undefined
        for (const relation of ["up", "pool", "reward", "exchange"] as const) {
            const entities = (legacy?.characters || []).filter(entity => entity.relation === relation), label = characterLabels[relation]
            if (entities.length) highlights.push({ label, names: [...new Set(entities.map(entity => entity.name))].slice(0, 8), total: entities.length })
            for (const entity of entities) for (const name of names([entity])) add(name, `${label}：${entity.name}`, relation === "up" ? 80 : 50)
        }
        const rewardGroups = new Map<string, DiscoveryReward[]>()
        for (const entity of legacy?.rewards || []) {
            const label = rewardLabels[entity.relation] || "关联奖励"
            if (!rewardGroups.has(label)) rewardGroups.set(label, [])
            rewardGroups.get(label)!.push(entity)
            for (const name of names([entity])) add(name, `${label}：${entity.name}`, 55)
        }
        for (const [label, entities] of rewardGroups) highlights.push({ label, names: [...new Set(entities.map(entity => entity.name))].slice(0, 8), total: entities.length })
        const view: DiscoveryView = { seriesKey, seriesTitle: p.title, ...(row?.editionLabel ? { editionLabel: row.editionLabel } : {}),
            highlights, notes: notes(row), matchReasons: [] }
        const result = { identity, view, fields }; preparedRows.set(parent.key, result); return result
    }
    function* fields(parent: DiscoveryParent, data: Prepared): Generator<SearchField, void, undefined> {
        yield* data.fields
        if (index?.schemaVersion !== 2) return
        const row = safeRecord(index, parent.key) as RuntimeRecord | undefined
        // Preserve the original relation traversal and tie-breaking order.
        for (const relation of ["up", "pool", "reward", "exchange"] as const) for (const ref of row?.characters || []) {
            const item = index.characters[ref]
            if (item.entity.relation === relation) yield* item.fields
        }
        for (const ref of row?.rewards || []) yield* index.rewards[ref].fields
    }
    return {
        verificationNotice: index ? undefined : "关联资料尚未完成核验或已经变化，暂只支持名称、说明和原始档期检索。",
        details,
        meta: (parent: DiscoveryParent) => { const view = prepared(parent).view; return { seriesKey: view.seriesKey, seriesTitle: view.seriesTitle,
            ...(view.editionLabel ? { editionLabel: view.editionLabel } : {}) } },
        view: (parent: DiscoveryParent) => prepared(parent).view,
        match(parent: DiscoveryParent, terms: string[]) {
            const data = prepared(parent)
            if (!terms.length) return { matched: true, score: 0, reasons: [] as string[] }
            let score = 0
            const reasons: string[] = []
            for (const term of terms) {
                let best: { text: string; reason: string; weight: number } | undefined, bestScore = -1
                for (const field of fields(parent, data)) {
                    if (!field.text.includes(term)) continue
                    const score = field.weight + (field.text === term ? 100 : field.text.startsWith(term) ? 15 : 0)
                    if (score > bestScore) { best = field; bestScore = score }
                }
                if (!best) return { matched: false, score: 0, reasons: [] as string[] }
                score += bestScore
                if (!reasons.includes(best.reason)) reasons.push(best.reason)
            }
            return { matched: true, score, reasons: reasons.slice(0, 4) }
        },
    }
}
