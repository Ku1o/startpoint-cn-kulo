require("ts-node/register");

const assert = require("node:assert");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { performance } = require("node:perf_hooks");

const { GachaMovieVariantCatalog } = require("../src/lib/gacha-movie-variants.ts");

function fixture() {
  return {
    schemaVersion: 1,
    movieId: "normal",
    buckets: {
      "3": { skip: [1], play_no_rarity_up: [2], play_rarity_up: [] },
      "4": { skip: [10, 11], play_no_rarity_up: [20, 21], play_rarity_up: [30, 31] },
      "5": { skip: [], play_no_rarity_up: [], play_rarity_up: [40] },
    },
  };
}

function catalogWithRolls(values, onLoad = () => {}) {
  let rollIndex = 0;
  return new GachaMovieVariantCatalog({
    loadMovie: (movieId) => {
      onLoad(movieId);
      return fixture();
    },
    randomIndex: (maxExclusive) => {
      assert.ok(rollIndex < values.length, `missing random roll ${rollIndex}`);
      const value = values[rollIndex++];
      assert.ok(value < maxExclusive, `roll ${value} must be below ${maxExclusive}`);
      return value;
    },
  });
}

// Natural non-upgrade play/skip outcomes remain distinct when the option is off.
assert.deepStrictEqual(
  catalogWithRolls([2, 0]).select({
    movieId: "normal",
    rarity: 4,
    skipNoRarityUpMovie: false,
  }),
  { seed: 20, moviePlayable: true, rarityUp: false },
);
assert.deepStrictEqual(
  catalogWithRolls([4, 0]).select({
    movieId: "normal",
    rarity: 4,
    skipNoRarityUpMovie: false,
  }),
  { seed: 10, moviePlayable: false, rarityUp: false },
);

// Enabling the option converts a naturally playable non-upgrade outcome to skip.
assert.deepStrictEqual(
  catalogWithRolls([2, 0]).select({
    movieId: "normal",
    rarity: 4,
    skipNoRarityUpMovie: true,
  }),
  { seed: 10, moviePlayable: false, rarityUp: false },
);

// The same upgrade outcome remains unchanged regardless of the option.
for (const skipNoRarityUpMovie of [false, true]) {
  assert.deepStrictEqual(
    catalogWithRolls([0, 1]).select({
      movieId: "normal",
      rarity: 4,
      skipNoRarityUpMovie,
    }),
    { seed: 31, moviePlayable: true, rarityUp: true },
  );
}

// Used and newly rejected seeds are bypassed, including after random retries.
let collisionRoll = 0;
assert.deepStrictEqual(
  new GachaMovieVariantCatalog({
    loadMovie: () => fixture(),
    randomIndex: () => collisionRoll++ === 0 ? 2 : 0,
  }).select({
    movieId: "normal",
    rarity: 4,
    skipNoRarityUpMovie: false,
    usedSeeds: new Set([20]),
    isRejected: (seed) => seed === 20,
  }),
  { seed: 21, moviePlayable: true, rarityUp: false },
);

// Catalog JSON is loaded and validated once per movie, not once per draw.
let loadCount = 0;
const cachedCatalog = catalogWithRolls([2, 0, 2, 1], () => { loadCount += 1; });
cachedCatalog.select({ movieId: "normal", rarity: 4, skipNoRarityUpMovie: false });
cachedCatalog.select({ movieId: "normal", rarity: 4, skipNoRarityUpMovie: false });
assert.strictEqual(loadCount, 1);

const assetDir = path.join(__dirname, "..", "assets", "gacha-movie-variants");
const manifest = JSON.parse(fs.readFileSync(path.join(assetDir, "manifest.json"), "utf8"));
for (const [movieId, movieInfo] of Object.entries(manifest.movies)) {
  const payload = fs.readFileSync(path.join(assetDir, movieInfo.file));
  assert.strictEqual(
    crypto.createHash("sha256").update(payload).digest("hex"),
    movieInfo.sha256,
    `${movieId} payload hash`,
  );
  const data = JSON.parse(payload);
  const seen = new Set();
  let total = 0;
  for (const rarity of ["3", "4", "5"]) {
    for (const kind of ["skip", "play_no_rarity_up", "play_rarity_up"]) {
      assert.strictEqual(data.buckets[rarity][kind].length, movieInfo.counts[rarity][kind]);
      for (const seed of data.buckets[rarity][kind]) {
        assert.ok(Number.isSafeInteger(seed));
        assert.ok(!seen.has(seed), `${movieId} duplicate seed ${seed}`);
        seen.add(seed);
        total += 1;
      }
    }
  }
  assert.strictEqual(total + movieInfo.excludedKnownMismatch, 20_000, `${movieId} seed coverage`);
}

assert.ok(manifest.movies.normal.counts["4"].play_rarity_up > 100);
assert.ok(manifest.movies.fes.counts["4"].play_rarity_up > 100);
assert.ok(manifest.movies.normal.counts["4"].play_no_rarity_up > 100);
assert.ok(manifest.movies.normal.counts["4"].skip > 1_000);

// Hot-path guard with the actual generated catalog: the first selection may
// read/parse one JSON file, while cached selections only index arrays.
let counter = 0;
const benchmarkCatalog = new GachaMovieVariantCatalog({
  catalogDir: assetDir,
  randomIndex: (maxExclusive) => (counter++) % maxExclusive,
});
const firstStarted = performance.now();
assert.ok(benchmarkCatalog.select({
  movieId: "normal",
  rarity: 4,
  skipNoRarityUpMovie: false,
}));
const firstElapsedMs = performance.now() - firstStarted;
const started = performance.now();
for (let index = 0; index < 10_000; index += 1) {
  assert.ok(benchmarkCatalog.select({
    movieId: "normal",
    rarity: 4,
    skipNoRarityUpMovie: index % 2 === 0,
  }));
}
const elapsedMs = performance.now() - started;
assert.ok(firstElapsedMs < 2_000, `first catalog selection took ${firstElapsedMs.toFixed(1)}ms`);
assert.ok(elapsedMs < 2_000, `cached selection took ${elapsedMs.toFixed(1)}ms`);

console.log(
  `gacha_movie_variants tests passed (first=${firstElapsedMs.toFixed(1)}ms, `
  + `cached=${elapsedMs.toFixed(1)}ms/10000 selections)`,
);
