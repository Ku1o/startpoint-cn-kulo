import { createHash, randomUUID } from "crypto"
import { closeSync, copyFileSync, existsSync, fsyncSync, openSync, readFileSync, readSync,
    renameSync, unlinkSync, writeFileSync } from "fs"
import { basename, dirname, join } from "path"
import type { PersistedSeedPool } from "./seed-persistence"

export type SeedFileKind = "confirmed" | "purified" | "verified"
const verifiedFiles = new Map<string, string>()
const CHUNK_BYTES = 64 * 1024

/** Encode entries directly instead of building a second copy of every seed map. */
export function* seedJsonChunks(pools: Map<string, PersistedSeedPool>, kind: SeedFileKind): Generator<string> {
    let chunk = "{", firstPool = true
    for (const [movie, pool] of pools) {
        const maps: Array<[string, Map<number, unknown>]> = kind === "confirmed"
            ? [[movie, pool.confirmPool], [`${movie}_pend`, pool.pendingPool]]
            : [[movie, kind === "purified" ? pool.playPool : pool.verifiedPool]]
        for (const [name, entries] of maps) {
            chunk += `${firstPool ? "" : ","}${JSON.stringify(name)}:{`
            firstPool = false
            let firstSeed = true
            for (const [seed, value] of entries) {
                const encoded = JSON.stringify(value)
                if (encoded === undefined) continue
                chunk += `${firstSeed ? "" : ","}${JSON.stringify(String(seed))}:${encoded}`
                firstSeed = false
                if (chunk.length >= CHUNK_BYTES) { yield chunk; chunk = "" }
            }
            chunk += "}"
        }
    }
    yield chunk + "}"
}
function digestFile(file: string): string {
    const fd = openSync(file, "r"), buffer = Buffer.allocUnsafe(CHUNK_BYTES), hash = createHash("sha256")
    try {
        for (;;) {
            const length = readSync(fd, buffer, 0, buffer.length, null)
            if (length === 0) break
            hash.update(buffer.subarray(0, length))
        }
        return hash.digest("hex")
    } finally { closeSync(fd) }
}
function removeTemporary(file: string): void {
    try { if (existsSync(file)) unlinkSync(file) } catch { /* retain the original error */ }
}
/** Same primary + .bak contract, bounded serialization/readback allocation. */
export function writeSeedJsonAtomicSync(file: string, pools: Map<string, PersistedSeedPool>, kind: SeedFileKind): number {
    const prefix = join(dirname(file), `.${basename(file)}.${process.pid}.${randomUUID()}`)
    const temporary = `${prefix}.tmp`, backupTemporary = `${prefix}.bak.tmp`, backup = `${file}.bak`
    let fd: number | null = null, bytes = 0
    try {
        fd = openSync(temporary, "wx")
        const expected = createHash("sha256")
        for (const chunk of seedJsonChunks(pools, kind)) {
            const buffer = Buffer.from(chunk, "utf8")
            writeFileSync(fd, buffer)
            expected.update(buffer); bytes += buffer.length
        }
        fsyncSync(fd); closeSync(fd); fd = null
        const digest = expected.digest("hex")
        if (digestFile(temporary) !== digest) throw new Error("Seed file readback checksum mismatch")
        if (existsSync(file)) {
            let valid = false
            let previous = ""
            try {
                previous = digestFile(file)
                if (verifiedFiles.get(file) === previous) valid = true
                else {
                    // First write after startup or externally replaced content:
                    // establish JSON validity before replacing a known-good backup.
                    const raw = readFileSync(file)
                    JSON.parse(raw.toString("utf8"))
                    valid = createHash("sha256").update(raw).digest("hex") === previous
                }
            } catch { valid = false }
            if (valid) {
                copyFileSync(file, backupTemporary)
                if (digestFile(backupTemporary) !== previous) throw new Error("Seed backup changed during copy")
                const backupFd = openSync(backupTemporary, "r+")
                try { fsyncSync(backupFd) } finally { closeSync(backupFd) }
                try { renameSync(backupTemporary, backup) }
                catch (error) {
                    if (!existsSync(backup)) throw error
                    unlinkSync(backup); renameSync(backupTemporary, backup)
                }
            }
        }
        renameSync(temporary, file)
        verifiedFiles.delete(file); verifiedFiles.set(file, digest)
        if (verifiedFiles.size > 16) verifiedFiles.delete(verifiedFiles.keys().next().value!)
        return bytes
    } finally {
        if (fd !== null) closeSync(fd)
        removeTemporary(temporary); removeTemporary(backupTemporary)
    }
}
