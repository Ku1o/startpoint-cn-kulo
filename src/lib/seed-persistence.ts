import { join } from "path";
import { Worker } from "worker_threads";
import type { SeedTag } from "./seed-validator";
import { recordSettlementPhase } from "./settlement-performance";
import { observeWorkerMemory, registerMemoryCounters } from "./memory-diagnostics";
let persistenceSequence = 0;

export interface PersistedPlaySeed { r: number; tag: SeedTag; play?: boolean }
export interface PersistedSeedPool {
    confirmPool: Map<number, number | null>;
    pendingPool: Map<number, number | null>;
    playPool: Map<number, PersistedPlaySeed>;
    verifiedPool: Map<number, number>;
}
export interface SeedUpdate {
    movieId: string;
    seed: number;
    confirmed: number | null | undefined;
    pending: number | null | undefined;
    play: PersistedPlaySeed | undefined;
    verified: number | undefined;
}
interface WriteResult { revision: number; elapsedMs: number; writes: number; error?: string }

/** Keeps only changed seeds on the request thread; one worker owns disk writes. */
export class SeedPersistence {
    private worker: Worker | null = null;
    private pending = new Map<string, SeedUpdate>();
    private inFlight: { revision: number; updates: SeedUpdate[] } | null = null;
    private revision = 0;
    private savedRevision = 0;
    private timer: NodeJS.Timeout | null = null;
    private closed = false;
    private lastErrorLogAt = 0;
    private waiters: { revision: number; resolve: () => void; reject: (error: Error) => void }[] = [];
    private unregisterMetrics: () => void;

    constructor(
        private directory: string,
        private snapshot: () => Map<string, PersistedSeedPool>,
        private delayMs = 1000,
    ) {
        this.unregisterMetrics = registerMemoryCounters(`seedQueue${++persistenceSequence}`, () => ({
            pendingUpdates: this.pending.size, inFlightUpdates: this.inFlight?.updates.length ?? 0,
            waiters: this.waiters.length, revision: this.revision, savedRevision: this.savedRevision,
            workerAvailable: this.worker !== null,
        }));
        this.startWorker(false);
    }

    private startWorker(recover: boolean): void {
        const typescript = __filename.endsWith(".ts");
        const worker = new Worker(join(__dirname, `seed-persistence-worker.${typescript ? "ts" : "js"}`), {
            workerData: { directory: this.directory, pools: this.snapshot(), recover },
            ...(typescript ? { execArgv: ["-r", require.resolve("ts-node/register/transpile-only")] } : {}),
        });
        this.worker = worker;
        observeWorkerMemory("seedPersistence", worker);
        worker.on("message", (result: WriteResult) => {
            if (!Number.isSafeInteger(result.revision)) return;
            if (this.worker !== worker || result.revision !== this.inFlight?.revision) return;
            recordSettlementPhase("gacha", "seed_write_worker", result.elapsedMs);
            if (result.error) { this.failed(new Error(result.error)); return; }
            this.savedRevision = result.revision;
            this.inFlight = null;
            const waiting = this.waiters;
            this.waiters = [];
            for (const waiter of waiting) {
                if (waiter.revision <= this.savedRevision) waiter.resolve();
                else this.waiters.push(waiter);
            }
            if (this.waiters.length > 0) this.dispatch();
            else if (this.pending.size > 0) this.schedule();
            else worker.unref();
        });
        const lost = (error: Error) => {
            if (this.worker !== worker) return;
            this.worker = null;
            this.failed(error);
        };
        worker.on("error", lost);
        worker.on("exit", code => {
            if (!this.closed) lost(new Error(`seed persistence worker exited (${code})`));
        });
        worker.unref();
    }

    update(update: SeedUpdate): void {
        if (this.closed) throw new Error("seed persistence is closed");
        this.revision += 1;
        this.pending.set(`${update.movieId}:${update.seed}`, update);
        this.worker?.ref();
        this.schedule();
    }

    private schedule(): void {
        if (this.closed || this.timer || this.inFlight || this.pending.size === 0) return;
        // Keep the process alive until pending records are durably acknowledged.
        this.timer = setTimeout(() => { this.timer = null; this.dispatch(); }, this.delayMs);
    }

    private dispatch(): void {
        if (this.inFlight || this.pending.size === 0 || this.closed) return;
        if (this.timer) { clearTimeout(this.timer); this.timer = null; }
        try {
            if (!this.worker) this.startWorker(true);
            this.inFlight = { revision: this.revision, updates: [...this.pending.values()] };
            this.pending.clear();
            this.worker!.ref();
            this.worker!.postMessage(this.inFlight);
        } catch (error) {
            this.failed(error instanceof Error ? error : new Error(String(error)));
        }
    }

    private failed(error: Error): void {
        if (this.inFlight) {
            for (const update of this.inFlight.updates) {
                const key = `${update.movieId}:${update.seed}`;
                if (!this.pending.has(key)) this.pending.set(key, update);
            }
            this.inFlight = null;
        }
        for (const waiter of this.waiters) waiter.reject(error);
        this.waiters = [];
        if (Date.now() - this.lastErrorLogAt >= 60_000) {
            console.error("[SEED] persistence failed; retaining changes for retry", error);
            this.lastErrorLogAt = Date.now();
        }
        this.schedule();
    }

    /** Barrier for admin changes, verified corrections and orderly shutdown. */
    flush(): Promise<void> {
        if (this.savedRevision >= this.revision) return Promise.resolve();
        return new Promise((resolve, reject) => {
            this.waiters.push({ revision: this.revision, resolve, reject });
            this.dispatch();
        });
    }

    async close(): Promise<void> {
        try { await this.flush(); }
        finally {
            this.closed = true;
            this.unregisterMetrics();
            if (this.timer) clearTimeout(this.timer);
            const worker = this.worker;
            this.worker = null;
            if (worker) await worker.terminate();
        }
    }
}
