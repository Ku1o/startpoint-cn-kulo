import { createHash } from "node:crypto"
import { readFileSync, realpathSync, statSync } from "node:fs"
import path from "node:path"

const HASH = /^[a-f0-9]{64}$/
const KEY = /^[a-z][a-z0-9_]{0,63}$/
const RESOURCE = /^[a-zA-Z0-9_/-]+(?:\.[a-zA-Z0-9_]+)*$/
export function townThemeHash(bytes: string | Buffer): string { return createHash("sha256").update(bytes).digest("hex") }
export function townThemeRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value)
}
function exact(value: Record<string, unknown>, keys: string[]): boolean {
    return Object.keys(value).length === keys.length && keys.every(key => Object.prototype.hasOwnProperty.call(value, key))
}
function resource(value: unknown, prefix?: string): value is string {
    return typeof value === "string" && value.length <= 240 && RESOURCE.test(value)
        && !value.startsWith("/") && !value.split("/").some(part => part === ".." || part === "." || part === "")
        && (!prefix || value.startsWith(prefix))
}
function text(value: unknown, max: number): value is string {
    return typeof value === "string" && value.trim().length > 0 && value.length <= max && !/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(value)
}
function readBounded(root: string, relative: string, max: number): Buffer {
    const base = realpathSync(root), target = realpathSync(path.join(root, relative))
    if (!target.startsWith(base + path.sep) || !statSync(target).isFile() || statSync(target).size > max) throw new Error("invalid_file")
    const bytes = readFileSync(target)
    if (bytes.length > max) throw new Error("invalid_file")
    return bytes
}
/** WebP container dimensions, checked before serving the already hashed bytes. */
function webpSize(bytes: Buffer): [number, number] {
    if (bytes.length < 30 || bytes.toString("ascii", 0, 4) !== "RIFF" || bytes.toString("ascii", 8, 12) !== "WEBP"
        || bytes.readUInt32LE(4) + 8 !== bytes.length) throw new Error("invalid_thumbnail")
    const kind = bytes.toString("ascii", 12, 16)
    if (kind === "VP8X") return [1 + bytes.readUIntLE(24, 3), 1 + bytes.readUIntLE(27, 3)]
    if (kind === "VP8L" && bytes[20] === 0x2f) {
        const bits = bytes.readUInt32LE(21)
        return [(bits & 0x3fff) + 1, ((bits >>> 14) & 0x3fff) + 1]
    }
    if (kind === "VP8 " && bytes[23] === 0x9d && bytes[24] === 1 && bytes[25] === 0x2a)
        return [bytes.readUInt16LE(26) & 0x3fff, bytes.readUInt16LE(28) & 0x3fff]
    throw new Error("invalid_thumbnail")
}
export interface TownTheme {
    readonly id: string; readonly name: string; readonly description: string; readonly nativeTownContentId: number
    readonly thumbnail: { readonly file: string; readonly sha256: string; readonly width: number; readonly height: number }
    readonly nativeRow: readonly string[]; readonly resourceVersion: string
    readonly originalPeriods?: readonly TownThemePeriod[]
}
export interface TownThemePeriod { nativeTownContentId: number; kind: "event" | "annual"; start: string; end: string }
export interface TownThemeListing {
    id: string; name: string; description: string; nativeTownContentId: number; thumbnailUrl: string
    originalPeriods: TownThemePeriod[]; annualEligible: boolean
}
interface ResourceIdentity { path: string; sha256: string; size: number }

function periodTime(value: unknown, annual: boolean): value is string {
    if (typeof value !== "string") return false
    const match = (annual ? /^(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/ : /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/).exec(value)
    if (!match) return false
    const fields = match.slice(1).map(Number), year = annual ? 1970 : fields.shift()!
    const [month, day, hour, minute, second] = fields
    if (year < 1 || month < 1 || month > 12 || day < 1 || hour > 23 || minute > 59 || second > 59) return false
    const date = new Date(0)
    date.setUTCFullYear(year, month - 1, day); date.setUTCHours(hour, minute, second, 0)
    return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
}
function nativePeriod(row: readonly string[], nativeTownContentId: number, allowLegacyEmpty: boolean): TownThemePeriod | undefined {
    const kind = row[1] === "1" ? "event" : row[1] === "2" ? "annual" : null
    if (!kind) return undefined
    const start = row[kind === "event" ? 2 : 4], end = row[kind === "event" ? 3 : 5]
    // Compatibility with old offline catalogs which did not capture date columns.
    if (allowLegacyEmpty && !start && !end) return undefined
    if (!periodTime(start, kind === "annual") || !periodTime(end, kind === "annual") || (kind === "event" && start > end)) throw new Error("invalid_original_period")
    return { nativeTownContentId, kind, start, end }
}
function originalPeriods(value: Record<string, unknown>, proof: Record<string, unknown>): readonly TownThemePeriod[] {
    const legacy = !Object.prototype.hasOwnProperty.call(value, "originalPeriods")
    const canonical = nativePeriod(value.nativeRow as string[], value.nativeTownContentId as number, legacy)
    if (legacy) {
        if (proof.originalPeriodsSha256 !== undefined) throw new Error("missing_original_periods")
        return Object.freeze(canonical ? [Object.freeze(canonical)] : [])
    }
    const periods = value.originalPeriods
    if (!Array.isArray(periods) || periods.length > 1000 || typeof proof.originalPeriodsSha256 !== "string"
        || !HASH.test(proof.originalPeriodsSha256) || townThemeHash(JSON.stringify(periods)) !== proof.originalPeriodsSha256) throw new Error("invalid_original_period_evidence")
    let previousId = 0
    const result: TownThemePeriod[] = []
    for (const entry of periods) {
        if (!townThemeRecord(entry) || !exact(entry, ["nativeTownContentId", "kind", "start", "end"])
            || !Number.isSafeInteger(entry.nativeTownContentId) || (entry.nativeTownContentId as number) <= previousId || (entry.nativeTownContentId as number) > 2147483647
            || !["event", "annual"].includes(entry.kind as string) || !periodTime(entry.start, entry.kind === "annual")
            || !periodTime(entry.end, entry.kind === "annual") || (entry.kind === "event" && entry.start > entry.end)) throw new Error("invalid_original_period")
        previousId = entry.nativeTownContentId as number
        result.push(Object.freeze({ nativeTownContentId: previousId, kind: entry.kind as "event" | "annual", start: entry.start, end: entry.end }))
    }
    if (canonical && !result.some(entry => entry.nativeTownContentId === canonical.nativeTownContentId && entry.kind === canonical.kind
        && entry.start === canonical.start && entry.end === canonical.end)) throw new Error("missing_canonical_period")
    return Object.freeze(result)
}

/** A deployment-time verified catalog. No archives, CDN scans or reads on player requests. */
export class TownThemeCatalog {
    private readonly rows: ReadonlyMap<string, TownTheme>
    private readonly images: ReadonlyMap<string, Buffer>
    private readonly themeDigests: ReadonlyMap<string, string>
    constructor(readonly digest: string, themes: readonly TownTheme[] = [], images: ReadonlyMap<string, Buffer> = new Map(), readonly degradedReason: string | null = null,
        resources: ReadonlyMap<string, readonly ResourceIdentity[]> = new Map()) {
        this.rows = new Map(themes.map(theme => [theme.id, theme])); this.images = new Map(images)
        // Display metadata, thumbnail, manifest and version changes do not alter the selected native theme.
        // Only verified, loader-captured native/resource identities can establish a manual binding.
        this.themeDigests = new Map(themes.flatMap(theme => {
            const identities = resources.get(theme.id)
            return identities ? [[theme.id, townThemeHash(JSON.stringify({ nativeTownContentId: theme.nativeTownContentId,
                nativeRow: theme.nativeRow, resources: identities.map(entry => ({ path: entry.path, sha256: entry.sha256, size: entry.size }))
                    .sort((left, right) => left.path < right.path ? -1 : left.path > right.path ? 1 : 0) }))] as const] : []
        }))
    }
    find(id: string): TownTheme | undefined { return this.rows.get(id) }
    themeDigest(id: string): string | undefined { return this.themeDigests.get(id) }
    thumbnail(hash: string): Buffer | undefined { return this.images.get(hash) }
    listing(): TownThemeListing[] {
        return [...this.rows.values()].map(row => ({ id: row.id, name: row.name, description: row.description,
            nativeTownContentId: row.nativeTownContentId, thumbnailUrl: `/api/server/town-theme/thumbnails/${row.thumbnail.sha256}.webp`,
            originalPeriods: (row.originalPeriods ?? []).map(period => ({ ...period })), annualEligible: row.nativeRow[1] !== "0" }))
    }
}

/** Receipt is generated by the offline resource verifier, never by an HTTP writer. */
export function loadTownThemeCatalog(assetRoot = path.resolve(__dirname, "../../assets")): TownThemeCatalog {
    let digest = ""
    try {
        const bytes = readBounded(assetRoot, "town_themes.json", 2 * 1024 * 1024)
        digest = townThemeHash(bytes)
        const catalog: unknown = JSON.parse(bytes.toString("utf8"))
        if (!townThemeRecord(catalog) || !exact(catalog, ["schemaVersion", "themes"]) || catalog.schemaVersion !== 1
            || !Array.isArray(catalog.themes) || catalog.themes.length < 1 || catalog.themes.length > 100) throw new Error("invalid_catalog")
        const receiptBytes = readBounded(assetRoot, "town_theme_resource_receipt.json", 4 * 1024 * 1024)
        const receipt: unknown = JSON.parse(receiptBytes.toString("utf8")), receiptDigest = townThemeHash(receiptBytes)
        if (!townThemeRecord(receipt) || receipt.schemaVersion !== 1 || typeof receipt.manifestSha256 !== "string" || !HASH.test(receipt.manifestSha256)
            || typeof receipt.resourceVersion !== "string" || !/^\d+\.\d+\.\d+$/.test(receipt.resourceVersion)
            || !Array.isArray(receipt.themes) || receipt.themes.length !== catalog.themes.length
            || receipt.manifestSha256 !== townThemeHash(readBounded(assetRoot, "asset-patch/manifest.json", 16 * 1024 * 1024))) throw new Error("invalid_resource_receipt")
        const receipts = new Map<string, Record<string, unknown>>()
        for (const entry of receipt.themes) {
            if (!townThemeRecord(entry) || typeof entry.id !== "string" || receipts.has(entry.id)) throw new Error("invalid_resource_receipt")
            receipts.set(entry.id, entry)
        }
        const themes: TownTheme[] = [], ids = new Set<string>(), nativeIds = new Set<number>(), images = new Map<string, Buffer>()
        const semanticResources = new Map<string, ResourceIdentity[]>()
        for (const value of catalog.themes) {
            if (!townThemeRecord(value) || !exact(value, ["id", "name", "description", "nativeTownContentId", "thumbnail", "nativeRow", "resourceVersion", "resourceEvidence",
                ...(Object.prototype.hasOwnProperty.call(value, "originalPeriods") ? ["originalPeriods"] : [])])
                || typeof value.id !== "string" || !KEY.test(value.id) || ids.has(value.id) || !text(value.name, 80) || !text(value.description, 500)
                || !Number.isSafeInteger(value.nativeTownContentId) || (value.nativeTownContentId as number) < 1 || (value.nativeTownContentId as number) > 2147483647
                || nativeIds.has(value.nativeTownContentId as number) || typeof value.resourceVersion !== "string" || !/^\d+\.\d+\.\d+$/.test(value.resourceVersion)
                || !Array.isArray(value.nativeRow) || value.nativeRow.length !== 20 || value.nativeRow.some(cell => typeof cell !== "string" || cell.length > 240)
                || !text(value.nativeRow[0], 64) || !["0", "1", "2"].includes(value.nativeRow[1])
                || !resource(value.nativeRow[6], "town/background/") || !resource(value.nativeRow[7], "town/background/")
                || (value.nativeRow[8] !== "(None)" && !resource(value.nativeRow[8], "town/background/"))
                || (value.nativeRow[9] !== "(None)" && !resource(value.nativeRow[9], "town/particle/")) || !resource(value.nativeRow[19], "bgm/")) throw new Error("invalid_theme")
            const thumb = value.thumbnail, proof = value.resourceEvidence, verified = receipts.get(value.id)
            if (!townThemeRecord(thumb) || !exact(thumb, ["file", "sha256", "width", "height"]) || typeof thumb.sha256 !== "string" || !HASH.test(thumb.sha256)
                || thumb.file !== `${thumb.sha256}.webp` || ![thumb.width, thumb.height].every(n => Number.isSafeInteger(n) && (n as number) >= 1 && (n as number) <= 1024)
                || !townThemeRecord(proof) || !exact(proof, ["schemaVersion", "receiptFile", "receiptSha256"]) || proof.schemaVersion !== 1
                || proof.receiptFile !== "town_theme_resource_receipt.json" || proof.receiptSha256 !== receiptDigest
                || !verified || verified.verified !== true || verified.nativeTownContentId !== value.nativeTownContentId
                || verified.nativeRowSha256 !== townThemeHash(JSON.stringify(value.nativeRow)) || receipt.resourceVersion !== value.resourceVersion
                || !Array.isArray(verified.resources) || verified.resources.length < 3 || verified.resources.length > 100) throw new Error("invalid_theme_evidence")
            const periods = originalPeriods(value, verified)
            const resources = new Set<string>()
            const identities: ResourceIdentity[] = []
            for (const entry of verified.resources) {
                if (!townThemeRecord(entry) || !resource(entry.path) || resources.has(entry.path) || typeof entry.sha256 !== "string" || !HASH.test(entry.sha256)
                    || !Number.isSafeInteger(entry.size) || (entry.size as number) < 1 || (entry.size as number) > 128 * 1024 * 1024) throw new Error("invalid_resource_identity")
                resources.add(entry.path)
                identities.push({ path: entry.path, sha256: entry.sha256, size: entry.size as number })
            }
            for (const index of [6, 7, 8]) if (value.nativeRow[index] !== "(None)" && !resources.has(`${value.nativeRow[index]}.png`)) throw new Error("missing_resource_identity")
            if (!resources.has(`${value.nativeRow[19]}.mp3`)) throw new Error("missing_resource_identity")
            const particle = value.nativeRow[9]
            if (particle !== "(None)" && ["parts", "timeline"].some(kind => !resources.has(`${particle}.${kind}.amf3.deflate`))) throw new Error("missing_particle_identity")
            let image = images.get(thumb.sha256)
            if (!image) { image = readBounded(assetRoot, `town_theme_thumbnails/${thumb.file}`, 512 * 1024); images.set(thumb.sha256, image) }
            const size = webpSize(image)
            if (townThemeHash(image) !== thumb.sha256 || size[0] !== thumb.width || size[1] !== thumb.height) throw new Error("invalid_thumbnail_identity")
            ids.add(value.id); nativeIds.add(value.nativeTownContentId as number)
            semanticResources.set(value.id, identities)
            themes.push(Object.freeze({ id: value.id, name: value.name, description: value.description, nativeTownContentId: value.nativeTownContentId as number,
                thumbnail: Object.freeze({ file: thumb.file as string, sha256: thumb.sha256, width: thumb.width as number, height: thumb.height as number }),
                nativeRow: Object.freeze([...value.nativeRow]), resourceVersion: value.resourceVersion, originalPeriods: periods }))
        }
        return new TownThemeCatalog(digest, themes, images, null, semanticResources)
    } catch {
        // Never expose filesystem paths or stack traces to players/admins and never repair source bytes implicitly.
        return new TownThemeCatalog(digest, [], new Map(), "town_theme_catalog_unavailable_or_invalid")
    }
}
