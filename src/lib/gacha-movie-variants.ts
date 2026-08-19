import { randomInt } from "crypto";
import { existsSync, readFileSync } from "fs";
import { join } from "path";

export type GachaMovieVariantKind = "skip" | "play_no_rarity_up" | "play_rarity_up";

interface GachaMovieVariantBuckets {
    skip: number[];
    play_no_rarity_up: number[];
    play_rarity_up: number[];
}

interface GachaMovieVariantFile {
    schemaVersion: number;
    movieId: string;
    buckets: Record<string, GachaMovieVariantBuckets>;
}

export interface GachaMovieVariantSelection {
    seed: number;
    moviePlayable: boolean;
    rarityUp: boolean;
}

export interface GachaMovieVariantSelectOptions {
    movieId: string;
    rarity: number;
    skipNoRarityUpMovie: boolean;
    usedSeeds?: ReadonlySet<number>;
    isRejected?: (seed: number) => boolean;
}

interface GachaMovieVariantCatalogOptions {
    catalogDir?: string;
    randomIndex?: (maxExclusive: number) => number;
    loadMovie?: (movieId: string) => unknown | null;
}

const VARIANT_KINDS: GachaMovieVariantKind[] = [
    "skip",
    "play_no_rarity_up",
    "play_rarity_up",
];
const RANDOM_RETRIES = 16;

function validateSeeds(value: unknown, movieId: string, rarity: string, kind: string): number[] {
    if (!Array.isArray(value)) {
        throw new Error(`invalid gacha movie catalog bucket: ${movieId} rarity=${rarity} kind=${kind}`);
    }
    for (const seed of value) {
        if (!Number.isSafeInteger(seed)) {
            throw new Error(`invalid gacha movie catalog seed: ${movieId} rarity=${rarity} kind=${kind}`);
        }
    }
    return value as number[];
}

function validateCatalog(value: unknown, expectedMovieId: string): GachaMovieVariantFile {
    if (typeof value !== "object" || value === null) {
        throw new Error(`invalid gacha movie catalog: ${expectedMovieId}`);
    }

    const catalog = value as Partial<GachaMovieVariantFile>;
    if (catalog.schemaVersion !== 1 || catalog.movieId !== expectedMovieId
        || typeof catalog.buckets !== "object" || catalog.buckets === null) {
        throw new Error(`unsupported gacha movie catalog: ${expectedMovieId}`);
    }

    for (const rarity of ["3", "4", "5"]) {
        const buckets = catalog.buckets[rarity];
        if (typeof buckets !== "object" || buckets === null) {
            throw new Error(`missing gacha movie catalog rarity: ${expectedMovieId} rarity=${rarity}`);
        }
        for (const kind of VARIANT_KINDS) {
            validateSeeds(buckets[kind], expectedMovieId, rarity, kind);
        }
    }

    return catalog as GachaMovieVariantFile;
}

export class GachaMovieVariantCatalog {
    private readonly catalogDir: string;
    private readonly randomIndex: (maxExclusive: number) => number;
    private readonly loadMovieOverride?: (movieId: string) => unknown | null;
    private readonly cache = new Map<string, GachaMovieVariantFile | null>();

    constructor(options: GachaMovieVariantCatalogOptions = {}) {
        this.catalogDir = options.catalogDir
            ?? join(__dirname, "..", "..", "assets", "gacha-movie-variants");
        this.randomIndex = options.randomIndex ?? ((maxExclusive) => randomInt(maxExclusive));
        this.loadMovieOverride = options.loadMovie;
    }

    private load(movieId: string): GachaMovieVariantFile | null {
        if (this.cache.has(movieId)) return this.cache.get(movieId)!;

        let raw: unknown | null;
        if (this.loadMovieOverride) {
            raw = this.loadMovieOverride(movieId);
        } else {
            const file = join(this.catalogDir, `${movieId}.json`);
            raw = existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : null;
        }

        const catalog = raw === null ? null : validateCatalog(raw, movieId);
        this.cache.set(movieId, catalog);
        return catalog;
    }

    private roll(maxExclusive: number): number {
        const value = this.randomIndex(maxExclusive);
        if (!Number.isInteger(value) || value < 0 || value >= maxExclusive) {
            throw new Error(`gacha movie random index out of range: ${value}/${maxExclusive}`);
        }
        return value;
    }

    private pickSeed(
        pool: number[],
        usedSeeds: ReadonlySet<number>,
        isRejected: (seed: number) => boolean
    ): number | null {
        if (pool.length === 0) return null;

        for (let attempt = 0; attempt < RANDOM_RETRIES; attempt += 1) {
            const seed = pool[this.roll(pool.length)];
            if (!usedSeeds.has(seed) && !isRejected(seed)) return seed;
        }

        // Only reached after repeated collisions. The normal request path never
        // scans the catalog; a ten-pull generally succeeds during the retries.
        const start = this.roll(pool.length);
        for (let offset = 0; offset < pool.length; offset += 1) {
            const seed = pool[(start + offset) % pool.length];
            if (!usedSeeds.has(seed) && !isRejected(seed)) return seed;
        }
        return null;
    }

    select(options: GachaMovieVariantSelectOptions): GachaMovieVariantSelection | null {
        const catalog = this.load(options.movieId);
        const buckets = catalog?.buckets[String(options.rarity)];
        if (!buckets) return null;

        const upgradeCount = buckets.play_rarity_up.length;
        const noUpgradeCount = buckets.skip.length + buckets.play_no_rarity_up.length;
        const total = upgradeCount + noUpgradeCount;
        if (total === 0) return null;

        // The rarity-up decision is independent from the client option. The
        // option only changes how a non-upgrade outcome is presented.
        const useRarityUp = this.roll(total) < upgradeCount;
        const preferredKind: GachaMovieVariantKind = useRarityUp
            ? "play_rarity_up"
            : options.skipNoRarityUpMovie ? "skip" : "play_no_rarity_up";
        const fallbackKind: GachaMovieVariantKind = options.skipNoRarityUpMovie
            ? "play_no_rarity_up"
            : "skip";
        const kinds: GachaMovieVariantKind[] = useRarityUp
            ? [preferredKind, fallbackKind, options.skipNoRarityUpMovie ? "skip" : "play_no_rarity_up"]
            : [preferredKind, fallbackKind];
        const usedSeeds = options.usedSeeds ?? new Set<number>();
        const isRejected = options.isRejected ?? (() => false);

        for (const kind of kinds) {
            const seed = this.pickSeed(buckets[kind], usedSeeds, isRejected);
            if (seed === null) continue;
            return {
                seed,
                moviePlayable: kind !== "skip",
                rarityUp: kind === "play_rarity_up",
            };
        }
        return null;
    }
}

const defaultCatalog = new GachaMovieVariantCatalog();

export default defaultCatalog;
