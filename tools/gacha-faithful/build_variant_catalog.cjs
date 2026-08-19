"use strict";

// Build the runtime gacha movie catalog offline. The server must never run the
// physics predictor on a request path; it only loads these pre-classified
// buckets and selects an array element.

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const world = require("./world.cjs");

const ROOT = path.join(__dirname, "..", "..");
const ASSETS = path.join(ROOT, "assets");
const OUTPUT_DIR = path.join(ASSETS, "gacha-movie-variants");
const VERIFIED_FILE = path.join(ASSETS, "verified_seeds.json");
const PREDICTOR_FILE = path.join(__dirname, "world.cjs");
const MOVIES = ["normal", "normal_guarantee", "fes", "fes_guarantee"];
const SEED_START = 10_000_000;
const SEED_END = 10_019_999;

function sha256(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

function emptyBuckets() {
  return {
    "3": { skip: [], play_no_rarity_up: [], play_rarity_up: [] },
    "4": { skip: [], play_no_rarity_up: [], play_rarity_up: [] },
    "5": { skip: [], play_no_rarity_up: [], play_rarity_up: [] },
  };
}

function loadVerifiedRarities() {
  if (!fs.existsSync(VERIFIED_FILE)) return {};
  return JSON.parse(fs.readFileSync(VERIFIED_FILE, "utf8"));
}

function simulate(seed, movieId) {
  const sim = world.initField(seed, movieId);
  const initialRarity = sim.ball.rarity;
  let guard = 0;
  if (sim.moviePlayable) {
    while (!sim.finished && guard < 20_000) {
      world.worldStep(sim);
      guard += 1;
    }
    if (!sim.finished) {
      throw new Error(`gacha simulation did not finish: movie=${movieId} seed=${seed}`);
    }
  }
  return {
    initialRarity,
    finalRarity: sim.ball.rarity,
    moviePlayable: sim.moviePlayable,
  };
}

function classify(result) {
  if (!result.moviePlayable) return "skip";
  return result.finalRarity > result.initialRarity
    ? "play_rarity_up"
    : "play_no_rarity_up";
}

function summarize(buckets) {
  return Object.fromEntries(Object.entries(buckets).map(([rarity, variants]) => [
    rarity,
    Object.fromEntries(Object.entries(variants).map(([kind, seeds]) => [kind, seeds.length])),
  ]));
}

function buildMovie(movieId, verifiedRarities, predictorSha256) {
  const buckets = emptyBuckets();
  let excludedKnownMismatch = 0;

  for (let seed = SEED_START; seed <= SEED_END; seed += 1) {
    const result = simulate(seed, movieId);
    const actualRarityIndex = verifiedRarities?.[movieId]?.[String(seed)];
    if (Number.isInteger(actualRarityIndex) && actualRarityIndex !== result.finalRarity) {
      excludedKnownMismatch += 1;
      continue;
    }

    const rarity = String(result.finalRarity + 3);
    buckets[rarity][classify(result)].push(seed);
  }

  return {
    schemaVersion: 1,
    movieId,
    seedRange: { start: SEED_START, end: SEED_END },
    predictorSha256,
    excludedKnownMismatch,
    buckets,
  };
}

function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const verifiedRarities = loadVerifiedRarities();
  const predictorSha256 = sha256(fs.readFileSync(PREDICTOR_FILE));
  const manifest = {
    schemaVersion: 1,
    seedRange: { start: SEED_START, end: SEED_END },
    predictorSha256,
    movies: {},
  };

  for (const movieId of MOVIES) {
    const catalog = buildMovie(movieId, verifiedRarities, predictorSha256);
    const payload = `${JSON.stringify(catalog)}\n`;
    const output = path.join(OUTPUT_DIR, `${movieId}.json`);
    fs.writeFileSync(output, payload, "utf8");
    manifest.movies[movieId] = {
      file: `${movieId}.json`,
      sha256: sha256(Buffer.from(payload)),
      excludedKnownMismatch: catalog.excludedKnownMismatch,
      counts: summarize(catalog.buckets),
    };
    console.log(movieId, JSON.stringify(manifest.movies[movieId].counts));
  }

  fs.writeFileSync(
    path.join(OUTPUT_DIR, "manifest.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );
}

main();
