import { createHash } from "node:crypto"
import { closeSync, openSync, readFileSync, readSync } from "node:fs"
import path from "node:path"

export interface ContentBoxAssociation {
    readonly parentKey: string
    readonly boxKey: string
    readonly relationshipMatches: boolean
    readonly description: string
}
export interface ContentBoxAssociationStatus {
    readonly available: boolean
    readonly relationshipsMatch: boolean
    readonly reason?: string
}
interface AssociationEvidence {
    parentKey: string; boxKey: string; description: string
    parent: { source: string; rowId: number; fieldIndex: number; boxId: number; rawSha256: string; definitionDigest: string; fields: string[] }
    box: { source: string; rowId: number; rawSha256: string; definitionDigest: string; fields: string[] }
    serverBoxDigest: string; serverRewardsDigest: string; nativeStagesDigest: string; nativeRewardsDigest: string
    stageCount: number; rewardCount: number; costItemId: number; costCount: number
}
interface AssociationAsset {
    schemaVersion: number; associationCount: number; parentTypeCounts: Record<string, number>
    catalogSha256: string; manifestSha256: string; assetVersion: string
    serverSources: Record<string, string>; nativeMasters: Record<string, { sha256: string }>
    associationsDigest: string; associations: AssociationEvidence[]
}
type Index = { status: Readonly<ContentBoxAssociationStatus>; rows: readonly ContentBoxAssociation[];
    byKey: ReadonlyMap<string, ContentBoxAssociation> }
const parentSources: Record<string, { source: string; column: number }> = {
    world_story_event: { source: "master/quest/event/world_story_event.orderedmap", column: 14 },
    raid_event: { source: "master/quest/event/raid_event.orderedmap", column: 18 },
}
const boxSource = "master/box_gacha/box_gacha.orderedmap"
const nativeSources = [boxSource, "master/box_gacha/box.orderedmap", "master/box_gacha/box_reward.orderedmap",
    ...Object.values(parentSources).map(value => value.source)].sort()
const serverSources = ["assets/box_gacha.json", "assets/box_reward.json", "assets/box_gacha_1001_settings.json", "src/lib/assets.ts"].sort()
let cached: Index | undefined

function hash(value: Buffer | string): string { return createHash("sha256").update(value).digest("hex") }
/** Hash original bytes without retaining another full catalog buffer. */
function hashFile(file: string): string {
    const digest = createHash("sha256"), buffer = Buffer.allocUnsafe(64 * 1024), fd = openSync(file, "r")
    try {
        let count: number
        while ((count = readSync(fd, buffer, 0, buffer.length, null)) > 0) digest.update(buffer.subarray(0, count))
        return digest.digest("hex")
    } finally { closeSync(fd) }
}
function stable(value: any): string {
    if (Array.isArray(value)) return "[" + value.map(stable).join(",") + "]"
    if (value !== null && typeof value === "object") return "{" + Object.keys(value).sort()
        .map(key => JSON.stringify(key) + ":" + stable(value[key])).join(",") + "}"
    return JSON.stringify(value)
}
function isHash(value: unknown): value is string { return typeof value === "string" && /^[a-f0-9]{64}$/.test(value) }
function sameKeys(value: unknown, expected: readonly string[]): boolean {
    return value !== null && typeof value === "object" && !Array.isArray(value)
        && JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort())
}
function checkStructure(value: AssociationAsset): void {
    if (!value || value.schemaVersion !== 1 || value.associationCount !== 48 || !Array.isArray(value.associations)
        || value.associations.length !== 48 || !isHash(value.catalogSha256) || !isHash(value.manifestSha256)
        || !isHash(value.associationsDigest) || hash(stable(value.associations)) !== value.associationsDigest
        || !sameKeys(value.parentTypeCounts, ["world_story_event", "raid_event"])
        || value.parentTypeCounts.world_story_event !== 41 || value.parentTypeCounts.raid_event !== 7
        || !sameKeys(value.nativeMasters, nativeSources) || !sameKeys(value.serverSources, serverSources)
        || Object.values(value.serverSources).some(item => !isHash(item))
        || Object.values(value.nativeMasters).some(item => !item || !isHash(item.sha256))) throw new Error("invalid_association_asset")
    const seen = new Set<string>(), counts: Record<string, number> = { world_story_event: 0, raid_event: 0 }
    for (const row of value.associations) {
        const parent = /^(world_story_event|raid_event):([1-9][0-9]*)$/.exec(row?.parentKey)
        const box = /^box_gacha:([1-9][0-9]*)$/.exec(row?.boxKey)
        if (!parent || !box || seen.has(row.parentKey) || seen.has(row.boxKey) || !row.parent || !row.box
            || row.parent.rowId !== Number(parent[2]) || row.box.rowId !== Number(box[1])
            || row.parent.boxId !== row.box.rowId || row.parent.fieldIndex !== parentSources[parent[1]].column
            || row.parent.source !== parentSources[parent[1]].source || row.box.source !== boxSource
            || !Array.isArray(row.parent.fields) || !Array.isArray(row.box.fields)
            || row.parent.fields.some(value => typeof value !== "string") || row.box.fields.some(value => typeof value !== "string")
            || hash(stable(row.parent.fields)) !== row.parent.definitionDigest || hash(stable(row.box.fields)) !== row.box.definitionDigest
            || row.parent.fields[row.parent.fieldIndex] !== String(row.box.rowId)
            || row.box.fields[1] !== "3" || Number(row.box.fields[2]) !== row.costItemId || Number(row.box.fields[3]) !== row.costCount
            || typeof row.description !== "string" || !row.description.trim()
            || [row.parent.rawSha256, row.parent.definitionDigest, row.box.rawSha256, row.box.definitionDigest,
                row.serverBoxDigest, row.serverRewardsDigest, row.nativeStagesDigest, row.nativeRewardsDigest].some(item => !isHash(item))
            || [row.stageCount, row.rewardCount, row.costItemId, row.costCount].some(item => !Number.isSafeInteger(item) || item < 1)) {
            throw new Error("invalid_association_asset")
        }
        seen.add(row.parentKey); seen.add(row.boxKey); counts[parent[1]]++
    }
    if (counts.world_story_event !== 41 || counts.raid_event !== 7) throw new Error("invalid_association_asset")
}

/** Static identity only. This module never reads player state or grants operations. */
function readIndex(): Index {
    if (cached) return cached
    const root = path.resolve(__dirname, "../.."), read = (relative: string): Buffer => readFileSync(path.join(root, relative))
    let evidence: AssociationAsset
    try { evidence = JSON.parse(read("assets/content_box_associations.json").toString("utf8")); checkStructure(evidence) }
    catch { return cached = { status: Object.freeze({ available: false, relationshipsMatch: false, reason: "association_index_unavailable" }), rows: Object.freeze([]), byKey: new Map() } }
    let reason: string | undefined
    try {
        if (hashFile(path.join(root, "assets/content_catalog.json")) !== evidence.catalogSha256) throw new Error("catalog_identity_mismatch")
        if (hashFile(path.join(root, "assets/asset-patch/manifest.json")) !== evidence.manifestSha256) throw new Error("manifest_identity_mismatch")
        // Resolve the same JSON module used by content-operations; Node shares its cached object.
        const catalog = require("../../assets/content_catalog.json"), rows = new Map<string, any>()
        for (const row of catalog.rows) {
            if (rows.has(row.key)) throw new Error("catalog_identity_mismatch")
            rows.set(row.key, row)
        }
        for (const source of nativeSources) if (catalog.resources?.[source]?.sha256 !== evidence.nativeMasters[source].sha256) {
            throw new Error("native_master_identity_mismatch")
        }
        for (const source of serverSources) {
            if (hashFile(path.join(root, source)) !== evidence.serverSources[source]) throw new Error("server_box_source_mismatch")
        }
        const boxes = require("../../assets/box_gacha.json")
        const rewards = require("../../assets/box_reward.json")
        const settings = require("../../assets/box_gacha_1001_settings.json")
        for (const entry of evidence.associations) {
            const parent = rows.get(entry.parentKey), box = rows.get(entry.boxKey), id = String(entry.box.rowId)
            if (!parent || !box || parent.source !== entry.parent.source || box.source !== entry.box.source
                || parent.definitionDigest !== entry.parent.definitionDigest || box.definitionDigest !== entry.box.definitionDigest
                || parent.type !== entry.parentKey.split(":")[0] || parent.id !== entry.parent.rowId
                || box.type !== "box_gacha" || box.id !== entry.box.rowId) throw new Error("catalog_row_identity_mismatch")
            if (!boxes[id] || !rewards[id] || hash(stable(boxes[id])) !== entry.serverBoxDigest
                || hash(stable(rewards[id])) !== entry.serverRewardsDigest
                || boxes[id].itemId !== entry.costItemId || boxes[id].count !== entry.costCount
                || Object.keys(rewards[id]).length !== entry.stageCount
                || Object.keys(box.boxRules ?? {}).length !== entry.stageCount
                || (id === "1001" && stable(settings.boxSettings) !== stable(box.boxRules))) throw new Error("server_box_definition_mismatch")
        }
    } catch (error) { reason = error instanceof Error ? error.message : "association_binding_unavailable" }
    const matches = reason === undefined
    const rows = Object.freeze(evidence.associations.map(entry => Object.freeze({ parentKey: entry.parentKey,
        boxKey: entry.boxKey, relationshipMatches: matches, description: entry.description })))
    const byKey = new Map<string, ContentBoxAssociation>()
    for (const row of rows) { byKey.set(row.parentKey, row); byKey.set(row.boxKey, row) }
    return cached = { status: Object.freeze({ available: true, relationshipsMatch: matches, ...(reason ? { reason } : {}) }), rows, byKey }
}

/** Accepts either exact native parent key or its box_gacha key. */
export function getContentBoxAssociation(key: string): Readonly<ContentBoxAssociation> | undefined { return readIndex().byKey.get(key) }
export function getContentBoxAssociations(): readonly Readonly<ContentBoxAssociation>[] { return readIndex().rows }
export function getContentBoxAssociationStatus(): Readonly<ContentBoxAssociationStatus> { return readIndex().status }
export function isContentBoxAssociationIndexAvailable(): boolean { return readIndex().status.available }
