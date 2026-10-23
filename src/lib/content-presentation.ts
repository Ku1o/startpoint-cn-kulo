import data from "../../assets/content_presentation.json"
import { createHash } from "node:crypto"
import { readFileSync, statSync } from "node:fs"
import path from "node:path"
import { Open } from "unzipper"

export const CONTENT_PRESENTATION_GROUPS = [
    { key: "events", label: "活动" }, { key: "gacha", label: "卡池" },
    { key: "missions", label: "任务与通行证" }, { key: "exchange", label: "兑换与奖励箱" },
] as const
export type ContentPresentationGroup = typeof CONTENT_PRESENTATION_GROUPS[number]["key"]
interface PresentationRow { title: string; type: string; images: string[]; subtitle?: string; nativeName?: string; gachaPrizeKind?: number | null;
    displayTitleSource?: { kind: string };
    imageMissingReason?: string; titleSource: { kind: string; parentKey?: string } }
interface Resource { archive: string; member: string; sha256: string; bytes: number; width: number; height: number }
const manifest = data as unknown as { source: { manifestSha256: string }; rows: Record<string, PresentationRow>; resources: Record<string, Resource> }
const lookup = (key: string): PresentationRow | undefined => Object.prototype.hasOwnProperty.call(manifest.rows, key) ? manifest.rows[key] : undefined
/** Shared server labels for rows and filter options; consumers do not maintain a second type dictionary. */
export const CONTENT_PRESENTATION_TYPE_LABELS: Readonly<Record<string, string>> = {
    gacha: "扭蛋卡池",
    advent_event: "讨伐活动", ranking_event: "竞速排行活动", story_event: "剧情活动", daily_week_event: "培育素材迷宫",
    challenge_dungeon_event: "崩坏域与宝物域", daily_exp_mana_event: "经验与玛纳关卡", world_story_event: "复刻剧情活动",
    tower_dungeon_event: "幽玄域", expert_single_event: "单人挑战", carnival_event: "嘉年华活动", raid_event: "团本活动",
    rush_event: "连战活动", solo_time_attack_event: "极时试炼", hard_multi_event: "共同决战", score_attack_event: "无限演武",
    active_mission_event: "成长与活动任务", collect_item_event: "收集任务", pass_card_event: "修行通行证", box_gacha: "奖励箱池",
    multi_special_exchange_campaign: "共同自选角色", special_exchange_campaign: "自选兑换", start_dash_exchange_campaign: "新手自选兑换",
    general_shop: "普通商店商品", treasure_shop: "宝物兑换商品", star_grain_shop: "星粒兑换商品", boss_coin_shop: "领主兑换商品",
    event_item_shop: "活动兑换商品", mission_regular: "常规任务", mission_daily: "每日任务", mission_event: "活动任务",
}
function groupFor(type: string): ContentPresentationGroup {
    if (type === "gacha") return "gacha"
    if (["active_mission_event", "collect_item_event", "pass_card_event"].includes(type) || type.startsWith("mission_")) return "missions"
    if (type === "box_gacha" || type.endsWith("_campaign") || type.endsWith("_shop")) return "exchange"
    return "events"
}
export function getContentPresentation(row: string | { key: string; type?: string; name?: string }): {
    title: string; group: ContentPresentationGroup; groupLabel: string; typeLabel: string;
    imageUrl: string | null; imageFallbackUrl: string | null; imageAlt: string; imageStatus: "available" | "missing"; imageMissingReason: string | null;
    subtitle?: string; originalTitle?: string;
} {
    const key = typeof row === "string" ? row : row.key, native = lookup(key)
    const type = native?.type ?? (typeof row === "string" ? key.split(":")[0] : row.type ?? key.split(":")[0])
    const group = groupFor(type), title = native?.title ?? (typeof row === "string" ? key : row.name || key)
    const hasImage = !!native?.images.some(logical => !!manifest.resources[logical])
    const originalUrl = hasImage ? `/api/content/${encodeURIComponent(key)}/image` : null
    const thumbnail = hasImage ? thumbnailForKey(key) : null
    return { title, group, groupLabel: CONTENT_PRESENTATION_GROUPS.find(value => value.key === group)!.label,
        typeLabel: type === "gacha" ? native?.gachaPrizeKind === 0 ? "角色扭蛋" : native?.gachaPrizeKind === 1 ? "装备扭蛋" : "扭蛋卡池"
            : CONTENT_PRESENTATION_TYPE_LABELS[type] ?? "其他内容",
        imageUrl: thumbnail ? `/api/content/thumbnail/${thumbnail.hash}.webp` : originalUrl,
        imageFallbackUrl: thumbnail ? originalUrl : null,
        imageAlt: `${title}游戏配图`, imageStatus: hasImage ? "available" : "missing",
        imageMissingReason: hasImage ? null : native?.imageMissingReason ?? "游戏资源未提供可用的独立横幅",
        ...(native?.subtitle ? { subtitle: native.subtitle } : {}),
        ...(native?.displayTitleSource && native.nativeName ? { originalTitle: native.nativeName } : {}) }
}

const root = path.resolve(__dirname, "../.."), salt = "K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy"
const maxImageBytes = 8 * 1024 * 1024, maxCachedBytes = 32 * 1024 * 1024
type ZipEntry = Awaited<ReturnType<typeof Open.file>>["files"][number]
type Image = { bytes: Buffer; contentType: "image/png"; etag: string }
type Thumbnail = { bytes: Buffer; contentType: "image/webp"; etag: string }
interface ThumbnailIndex {
    schemaVersion: number
    source: { manifestSha256: string; presentationSha256: string }
    rows: Record<string, { image: string; sourceLogical: string; sourceRawSha256: string; sourcePngSha256: string }>
    images: Record<string, { file: string; bytes: number; width: number; height: number }>
}
const hashPattern = /^[a-f0-9]{64}$/
const presentationSha256 = createHash("sha256").update(readFileSync(path.join(root, "assets/content_presentation.json"))).digest("hex")
const thumbnailRoot = path.join(root, "assets/content_thumbnails")
const thumbnailIndex: ThumbnailIndex | null = (() => {
    try {
        const value = JSON.parse(readFileSync(path.join(thumbnailRoot, "index.json"), "utf8")) as ThumbnailIndex
        return value.schemaVersion === 1 && value.source?.presentationSha256 === presentationSha256
            && hashPattern.test(value.source.manifestSha256) && value.rows && value.images ? value : null
    } catch { return null }
})()
function thumbnailForKey(key: string) {
    const index = thumbnailIndex, native = lookup(key)
    if (!index || !native || !Object.prototype.hasOwnProperty.call(index.rows, key)) return null
    const row = index.rows[key]
    if (!row || !hashPattern.test(row.image) || !hashPattern.test(row.sourcePngSha256)
        || !native.images.includes(row.sourceLogical) || manifest.resources[row.sourceLogical]?.sha256 !== row.sourceRawSha256) return null
    const image = index.images[row.image]
    if (!image || image.file !== `${row.image}.webp` || !Number.isSafeInteger(image.bytes) || image.bytes <= 0 || image.bytes > maxImageBytes
        || !Number.isSafeInteger(image.width) || image.width <= 0 || image.width > 960
        || !Number.isSafeInteger(image.height) || image.height <= 0 || image.height > 360) return null
    try { if (chain().digest !== index.source.manifestSha256) return null } catch { return null }
    return { hash: row.image, image }
}
const directories = new Map<string, Promise<Map<string, ZipEntry>>>()
const images = new Map<string, Image | Thumbnail>()
let imageBytes = 0
function archivePath(relative: string): string | null {
    if (/^assets\/asset-patch\/active\/[a-zA-Z0-9][a-zA-Z0-9._-]*\.zip$/.test(relative)) return path.join(root, relative)
    if (!/^\.cdn\/cn\/archive-(?:common|android)-(?:full|diff)\/[a-zA-Z0-9][a-zA-Z0-9._-]*\.zip$/.test(relative)) return null
    const configured = process.env.CDN_DIR || ".cdn", cdn = path.isAbsolute(configured) ? configured : path.join(root, configured)
    return path.join(cdn, relative.slice(".cdn/".length))
}
async function exactMember(relative: string, member: string): Promise<Buffer | null> {
    const file = archivePath(relative)
    if (!file) return null
    let index = directories.get(file)
    if (!index) {
        index = Open.file(file).then(directory => {
            const result = new Map<string, ZipEntry>()
            for (const entry of directory.files) {
                if (result.has(entry.path)) throw new Error("Duplicate image archive member")
                result.set(entry.path, entry)
            }
            return result
        })
        directories.set(file, index)
        if (directories.size > 64) directories.delete(directories.keys().next().value!)
    }
    try {
        const entry = (await index).get(member)
        if (!entry || entry.type !== "File" || entry.uncompressedSize > maxImageBytes || entry.compressedSize > maxImageBytes) return null
        const bytes = await entry.buffer()
        return bytes.length <= maxImageBytes ? bytes : null
    } catch { directories.delete(file); return null }
}
function png(bytes: Buffer): Buffer | null {
    const stored = Buffer.from([137, 112, 110, 103, 13, 10, 26, 10]), real = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])
    if (bytes.length < 33 || (!bytes.subarray(0, 8).equals(stored) && !bytes.subarray(0, 8).equals(real))) return null
    if (bytes.toString("ascii", 12, 16) !== "IHDR" || bytes.readUInt32BE(8) !== 13) return null
    const width = bytes.readUInt32BE(16), height = bytes.readUInt32BE(20)
    if (width < 1 || height < 1 || width > 16384 || height > 16384) return null
    let at = 8, idat = false, ended = false
    while (at + 12 <= bytes.length) {
        const length = bytes.readUInt32BE(at), end = at + 12 + length
        if (end > bytes.length) return null
        const type = bytes.toString("ascii", at + 4, at + 8)
        if (type === "IDAT") idat = true
        if (type === "IEND") { ended = length === 0 && end === bytes.length; break }
        at = end
    }
    if (!idat || !ended) return null
    return Buffer.concat([real, bytes.subarray(8)])
}
type Chain = { digest: string; active: string[] }
let chainCache: Chain | null = null
let chainStat = ""
function chain(): Chain {
    const file = path.join(root, "assets/asset-patch/manifest.json"), info = statSync(file, { bigint: true })
    const signature = `${info.dev}:${info.ino}:${info.size}:${info.mtimeNs}:${info.ctimeNs}`
    if (chainCache && chainStat === signature) return chainCache
    const bytes = readFileSync(path.join(root, "assets/asset-patch/manifest.json")), digest = createHash("sha256").update(bytes).digest("hex")
    if (chainCache?.digest === digest) { chainStat = signature; return chainCache }
    const source = JSON.parse(bytes.toString("utf8")) as { patches: Array<{ enabled?: boolean; archive?: string; chain?: string[]; archive_integrity?: Array<{ name: string }> }> }
    const active = source.patches.filter(patch => patch.enabled).flatMap(patch =>
        patch.chain ?? (patch.archive ? [patch.archive] : patch.archive_integrity?.map(value => value.name) ?? []))
        .map(name => `assets/asset-patch/active/${name}`)
    if (active.some(name => !archivePath(name))) throw new Error("Invalid presentation resource chain")
    chainCache = { digest, active }; chainStat = signature; directories.clear(); images.clear(); imageBytes = 0
    return chainCache
}

/** Only a manifest parent key is accepted. The admin route owns authentication; no caller-supplied resource path is used. */
export async function readContentPresentationImage(key: string): Promise<Image | null> {
    const row = lookup(key)
    if (!row) return null
    try {
        const current = chain()
        for (const logical of row.images) {
            const receipt = manifest.resources[logical]
            if (!receipt) continue
            const cacheKey = `${current.digest}:${logical}`, cached = images.get(cacheKey)
            if (cached?.contentType === "image/png") { images.delete(cacheKey); images.set(cacheKey, cached); return cached }
            const hash = createHash("sha1").update(logical + salt).digest("hex"), member = `production/upload/${hash.slice(0, 2)}/${hash.slice(2)}`
            if (receipt.member !== member) continue
            let raw: Buffer | null = null
            if (current.digest === manifest.source.manifestSha256) {
                raw = await exactMember(receipt.archive, member)
                if (raw && createHash("sha256").update(raw).digest("hex") !== receipt.sha256) raw = null
            } else {
                for (const archive of [...current.active].reverse()) { raw = await exactMember(archive, member); if (raw) break }
                if (!raw && receipt.archive.startsWith(".cdn/")) raw = await exactMember(receipt.archive, member)
            }
            if (!raw) continue
            const decoded = png(raw)
            if (!decoded) continue
            const image: Image = { bytes: decoded, contentType: "image/png", etag: `"${createHash("sha256").update(decoded).digest("hex")}"` }
            while (imageBytes + decoded.length > maxCachedBytes && images.size) {
                const oldest = images.keys().next().value!, previous = images.get(oldest)!
                imageBytes -= previous.bytes.length; images.delete(oldest)
            }
            images.set(cacheKey, image); imageBytes += decoded.length
            return image
        }
        return null
    } catch { return null }
}

/** Fixed, content-hashed offline thumbnails only; the admin route owns authentication. */
export function readContentPresentationThumbnail(hash: string, isParentAllowed: (key: string) => boolean = () => true): Thumbnail | null {
    if (!hashPattern.test(hash) || !thumbnailIndex) return null
    const key = Object.keys(thumbnailIndex.rows).find(key => thumbnailIndex.rows[key]?.image === hash && isParentAllowed(key) && thumbnailForKey(key))
    const selected = key ? thumbnailForKey(key) : null
    if (!selected) return null
    const cacheKey = `thumbnail:${hash}`, cached = images.get(cacheKey)
    if (cached?.contentType === "image/webp") { images.delete(cacheKey); images.set(cacheKey, cached); return cached }
    try {
        const file = path.join(thumbnailRoot, selected.image.file)
        if (statSync(file).size !== selected.image.bytes) return null
        const bytes = readFileSync(file)
        if (bytes.toString("ascii", 0, 4) !== "RIFF" || bytes.toString("ascii", 8, 12) !== "WEBP"
            || createHash("sha256").update(bytes).digest("hex") !== hash) return null
        const image: Thumbnail = { bytes, contentType: "image/webp", etag: `"${hash}"` }
        while (imageBytes + bytes.length > maxCachedBytes && images.size) {
            const oldest = images.keys().next().value!, previous = images.get(oldest)!
            imageBytes -= previous.bytes.length; images.delete(oldest)
        }
        images.set(cacheKey, image); imageBytes += bytes.length
        return image
    } catch { return null }
}
