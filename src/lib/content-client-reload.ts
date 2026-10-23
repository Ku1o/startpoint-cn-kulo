import type { Database } from "better-sqlite3"
import type { FastifyInstance } from "fastify"
import { requestRoutePath } from "./request-route-path"

export const CONTENT_CLIENT_RELOAD_MESSAGE = "活动与卡池配置已更新，请重新登录。"
export const CONTENT_CLIENT_RELOAD_CONFIRM = "RELOAD_ALL_CLIENTS"

export interface ContentClientReloadState { epoch: number; updatedAtMs: number | null }
export interface ContentClientReloadPlay {
    viewerId: number; playerId: number; playId: string; roomNumber: string; category: number; questId: number
}
export class ContentClientReloadConflict extends Error {
    constructor(public readonly current: ContentClientReloadState) {
        super("重登状态已更新，请刷新后重试。")
    }
}

/** Global operational state: no player/account FK, credentials, saves or progress. */
export class ContentClientReloadStore {
    constructor(private readonly db: Database) {
        db.exec(`
            CREATE TABLE IF NOT EXISTS content_client_reload_meta (
                id INTEGER PRIMARY KEY CHECK(id=1), epoch INTEGER NOT NULL CHECK(epoch>=0), updated_at_ms INTEGER
            );
            INSERT OR IGNORE INTO content_client_reload_meta(id,epoch) VALUES(1,0);
            CREATE TABLE IF NOT EXISTS content_client_reload_ack (
                viewer_id INTEGER PRIMARY KEY, epoch INTEGER NOT NULL CHECK(epoch>=0), loaded_at_ms INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS content_client_reload_audit (
                epoch INTEGER PRIMARY KEY, created_at_ms INTEGER NOT NULL, reason TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS content_client_reload_plays (
                player_id INTEGER NOT NULL, play_id TEXT NOT NULL, viewer_id INTEGER NOT NULL,
                epoch INTEGER NOT NULL, protected_at_ms INTEGER NOT NULL,
                PRIMARY KEY(player_id,play_id)
            );
        `)
    }
    state(): ContentClientReloadState {
        const row = this.db.prepare("SELECT epoch,updated_at_ms FROM content_client_reload_meta WHERE id=1").get() as { epoch: number; updated_at_ms: number | null }
        return { epoch: row.epoch, updatedAtMs: row.updated_at_ms }
    }
    required(viewer: unknown): boolean {
        const viewerId = Number(viewer)
        if (!Number.isSafeInteger(viewerId) || viewerId <= 0) return false
        const row = this.db.prepare(`SELECT m.epoch,COALESCE(a.epoch,0) AS acknowledged
            FROM content_client_reload_meta m LEFT JOIN content_client_reload_ack a ON a.viewer_id=? WHERE m.id=1`).get(viewerId) as { epoch: number; acknowledged: number }
        return row.acknowledged < row.epoch
    }
    request(expectedEpoch: number, nowMs = Date.now(), plays: readonly ContentClientReloadPlay[] = []): ContentClientReloadState {
        if (!Number.isSafeInteger(expectedEpoch) || expectedEpoch < 0 || expectedEpoch >= Number.MAX_SAFE_INTEGER) throw new Error("Invalid reload epoch")
        const apply = () => {
            const updated = this.db.prepare(`UPDATE content_client_reload_meta SET epoch=epoch+1,updated_at_ms=? WHERE id=1 AND epoch=?`).run(nowMs, expectedEpoch)
            if (updated.changes !== 1) throw new ContentClientReloadConflict(this.state())
            const next = this.state()
            this.db.prepare("INSERT INTO content_client_reload_audit(epoch,created_at_ms,reason) VALUES(?,?,?)")
                .run(next.epoch, nowMs, CONTENT_CLIENT_RELOAD_MESSAGE)
            this.protectActivePlays(plays, nowMs)
            return next
        }
        return this.db.inTransaction ? apply() : this.db.transaction(apply).immediate()
    }
    /** Owner supplies only connected, committed current battle bindings; the parent
     * rechecks the exact durable play and account identity in the signal transaction. */
    protectActivePlays(plays: readonly ContentClientReloadPlay[], nowMs = Date.now()): void {
        if (!this.db.inTransaction) throw new Error("Reload play protection requires a transaction")
        const epoch = this.state().epoch
        for (const play of plays) {
            if (![play.viewerId, play.playerId, play.category, play.questId].every(value => Number.isSafeInteger(value) && value > 0)
                || typeof play.playId !== "string" || !play.playId || play.playId.length > 256
                || typeof play.roomNumber !== "string" || !play.roomNumber || play.roomNumber.length > 128) throw new Error("Invalid reload play")
            if (!this.required(play.viewerId)) continue
            const current = this.db.prepare(`SELECT 1 FROM players_active_quests q JOIN players p ON p.id=q.player_id
                JOIN sessions s ON s.account_id=p.account_id AND s.type=2
                WHERE s.token=? AND q.player_id=? AND q.play_id=? AND q.room_number=? AND q.is_multi=1 AND q.category=? AND q.quest_id=?`)
                .get(String(play.viewerId), play.playerId, play.playId, play.roomNumber, play.category, play.questId)
            if (!current) continue
            this.db.prepare(`INSERT OR IGNORE INTO content_client_reload_plays(player_id,play_id,viewer_id,epoch,protected_at_ms) VALUES(?,?,?,?,?)`)
                .run(play.playerId, play.playId, play.viewerId, epoch, nowMs)
        }
    }
    preservesPlay(playerId: number, playId: string): boolean {
        return !!this.db.prepare("SELECT 1 FROM content_client_reload_plays WHERE player_id=? AND play_id=?").get(playerId, playId)
    }
    pruneFinishedPlays(playerId: number): void {
        this.db.prepare(`DELETE FROM content_client_reload_plays WHERE player_id=? AND NOT EXISTS (
            SELECT 1 FROM players_active_quests q WHERE q.player_id=content_client_reload_plays.player_id
                AND q.play_id=content_client_reload_plays.play_id)`).run(playerId)
    }
    /** A completed load acknowledges only its captured epoch, never a later signal. */
    acknowledge(viewer: unknown, loadedEpoch: number, nowMs = Date.now()): void {
        const viewerId = Number(viewer)
        if (!Number.isSafeInteger(viewerId) || viewerId <= 0 || !Number.isSafeInteger(loadedEpoch) || loadedEpoch < 0 || loadedEpoch > this.state().epoch) throw new Error("Invalid reload acknowledgement")
        this.db.prepare(`INSERT INTO content_client_reload_ack(viewer_id,epoch,loaded_at_ms) VALUES(?,?,?)
            ON CONFLICT(viewer_id) DO UPDATE SET epoch=excluded.epoch,loaded_at_ms=excluded.loaded_at_ms
            WHERE excluded.epoch>=content_client_reload_ack.epoch`).run(viewerId, loadedEpoch, nowMs)
    }
}

const stores = new WeakMap<Database, ContentClientReloadStore>()
export function contentClientReload(): ContentClientReloadStore {
    const db = (require("../data/db") as typeof import("../data/db")).getDb()
    let store = stores.get(db)
    if (!store) { store = new ContentClientReloadStore(db); stores.set(db, store) }
    return store
}

/** Uses Fastify's resolved route; query strings and encoded aliases cannot bypass it. */
export function contentReloadBusinessPath(route: string): boolean {
    const path = route.split("?", 1)[0]
    const prefix = ["/api/index.php/", "/latest/api/index.php/"].find(value => path.startsWith(value))
    if (!prefix) return false
    const endpoint = path.slice(prefix.length)
    return !["load", "title", "initialize", "tool/auth", "tool/signup"].includes(endpoint)
        && !endpoint.startsWith("asset/") && !endpoint.startsWith("take_over/")
}

export function installContentClientReloadGuard(app: FastifyInstance, dependencies: {
    store?: () => ContentClientReloadStore; headers?: (viewerId: number) => unknown
} = {}): void {
    // The default store performs schema initialization. Do that during startup,
    // not in a player's first request while a background worker owns the DB.
    if (!dependencies.store) contentClientReload()
    app.addHook("preHandler", async (request, reply) => {
        if (!contentReloadBusinessPath(requestRoutePath(request))) return
        const body = request.body && typeof request.body === "object" && !Array.isArray(request.body)
            ? request.body as Record<string, unknown> : {}
        const viewer = body.viewer_id || body.keychain
        // Bootstrap requests without an identity must reach their existing handlers.
        if (!Number.isSafeInteger(Number(viewer)) || Number(viewer) <= 0) return
        if (!(dependencies.store?.() ?? contentClientReload()).required(viewer)) return
        const headers = dependencies.headers?.(Number(viewer)) ?? (require("../utils") as typeof import("../utils"))
            .generateDataHeaders({ viewer_id: Number(viewer), result_code: 101 })
        reply.type("application/x-msgpack")
        return reply.send({ data_headers: headers, data: { message: CONTENT_CLIENT_RELOAD_MESSAGE } })
    })
}
