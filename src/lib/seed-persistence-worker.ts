import { parentPort, workerData } from "worker_threads";
import { join } from "path";
import { performance } from "perf_hooks";
import { writeJsonAtomicSync } from "./atomic-json-file";
import type { PersistedSeedPool, SeedUpdate } from "./seed-persistence";

const { directory, pools, recover } = workerData as {
    directory: string;
    pools: Map<string, PersistedSeedPool>;
    recover: boolean;
};
type FileKind = "confirmed" | "purified" | "verified";
const dirty = new Set<FileKind>(recover ? ["confirmed", "purified", "verified"] : []);

function updateMap<T>(map: Map<number, T>, seed: number, value: T | undefined): boolean {
    if (value === undefined) return map.delete(seed);
    const previous = map.get(seed);
    if (previous === value || (typeof value === "object" && value !== null
        && JSON.stringify(previous) === JSON.stringify(value))) return false;
    map.set(seed, value);
    return true;
}

function apply(update: SeedUpdate): void {
    let pool = pools.get(update.movieId);
    if (!pool) {
        pool = { confirmPool: new Map(), pendingPool: new Map(), playPool: new Map(), verifiedPool: new Map() };
        pools.set(update.movieId, pool);
    }
    const confirmed = updateMap(pool.confirmPool, update.seed, update.confirmed);
    const pending = updateMap(pool.pendingPool, update.seed, update.pending);
    if (confirmed || pending) dirty.add("confirmed");
    if (updateMap(pool.playPool, update.seed, update.play)) dirty.add("purified");
    if (updateMap(pool.verifiedPool, update.seed, update.verified)) dirty.add("verified");
}

function serialize(kind: FileKind): Record<string, unknown> {
    const value: Record<string, unknown> = {};
    for (const [movieId, pool] of pools) {
        value[movieId] = Object.fromEntries<unknown>(kind === "confirmed" ? pool.confirmPool
            : kind === "purified" ? pool.playPool : pool.verifiedPool);
        if (kind === "confirmed") value[`${movieId}_pend`] = Object.fromEntries(pool.pendingPool);
    }
    return value;
}

parentPort!.on("message", ({ revision, updates }: { revision: number; updates: SeedUpdate[] }) => {
    const startedAt = performance.now();
    let writes = 0;
    try {
        for (const update of updates) apply(update);
        for (const kind of dirty) {
            writeJsonAtomicSync(join(directory, `${kind}_seeds.json`), serialize(kind));
            dirty.delete(kind);
            writes += 1;
        }
        parentPort!.postMessage({ revision, writes, elapsedMs: performance.now() - startedAt });
    } catch (error) {
        // Dirty files remain queued; an acknowledged write is never discarded.
        parentPort!.postMessage({ revision, writes, elapsedMs: performance.now() - startedAt,
            error: error instanceof Error ? error.message : String(error) });
    }
});
