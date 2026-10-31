import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import path from "node:path"
import { readWinningContentResourceHashesSync } from "./content-definition-evidence"

export interface ContentResourceSource {
    schemaVersion: 1
    source: { assetVersion: string; manifestSha256: string }
    resources: Record<string, { archive: string; sha256: string }>
}
const hashPattern = /^[a-f0-9]{64}$/
const archivePattern = /^(?:\.cdn\/cn\/archive-common-(?:full|diff)|assets\/asset-patch\/active)\/[a-zA-Z0-9][a-zA-Z0-9._-]*\.zip$/

/** Only tables used by ownership, eligibility and economy define this identity. */
export function contentBusinessResourcesSync(root: string): Record<string, { archive: string }> {
    const catalog = require(path.join(root, "assets/content_catalog.json"))
    const quests = require(path.join(root, "assets/content_history_quest_rules.json"))
    const shops = require(path.join(root, "assets/content_history_shop_rules.json"))
    return Object.fromEntries(Object.entries({ ...catalog.resources, ...quests.source.resources, ...shops.source.resources })
        .filter(([logical]) => logical.startsWith("master/") && !logical.startsWith("master/battle/"))
        .sort(([a], [b]) => a.localeCompare(b)).map(([logical, resource]) => {
            const value = resource as { archive: string }
            if (!/^master\/[a-zA-Z0-9_/-]+\.orderedmap$/.test(logical) || !archivePattern.test(value.archive))
                throw new Error("Invalid content business resource: " + logical)
            return [logical, { archive: value.archive }]
        }))
}

/** Capture a candidate for an explicitly reviewed business update, never at startup. */
export function captureContentResourceSourceSync(root = path.resolve(__dirname, "../..")): ContentResourceSource {
    const manifest = readFileSync(path.join(root, "assets/asset-patch/manifest.json"))
    const resources = contentBusinessResourcesSync(root), hashes = readWinningContentResourceHashesSync(root, resources)
    if (!manifest.equals(readFileSync(path.join(root, "assets/asset-patch/manifest.json")))) throw new Error("Content manifest changed during capture")
    const assetVersion = JSON.parse(manifest.toString("utf8")).cdn_version
    if (typeof assetVersion !== "string" || !/^\d+\.\d+\.\d+$/.test(assetVersion)) throw new Error("Invalid CDN version")
    return { schemaVersion: 1, source: { assetVersion, manifestSha256: createHash("sha256").update(manifest).digest("hex") },
        resources: Object.fromEntries(Object.entries(resources).map(([name, value]) => [name, { ...value, sha256: hashes[name] }])) }
}

/** Preserve the reviewed deployment identity while actual business tables agree.
 * A resource version bump never republishes activities or resets player progress.
 */
export function readContentResourceSourceSync(root = path.resolve(__dirname, "../..")): ContentResourceSource["source"] {
    const value = JSON.parse(readFileSync(path.join(root, "assets/content_resource_source.json"), "utf8")) as ContentResourceSource
    const required = Object.keys(contentBusinessResourcesSync(root)).sort()
    if (value.schemaVersion !== 1 || !/^\d+\.\d+\.\d+$/.test(value.source?.assetVersion)
        || !hashPattern.test(value.source?.manifestSha256) || !value.resources || !required.length
        || Object.keys(value.resources).sort().join("|") !== required.join("|")) throw new Error("Invalid content resource source scope")
    for (const [logical, resource] of Object.entries(value.resources)) {
        if (!resource || !archivePattern.test(resource.archive) || !hashPattern.test(resource.sha256))
            throw new Error("Invalid content resource source: " + logical)
    }
    const actual = readWinningContentResourceHashesSync(root, value.resources)
    const changed = required.filter(logical => actual[logical] !== value.resources[logical].sha256)
    if (changed.length) throw new Error("Content business definitions changed; review required: " + changed.join(", "))
    return { ...value.source }
}
