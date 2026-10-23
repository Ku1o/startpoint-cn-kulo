/** Pure offline evidence validation. Rule closure never invents a live entitlement or availability. */
export type EntitlementProofStatus = "verified" | "unknown" | "unsupported"
export interface EntitlementEvidence {
    key: string
    action: string
    scope?: string
    status: EntitlementProofStatus
    catalogDigest: string
    manifestSha256: string
    resourceSha256: readonly string[]
    sourceSha256: readonly string[]
    condition: string
    issues: readonly string[]
}
export interface EvidenceIdentity { catalogDigest: string; manifestSha256: string }
export function evaluateEntitlementEvidence(evidence: EntitlementEvidence, identity: EvidenceIdentity) {
    const issues = [...evidence.issues]
    const hash = /^[a-f0-9]{64}$/
    if (!evidence.key || !evidence.action || !evidence.condition.trim()) issues.push("missing_exact_action_or_condition")
    if (!hash.test(identity.catalogDigest) || !hash.test(identity.manifestSha256)
        || evidence.catalogDigest !== identity.catalogDigest || evidence.manifestSha256 !== identity.manifestSha256)
        issues.push("identity_mismatch")
    if (!["verified", "unknown", "unsupported"].includes(evidence.status)) issues.push("invalid_status")
    if (evidence.status === "verified" && (!evidence.resourceSha256.length || !evidence.sourceSha256.length
        || [...evidence.resourceSha256, ...evidence.sourceSha256].some(value => !hash.test(value))))
        issues.push("missing_byte_or_business_path_identity")
    const status: EntitlementProofStatus = evidence.status === "unsupported" ? "unsupported"
        : evidence.status === "verified" && issues.length === 0 ? "verified" : "unknown"
    return { status, issues, observedBeforeAvailability: "unknown" as const, ruleVerified: status === "verified", mayEnable: false as const,
        currentPlayerEntitlementVerified: false as const, productionReady: false as const }
}

/** Compare snapshots supplied by the caller. This module never reads a player database. */
export function verifyEntitlementPreservation(before: Readonly<Record<string, unknown>>, after: Readonly<Record<string, unknown>>) {
    const lost: string[] = []
    for (const [key, value] of Object.entries(before))
        if (!(key in after) || JSON.stringify(after[key]) !== JSON.stringify(value)) lost.push(key)
    return { preserved: lost.length === 0, changedOrMissing: lost.sort() }
}

export interface ContentActionClosureEvidence extends EntitlementEvidence {
    definitionSha256: string
    contentDigest: string
    missingRefs: readonly string[]
    exactScope: string
}

/** A parent's proof cannot authorize a sibling or a different action; this has no store/database access. */
export function evaluateContentActionClosure(evidence: ContentActionClosureEvidence,
    identity: EvidenceIdentity & { definitionSha256: string; contentDigest: string; exactScope: string; action: string }) {
    const issues = [...evidence.issues, ...evidence.missingRefs.map(reference => `missing_reference:${reference}`)]
    const hash = /^[a-f0-9]{64}$/
    if (!hash.test(evidence.definitionSha256) || evidence.definitionSha256 !== identity.definitionSha256
        || !hash.test(evidence.contentDigest) || evidence.contentDigest !== identity.contentDigest)
        issues.push("definition_cas_identity_mismatch")
    if (!evidence.exactScope || evidence.exactScope !== identity.exactScope || evidence.action !== identity.action)
        issues.push("exact_scope_or_action_mismatch")
    return evaluateEntitlementEvidence({ ...evidence, issues }, identity)
}
