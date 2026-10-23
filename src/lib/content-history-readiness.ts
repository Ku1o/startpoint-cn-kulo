import { closeSync, openSync, readFileSync, readSync, statSync } from "node:fs"
import { createHash } from "node:crypto"
import { Buffer } from "node:buffer"
import path from "node:path"
import type { ContentAction } from "./content-operations-store"
import { getContentBoxAssociation } from "./content-box-associations"

export type HistoryActionStatus = "passed" | "blocked" | "unreviewed" | "not_applicable"
export interface HistoryReadinessExplanation {
    status: HistoryActionStatus
    reasons: string[]
}
export interface ContentHistoryNativePage { kind: string; label: string; description?: string }
interface HistoryAction {
    status?: HistoryActionStatus
    blockers?: Array<{ code?: string; message?: string; evidence?: unknown }>
}
interface HistoryRow {
    key: string
    staticStatus?: HistoryActionStatus
    actions?: Partial<Record<ContentAction, HistoryAction>>
    nativePage?: ContentHistoryNativePage
    dependencies?: { boxGachaKeys?: string[] }
}
interface HistoryManifest { schemaVersion: number; canonicalSha256: string; rows: HistoryRow[] }
const manifestPath = path.resolve(__dirname, "../../assets/content_history_readiness_runtime.json")
const canonicalPath = path.resolve(__dirname, "../../assets/content_history_readiness.json")
let cachedSignature: string | undefined
let cachedRows = new Map<string, HistoryRow>()
const signature = (file: string) => { const stat = statSync(file, { bigint: true }); return `${stat.dev}:${stat.ino}:${stat.size}:${stat.mtimeNs}:${stat.ctimeNs}` }
let canonicalIdentity: { signature: string; digest: string } | undefined
function canonicalDigest(current: string) {
    if (canonicalIdentity?.signature === current) return canonicalIdentity.digest
    const hash = createHash("sha256"), buffer = Buffer.allocUnsafe(64 * 1024), fd = openSync(canonicalPath, "r")
    try { let count: number; while ((count = readSync(fd, buffer, 0, buffer.length, null))) hash.update(buffer.subarray(0, count)) }
    finally { closeSync(fd) }
    if (signature(canonicalPath) !== current) throw new Error("Readiness source changed during verification")
    canonicalIdentity = { signature: current, digest: hash.digest("hex") }
    return canonicalIdentity.digest
}

function manifestRows(): ReadonlyMap<string, HistoryRow> {
    try {
        const summarySignature = signature(manifestPath), sourceSignature = signature(canonicalPath)
        const current = `${summarySignature}|${sourceSignature}`
        if (current === cachedSignature) return cachedRows
        // Reject an accidentally substituted full audit before allocating a string.
        if (statSync(manifestPath).size > 4 * 1024 * 1024) throw new Error("Oversized readiness runtime summary")
        const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as HistoryManifest
        if (manifest.schemaVersion !== 1 || !Array.isArray(manifest.rows) || !/^[a-f0-9]{64}$/.test(manifest.canonicalSha256 || "")
            || canonicalDigest(sourceSignature) !== manifest.canonicalSha256) throw new Error("Invalid history readiness manifest")
        const rows = new Map<string, HistoryRow>()
        for (const row of manifest.rows) {
            if (!row || typeof row.key !== "string" || rows.has(row.key)) throw new Error("Invalid history readiness row")
            for (const [action, review] of Object.entries(row.actions || {})) {
                if (!["visible", "enter", "claim", "exchange"].includes(action) || !review
                    || (review.status !== undefined && !["passed", "blocked", "unreviewed", "not_applicable"].includes(review.status))
                    || (review.blockers !== undefined && (!Array.isArray(review.blockers)
                        || review.blockers.some(blocker => !blocker || (blocker.message !== undefined && typeof blocker.message !== "string"))))) throw new Error("Invalid readiness action")
            }
            rows.set(row.key, row)
        }
        if (signature(manifestPath) !== summarySignature) throw new Error("Readiness summary changed during verification")
        cachedRows = rows; cachedSignature = current
        return cachedRows
    } catch {
        // An absent audit is an unreviewed integration, never evidence that a
        // game resource is missing and never an authorization to enable it.
        cachedRows = new Map(); cachedSignature = undefined
        return cachedRows
    }
}

/** Explanations only. This module cannot create, approve, or update controls. */
export function explainContentHistoryReadiness(row: HistoryRow | undefined, actions: readonly ContentAction[]): HistoryReadinessExplanation {
    if (!row) return { status: "unreviewed", reasons: ["尚未完成历史内容核查与接入"] }
    const reviews = actions.map(action => row.actions?.[action]).filter((review): review is HistoryAction => !!review)
    const blockers = reviews.flatMap(review => review.blockers ?? [])
    const reasons = [...new Set(blockers.map(blocker => blocker.message?.trim()).filter((message): message is string => !!message))]
    // The aggregate may include an unrelated claim/exchange limitation. Only
    // the requested primary actions and their audited dependencies block it.
    if (reviews.some(review => review.status === "blocked")) {
        return { status: "blocked", reasons: reasons.length ? reasons : ["该内容存在尚未解决的玩法或资源问题"] }
    }
    if (reviews.length !== actions.length || reviews.some(review => !review.status || review.status === "unreviewed")) {
        return { status: "unreviewed", reasons: reasons.length ? reasons : ["尚未完成所需玩法与入口的核查"] }
    }
    if (reviews.length && reviews.every(review => review.status === "not_applicable")) return { status: "not_applicable", reasons: ["该内容没有适用的开放入口"] }
    return { status: "passed", reasons: [] }
}

export function getContentHistoryReadiness(key: string, actions: readonly ContentAction[]): HistoryReadinessExplanation {
    return contentHistoryReadinessReader().get(key, actions)
}

/** Native page identity is display metadata, never an operational permission. */
export function getContentHistoryNativePage(key: string): ContentHistoryNativePage | undefined {
    return contentHistoryReadinessReader().nativePage(key)
}
function nativePage(rows: ReadonlyMap<string, HistoryRow>, key: string): ContentHistoryNativePage | undefined {
    const page = rows.get(key)?.nativePage
    if (!page || typeof page.kind !== "string" || typeof page.label !== "string" || !page.label.trim()) return undefined
    return { kind: page.kind, label: page.label.trim(),
        ...(typeof page.description === "string" && page.description.trim() ? { description: page.description.trim() } : {}) }
}

/** The audited native association is fixed to the matching client route. */
export function getContentHistoryBoxAssociation(key: string) {
    return contentHistoryReadinessReader().boxAssociation(key)
}
/** Capture once per request (or at startup): row/action reads perform no filesystem work. */
export function contentHistoryReadinessReader() {
    const rows = manifestRows()
    return { get: (key: string, actions: readonly ContentAction[]) => explainContentHistoryReadiness(rows.get(key), actions),
        nativePage: (key: string) => nativePage(rows, key), boxAssociation: getContentBoxAssociation }
}
