"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
var _a, _b, _c;
Object.defineProperty(exports, "__esModule", { value: true });
const file_exists_1 = require("./lib/file-exists");
const fastify_1 = __importDefault(require("fastify"));
const msgpackr_1 = require("msgpackr");
const cn_response_hook_1 = require("./lib/cn-response-hook");
const static_1 = __importDefault(require("@fastify/static"));
const path_1 = __importDefault(require("path"));
const fs_1 = require("fs");
const atomic_json_file_1 = require("./lib/atomic-json-file");
const storage_layout_1 = require("./lib/storage-layout");
const utils_1 = require("./utils");
const activeAccount_1 = require("./data/activeAccount");
const session_1 = require("./data/domains/session");
const management_auth_1 = require("./lib/management-auth");
const route_performance_1 = require("./lib/route-performance");
const online_presence_1 = require("./lib/online-presence");
const takeover_access_1 = require("./lib/takeover-access");
const player_login_1 = require("./lib/player-login");
const playerLogin_1 = __importStar(require("./routes/cn/playerLogin"));
const client_admission_1 = require("./lib/client-admission");
const SessionManager_1 = require("./multi/state/SessionManager");
const state_1 = require("./lounge/state");
const local_client_compat_1 = require("./lib/local-client-compat");
const version_1 = require("./lib/version");
const custom_cdn_resource_routes_1 = require("./lib/custom-cdn-resource-routes");
const versionCheck_1 = __importDefault(require("./routes/cn/versionCheck"));
const ios_leiting_1 = __importDefault(require("./routes/cn/ios-leiting"));
const leitingAuth_1 = __importDefault(require("./routes/cn/leitingAuth"));
const tool_1 = __importDefault(require("./routes/cn/tool"));
const load_1 = __importDefault(require("./routes/cn/load"));
const asset_1 = __importDefault(require("./routes/cn/asset"));
const takeOver_1 = __importDefault(require("./routes/cn/takeOver"));
const web_1 = __importDefault(require("./routes/web"));
const web_api_1 = __importDefault(require("./routes/web_api"));
const seeds_1 = __importDefault(require("./routes/web_api/seeds"));
const modAdmin_1 = __importDefault(require("./routes/api/modAdmin"));
const seed_validator_1 = __importDefault(require("./lib/seed-validator"));
const reproduce_1 = __importDefault(require("./routes/api/reproduce"));
const tutorial_1 = __importDefault(require("./routes/api/tutorial"));
const gacha_1 = __importDefault(require("./routes/api/gacha"));
const party_1 = __importDefault(require("./routes/api/party"));
const expod_1 = __importDefault(require("./routes/api/expod"));
const storyQuest_1 = __importDefault(require("./routes/api/storyQuest"));
const option_1 = __importDefault(require("./routes/api/option"));
const singleBattleQuest_1 = __importDefault(require("./routes/api/singleBattleQuest"));
const quest_1 = __importDefault(require("./routes/api/quest"));
const multi_1 = require("./multi");
const attention_1 = __importDefault(require("./routes/api/attention"));
const character_1 = __importDefault(require("./routes/api/character"));
const mana_1 = __importDefault(require("./routes/api/character/mana"));
const bond_1 = __importDefault(require("./routes/api/character/bond"));
const partyGroup_1 = __importDefault(require("./routes/api/partyGroup"));
const equipment_1 = __importDefault(require("./routes/api/equipment"));
const sell_1 = __importDefault(require("./routes/api/sell"));
const exBoost_1 = __importDefault(require("./routes/api/exBoost"));
const boxGacha_1 = __importDefault(require("./routes/api/boxGacha"));
const shop_1 = __importDefault(require("./routes/api/shop"));
const exchange_1 = __importDefault(require("./routes/api/exchange"));
const encyclopedia_1 = __importDefault(require("./routes/api/encyclopedia"));
const mail_1 = __importDefault(require("./routes/api/mail"));
const rankingEvent_1 = __importDefault(require("./routes/api/rankingEvent"));
const mission_1 = __importDefault(require("./routes/api/mission"));
const activeMission_1 = __importDefault(require("./routes/api/activeMission"));
const passCard_1 = __importDefault(require("./routes/api/passCard"));
const payment_1 = __importDefault(require("./routes/api/payment"));
const news_1 = __importDefault(require("./routes/api/news"));
const raidEvent_1 = __importDefault(require("./routes/api/raidEvent"));
const rushEvent_1 = __importDefault(require("./routes/api/rushEvent"));
const abyssRecords_1 = __importDefault(require("./routes/cn/abyssRecords"));
const carnivalEvent_1 = __importDefault(require("./routes/api/carnivalEvent"));
const howToGet_1 = __importDefault(require("./routes/api/howToGet"));
const contentsGuide_1 = __importDefault(require("./routes/api/contentsGuide"));
const profile_1 = __importDefault(require("./routes/api/profile"));
const follow_1 = __importDefault(require("./routes/api/follow"));
const sns_1 = __importDefault(require("./routes/api/sns"));
const history_1 = __importDefault(require("./routes/api/history"));
const playerHistory_1 = __importDefault(require("./routes/api/playerHistory"));
const comic_1 = __importDefault(require("./routes/api/comic"));
const questUnlock_1 = __importDefault(require("./routes/api/questUnlock"));
const item_1 = __importDefault(require("./routes/api/item"));
const lounge_1 = __importDefault(require("./routes/api/lounge"));
const multiSpecialExchange_1 = __importDefault(require("./routes/api/multiSpecialExchange"));
const player_party_pool_1 = require("./multi/npc/player-party-pool");
const ios_compat_1 = require("./lib/ios-compat");
const db_1 = require("./data/db");
const receive_history_retention_1 = require("./lib/receive-history-retention");
const settlement_1 = require("./lib/leaderboard/settlement");
const daily_vmoney_mail_1 = require("./lib/daily-vmoney-mail");
const sqlite_checkpoint_worker_1 = require("./lib/sqlite-checkpoint-worker");
const persistence_coordinator_1 = require("./lib/persistence-coordinator");
const sqlite_persistence_worker_1 = require("./lib/sqlite-persistence-worker");
const fastify = (0, fastify_1.default)({
    logger: {
        // Default remains compatible with the existing development behavior.
        // Startup BAT files may set LOG_LEVEL=warn to suppress per-request
        // Fastify access logs during normal low-overhead operation.
        level: process.env.LOG_LEVEL || "info"
    },
    bodyLimit: 262144 // 256KB — covers /single_battle_quest/finish large battle stats
});
(0, local_client_compat_1.installLocalClientCompat)(fastify, process.env.CN_LOCAL_CLIENT_PLATFORM || ((0, version_1.getPatchManifest)().patches.some(p => p.enabled && p.local_test_only
    && p.required_local_platform === "android") ? "android" : undefined));
(0, route_performance_1.installRoutePerformanceMonitor)(fastify);
// Viewer IDs >= 900,000,000 are interpreted as COM/AI members by the
// multiplayer protocol. Repair legacy human sessions before rooms can open.
const migratedUnsafeViewerIds = (0, session_1.migrateUnsafeViewerIdsSync)();
if (migratedUnsafeViewerIds > 0) {
    console.log(`[MULTI] migrated ${migratedUnsafeViewerIds} legacy viewer ID(s) out of the COM range`);
}
// Restore saved time offset from active player on startup
(0, activeAccount_1.restoreTimeOffset)();
// Game endpoints remain public; only the legacy management pages and their
// management APIs are protected by the password session below.
(0, management_auth_1.installManagementAuth)(fastify);
// Simple in-memory rate limiter for /crash endpoint only.
// /debug is excluded — game client sends heavy beacon traffic during normal startup.
const rateLimitMap = new Map();
const RATE_LIMIT_MAX = 30;
const RATE_LIMIT_WINDOW = 60000;
// A hostile client can rotate source IPs; expiry alone must not make this map
// grow for the lifetime of the process.
const RATE_LIMIT_MAP_MAX = 4096;
let nextRateLimitSweep = 0;
fastify.addHook("onRequest", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
    var _d, _e;
    if (request.url === "/crash") {
        const ip = ((_e = (_d = request.headers["x-forwarded-for"]) === null || _d === void 0 ? void 0 : _d.split(",")[0]) === null || _e === void 0 ? void 0 : _e.trim())
            || request.ip;
        const now = Date.now();
        if (now >= nextRateLimitSweep) {
            for (const [key, value] of rateLimitMap) {
                if (value.reset <= now)
                    rateLimitMap.delete(key);
            }
            nextRateLimitSweep = now + RATE_LIMIT_WINDOW;
        }
        const existing = rateLimitMap.get(ip);
        if (!existing && rateLimitMap.size >= RATE_LIMIT_MAP_MAX) {
            return reply.status(429).send("Too Many Requests");
        }
        const entry = existing || { count: 0, reset: now + RATE_LIMIT_WINDOW };
        if (now > entry.reset) {
            entry.count = 0;
            entry.reset = now + RATE_LIMIT_WINDOW;
        }
        if (++entry.count > RATE_LIMIT_MAX) {
            return reply.status(429).send("Too Many Requests");
        }
        rateLimitMap.set(ip, entry);
    }
}));
// Lightweight online counter: reuse normal game traffic and keep only a
// viewerId -> lastSeen timestamp in memory. No database writes or extra client
// requests are introduced. The management page treats five-minute activity as
// online presence.
fastify.addHook("onResponse", (request) => __awaiter(void 0, void 0, void 0, function* () {
    if (!request.url.startsWith("/api/index.php/"))
        return;
    const body = request.body;
    if (!body || typeof body !== "object" || Array.isArray(body))
        return;
    (0, online_presence_1.markPlayerOnline)(body.viewer_id);
}));
(0, cn_response_hook_1.installCnResponseEncoding)(fastify);
function jsonParser(_, body, done) {
    try {
        done(null, JSON.parse(body));
    }
    catch (_a) {
        done(null, undefined);
    }
}
fastify.addContentTypeParser("application/x-www-form-urlencoded", { parseAs: "string" }, (_request, body, done) => {
    try {
        done(null, (0, msgpackr_1.unpack)(Buffer.from(body, "base64")));
    }
    catch (_a) {
        try {
            done(null, Object.fromEntries(new URLSearchParams(body)));
        }
        catch (_b) {
            jsonParser(_request, body, done);
        }
    }
});
fastify.addContentTypeParser("application/json", { parseAs: "string" }, jsonParser);
(0, player_login_1.initializePlayerLogin)(viewerId => {
    SessionManager_1.sessionManager.disconnectPlayerLogin(viewerId);
    (0, state_1.disconnectLoungePlayerLogin)(viewerId);
});
(0, client_admission_1.installClientAdmission)(fastify);
(0, playerLogin_1.installPlayerLoginGuard)(fastify);
(0, takeover_access_1.installTakeoverUdidGuard)(fastify);
fastify.register(playerLogin_1.default);
fastify.register(abyssRecords_1.default);
const iosCompat = (0, ios_compat_1.parseIosCompatConfig)();
fastify.register(versionCheck_1.default, { ios: iosCompat });
if (iosCompat.enabled) {
    // Native Leiting SDK requests use bare paths rather than /api/index.php.
    fastify.register(ios_leiting_1.default, { ios: iosCompat });
    console.log(`[iOS] compatibility enabled: ${iosCompat.apiScheme}://${iosCompat.apiHost}`);
}
fastify.register(leitingAuth_1.default, { prefix: "/api/index.php" });
const apiPrefix = "/api/index.php";
fastify.register(load_1.default, { prefix: apiPrefix });
fastify.register(asset_1.default, { prefix: `${apiPrefix}/asset` });
fastify.register(takeOver_1.default, { prefix: apiPrefix });
function stubMsgpackReply(reply, data, playerId) {
    const servertime = playerId ? (0, utils_1.getServerTimeForPlayer)(playerId) : (0, utils_1.getServerTime)();
    reply.header("content-type", "application/x-msgpack");
    return reply.status(200).send({
        data_headers: { force_update: false, asset_update: false, short_udid: 0, viewer_id: 0, servertime, result_code: 1 },
        data
    });
}
fastify.post(`${apiPrefix}/assetintitle/version_info_in_title`, (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
    const { getAssetDownloadSize, getVersionInfo } = require("./routes/cn/asset");
    const resVer = request.headers['res_ver'];
    const device = request.headers.device;
    return stubMsgpackReply(reply, getVersionInfo(CDN_BASE_URL, getAssetDownloadSize(resVer, device), device));
}));
fastify.post(`${apiPrefix}/tool/check_social_link_enable`, (_request, reply) => __awaiter(void 0, void 0, void 0, function* () {
    return stubMsgpackReply(reply, { enable: false });
}));
// Gift code exchange (礼包码兑换): enable button in menu, exchange not implemented
fastify.post(`${apiPrefix}/tool/check_enable_gift`, (_request, reply) => __awaiter(void 0, void 0, void 0, function* () {
    return stubMsgpackReply(reply, { enable_gift: true });
}));
fastify.post(`${apiPrefix}/tool/contact_active`, (_request, reply) => __awaiter(void 0, void 0, void 0, function* () {
    return stubMsgpackReply(reply, { enable_customer_service: false });
}));
fastify.post(`${apiPrefix}/tool/custom_notify`, (_request, reply) => __awaiter(void 0, void 0, void 0, function* () {
    return stubMsgpackReply(reply, {});
}));
fastify.post(`${apiPrefix}/channels/channel_leiting_pay/query_unfinish_order`, (_request, reply) => __awaiter(void 0, void 0, void 0, function* () {
    return stubMsgpackReply(reply, { order_id: "" });
}));
fastify.post(`${apiPrefix}/channels/channel_leiting_pay/query_purcharge`, (_request, reply) => __awaiter(void 0, void 0, void 0, function* () {
    return stubMsgpackReply(reply, { status: 3 }); // 3 = purchase success
}));
fastify.post(`${apiPrefix}/channels/channel_leiting_pay/set_unfinish_order_status`, (_request, reply) => __awaiter(void 0, void 0, void 0, function* () {
    return stubMsgpackReply(reply, {});
}));
// Episode trial reading: finish stub (character story trial)
fastify.post(`${apiPrefix}/episode_trial_reading/finish`, (_request, reply) => __awaiter(void 0, void 0, void 0, function* () {
    return stubMsgpackReply(reply, {});
}));
function persistSeedFeedback() {
    return __awaiter(this, void 0, void 0, function* () {
        try {
            yield seed_validator_1.default.flushPersistence();
        }
        catch (_a) {
            // SeedPersistence logs the failure and retains changes for retry.
            // Keep the existing best-effort beacon response contract on disk errors.
        }
    });
}
fastify.get("/debug", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
    var _f;
    const ts = new Date().toISOString();
    const loc = ((_f = request.query) === null || _f === void 0 ? void 0 : _f.loc) || "unknown";
    // Parse C3032 from beacon query string (04e patch sends via CrashUtil.debugBeacon)
    try {
        parseC3032Beacon(loc);
    }
    catch (_) { }
    try {
        parsePlayBeacon(loc);
    }
    catch (_) { }
    if (typeof loc === "string" && (loc.includes("C3032") || loc.startsWith("PLAY|"))) {
        yield persistSeedFeedback();
    }
    return reply.status(200).send("OK");
}));
// Parse C3032 from beacon loc string — ★ garbled to â, extract digits via garbled pattern
function parseC3032Beacon(loc) {
    if (!loc.includes("C3032"))
        return;
    const seedMatch = loc.match(/seed=(\d+)/);
    if (!seedMatch)
        return;
    const badSeed = parseInt(seedMatch[1], 10);
    const movieMatch = loc.match(/movie_id=(\w+)/);
    const movieId = movieMatch ? movieMatch[1] : "normal";
    console.log(`[DBG-BCN] C3032 seed=${badSeed} movieId=${movieId}`);
    const starDigits = [...loc.matchAll(/â(\d)/g)];
    // first match = ball rarity (結果レア度), second = char rarity (キャラクターレア度)
    const ballRarity = starDigits.length > 0 ? parseInt(starDigits[0][1], 10) : 3;
    // Extract play= field (0=no animation, 1=played) — APK 04e patch v2
    const playMatch = loc.match(/play=(\d)/);
    const didPlay = playMatch ? playMatch[1] === '1' : null;
    const r = ballRarity - 3; // 0=★3, 1=★4, 2=★5
    if (didPlay !== null)
        seed_validator_1.default.recordPlay(movieId, badSeed, didPlay); // record for flushAll
    // C3032 = client-verified rarity → verifiedPool (superset of playPool/confirmPool)
    console.log(`[DBG-BCN] C3032 → moveToVerified [${movieId}] seed=${badSeed} ★${ballRarity}`);
    seed_validator_1.default.moveToVerified(movieId, badSeed, r);
    if (didPlay === false) {
        console.log(`[DBG-BCN] C3032 → confirm [${movieId}] seed=${badSeed} ★${ballRarity}`);
        seed_validator_1.default.confirm(movieId, badSeed, r); // play=0 → confirmPool
    }
    const playStr = didPlay === true ? ' play=1' : didPlay === false ? ' play=0' : '';
    console.log(`[BEACON] C3032 → ${didPlay === true ? 'play' : 'confirm'} seed ${badSeed} ★${ballRarity}${playStr} [${movieId}]`);
    if (didPlay === null) {
        seed_validator_1.default.addPending(movieId, badSeed, r);
    }
}
// PLAY beacon — every draw reports play=1|0 (APK 04e Patch 5)
// Format: PLAY|play=1|seed=10000001, movie_id=fes
function parsePlayBeacon(loc) {
    if (loc.startsWith("PLAY|")) {
        const seedMatch = loc.match(/seed=(\d+)/);
        if (!seedMatch) {
            console.log(`[PLAY] no seed in: ${loc.substring(0, 80)}`);
            return;
        }
        const seed = parseInt(seedMatch[1], 10);
        const movieMatch = loc.match(/movie_id=(\w+)/);
        const movieId = movieMatch ? movieMatch[1] : "normal";
        const playMatch = loc.match(/play=(\d)/);
        const didPlay = playMatch ? playMatch[1] === '1' : false;
        console.log(`[DBG-BCN] PLAY seed=${seed} play=${didPlay ? '1' : '0'} movieId=${movieId}`);
        seed_validator_1.default.recordPlay(movieId, seed, didPlay); // record for flushAll
        if (didPlay) {
            const r = seed_validator_1.default.getSentR(movieId, seed);
            if (r !== undefined && r !== null) {
                seed_validator_1.default.addPlay(movieId, seed, r, true);
                seed_validator_1.default.moveToVerified(movieId, seed, r);
                console.log(`[PLAY] playPool seed=${seed} movie=${movieId}`);
            }
            else {
                console.log(`[PLAY] play=1 skipped seed=${seed} getSentR=${r === null ? 'null' : 'undefined'} (already cleaned up by prior beacon)`);
            }
        }
        else {
            const r = seed_validator_1.default.getSentR(movieId, seed);
            console.log(`[DBG-BCN] PLAY play=0 → confirm [${movieId}] seed=${seed} r=${r !== undefined && r !== null ? '★' + (r + 3) : r === null ? 'null' : 'undefined'}`);
            if (r !== undefined)
                seed_validator_1.default.confirm(movieId, seed, r);
        }
    }
}
fastify.post("/debug", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
    var _g;
    const ts = new Date().toISOString();
    const loc = ((_g = request.body) === null || _g === void 0 ? void 0 : _g.loc) || "unknown";
    console.log(`[BEACON ${ts}] ${loc}`);
    // Parse C3032 beacons for auto-purification (04e patch skips throw but keeps beacon)
    try {
        parseC3032Beacon(loc);
    }
    catch (_) { }
    if (typeof loc === "string" && loc.includes("C3032"))
        yield persistSeedFeedback();
    return reply.status(200).send("OK");
}));
fastify.post("/crash", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
    // Log crash (truncated to avoid log explosion)
    const bodyStr = JSON.stringify(request.body);
    console.log(`[CRASH] ${bodyStr.substring(0, 2000)}`);
    // Parse C3032 gacha seed mismatches and auto-block bad seeds
    try {
        const seedMatch = bodyStr.match(/seed=(\d+)/);
        if (seedMatch && bodyStr.includes("C3032")) {
            const badSeed = parseInt(seedMatch[1], 10);
            const ballMatch = bodyStr.match(/結果レア度=★(\d)/);
            const ballRarity = ballMatch ? parseInt(ballMatch[1], 10) : 0;
            const r = ballRarity - 3;
            const movieMatch = bodyStr.match(/movie_id=(\w+)/);
            const movieId = movieMatch ? movieMatch[1] : "normal";
            // Crash path: no play= info → pendingPlay (rarity known, play unknown)
            if (r >= 0 && r <= 2)
                seed_validator_1.default.addPending(movieId, badSeed, r);
            console.log(`[CRASH] seed ${badSeed} device★${ballRarity} movie=${movieId}`);
        }
    }
    catch (e) { }
    if (bodyStr.includes("C3032"))
        yield persistSeedFeedback();
    return reply.status(200).send("OK");
}));
fastify.register(tool_1.default, { prefix: `${apiPrefix}/tool` });
fastify.register(reproduce_1.default, { prefix: `${apiPrefix}/reproduce` });
fastify.register(tutorial_1.default, { prefix: `${apiPrefix}/tutorial` });
fastify.register(gacha_1.default, { prefix: `${apiPrefix}/gacha` });
fastify.register(party_1.default, { prefix: `${apiPrefix}/party` });
fastify.register(expod_1.default, { prefix: `${apiPrefix}/expod` });
fastify.register(storyQuest_1.default, { prefix: `${apiPrefix}/story_quest` });
fastify.register(option_1.default, { prefix: `${apiPrefix}/option` });
fastify.register(singleBattleQuest_1.default, { prefix: `${apiPrefix}/single_battle_quest` });
fastify.register(quest_1.default, { prefix: `${apiPrefix}/quest` });
fastify.register(multi_1.multiBattleRoutes, { prefix: `${apiPrefix}/multi_battle_quest` });
fastify.register(attention_1.default, { prefix: `${apiPrefix}/attention` });
fastify.register(character_1.default, { prefix: `${apiPrefix}/character` });
fastify.register(mana_1.default, { prefix: `${apiPrefix}/character` });
fastify.register(bond_1.default, { prefix: `${apiPrefix}/character` });
fastify.register(partyGroup_1.default, { prefix: `${apiPrefix}/party_group` });
fastify.register(equipment_1.default, { prefix: `${apiPrefix}/equipment` });
fastify.register(sell_1.default, { prefix: `${apiPrefix}/equipment` });
fastify.register(exBoost_1.default, { prefix: `${apiPrefix}/ex_boost` });
fastify.register(boxGacha_1.default, { prefix: `${apiPrefix}/box_gacha` });
fastify.register(shop_1.default, { prefix: `${apiPrefix}/shop` });
fastify.register(exchange_1.default, { prefix: `${apiPrefix}/exchange` });
fastify.register(encyclopedia_1.default, { prefix: `${apiPrefix}/encyclopedia` });
fastify.register(mail_1.default, { prefix: `${apiPrefix}/mail` });
fastify.register(rankingEvent_1.default, { prefix: `${apiPrefix}/ranking_event` });
fastify.register(mission_1.default, { prefix: `${apiPrefix}/mission` });
fastify.register(activeMission_1.default, { prefix: `${apiPrefix}/active_mission` });
fastify.register(passCard_1.default, { prefix: `${apiPrefix}/Pass_card` });
fastify.register(payment_1.default, { prefix: `${apiPrefix}/payment` });
fastify.register(news_1.default, { prefix: `${apiPrefix}/news` });
fastify.register(raidEvent_1.default, { prefix: `${apiPrefix}/event/raid` });
fastify.register(rushEvent_1.default, { prefix: `${apiPrefix}/event/rush` });
fastify.register(carnivalEvent_1.default, { prefix: `${apiPrefix}/carnival_event` });
fastify.register(contentsGuide_1.default, { prefix: `${apiPrefix}/contents_guide` });
fastify.register(profile_1.default, { prefix: `${apiPrefix}/profile` });
fastify.register(follow_1.default, { prefix: `${apiPrefix}/follow` });
fastify.register(sns_1.default, { prefix: `${apiPrefix}/sns` });
fastify.register(history_1.default, { prefix: `${apiPrefix}/history` });
fastify.register(playerHistory_1.default, { prefix: `${apiPrefix}/player_history` });
fastify.register(comic_1.default, { prefix: `${apiPrefix}/comic` });
fastify.register(questUnlock_1.default, { prefix: `${apiPrefix}/quest` });
fastify.register(item_1.default, { prefix: `${apiPrefix}/item` });
fastify.register(lounge_1.default, { prefix: `${apiPrefix}/lounge` });
fastify.register(multiSpecialExchange_1.default, { prefix: `${apiPrefix}/multi_special_exchange` });
fastify.register(howToGet_1.default, { prefix: `${apiPrefix}/how_to_get` });
// Web management panel
fastify.register(web_1.default);
fastify.register(web_api_1.default, { prefix: "/api" });
fastify.register(seeds_1.default, { prefix: "/api/seeds" });
fastify.register(modAdmin_1.default, { prefix: "/api/mod-admin" });
const cdnHost = process.env.CN_LISTEN_HOST || "localhost";
const cdnPort = process.env.CN_LISTEN_PORT || "8001";
const cdnDisplayHost = cdnHost === "0.0.0.0" ? "localhost" : cdnHost;
const CDN_BASE_URL = process.env.CDN_BASE_URL || `http://${cdnDisplayHost}:${cdnPort}/patch/cn`;
const cdnDir = process.env.CDN_DIR || ".cdn";
// Native readers can request common, medium, Android or iOS files directly.
(0, custom_cdn_resource_routes_1.installCustomCdnResourceRoutes)(fastify, {
    patchRoot: path_1.default.join(__dirname, "..", "assets", "asset-patch"),
    cdnRoot: path_1.default.isAbsolute(cdnDir) ? cdnDir : path_1.default.join(__dirname, "..", cdnDir),
});
// Serve patch archive files for asset update
fastify.get("/patch/cn/asset-patch/active/:file", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
    const { file } = request.params;
    const patchFile = path_1.default.join(__dirname, "..", "assets", "asset-patch", "active", file);
    if ((0, file_exists_1.existsSync)(patchFile)) {
        return reply.type("application/zip").send((0, fs_1.readFileSync)(patchFile));
    }
    return reply.status(404).send("Not Found");
}));
fastify.register(static_1.default, {
    root: path_1.default.isAbsolute(cdnDir) ? cdnDir : path_1.default.join(__dirname, "..", cdnDir),
    prefix: "/patch",
    decorateReply: false
});
// Web static assets
fastify.register(static_1.default, {
    root: path_1.default.join(__dirname, "..", "web", "public"),
    prefix: "/public",
    decorateReply: false
});
// New admin SPA (React, built from admin/ into web/dist) — served at /admin.
// Old pages at / stay untouched until the SPA fully replaces them (see docs/admin-refactor-plan.md).
const adminDistDir = path_1.default.join(__dirname, "..", "web", "dist");
const adminSpaAvailable = (0, file_exists_1.existsSync)(path_1.default.join(adminDistDir, "index.html"));
if (adminSpaAvailable) {
    fastify.register(static_1.default, {
        root: adminDistDir,
        prefix: "/admin/",
        decorateReply: false
    });
    fastify.get("/admin", (_request, reply) => reply.redirect("/admin/"));
}
else {
    console.log("[admin] web/dist not found — admin SPA disabled (run: npm run build:admin)");
}
// Catch-all to log unknown endpoints
fastify.setNotFoundHandler((request, reply) => {
    // SPA fallback: client-side routes like /admin/accounts resolve to index.html
    if (adminSpaAvailable && request.method === "GET" && request.url.startsWith("/admin/")) {
        reply.header("content-type", "text/html; charset=utf-8");
        reply.send((0, fs_1.readFileSync)(path_1.default.join(adminDistDir, "index.html")));
        return;
    }
    console.log(`[UNKNOWN] ${request.method} ${request.url}`);
    reply.status(404).send({ error: "Not Found" });
});
const host = (_a = process.env.CN_LISTEN_HOST) !== null && _a !== void 0 ? _a : "127.0.0.1";
const port = parseInt((_b = process.env.CN_LISTEN_PORT) !== null && _b !== void 0 ? _b : "8001");
const receiveHistoryRetention = (0, receive_history_retention_1.createReceiveHistoryRetentionService)((0, db_1.getDb)(), {
    executeTransaction: persistence_coordinator_1.runPersistenceTransaction,
});
const leaderboardSettlementScheduler = (0, settlement_1.createLeaderboardSettlementScheduler)();
const dailyVmoneyMailScheduler = (0, daily_vmoney_mail_1.createDailyVmoneyMailScheduler)((0, db_1.getDb)());
fastify.addHook("onClose", () => __awaiter(void 0, void 0, void 0, function* () {
    // The multiplayer TCP listener is not owned by Fastify. Stop it first so
    // no new realtime callback can enqueue a database write while the queues
    // below are draining.
    yield (0, multi_1.stopSessionServer)();
    yield seed_validator_1.default.close();
    dailyVmoneyMailScheduler.stop();
    leaderboardSettlementScheduler.stop();
    yield receiveHistoryRetention.stop();
    yield (0, player_party_pool_1.stopQuestNpcPartyPoolWorker)();
    yield (0, persistence_coordinator_1.drainPersistence)();
    yield (0, sqlite_persistence_worker_1.stopSqlitePersistenceWorker)();
    (0, persistence_coordinator_1.configurePersistenceSqlExecutor)(null);
    yield (0, sqlite_checkpoint_worker_1.stopSqliteCheckpointWorker)();
}));
// Ctrl+C and a normal service-manager stop must enter Fastify's close hooks;
// terminating the process forcibly still bypasses every cleanup callback.
let gracefulShutdown = null;
const shutdownTimeoutMs = Math.max(5000, Number.parseInt((_c = process.env.GRACEFUL_SHUTDOWN_TIMEOUT_MS) !== null && _c !== void 0 ? _c : "15000", 10) || 15000);
function requestGracefulShutdown(signal) {
    if (gracefulShutdown)
        return;
    console.warn(`[SHUTDOWN] ${signal} received; draining realtime and persistence work`);
    gracefulShutdown = (() => __awaiter(this, void 0, void 0, function* () {
        let timeout;
        try {
            yield Promise.race([
                fastify.close(),
                new Promise((_, reject) => {
                    timeout = setTimeout(() => reject(new Error(`graceful shutdown timed out after ${shutdownTimeoutMs}ms`)), shutdownTimeoutMs);
                }),
            ]);
            console.log("[SHUTDOWN] graceful shutdown complete");
        }
        catch (error) {
            process.exitCode = 1;
            console.error(`[SHUTDOWN] graceful shutdown failed: ${error.message}`);
        }
        finally {
            if (timeout)
                clearTimeout(timeout);
        }
    }))();
    void gracefulShutdown;
}
process.once("SIGINT", () => requestGracefulShutdown("SIGINT"));
process.once("SIGTERM", () => requestGracefulShutdown("SIGTERM"));
process.once("SIGBREAK", () => requestGracefulShutdown("SIGBREAK"));
(0, player_party_pool_1.startQuestNpcPartyPoolWorker)();
const persistenceWorkerStarted = (0, sqlite_persistence_worker_1.startSqlitePersistenceWorker)((0, db_1.getDb)().name);
if (persistenceWorkerStarted && (0, sqlite_persistence_worker_1.isSqlitePersistenceWorkerStarted)()) {
    (0, persistence_coordinator_1.configurePersistenceSqlExecutor)((_context, statements) => __awaiter(void 0, void 0, void 0, function* () {
        yield (0, sqlite_persistence_worker_1.executeSqlitePersistenceCommand)({
            operation: _context.operation,
            statements,
        });
    }));
}
fastify.listen({ port, host }, (err, address) => {
    if (err) {
        console.error(err);
        process.exit(1);
    }
    console.log(`CN StarPoint listening on http://${host}:${port}`);
    receiveHistoryRetention.start();
    leaderboardSettlementScheduler.start();
    dailyVmoneyMailScheduler.start();
    // Start multi battle TCP session server
    (0, multi_1.startSessionServer)();
    (0, sqlite_checkpoint_worker_1.startSqliteCheckpointWorker)((0, db_1.getDb)().name);
    const logDirectory = path_1.default.resolve(__dirname, "../.logs");
    (0, fs_1.mkdirSync)(logDirectory, { recursive: true });
    (0, atomic_json_file_1.writeJsonAtomicSync)(path_1.default.join(logDirectory, "cn-server-ready.json"), {
        pid: process.pid, readyAt: new Date().toISOString(), port,
        database: path_1.default.resolve((0, db_1.getDb)().name), storageLayoutVersion: (0, storage_layout_1.getStorageLayoutVersion)((0, db_1.getDb)()),
    });
});
