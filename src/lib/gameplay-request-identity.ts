import { createHash, randomBytes } from "node:crypto"
import type { Database } from "better-sqlite3"

const initialized = new WeakSet<Database>()
const hash = (value: string) => createHash("sha256").update(value).digest("hex")
interface GameplayLogin {
    token_hash: string; account_id: number; viewer_id: number
    parent_token: string | null; is_current: number; expires_at: number
}

/** Authentication metadata, deliberately separate from transferable player saves. */
export function initializeGameplayRequestIdentitySchemaSync(db: Database): void {
    if (initialized.has(db)) return
    if (db.inTransaction) throw new Error("Initialize gameplay login schema before business transactions")
    db.exec(`CREATE TABLE IF NOT EXISTS gameplay_login_sessions (
        token_hash TEXT PRIMARY KEY,
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        viewer_id INTEGER NOT NULL,
        parent_token TEXT,
        scope_key TEXT NOT NULL,
        expires_at INTEGER NOT NULL,
        is_current INTEGER NOT NULL CHECK(is_current IN (0,1))
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_gameplay_login_current_scope
        ON gameplay_login_sessions(scope_key) WHERE is_current=1;`)
    initialized.add(db)
}

/** Call inside the successful signup persistence transaction. The original web
 * credential remains valid; native LOGIN_TOKEN identifies this signup alone. */
export function issueGameplayLoginTokenSync(db: Database, input: {
    accountId: number; viewerId: number; udid: string; parentToken?: string
    expiresAt: number; nowMs?: number
}): string {
    const nowMs = input.nowMs ?? Date.now()
    if (!db.inTransaction) throw new Error("Gameplay login issuance requires a persistence transaction")
    if (!Number.isSafeInteger(input.accountId) || input.accountId <= 0
        || !Number.isSafeInteger(input.viewerId) || input.viewerId <= 0
        || typeof input.udid !== "string" || !input.udid.length || input.udid.length > 256
        || !Number.isSafeInteger(input.expiresAt) || input.expiresAt <= nowMs
        || (input.parentToken !== undefined && !/^[a-f0-9]{64}$/.test(input.parentToken)))
        throw new TypeError("Invalid gameplay login identity")
    if (!initialized.has(db)) throw new Error("Gameplay login schema has not been initialized")
    if (!db.prepare("SELECT 1 FROM sessions WHERE token=? AND type=2 AND account_id=?")
        .get(String(input.viewerId), input.accountId)) throw new Error("Gameplay viewer does not belong to account")
    if (input.parentToken !== undefined && !db.prepare(`SELECT 1 FROM player_login_sessions
        WHERE token=? AND account_id=? AND viewer_id=? AND expires_at>=?`)
        .get(input.parentToken, input.accountId, input.viewerId, input.expiresAt))
        throw new Error("Gameplay login parent credential is invalid")
    const scope = hash(input.parentToken === undefined ? `legacy:${input.accountId}:${input.udid}` : `account:${input.parentToken}`)
    const token = randomBytes(32).toString("hex")
    db.prepare("UPDATE gameplay_login_sessions SET is_current=0 WHERE scope_key=? AND is_current=1").run(scope)
    db.prepare(`INSERT INTO gameplay_login_sessions
        (token_hash,account_id,viewer_id,parent_token,scope_key,expires_at,is_current)
        VALUES(?,?,?,?,?,?,1)`).run(hash(token), input.accountId, input.viewerId, input.parentToken ?? null, scope, input.expiresAt)
    return token
}

/** A stable logical request identity. Superseded identities remain recognizable
 * for receipt lookup, but may never begin a previously unprocessed mutation. */
export function readGameplayMutationIdentitySync(db: Database, headerToken: unknown,
    body: { viewer_id?: unknown; api_count?: unknown }, expectedAccountId: number,
    nowMs = Date.now()): { requestKey: string; isCurrent: boolean } | null {
    if (typeof headerToken !== "string" || !/^[a-f0-9]{64}$/.test(headerToken)
        || !Number.isSafeInteger(body.api_count) || Number(body.api_count) < 1
        || !Number.isSafeInteger(expectedAccountId) || expectedAccountId <= 0) return null
    if (!initialized.has(db)) {
        if (!db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gameplay_login_sessions'").get()) return null
        initialized.add(db)
    }
    const digest = hash(headerToken)
    const login = db.prepare(`SELECT s.* FROM gameplay_login_sessions s JOIN accounts a ON a.id=s.account_id
        WHERE s.token_hash=? AND s.expires_at>? AND a.status='normal'`).get(digest, nowMs) as GameplayLogin | undefined
    if (!login || login.account_id !== expectedAccountId || login.viewer_id !== Number(body.viewer_id)) return null
    if (login.parent_token !== null && !db.prepare(`SELECT 1 FROM player_login_sessions
        WHERE token=? AND account_id=? AND expires_at>?`).get(login.parent_token, expectedAccountId, nowMs)) return null
    return { requestKey: `native:${digest}:${body.api_count}`, isCurrent: login.is_current === 1 }
}

/** Used only by the indexed native credential queries, never exposed in APIs. */
export function gameplayLoginTokenHash(value: string): string { return hash(value) }
