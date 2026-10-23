import { readdirSync, readFileSync, statSync } from "fs"
import { join } from "path"

interface CountEntry { signature: string; count: number; catalog: SeedCatalog }
export interface SeedFileCounts { total: number; byMovie: ReadonlyMap<string, number>; catalogs: ReadonlyMap<string, SeedCatalog> }

/** Exact membership with compact numeric storage, never a permanent JS Set.
 * Current four catalogs use 3.28 MiB of Uint32Array storage in total.
 */
export class SeedCatalog {
    constructor(private readonly values: Uint32Array | Float64Array, readonly valid: boolean) {}
    get size(): number { return this.values.length }
    get byteLength(): number { return this.values.byteLength }
    has(seed: number): boolean {
        if (!Number.isSafeInteger(seed)) return false
        let low = 0, high = this.values.length - 1
        while (low <= high) {
            const middle = Math.floor((low + high) / 2), value = this.values[middle]
            if (value === seed) return true
            if (value < seed) low = middle + 1
            else high = middle - 1
        }
        return false
    }
}

function catalogFrom(data: unknown): { count: number; catalog: SeedCatalog } {
    let count = 0, validCount = 0, uint32 = true, valid = !!data && typeof data === "object" && !Array.isArray(data)
    const arrays: unknown[][] = []
    if (data && typeof data === "object") for (const group of Object.values(data)) {
        if (!group || typeof group !== "object" || Array.isArray(group)) { valid = false; continue }
        for (const seeds of Object.values(group)) {
            if (!Array.isArray(seeds)) { valid = false; continue }
            arrays.push(seeds); count += seeds.length
            for (const seed of seeds) {
                if (typeof seed !== "number" || !Number.isSafeInteger(seed) || seed < 0) { valid = false; continue }
                validCount++; if (seed > 0xffffffff) uint32 = false
            }
        }
    }
    const values = uint32 ? new Uint32Array(validCount) : new Float64Array(validCount)
    let index = 0
    for (const seeds of arrays) for (const seed of seeds) if (typeof seed === "number" && Number.isSafeInteger(seed) && seed >= 0) values[index++] = seed
    values.sort()
    let unique = 0
    for (let read = 0; read < values.length; read++) if (unique === 0 || values[read] !== values[unique - 1]) values[unique++] = values[read]
    return { count, catalog: new SeedCatalog(unique === values.length ? values : values.slice(0, unique), valid) }
}

/** Only static movie seed files are cached. Live learned pools always come from
 * SeedValidator's current maps, not from its asynchronous persistence files.
 */
export class SeedFileCountCache {
    private readonly files = new Map<string, CountEntry>()
    constructor(private readonly directory: string) {}

    snapshot(): SeedFileCounts {
        const byMovie = new Map<string, number>(), catalogs = new Map<string, SeedCatalog>(), present = new Set<string>()
        let filenames: string[]
        try { filenames = readdirSync(this.directory) } catch { this.files.clear(); return { total: 19941, byMovie, catalogs } }
        for (const filename of filenames) {
            const match = /^gacha_movie_seeds_([a-z0-9_]+)\.json$/i.exec(filename)
            if (!match) continue
            present.add(filename)
            const file = join(this.directory, filename)
            try {
                // ctime/inode also catch atomic replacement or preserved mtime.
                const stat = statSync(file, { bigint: true })
                const signature = `${stat.dev}:${stat.ino}:${stat.size}:${stat.mtimeNs}:${stat.ctimeNs}`
                let entry = this.files.get(filename)
                if (!entry || entry.signature !== signature) {
                    let counted = { count: 0, catalog: new SeedCatalog(new Uint32Array(), false) }
                    try {
                        counted = catalogFrom(JSON.parse(readFileSync(file, "utf8")))
                    } catch { /* An unchanged invalid file contributes zero until replaced. */ }
                    entry = { signature, ...counted }; this.files.set(filename, entry)
                }
                byMovie.set(match[1], entry.count)
                catalogs.set(match[1], entry.catalog)
            } catch { this.files.delete(filename) }
        }
        for (const filename of this.files.keys()) if (!present.has(filename)) this.files.delete(filename)
        const count = [...byMovie.values()].reduce((sum, value) => sum + value, 0)
        return { total: count > 0 ? count : 19941, byMovie, catalogs }
    }
}
