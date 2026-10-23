import { createHash } from "node:crypto"
import { closeSync, fstatSync, openSync, readFileSync, readSync } from "node:fs"
import path from "node:path"
import { inflateRawSync } from "node:zlib"
import type { ContentCatalogRow } from "./content-operations-store"
import { SPECIAL_EXCHANGE_DEFINITIONS, START_DASH_EXCHANGE_DEFINITIONS } from "./exchange-campaign-definitions"

/** A content dependency receipt, separate from whole-table provenance. */
export interface ExactDefinitionEvidence {
    schemaVersion: 1
    key: string
    oldDefinitionMatched: true
    definitionDigest: string
    dependencyDigest: string
    loaders: Record<string, string>
    previousServerDefinitionDigest: string
}
export interface CurrentParentDefinitionEvidence {
    schemaVersion: 1
    key: string
    definitionDigest: string
    dependencyDigest: string
    loaders: Record<string, string>
    previousServerDefinitionDigest: string
    reviewedExistingChildren: string[]
    newUncataloguedChildren: string[]
}
export type ExactDefinitionRow = ContentCatalogRow & { exactDefinitionEvidence?: ExactDefinitionEvidence;
    currentParentDefinitionEvidence?: CurrentParentDefinitionEvidence }
export interface CampaignDefinitionEvidence {
    schemaVersion: 1
    key: string
    clientDefinitionDigest: string
    runtimeDigest: string
    manifestSha256: string
    currentMasterSources: Record<string, string>
    currentMasterArchives: Record<string, string>
}
const loaders = ["src/lib/assets.ts", "src/lib/content-master.ts", "src/lib/shop-sales.ts", "src/lib/multi-special-exchange.ts",
    "src/lib/content-quest-rules.ts", "src/lib/content-shop-rules.ts"]
const parentTypes: Record<string, number> = { advent_event: 0, story_event: 2, challenge_dungeon_event: 4,
    world_story_event: 6, collect_item_event: 9, carnival_event: 10, rush_event: 11, score_attack_event: 12 }
const shops = new Set(["general_shop", "star_grain_shop", "treasure_shop", "boss_coin_shop", "event_item_shop"])
const runtimeInputs = new Map<string, Map<string, any>>()
const campaignSalt = "K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy"
const specialMaster = "master/campaign/special_exchange/special_exchange_campaign.orderedmap"
const characterMaster = "master/campaign/special_exchange/special_exchange_campaign_character.orderedmap"
const equipmentMaster = "master/campaign/special_exchange/special_exchange_campaign_equipment.orderedmap"
const startMaster = "master/campaign/start_dash_exchange/start_dash_exchange_campaign.orderedmap"
const termMaster = "master/campaign/start_dash_exchange/start_dash_exchange_campaign_term.orderedmap"
const excludeMaster = "master/campaign/start_dash_exchange/start_dash_exchange_campaign_exclude_character.orderedmap"
const masterNames = new Set([specialMaster, characterMaster, equipmentMaster, startMaster, termMaster, excludeMaster])
const maxZipDirectory = 16 * 1024 * 1024
const maxMasterBytes = 16 * 1024 * 1024
type ZipEntry = { offset: number; compressed: number; uncompressed: number; method: number }
type CampaignChain = { manifestSha256: string; active: string[]; indexes: Map<string, Map<string, ZipEntry>>;
    sources: Map<string, string> }
const campaignChains = new Map<string, CampaignChain>()

function zipRead(fd: number, offset: number, length: number): Buffer {
    const result = Buffer.alloc(length)
    let done = 0
    while (done < length) {
        const count = readSync(fd, result, done, length - done, offset + done)
        if (!count) throw new Error("Truncated CDN ZIP")
        done += count
    }
    return result
}

/** Read only the central directory and, when requested, one exact member. */
function zipIndex(file: string): Map<string, ZipEntry> {
    const fd = openSync(file, "r")
    try {
        const size = fstatSync(fd).size
        const tailSize = Math.min(size, 65557)
        const tail = zipRead(fd, size - tailSize, tailSize)
        let eocd = -1
        for (let at = tail.length - 22; at >= 0; at--) {
            if (tail.readUInt32LE(at) === 0x06054b50 && at + 22 + tail.readUInt16LE(at + 20) === tail.length) {
                eocd = at; break
            }
        }
        if (eocd < 0 || tail.readUInt16LE(eocd + 4) !== 0 || tail.readUInt16LE(eocd + 6) !== 0)
            throw new Error("Unsupported CDN ZIP directory")
        const count = tail.readUInt16LE(eocd + 10), length = tail.readUInt32LE(eocd + 12)
        const offset = tail.readUInt32LE(eocd + 16)
        if (count === 0xffff || length === 0xffffffff || offset === 0xffffffff
            || length > maxZipDirectory || offset + length > size) throw new Error("Unsupported CDN ZIP size")
        const directory = zipRead(fd, offset, length), entries = new Map<string, ZipEntry>()
        let at = 0
        for (let i = 0; i < count; i++) {
            if (at + 46 > directory.length || directory.readUInt32LE(at) !== 0x02014b50)
                throw new Error("Malformed CDN ZIP directory")
            const nameLength = directory.readUInt16LE(at + 28), extra = directory.readUInt16LE(at + 30)
            const comment = directory.readUInt16LE(at + 32), end = at + 46 + nameLength + extra + comment
            if (end > directory.length || directory.readUInt16LE(at + 34) !== 0)
                throw new Error("Malformed CDN ZIP entry")
            const name = directory.toString("utf8", at + 46, at + 46 + nameLength)
            if (entries.has(name)) throw new Error("Ambiguous CDN ZIP member")
            entries.set(name, { method: directory.readUInt16LE(at + 10),
                compressed: directory.readUInt32LE(at + 20), uncompressed: directory.readUInt32LE(at + 24),
                offset: directory.readUInt32LE(at + 42) })
            at = end
        }
        if (at !== directory.length) throw new Error("Unexpected CDN ZIP directory bytes")
        return entries
    } finally { closeSync(fd) }
}

function zipMember(file: string, member: string, entry: ZipEntry): Buffer {
    if (entry.compressed > maxMasterBytes || entry.uncompressed > maxMasterBytes)
        throw new Error("CDN master exceeds bounded reader")
    const fd = openSync(file, "r")
    try {
        const local = zipRead(fd, entry.offset, 30)
        if (local.readUInt32LE(0) !== 0x04034b50 || local.readUInt16LE(8) !== entry.method)
            throw new Error("CDN ZIP local entry mismatch")
        const nameLength = local.readUInt16LE(26), extraLength = local.readUInt16LE(28)
        if (zipRead(fd, entry.offset + 30, nameLength).toString("utf8") !== member)
            throw new Error("CDN ZIP member name mismatch")
        const encoded = zipRead(fd, entry.offset + 30 + nameLength + extraLength, entry.compressed)
        const raw = entry.method === 0 ? encoded : entry.method === 8
            ? inflateRawSync(encoded, { maxOutputLength: maxMasterBytes }) : null
        if (!raw || raw.length !== entry.uncompressed) throw new Error("CDN ZIP master decode mismatch")
        return raw
    } finally { closeSync(fd) }
}

function campaignChain(root: string): CampaignChain {
    // Check the manifest identity on each lookup, so a new chain invalidates the six shared winners.
    const bytes = readFileSync(path.join(root, "assets/asset-patch/manifest.json"))
    const manifestSha256 = createHash("sha256").update(bytes).digest("hex")
    const previous = campaignChains.get(root)
    if (previous?.manifestSha256 === manifestSha256) return previous
    const manifest = JSON.parse(bytes.toString("utf8")) as { patches?: Array<{
        enabled?: boolean; archive?: string; chain?: string[]; archive_integrity?: Array<{ name: string }> }> }
    if (!Array.isArray(manifest.patches)) throw new Error("Missing CDN patch chain")
    const names: string[] = []
    for (const patch of manifest.patches) {
        if (!patch.enabled) continue
        const archives = patch.chain ?? (patch.archive ? [patch.archive] : patch.archive_integrity?.map(value => value.name))
        if (!Array.isArray(archives) || !archives.length) throw new Error("Incomplete CDN patch chain")
        for (const archive of archives) {
            if (typeof archive !== "string" || !/^[a-zA-Z0-9][a-zA-Z0-9._-]*\.zip$/.test(archive))
                throw new Error("Invalid CDN patch archive")
            names.push(path.join(root, "assets/asset-patch/active", archive))
        }
    }
    const result = { manifestSha256, active: names, indexes: new Map<string, Map<string, ZipEntry>>(),
        sources: new Map<string, string>() }
    campaignChains.set(root, result)
    return result
}

function winningMasterSha(root: string, logical: string, baseline: string, chain: CampaignChain): string {
    const cached = chain.sources.get(logical)
    if (cached) return cached
    const hash = createHash("sha1").update(logical + campaignSalt).digest("hex")
    const member = `production/upload/${hash.slice(0, 2)}/${hash.slice(2)}`
    // Match the CDN route's configured pristine root; the receipt stores only a
    // relative common-chain location, never an environment-specific absolute path.
    const configuredCdn = process.env.CDN_DIR || ".cdn"
    const cdnRoot = path.isAbsolute(configuredCdn) ? configuredCdn : path.join(root, configuredCdn)
    let winner = path.join(cdnRoot, baseline.slice(".cdn/".length))
    let entry: ZipEntry | undefined
    for (let i = chain.active.length - 1; i >= 0; i--) {
        const archive = chain.active[i]
        let index = chain.indexes.get(archive)
        if (!index) { index = zipIndex(archive); chain.indexes.set(archive, index) }
        const candidate = index.get(member)
        if (candidate) { winner = archive; entry = candidate; break }
    }
    if (!entry) entry = zipIndex(winner).get(member)
    if (!entry) throw new Error("Missing winning CDN master")
    const digest = createHash("sha256").update(zipMember(winner, member, entry)).digest("hex")
    chain.sources.set(logical, digest)
    return digest
}
export function stableDefinitionJson(value: unknown): string {
    if (value === undefined) return "null"
    if (Array.isArray(value)) return `[${value.map(stableDefinitionJson).join(",")}]`
    if (value !== null && typeof value === "object") return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableDefinitionJson((value as Record<string, unknown>)[key])}`).join(",")}}`
    return JSON.stringify(value)
}
export function exactDefinitionHash(value: unknown): string {
    return createHash("sha256").update(stableDefinitionJson(value)).digest("hex")
}
/** CDN master-to-server parity is audited offline; runtime re-reads the six bounded winning masters. */
export function matchCampaignDefinition(row: ContentCatalogRow, root: string): { digest: string; matchesCatalog: boolean } | null {
    if (row.type !== "special_exchange_campaign" && row.type !== "start_dash_exchange_campaign") return null
    const evidence = (row as ContentCatalogRow & { campaignDefinitionEvidence?: CampaignDefinitionEvidence }).campaignDefinitionEvidence
    const definition = row.type === "special_exchange_campaign"
        ? SPECIAL_EXCHANGE_DEFINITIONS[String(row.id)] : START_DASH_EXCHANGE_DEFINITIONS[String(row.id)]
    const runtimeDigest = exactDefinitionHash({ key: row.key, definition: definition ?? null })
    const required = row.type === "start_dash_exchange_campaign" ? [startMaster, termMaster, excludeMaster]
        : [specialMaster, (definition as typeof SPECIAL_EXCHANGE_DEFINITIONS[string] | undefined)?.rewardType === 0
            ? characterMaster : equipmentMaster]
    try {
        if (!definition || !evidence || evidence.schemaVersion !== 1 || evidence.key !== row.key
            || evidence.clientDefinitionDigest !== row.definitionDigest || evidence.runtimeDigest !== runtimeDigest
            || (row.type === "special_exchange_campaign" && ![0, 1].includes((definition as typeof SPECIAL_EXCHANGE_DEFINITIONS[string]).rewardType))
            || Object.keys(evidence.currentMasterSources ?? {}).sort().join("|") !== [...required].sort().join("|")
            || Object.keys(evidence.currentMasterArchives ?? {}).sort().join("|") !== [...required].sort().join("|"))
            throw new Error("Incomplete campaign receipt")
        const chain = campaignChain(root)
        const currentMasterSources: Record<string, string> = {}
        for (const logical of required) {
            if (!masterNames.has(logical) || !/^[a-f0-9]{64}$/.test(evidence.currentMasterSources[logical])
                || !/^\.cdn\/cn\/archive-common-(?:full|diff)\/[a-zA-Z0-9][a-zA-Z0-9._-]*\.zip$/.test(evidence.currentMasterArchives[logical]))
                throw new Error("Invalid campaign source receipt")
            currentMasterSources[logical] = winningMasterSha(root, logical, evidence.currentMasterArchives[logical], chain)
        }
        return { digest: exactDefinitionHash({ key: row.key, runtimeDigest, currentMasterSources }),
            matchesCatalog: required.every(logical => currentMasterSources[logical] === evidence.currentMasterSources[logical]) }
    } catch {
        return { digest: exactDefinitionHash({ key: row.key, runtimeDigest, unavailable: true }), matchesCatalog: false }
    }
}
/** Selectors are derived here, never supplied by an administrator or a catalog recipe. */
export function captureExactDefinition(row: ContentCatalogRow, root: string, tables = new Map<string, any>()): { dependencies: Record<string, unknown>; loaders: Record<string, string>; digest: string } | null {
    const dependencies: Record<string, unknown> = {}
    const read = (source: string): any => {
        if (!tables.has(source)) tables.set(source, JSON.parse(readFileSync(path.join(root, source), "utf8")))
        return tables.get(source)
    }
    const take = (source: string, keys: string[]) => {
        let value = read(source)
        for (const key of keys) value = value?.[key]
        dependencies[`${source}#${keys.join("/")}`] = value ?? null
        return value
    }
    const id = String(row.id)
    const eventSources = ["assets/event_item_shop.json", "assets/event_item_shop_rank_p5b.json"]
    const mapSources = ["assets/event_item_shop_id_map.json", "assets/event_item_shop_id_map_rank_p5b.json"]
    if (shops.has(row.type)) {
        if (row.type === "event_item_shop") {
            // Bind every candidate map, including absent overlays, and all candidate item locations.
            // Thus a later map overwrite or an overlay that starts defining this item invalidates it.
            const mappings = mapSources.map(source => take(source, [id])).filter(Boolean)
            for (const mapping of mappings) for (const source of eventSources)
                take(source, [String(mapping.eventType), String(mapping.eventId), id])
        } else if (row.type === "boss_coin_shop") {
            const category = take("assets/boss_coin_shop_item_category_map.json", [id])
            take("assets/boss_coin_shop.json", [String(category), id])
        } else take(`assets/${row.type}.json`, [id])
    } else if (row.type in parentTypes) {
        // An event shop parent binds the complete child set and mapping subset, including
        // siblings that remain disabled. Its receipt grants no quest participation.
        const eventType = parentTypes[row.type]
        for (const source of eventSources) take(source, [String(eventType), id])
        for (const source of mapSources) dependencies[`${source}#parent:${eventType}:${id}`] = Object.fromEntries(
            Object.entries(read(source)).filter(([, value]) => {
                const mapping = value as { eventType: number; eventId: number }
                return Number(mapping.eventType) === eventType && String(mapping.eventId) === id
            }))
        for (const source of row.definitionEvidence?.serverSources ?? []) {
            if (!/^assets\/[a-zA-Z0-9_/-]+\.json$/.test(source) || source.split("/").includes("..")) return null
            dependencies[`${source}#parent-definition`] = read(source)
        }
    } else if (row.type === "active_mission_event") {
        take("assets/mission_active_event.json", [id])
        const members = Object.entries(read("assets/mission_active.json"))
            .filter(([, value]) => Array.isArray(value) && Array.isArray(value[0]) && String(value[0][0]) === id)
            .map(([missionId]) => missionId).sort()
        dependencies["assets/mission_active.json#owned-members"] = members
        for (const missionId of members) {
            take("assets/mission_active.json", [missionId])
            take("assets/mission_active_reward.json", [missionId])
        }
    } else if (row.type === "multi_special_exchange_campaign") {
        const raw = readFileSync(path.join(root, "src/lib/multi-special-exchange.ts"), "utf8")
        const allocation = [...raw.matchAll(/\[(\d+),\s*\{\s*campaignId:\s*(\d+),\s*ticketItemIds:\s*\[([\d,\s]+)\]\s*\}\]/g)]
            .find(match => match[1] === id && match[2] === id)?.[3].split(",").map(value => Number(value.trim()))
        dependencies.allocation = allocation ?? null
        for (const ticket of allocation ?? []) {
            const characters: number[] = take("assets/multi_special_exchange_campaign_character.json", [String(ticket)]) ?? []
            for (const source of ["assets/item_ids.json", "assets/item_ids_rank_p5b.json"])
                dependencies[`${source}#member:${ticket}`] = read(source).includes(ticket)
            for (const character of characters) for (const source of ["assets/character.json", "assets/character_rank_p5b.json"])
                take(source, [String(character)])
        }
    } else return null
    if (!Object.keys(dependencies).length) return null
    const rowLoaders = row.type === "active_mission_event" ? [...loaders,
        "src/lib/mission/active-master-data.ts", "src/lib/mission/active-core.ts",
        "src/lib/mission/active-reconciliation.ts", "src/lib/mission/rewards.ts"] : loaders
    const identities = Object.fromEntries(rowLoaders.map(source => {
        const key = `loader:${source}`
        if (!tables.has(key)) tables.set(key, createHash("sha256").update(readFileSync(path.join(root, source))).digest("hex"))
        return [source, tables.get(key) as string]
    }))
    return { dependencies, loaders: identities, digest: exactDefinitionHash({ key: row.key, dependencies }) }
}
export function matchExactDefinition(row: ExactDefinitionRow, root: string): { digest: string; matchesCatalog: boolean } | null {
    const evidence = row.exactDefinitionEvidence
    const currentParent = row.currentParentDefinitionEvidence
    if (!evidence && !currentParent) return null
    try {
        // Like imported JSON masters, these identities remain pinned for this process.
        // Resource/master deployments require a process restart, not mixed live file replacement.
        if (!runtimeInputs.has(root)) runtimeInputs.set(root, new Map())
        const captured = captureExactDefinition(row, root, runtimeInputs.get(root))
        const digest = exactDefinitionHash({ key: row.key, dependencyDigest: captured?.digest, loaders: captured?.loaders })
        const identity = evidence ?? currentParent!
        const common = !!captured && identity.schemaVersion === 1 && identity.key === row.key
            && /^[a-f0-9]{64}$/.test(identity.previousServerDefinitionDigest)
            && identity.definitionDigest === row.definitionDigest && identity.previousServerDefinitionDigest === row.serverDefinitionDigest
            && identity.dependencyDigest === captured.digest
            && stableDefinitionJson(identity.loaders) === stableDefinitionJson(captured.loaders)
        const reviewedParent = !!currentParent && row.key === "rush_event:700099"
            && stableDefinitionJson(currentParent.reviewedExistingChildren)
                === stableDefinitionJson([...Array.from({ length: 17 }, (_, index) => String(9700101 + index)), "9700199"])
            && stableDefinitionJson(currentParent.newUncataloguedChildren)
                === stableDefinitionJson(Array.from({ length: 9 }, (_, index) => String(9700121 + index)))
        return { digest, matchesCatalog: common && (evidence?.oldDefinitionMatched === true || reviewedParent) }
    } catch { return { digest: exactDefinitionHash({ key: row.key, unavailable: true }), matchesCatalog: false } }
}
