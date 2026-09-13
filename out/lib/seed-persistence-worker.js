"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const worker_threads_1 = require("worker_threads");
const path_1 = require("path");
const perf_hooks_1 = require("perf_hooks");
const atomic_json_file_1 = require("./atomic-json-file");
const { directory, pools, recover } = worker_threads_1.workerData;
const dirty = new Set(recover ? ["confirmed", "purified", "verified"] : []);
function updateMap(map, seed, value) {
    if (value === undefined)
        return map.delete(seed);
    const previous = map.get(seed);
    if (previous === value || (typeof value === "object" && value !== null
        && JSON.stringify(previous) === JSON.stringify(value)))
        return false;
    map.set(seed, value);
    return true;
}
function apply(update) {
    let pool = pools.get(update.movieId);
    if (!pool) {
        pool = { confirmPool: new Map(), pendingPool: new Map(), playPool: new Map(), verifiedPool: new Map() };
        pools.set(update.movieId, pool);
    }
    const confirmed = updateMap(pool.confirmPool, update.seed, update.confirmed);
    const pending = updateMap(pool.pendingPool, update.seed, update.pending);
    if (confirmed || pending)
        dirty.add("confirmed");
    if (updateMap(pool.playPool, update.seed, update.play))
        dirty.add("purified");
    if (updateMap(pool.verifiedPool, update.seed, update.verified))
        dirty.add("verified");
}
function serialize(kind) {
    const value = {};
    for (const [movieId, pool] of pools) {
        value[movieId] = Object.fromEntries(kind === "confirmed" ? pool.confirmPool
            : kind === "purified" ? pool.playPool : pool.verifiedPool);
        if (kind === "confirmed")
            value[`${movieId}_pend`] = Object.fromEntries(pool.pendingPool);
    }
    return value;
}
worker_threads_1.parentPort.on("message", ({ revision, updates }) => {
    const startedAt = perf_hooks_1.performance.now();
    let writes = 0;
    try {
        for (const update of updates)
            apply(update);
        for (const kind of dirty) {
            (0, atomic_json_file_1.writeJsonAtomicSync)((0, path_1.join)(directory, `${kind}_seeds.json`), serialize(kind));
            dirty.delete(kind);
            writes += 1;
        }
        worker_threads_1.parentPort.postMessage({ revision, writes, elapsedMs: perf_hooks_1.performance.now() - startedAt });
    }
    catch (error) {
        // Dirty files remain queued; an acknowledged write is never discarded.
        worker_threads_1.parentPort.postMessage({ revision, writes, elapsedMs: perf_hooks_1.performance.now() - startedAt,
            error: error instanceof Error ? error.message : String(error) });
    }
});
