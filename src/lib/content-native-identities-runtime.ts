import { createHash } from "node:crypto"
import { closeSync, fstatSync, openSync, readFileSync, readSync, statSync } from "node:fs"
import path from "node:path"
import { CONTENT_NATIVE_IDENTITIES_IDENTITY } from "./content-native-identities-identity"

export const CONTENT_NATIVE_IDENTITY_SOURCES = [
    "assets/content_history_quest_rules.json", "assets/content_history_shop_rules.json", "assets/content_catalog.json",
    "assets/asset-patch/manifest.json", "src/lib/content-operations.ts", "src/lib/content-quest-rules.ts",
    "src/lib/assets.ts", "src/lib/stamina-cost.ts", "src/lib/content-shop-rules.ts", "src/lib/shop-quota.ts",
    "src/lib/types/shop.ts", "src/lib/content-native-identities-runtime.ts",
] as const
export interface ContentNativeIdentitiesIdentity {
    readonly schemaVersion: 1
    readonly indexSha256: string
    readonly sources: Readonly<Record<string, { readonly sha256: string; readonly bytes: number }>>
}
const hashPattern = /^[a-f0-9]{64}$/, keyPattern = /^[a-z_]+:\d+$/
function fail(message: string): never { throw new Error("Native content identity index rejected: " + message) }
function check(value: unknown, message: string): asserts value { if (!value) fail(message) }
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value)
function fields(value: Record<string, unknown>, names: readonly string[], message: string): void {
    check(Object.keys(value).sort().join("|") === [...names].sort().join("|"), message)
}
const signature = (value: ReturnType<typeof fstatSync>) => `${value.dev}:${value.ino}:${value.size}:${value.mtimeMs}:${value.ctimeMs}`
function streamIdentity(file: string): { sha256: string; bytes: number } {
    const fd = openSync(file, "r"), block = Buffer.allocUnsafe(65536), hash = createHash("sha256")
    try {
        const before = fstatSync(fd)
        check(before.isFile() && before.size > 0 && before.size <= 256 * 1024 * 1024, "invalid source size")
        let count = 0, total = 0
        while ((count = readSync(fd, block, 0, block.length, null))) { hash.update(block.subarray(0, count)); total += count }
        check(total === before.size && signature(fstatSync(fd)) === signature(before) && signature(statSync(file)) === signature(before), "source changed during verification")
        return { sha256: hash.digest("hex"), bytes: total }
    } finally { closeSync(fd) }
}

/** Precomputed original native identities only. Every call owns fresh Maps;
 * this does not substitute, trim or mutate either business-rule JSON module.
 * Production uses the generated anchor; options support isolated fixtures.
 */
export function loadContentNativeIdentities(options: {
    root?: string; identity?: ContentNativeIdentitiesIdentity
} = {}): { quests: Map<string, string>; shops: Map<string, string> } {
    const root = path.resolve(options.root ?? path.resolve(__dirname, "../.."))
    const identity = options.identity ?? CONTENT_NATIVE_IDENTITIES_IDENTITY
    check(identity.schemaVersion === 1 && hashPattern.test(identity.indexSha256) && record(identity.sources), "invalid generated anchor")
    fields(identity.sources, CONTENT_NATIVE_IDENTITY_SOURCES, "invalid source anchor scope")
    const file = path.join(root, "assets/content_native_identities_runtime.json"), before = statSync(file)
    check(before.isFile() && before.size > 0 && before.size <= 4 * 1024 * 1024, "invalid index size")
    const body = readFileSync(file)
    check(createHash("sha256").update(body).digest("hex") === identity.indexSha256, "index SHA mismatch")
    check(signature(statSync(file)) === signature(before), "index changed during verification")
    let parsed: unknown
    try { parsed = JSON.parse(body.toString("utf8")) } catch { fail("invalid index JSON") }
    check(record(parsed), "index must be an object")
    fields(parsed, ["schemaVersion", "sources", "quests", "shops", "counts"], "unsupported index fields")
    check(parsed.schemaVersion === 1 && record(parsed.sources) && record(parsed.counts), "unsupported index schema")
    fields(parsed.sources, CONTENT_NATIVE_IDENTITY_SOURCES, "invalid source scope")
    for (const source of CONTENT_NATIVE_IDENTITY_SOURCES) {
        const expected = identity.sources[source], claimed = parsed.sources[source]
        check(record(expected) && hashPattern.test(expected.sha256) && Number.isSafeInteger(expected.bytes) && expected.bytes > 0, "invalid source anchor")
        check(record(claimed), "invalid source record")
        fields(claimed, ["sha256", "bytes"], "invalid source record fields")
        check(claimed.sha256 === expected.sha256 && claimed.bytes === expected.bytes, "source anchor mismatch: " + source)
        const actual = streamIdentity(path.join(root, source))
        check(actual.sha256 === expected.sha256 && actual.bytes === expected.bytes, "source identity mismatch: " + source)
    }
    const decode = (value: unknown, name: string): Map<string, string> => {
        check(Array.isArray(value) && value.length > 0 && value.length <= 30000, "invalid " + name + " table")
        const result = new Map<string, string>()
        for (const entry of value) {
            check(Array.isArray(entry) && entry.length === 2 && typeof entry[0] === "string" && keyPattern.test(entry[0])
                && typeof entry[1] === "string" && hashPattern.test(entry[1]), "invalid " + name + " entry")
            check(!result.has(entry[0]), "duplicate " + name + " identity")
            result.set(entry[0], entry[1])
        }
        return result
    }
    const quests = decode(parsed.quests, "quests"), shops = decode(parsed.shops, "shops")
    fields(parsed.counts, ["quests", "shops"], "invalid count scope")
    check(parsed.counts.quests === quests.size && parsed.counts.shops === shops.size, "identity count mismatch")
    return { quests, shops }
}
