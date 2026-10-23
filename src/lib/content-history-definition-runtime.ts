import { createHash } from "node:crypto"
import { closeSync, fstatSync, openSync, readFileSync, readSync, statSync } from "node:fs"
import path from "node:path"
import type { CurrentParentDefinitionEvidence, ExactDefinitionEvidence } from "./content-definition-evidence"
import { CONTENT_HISTORY_DEFINITION_RUNTIME_IDENTITY } from "./content-history-definition-runtime-identity"

export interface ContentDefinitionRuntimeIdentity {
    readonly schemaVersion: 1
    readonly canonicalSha256: string
    readonly catalogSha256: string
    readonly runtimeSha256: string
}
export interface ContentHistoryDefinitionRuntime {
    schemaVersion: number
    source: { catalogSha256: string }
    rows: Record<string, ExactDefinitionEvidence>
    existingEvidenceRebind: Record<string, {
        kind: "exact" | "currentParent"; status: string
        previousEvidence: ExactDefinitionEvidence | CurrentParentDefinitionEvidence
        evidence: ExactDefinitionEvidence | CurrentParentDefinitionEvidence
        nativeRowMatchesCatalog: boolean; dependencyDigestUnchanged: boolean
    }>
}
const hashPattern = /^[a-f0-9]{64}$/, keyPattern = /^[a-z_]+:\d+$/
const maximumSummaryBytes = 16 * 1024 * 1024, maximumRecords = 50000
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value)
function fail(message: string): never { throw new Error("Historical definition runtime summary rejected: " + message) }
function check(value: unknown, message: string): asserts value { if (!value) fail(message) }
function fields(value: Record<string, unknown>, expected: readonly string[], message: string): void {
    check(Object.keys(value).sort().join("|") === [...expected].sort().join("|"), message)
}
const signature = (value: ReturnType<typeof fstatSync>) => `${value.dev}:${value.ino}:${value.size}:${value.mtimeMs}:${value.ctimeMs}`
/** Bounded buffers only: the complete audit and catalog are not parsed here. */
function streamedIdentity(file: string): { sha256: string; bytes: number } {
    const fd = openSync(file, "r"), block = Buffer.allocUnsafe(64 * 1024), hash = createHash("sha256")
    try {
        const before = fstatSync(fd)
        check(before.isFile() && before.size > 0 && before.size <= 256 * 1024 * 1024, "source size is invalid")
        let count = 0, total = 0
        while ((count = readSync(fd, block, 0, block.length, null))) { hash.update(block.subarray(0, count)); total += count }
        check(total === before.size && signature(fstatSync(fd)) === signature(before) && signature(statSync(file)) === signature(before), "source changed during verification")
        return { sha256: hash.digest("hex"), bytes: total }
    } finally { closeSync(fd) }
}
function table(value: unknown, name: string, maximum = maximumRecords): unknown[] {
    check(Array.isArray(value) && value.length <= maximum, "invalid " + name + " table")
    return value
}

/** A generated source anchor binds the compact payload to the unchanged audit.
 * Options are for explicit offline fixtures; production supplies no overrides.
 * Missing/corrupt/mismatched summaries are fatal, never full-report fallbacks.
 */
export function loadContentHistoryDefinitionRuntime(options: {
    root?: string; identity?: ContentDefinitionRuntimeIdentity
} = {}): ContentHistoryDefinitionRuntime {
    const root = path.resolve(options.root ?? path.resolve(__dirname, "../.."))
    const identity = options.identity ?? CONTENT_HISTORY_DEFINITION_RUNTIME_IDENTITY
    check(identity.schemaVersion === 1 && [identity.canonicalSha256, identity.catalogSha256, identity.runtimeSha256]
        .every(value => typeof value === "string" && hashPattern.test(value)), "invalid generated source anchor")
    const file = path.join(root, "assets/content_history_definition_runtime.json")
    const before = statSync(file)
    check(before.isFile() && before.size > 0 && before.size <= maximumSummaryBytes, "summary exceeds runtime size bound")
    const text = readFileSync(file, "utf8")
    check(createHash("sha256").update(text).digest("hex") === identity.runtimeSha256, "summary SHA does not match generated source anchor")
    check(signature(statSync(file)) === signature(before), "summary changed during verification")
    let parsed: unknown
    try { parsed = JSON.parse(text) } catch { fail("invalid summary JSON") }
    check(record(parsed), "summary must be an object")
    fields(parsed, ["schemaVersion", "source", "loaders", "proofs", "children", "statuses", "rows", "rebind", "counts"], "unsupported summary fields")
    check(parsed.schemaVersion === 1 && record(parsed.source) && record(parsed.counts), "unsupported summary schema")
    fields(parsed.source, ["schemaVersion", "canonicalSha256", "canonicalBytes", "catalogSha256"], "invalid summary provenance")
    check(parsed.source.schemaVersion === 1 && parsed.source.canonicalSha256 === identity.canonicalSha256
        && parsed.source.catalogSha256 === identity.catalogSha256 && Number.isSafeInteger(parsed.source.canonicalBytes)
        && (parsed.source.canonicalBytes as number) > 0, "summary provenance does not match generated source anchor")
    const canonical = streamedIdentity(path.join(root, "assets/content_history_definition_evidence.json"))
    check(canonical.sha256 === identity.canonicalSha256 && canonical.bytes === parsed.source.canonicalBytes, "canonical audit identity mismatch")
    check(streamedIdentity(path.join(root, "assets/content_catalog.json")).sha256 === identity.catalogSha256, "catalog identity mismatch")

    const loaders = table(parsed.loaders, "loaders", 256).map(value => {
        check(record(value), "invalid loader dictionary")
        const names = Object.keys(value)
        check(names.length > 0 && names.length <= 64, "invalid loader dictionary size")
        for (const name of names) check(/^src\/[A-Za-z0-9_./-]+\.ts$/.test(name)
            && !name.split("/").some(part => part === ".." || part === "." || !part)
            && typeof value[name] === "string" && hashPattern.test(value[name] as string), "invalid loader source or SHA")
        return Object.freeze(value) as Record<string, string>
    })
    const proofs = table(parsed.proofs, "proofs").map(value => {
        check(Array.isArray(value) && value.length === 3 && value.every(item => typeof item === "string" && hashPattern.test(item)), "invalid proof tuple")
        return value as [string, string, string]
    })
    const children = table(parsed.children, "children", 256).map(value => {
        check(Array.isArray(value) && value.length <= 5000 && value.every(item => typeof item === "string" && /^\d+$/.test(item)), "invalid ordered child list")
        return Object.freeze(value) as string[]
    })
    const statuses = table(parsed.statuses, "statuses", 256).map(value => {
        check(typeof value === "string" && value.length > 0 && value.length <= 500, "invalid rebind status")
        return value
    })
    const rows = table(parsed.rows, "rows"), transitions = table(parsed.rebind, "rebind")
    const used = { loaders: new Set<number>(), proofs: new Set<number>(), children: new Set<number>(), statuses: new Set<number>() }
    const index = (value: unknown, name: keyof typeof used, values: readonly unknown[]) => {
        check(Number.isSafeInteger(value) && (value as number) >= 0 && (value as number) < values.length, "invalid " + name + " reference")
        used[name].add(value as number); return value as number
    }
    let evidenceReferences = 0
    const evidence = (key: string, kind: 0 | 1, reference: unknown): ExactDefinitionEvidence | CurrentParentDefinitionEvidence => {
        check(Array.isArray(reference) && reference.length === (kind === 0 ? 2 : 4), "invalid evidence reference")
        const proof = proofs[index(reference[0], "proofs", proofs)], loader = loaders[index(reference[1], "loaders", loaders)]
        const base = { schemaVersion: 1 as const, key, definitionDigest: proof[0], dependencyDigest: proof[1], loaders: loader, previousServerDefinitionDigest: proof[2] }
        evidenceReferences++
        return kind === 0 ? Object.freeze({ ...base, oldDefinitionMatched: true as const })
            : Object.freeze({ ...base, reviewedExistingChildren: children[index(reference[2], "children", children)],
                newUncataloguedChildren: children[index(reference[3], "children", children)] })
    }
    const restoredRows: ContentHistoryDefinitionRuntime["rows"] = {}
    for (const value of rows) {
        check(Array.isArray(value) && value.length === 3 && typeof value[0] === "string" && keyPattern.test(value[0]), "invalid historical row")
        const key = value[0]
        check(!Object.prototype.hasOwnProperty.call(restoredRows, key), "duplicate historical row")
        restoredRows[key] = evidence(key, 0, value.slice(1)) as ExactDefinitionEvidence
    }
    const rebind: ContentHistoryDefinitionRuntime["existingEvidenceRebind"] = {}
    for (const value of transitions) {
        check(Array.isArray(value) && value.length === 7 && typeof value[0] === "string" && keyPattern.test(value[0])
            && (value[1] === 0 || value[1] === 1) && typeof value[5] === "boolean" && typeof value[6] === "boolean", "invalid existing-evidence transition")
        const key = value[0], kind = value[1] as 0 | 1
        check(!Object.prototype.hasOwnProperty.call(rebind, key), "duplicate existing-evidence transition")
        rebind[key] = Object.freeze({ kind: kind === 0 ? "exact" as const : "currentParent" as const,
            status: statuses[index(value[2], "statuses", statuses)], previousEvidence: evidence(key, kind, value[3]),
            evidence: evidence(key, kind, value[4]), nativeRowMatchesCatalog: value[5], dependencyDigestUnchanged: value[6] })
    }
    const counts = { rows: rows.length, rebind: transitions.length, evidenceReferences, loaders: loaders.length,
        proofs: proofs.length, children: children.length, statuses: statuses.length }
    fields(parsed.counts, Object.keys(counts), "invalid count fields")
    for (const [name, expected] of Object.entries(counts)) check(parsed.counts[name] === expected, "count mismatch: " + name)
    for (const name of ["loaders", "proofs", "children", "statuses"] as const) check(used[name].size === counts[name], "unreferenced " + name + " dictionary entry")
    return Object.freeze({ schemaVersion: 1, source: Object.freeze({ catalogSha256: identity.catalogSha256 }),
        rows: Object.freeze(restoredRows), existingEvidenceRebind: Object.freeze(rebind) })
}
