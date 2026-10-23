/** Offline, read-only rehearsal. No store, clock, filesystem or database access. */
export type CutoverAction = "visible" | "enter" | "claim" | "exchange"
export type Availability = "available" | "unavailable" | "unknown"
export interface CutoverScope { kind: "quest" | "mission"; member: string }
export interface CutoverObservation {
    key: string; action: CutoverAction; availability: Availability; scope?: CutoverScope; source: string
}
export interface CutoverEvidence {
    key: string; action: CutoverAction; status: "verified" | "unknown" | "unsupported"
    scope?: CutoverScope; source: string; catalogDigest: string
}
export interface CutoverRow {
    key: string; capabilities: readonly CutoverAction[]; questKeys?: readonly string[]; missionKeys?: readonly string[]
}
export interface ProposedContentControl {
    key: string; controlled: boolean; flags?: Record<CutoverAction, boolean>; endsAtMs?: number | null
    actionOverrides?: Partial<Record<CutoverAction, {
        enabled: boolean; endsAtMs: number | null; readiness: "verified" | "current_baseline" | "unverified" | "blocked"; evidence: string
        questKeys?: readonly string[] | null; missionKeys?: readonly string[] | null
    }>>
    questKeys?: readonly string[] | null; missionKeys?: readonly string[] | null; catalogDigest: string
}
export interface ContentCutoverPreflightInput {
    mode: "complete_cutover" | "scenario"
    identity: {
        catalogFileSha256: string; catalogDigest: string; assetVersion: string; manifestSha256: string
        referenceBusinessTimeMs: number; referenceCapturedAtUtc: string; runtimeMemoryClockVerified: boolean
    }
    rows: readonly CutoverRow[]
    observedBefore: readonly CutoverObservation[]
    /** Explicit projection of the old policy at the proposed new clock, never inferred from before. */
    legacyAfter: readonly CutoverObservation[]
    proposedAfter: readonly ProposedContentControl[]
    evidence: readonly CutoverEvidence[]
    proposedTimeMs: number
    completeness: {
        currentAvailabilityInventoryComplete: boolean; playerEntitlementsPreserved: boolean
        runtimeClockVerified: boolean; clientRuntimeVerified: boolean
    }
}
export interface CutoverDifference {
    key: string; action: CutoverAction; scope?: CutoverScope
    before: Availability; after: Availability; strategy: "legacy" | "whole_row" | "action_override"
    evidence: "verified" | "unknown" | "unsupported"; reasons: string[]
    /** preserve_legacy records explicit old-policy observations; it never authorizes taking control or enabling content. */
    retentionDecision: "preserve_legacy" | "keep_closed" | "preserve_controlled" | "verified_opening" | "blocked"
    /** Known closed before and after is outside preservation of existing usable actions. Unknown is never excluded. */
    affectsRetention: boolean; diagnostics: string[]
}
export interface ContentCutoverPreflightResult {
    schemaVersion: 1; identity: ContentCutoverPreflightInput["identity"]
    mode: ContentCutoverPreflightInput["mode"]; decision: "reject" | "scenario_only" | "production_ready"
    scenarioReady: boolean; productionReady: boolean; blockers: string[]
    differences: CutoverDifference[]; lost: CutoverDifference[]; unknown: CutoverDifference[]
    unsupported: CutoverDifference[]; allowedScopes: CutoverDifference[]
    /** Informational capability/evidence gaps do not authorize an opening or remove inventory members. */
    diagnostics: string[]
}
const ACTIONS: readonly CutoverAction[] = ["visible", "enter", "claim", "exchange"]
const identityOf = (value: { key: string; action: CutoverAction; scope?: CutoverScope }) =>
    JSON.stringify([value.key, value.action, value.scope?.kind ?? null, value.scope?.member ?? null])

/**
 * Models legacy whole-row takeover and independent action overrides with exact member scopes.
 * A draw proof never grants exchange; one member proof never grants its siblings.
 * The caller must supply an explicit before inventory and old-policy after projection.
 */
export function evaluateContentCutoverPreflight(input: ContentCutoverPreflightInput): ContentCutoverPreflightResult {
    const blockers = new Set<string>()
    const invalid = (reason: string) => blockers.add(`invalid_input:${reason}`)
    const digest = input.identity.catalogDigest
    for (const field of ["catalogFileSha256", "catalogDigest", "manifestSha256"] as const)
        if (!/^[a-f0-9]{64}$/.test(input.identity[field])) invalid(field)
    if (!input.identity.assetVersion || !input.identity.referenceCapturedAtUtc
        || !Number.isSafeInteger(input.identity.referenceBusinessTimeMs)
        || !Number.isSafeInteger(input.proposedTimeMs) || input.proposedTimeMs < 0) invalid("clock_or_source")
    if (!["scenario", "complete_cutover"].includes(input.mode)) invalid("mode")
    const rows = new Map(input.rows.map(row => [row.key, row]))
    if (!input.rows.length) invalid("empty_inventory")
    if (rows.size !== input.rows.length) invalid("duplicate_rows")
    for (const row of input.rows) {
        if (!row.key || new Set(row.capabilities).size !== row.capabilities.length
            || row.capabilities.some(action => !ACTIONS.includes(action))) invalid(`capabilities:${row.key}`)
        for (const members of [row.questKeys, row.missionKeys]) if (members &&
            (new Set(members).size !== members.length || members.some(member => !/^\d+:\d+$/.test(member)))) invalid(`members:${row.key}`)
    }
    const controls = new Map(input.proposedAfter.map(control => [control.key, control]))
    if (controls.size !== input.proposedAfter.length) invalid("duplicate_controls")
    for (const control of input.proposedAfter) {
        const row = rows.get(control.key)
        if (!row) { invalid(`unknown_control:${control.key}`); continue }
        if (control.catalogDigest !== digest) invalid(`stale_control:${control.key}`)
        if (typeof control.controlled !== "boolean") invalid(`control:${control.key}`)
        if (control.actionOverrides === undefined && (ACTIONS.some(action => typeof control.flags?.[action] !== "boolean")
            || !(control.endsAtMs === null || (Number.isSafeInteger(control.endsAtMs) && control.endsAtMs! >= 0)))) invalid(`control:${control.key}`)
        if (control.actionOverrides !== undefined) {
            if (!control.actionOverrides || typeof control.actionOverrides !== "object" || Array.isArray(control.actionOverrides)
                || Object.keys(control.actionOverrides).some(action => !ACTIONS.includes(action as CutoverAction))) invalid(`action_overrides:${control.key}`)
            else for (const [action, override] of Object.entries(control.actionOverrides)) {
                if (!override || typeof override.enabled !== "boolean" || !["verified", "current_baseline", "unverified", "blocked"].includes(override.readiness)
                    || typeof override.evidence !== "string" || !override.evidence.trim()
                    || !(override.endsAtMs === null || (Number.isSafeInteger(override.endsAtMs) && override.endsAtMs >= 0))) { invalid(`action_override:${control.key}:${action}`); continue }
                for (const kind of ["quest", "mission"] as const) {
                    const field = kind === "quest" ? "questKeys" : "missionKeys", members = override[field], available = row[field] ?? []
                    if (members && (!Array.isArray(members) || new Set(members).size !== members.length || (!members.length && override.enabled)
                        || members.some(member => !available.includes(member)))) invalid(`action_scope:${control.key}:${action}:${kind}`)
                }
                if (override.enabled && !row.capabilities.includes(action as CutoverAction)) blockers.add(`unsupported_enabled_action:${control.key}:${action}`)
                if (override.enabled && !["verified", "current_baseline"].includes(override.readiness)) invalid(`action_readiness:${control.key}:${action}`)
            }
        }
        for (const kind of ["quest", "mission"] as const) {
            const members = control[kind === "quest" ? "questKeys" : "missionKeys"]
            const catalogMembers = row[kind === "quest" ? "questKeys" : "missionKeys"] ?? []
            const enabledMemberAction = control.actionOverrides === undefined
                && (control.flags?.enter || (kind === "mission" && control.flags?.claim))
            if (members && (new Set(members).size !== members.length || (!members.length && enabledMemberAction)
                || members.some(member => !catalogMembers.includes(member)))) invalid(`scope:${control.key}:${kind}`)
        }
        for (const action of ACTIONS) if (control.actionOverrides === undefined && control.flags?.[action] && !row.capabilities.includes(action))
            blockers.add(`unsupported_enabled_action:${control.key}:${action}`)
    }
    function index<T extends CutoverObservation | CutoverEvidence>(values: readonly T[], label: string): Map<string, T> {
        const result = new Map<string, T>()
        for (const value of values) {
            const row = rows.get(value.key), unit = identityOf(value)
            if (!row || !ACTIONS.includes(value.action) || !value.source.trim()) invalid(`${label}:${unit}`)
            if (value.scope && (!/^\d+:\d+$/.test(value.scope.member)
                || !["quest", "mission"].includes(value.scope.kind)
                || !row?.[value.scope.kind === "quest" ? "questKeys" : "missionKeys"]?.includes(value.scope.member))) invalid(`${label}_scope:${unit}`)
            if (result.has(unit)) invalid(`duplicate_${label}:${unit}`)
            result.set(unit, value)
        }
        return result
    }
    const before = index(input.observedBefore, "before"), legacy = index(input.legacyAfter, "legacy_after"), evidence = index(input.evidence, "evidence")
    for (const value of [...input.observedBefore, ...input.legacyAfter])
        if (!["available", "unavailable", "unknown"].includes(value.availability)) invalid(`availability:${identityOf(value)}`)
    for (const value of input.evidence) {
        if (value.catalogDigest !== digest) invalid(`stale_evidence:${identityOf(value)}`)
        if (!["verified", "unknown", "unsupported"].includes(value.status)) invalid(`evidence_status:${identityOf(value)}`)
    }
    const units = new Map<string, { key: string; action: CutoverAction; scope?: CutoverScope }>()
    function add(key: string, action: CutoverAction, scope?: CutoverScope) {
        const value = { key, action, ...(scope ? { scope } : {}) }; units.set(identityOf(value), value)
    }
    // Every supported action participates, including omitted/false flags during whole-row takeover.
    for (const row of input.rows) for (const action of row.capabilities) {
        // Parent gates also feed non-member routes (for example pass reward claims).
        add(row.key, action)
        const members = action === "enter" ? (row.questKeys?.length ? ["quest", row.questKeys] as const
            : row.missionKeys?.length ? ["mission", row.missionKeys] as const : null)
            : action === "claim" && row.missionKeys?.length ? ["mission", row.missionKeys] as const : null
        if (members) for (const member of members[1]) add(row.key, action, { kind: members[0], member })
    }
    // An unwired candidate still needs an explicit availability verdict; absence is not proof of closure.
    for (const row of input.rows) if (!row.capabilities.length) add(row.key, "visible")
    for (const value of [...input.observedBefore, ...input.legacyAfter, ...input.evidence]) add(value.key, value.action, value.scope)
    const differences: CutoverDifference[] = []
    for (const [unit, value] of units) {
        const control = controls.get(value.key), row = rows.get(value.key)
        const observed = before.get(unit)?.availability ?? "unknown"
        const proof = evidence.get(unit)
        const proofStatus = proof?.catalogDigest === digest ? proof.status : "unknown"
        const reasons: string[] = [], diagnostics: string[] = []
        let after: Availability = "unknown"
        const override = control?.actionOverrides?.[value.action]
        const strategy: CutoverDifference["strategy"] = control?.controlled
            ? control.actionOverrides === undefined ? "whole_row" : override ? "action_override" : "legacy" : "legacy"
        if (strategy === "legacy") {
            after = legacy.get(unit)?.availability ?? "unknown"
            if (!legacy.has(unit)) reasons.push("old_policy_after_clock_not_observed")
        } else {
            const permissions = override ?? control!
            const scope = value.scope ? permissions[value.scope.kind === "quest" ? "questKeys" : "missionKeys"] : null
            const supported = !!row?.capabilities.includes(value.action)
            const enabled = override ? override.enabled && ["verified", "current_baseline"].includes(override.readiness) : control!.flags?.[value.action]
            after = supported && enabled && (permissions.endsAtMs === null || input.proposedTimeMs <= permissions.endsAtMs!)
                && (!value.scope || scope === null || scope === undefined || scope.includes(value.scope.member)) ? "available" : "unavailable"
            if (!supported) {
                if (enabled) reasons.push("action_not_wired")
                else diagnostics.push("closed_action_not_wired")
            }
            if (control!.catalogDigest !== digest) { after = "unknown"; reasons.push("control_catalog_identity_mismatch") }
        }
        if (observed === "unknown") reasons.push("before_availability_unknown")
        if (after === "unknown") reasons.push("after_availability_unknown")
        if (observed === "available" && after !== "available") reasons.push("current_action_or_entitlement_not_preserved")
        // Unknown prior availability cannot authorize a false flag simply because another action was verified.
        if (strategy !== "legacy" && after === "unavailable" && observed === "unknown") reasons.push(strategy === "whole_row" ? "whole_row_closure_without_before_proof" : "action_closure_without_before_proof")
        const stableLegacy = strategy === "legacy" && observed === "available" && after === "available"
        const needsOpeningProof = after === "available" && !stableLegacy
        if (needsOpeningProof) {
            if (!row?.capabilities.includes(value.action)) reasons.push("action_not_wired")
            if (proofStatus !== "verified") reasons.push("action_scope_not_verified")
            if (proofStatus === "unsupported") reasons.push("unsupported_evidence")
        } else if (proofStatus === "unsupported") diagnostics.push("unsupported_operations_evidence")
        const affectsRetention = observed !== "unavailable" || after !== "unavailable"
        const retentionDecision: CutoverDifference["retentionDecision"] = reasons.length ? "blocked"
            : observed === "unavailable" && after === "unavailable" ? "keep_closed"
            : stableLegacy ? "preserve_legacy"
            : observed === "available" ? "preserve_controlled" : "verified_opening"
        const difference: CutoverDifference = { ...value, before: observed, after, strategy, evidence: proofStatus,
            reasons, retentionDecision, affectsRetention, diagnostics }
        differences.push(difference)
        for (const reason of reasons) blockers.add(`${reason}:${unit}`)
    }
    const lost = differences.filter(row => row.before === "available" && row.after !== "available")
    const unknown = differences.filter(row => row.before === "unknown" || row.after === "unknown"
        || (row.after === "available" && row.retentionDecision !== "preserve_legacy" && row.evidence === "unknown"))
    const unsupported = differences.filter(row => row.evidence === "unsupported" || row.reasons.includes("action_not_wired"))
    const allowedScopes = differences.filter(row => row.after === "available" && !row.reasons.length)
    const diagnostics = differences.flatMap(row => row.diagnostics.map(reason => `${reason}:${identityOf(row)}`))
    const scenarioReady = blockers.size === 0
    if (input.mode === "complete_cutover") {
        for (const key of ["currentAvailabilityInventoryComplete", "playerEntitlementsPreserved", "runtimeClockVerified", "clientRuntimeVerified"] as const)
            if (input.completeness[key] !== true) blockers.add(`complete_cutover_missing:${key}`)
        if (input.identity.runtimeMemoryClockVerified !== true) blockers.add("complete_cutover_missing:runtimeMemoryClockVerified")
    }
    const productionReady = input.mode === "complete_cutover" && blockers.size === 0
    return { schemaVersion: 1, identity: { ...input.identity }, mode: input.mode,
        decision: productionReady ? "production_ready" : input.mode === "scenario" && scenarioReady ? "scenario_only" : "reject",
        scenarioReady, productionReady, blockers: [...blockers].sort(), differences, lost, unknown, unsupported, allowedScopes, diagnostics }
}
