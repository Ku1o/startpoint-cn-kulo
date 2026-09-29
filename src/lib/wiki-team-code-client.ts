import { createHash } from "node:crypto"

export const GAME_CODE_PATTERN = /^[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{12}$/
export const TEAM_GROUPS = ["main", "unison", "weapon", "soul"] as const
export type TeamGroup = typeof TEAM_GROUPS[number]
export type PublicTeam = Record<TeamGroup, string[]>

export interface TeamCodePayload {
    title: string
    active: true
    team: PublicTeam
}

export class TeamCodeError extends Error {
    constructor(readonly kind: "not-found" | "unavailable" | "incompatible") {
        super(kind)
        this.name = "TeamCodeError"
    }
}

/** Stable opaque IDs shared with the Wiki. Raw game IDs never leave the server. */
export function wikiPublicId(kind: "c" | "w", id: string | number): string {
    return kind + createHash("sha256")
        .update(`wf-wiki-public-v1:${kind}:${id}`)
        .digest("hex")
        .slice(0, 12)
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
    value !== null && typeof value === "object" && !Array.isArray(value)

export function parseTeamCodePayload(value: unknown): TeamCodePayload {
    if (!isRecord(value)
        || Object.keys(value).sort().join(",") !== "active,team,title"
        || value.active !== true
        || typeof value.title !== "string"
        || value.title.trim().length === 0
        || [...value.title].length > 80
        || /[\u0000-\u001f\u007f]/.test(value.title)
        || !isRecord(value.team)
        || Object.keys(value.team).sort().join(",") !== "main,soul,unison,weapon") {
        throw new TeamCodeError("incompatible")
    }

    const team = {} as PublicTeam
    const seenCharacters = new Set<string>()
    for (const group of TEAM_GROUPS) {
        const ids = value.team[group]
        const isCharacter = group === "main" || group === "unison"
        if (!Array.isArray(ids) || ids.length !== 3) throw new TeamCodeError("incompatible")

        team[group] = ids.map((id) => {
            if (id === "" && group !== "main") return ""
            const pattern = isCharacter ? /^c[0-9a-f]{12}$/ : /^w[0-9a-f]{12}$/
            if (typeof id !== "string" || !pattern.test(id)
                || (isCharacter && seenCharacters.has(id))) {
                throw new TeamCodeError("incompatible")
            }
            if (isCharacter) seenCharacters.add(id)
            return id
        })
    }

    return { title: value.title, active: true, team }
}

export function teamCodeBaseUrl(raw: string | undefined): URL {
    let url: URL
    try {
        url = new URL(raw || "")
    } catch {
        throw new TeamCodeError("unavailable")
    }

    const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)
    const pathname = url.pathname.replace(/\/+$/, "")
    if ((url.protocol !== "https:" && !(url.protocol === "http:" && loopback))
        || url.username
        || url.password
        || url.search
        || url.hash
        || pathname !== "/api/community/game-codes") {
        throw new TeamCodeError("unavailable")
    }
    url.pathname = pathname
    return url
}

export class TeamCodeLimiter {
    private readonly entries = new Map<string, { start: number; count: number }>()

    take(key: string, limit: number, now = Date.now()): boolean {
        for (const [name, entry] of this.entries) {
            if (now - entry.start >= 60_000) this.entries.delete(name)
        }
        const entry = this.entries.get(key)
        if (!entry) {
            if (this.entries.size >= 10_000) return false
            this.entries.set(key, { start: now, count: 1 })
            return true
        }
        if (entry.count >= limit) return false
        entry.count++
        return true
    }
}

export function createTeamCodeClient(options: {
    fetcher?: typeof fetch
    now?: () => number
    url?: () => string | undefined
} = {}) {
    const fetcher = options.fetcher || fetch
    const now = options.now || Date.now
    const cache = new Map<string, { expires: number; value: TeamCodePayload }>()

    return async (code: string): Promise<TeamCodePayload> => {
        if (!GAME_CODE_PATTERN.test(code)) throw new TeamCodeError("not-found")
        const base = teamCodeBaseUrl(
            (options.url || (() => process.env.COMMUNITY_TEAM_CODES_URL))(),
        )
        const key = `${base.href.replace(/\/$/, "")}/${code}`
        const cached = cache.get(key)
        if (cached && cached.expires > now()) return cached.value

        const controller = new AbortController()
        const timer = setTimeout(() => controller.abort(), 3_000)
        try {
            const response = await fetcher(key, {
                headers: { Accept: "application/json" },
                redirect: "error",
                signal: controller.signal,
            })
            if (response.status === 404 || response.status === 410) {
                throw new TeamCodeError("not-found")
            }
            if (!response.ok
                || !response.headers.get("content-type")?.includes("application/json")
                || Number(response.headers.get("content-length")) > 16_384
                || !response.body) {
                throw new TeamCodeError("unavailable")
            }

            const reader = response.body.getReader()
            const chunks: Uint8Array[] = []
            let size = 0
            try {
                while (true) {
                    const part = await reader.read()
                    if (part.done) break
                    size += part.value.length
                    if (size > 16_384) {
                        await reader.cancel()
                        throw new TeamCodeError("unavailable")
                    }
                    chunks.push(part.value)
                }
            } finally {
                reader.releaseLock()
            }

            const raw = JSON.parse(Buffer.concat(chunks).toString("utf8"))
            if (isRecord(raw) && raw.active === false) {
                throw new TeamCodeError("not-found")
            }
            const value = parseTeamCodePayload(raw)
            for (const [name, entry] of cache) {
                if (entry.expires <= now()) cache.delete(name)
            }
            if (cache.size >= 500) {
                const oldest = cache.keys().next().value as string | undefined
                if (oldest !== undefined) cache.delete(oldest)
            }
            cache.set(key, { expires: now() + 5_000, value })
            return value
        } catch (error) {
            throw error instanceof TeamCodeError
                ? error
                : new TeamCodeError("unavailable")
        } finally {
            clearTimeout(timer)
        }
    }
}
