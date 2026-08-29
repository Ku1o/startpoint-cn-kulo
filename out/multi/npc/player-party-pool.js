"use strict";
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
Object.defineProperty(exports, "__esModule", { value: true });
exports.getPlayerNpcPartyPoolStats = exports.getRandomPlayerNpcPartiesSync = exports.invalidatePlayerNpcPartyPool = exports.refreshPlayerNpcPartyPoolSync = exports.getNpcPartySelectionOptions = exports.removePlayerQuestNpcPartySnapshots = exports.reloadQuestNpcPartyPool = exports.recordSuccessfulQuestNpcParty = exports.stopQuestNpcPartyPoolWorker = exports.startQuestNpcPartyPoolWorker = void 0;
const fs_1 = require("fs");
const path_1 = __importDefault(require("path"));
const worker_threads_1 = require("worker_threads");
const db_1 = require("../../data/db");
const types_1 = require("../../data/types");
const game_logging_1 = require("../../lib/game-logging");
const quest_1 = require("../../lib/types/quest");
const special_event_parties_1 = require("../../lib/special-event-parties");
const content_master_1 = require("../../lib/content-master");
const handshake_1 = require("../tcp/handshake");
const quest_party_pool_shared_1 = require("./quest-party-pool-shared");
const STEAM_ROBOT_DECISIVE_ELEMENTS = {
    1001001: 1, // fire robot -> water
    1002001: 2, // water robot -> thunder
    1003001: 3, // thunder robot -> wind
    1004001: 0, // wind robot -> fire
    1005001: 5, // light robot -> dark
    1006001: 4, // dark robot -> light
};
const CACHE_TTL_MS = Math.max(10000, Number.parseInt(process.env.NPC_PARTY_POOL_TTL_MS || "300000", 10) || 300000);
const CACHE_MAX_ENTRIES = Math.max(100, Number.parseInt(process.env.NPC_PARTY_POOL_MAX_ENTRIES || "5000", 10) || 5000);
const MIN_BATTLE_POWER_INCLUSIVE = Math.max(0, Number.parseInt(process.env.NPC_PARTY_POOL_MIN_BATTLE_POWER || "8000", 10) || 8000);
let cachedParties = [];
let cachedPartiesByElement = new Map();
let cacheExpiresAt = 0;
let questPartyPools = new Map();
let questPartyPoolWorker = null;
let questPartyPoolWorkerReady = false;
let pendingClearRecords = [];
let nextCleanupRequestId = 1;
const pendingCleanupMessages = [];
const pendingCleanupRequests = new Map();
function rejectPendingCleanupRequests(error) {
    for (const request of pendingCleanupRequests.values()) {
        clearTimeout(request.timeout);
        request.reject(error);
    }
    pendingCleanupRequests.clear();
    pendingCleanupMessages.length = 0;
}
function getQuestPartyWorkerLocation() {
    const compiled = path_1.default.resolve(__dirname, "../../workers/quest-npc-party-pool-worker.js");
    if ((0, fs_1.existsSync)(compiled))
        return { filename: compiled };
    return {
        filename: path_1.default.resolve(__dirname, "../../workers/quest-npc-party-pool-worker.ts"),
        execArgv: ["-r", require.resolve("ts-node/register/transpile-only")],
    };
}
function startQuestNpcPartyPoolWorker() {
    if (questPartyPoolWorker)
        return;
    const location = getQuestPartyWorkerLocation();
    const worker = new worker_threads_1.Worker(location.filename, { execArgv: location.execArgv });
    questPartyPoolWorker = worker;
    questPartyPoolWorkerReady = false;
    worker.on("message", (message) => {
        if ((message === null || message === void 0 ? void 0 : message.type) === "full_snapshot" && message.pools && typeof message.pools === "object") {
            questPartyPools = new Map(Object.entries(message.pools));
            return;
        }
        if ((message === null || message === void 0 ? void 0 : message.type) === "quest_snapshot" && typeof message.key === "string") {
            questPartyPools.set(message.key, Array.isArray(message.entries) ? message.entries : []);
            return;
        }
        if ((message === null || message === void 0 ? void 0 : message.type) === "ready") {
            questPartyPoolWorkerReady = true;
            const queued = pendingClearRecords;
            pendingClearRecords = [];
            for (const snapshot of queued)
                worker.postMessage({ type: "record", snapshot });
            for (const cleanup of pendingCleanupMessages.splice(0))
                worker.postMessage(cleanup);
            console.log(`[LOBBY] quest-specific NPC party worker ready: pools=${questPartyPools.size}`);
            return;
        }
        if ((message === null || message === void 0 ? void 0 : message.type) === "remove_players_result" && Number.isSafeInteger(message.requestId)) {
            const request = pendingCleanupRequests.get(message.requestId);
            if (!request)
                return;
            pendingCleanupRequests.delete(message.requestId);
            clearTimeout(request.timeout);
            cachedParties = cachedParties.filter(party => !request.playerIds.has(party.player_id));
            indexCachedPartiesByElement();
            request.resolve({
                removedRows: Math.max(0, Math.trunc(Number(message.removedRows) || 0)),
                affectedQuestCount: Math.max(0, Math.trunc(Number(message.affectedQuestCount) || 0)),
            });
            return;
        }
        if ((message === null || message === void 0 ? void 0 : message.type) === "operation_error") {
            if (Number.isSafeInteger(message.requestId)) {
                const request = pendingCleanupRequests.get(message.requestId);
                if (request) {
                    pendingCleanupRequests.delete(message.requestId);
                    clearTimeout(request.timeout);
                    request.reject(new Error(String(message.error || "AI party cleanup failed")));
                }
            }
            console.error(`[LOBBY] quest NPC party worker ${message.operation} failed: ${message.error}`);
        }
    });
    worker.on("error", error => {
        rejectPendingCleanupRequests(error);
        console.error("[LOBBY] quest NPC party worker error", error);
    });
    worker.on("exit", code => {
        const wasCurrentWorker = questPartyPoolWorker === worker;
        if (wasCurrentWorker)
            questPartyPoolWorker = null;
        questPartyPoolWorkerReady = false;
        if (wasCurrentWorker) {
            rejectPendingCleanupRequests(new Error(`Quest NPC party worker exited (code ${code})`));
        }
        if (code !== 0 && wasCurrentWorker) {
            console.error(`[LOBBY] quest NPC party worker exited: code=${code}`);
        }
    });
}
exports.startQuestNpcPartyPoolWorker = startQuestNpcPartyPoolWorker;
function stopQuestNpcPartyPoolWorker() {
    return __awaiter(this, void 0, void 0, function* () {
        const worker = questPartyPoolWorker;
        if (!worker)
            return;
        questPartyPoolWorker = null;
        questPartyPoolWorkerReady = false;
        yield worker.terminate();
    });
}
exports.stopQuestNpcPartyPoolWorker = stopQuestNpcPartyPoolWorker;
function recordSuccessfulQuestNpcParty(playerId, questCategory, questId, partySlot) {
    var _a, _b;
    if (!(0, quest_party_pool_shared_1.isQuestNpcPartyPoolEligibleCategory)(questCategory))
        return;
    const parsed = (0, special_event_parties_1.parseGlobalPartyId)(partySlot);
    if (!parsed)
        return;
    const row = (0, db_1.getDb)().prepare(`
        SELECT slot, name, character_id_1, character_id_2, character_id_3,
               unison_character_1, unison_character_2, unison_character_3,
               equipment_1, equipment_2, equipment_3,
               ability_soul_1, ability_soul_2, ability_soul_3,
               edited, group_id, category, current_battle_power, before_battle_power,
               player_id
        FROM players_parties
        WHERE player_id = ? AND category = ? AND group_id = ? AND slot = ?
    `).get(playerId, types_1.PartyCategory.NORMAL, parsed.groupId, parsed.slot);
    if (!row || ((_a = row.current_battle_power) !== null && _a !== void 0 ? _a : 0) < quest_party_pool_shared_1.QUEST_NPC_POOL_MIN_POWER)
        return;
    const party = (0, handshake_1.buildRealParty)(playerId, toPlayerParty(row));
    if (!hasCompleteMainCharacters(party))
        return;
    const snapshot = {
        questCategory,
        questId,
        sourcePlayerId: playerId,
        partySlot,
        battlePower: (_b = row.current_battle_power) !== null && _b !== void 0 ? _b : 0,
        partyElement: getUniformPartyElement(row),
        clearedAt: Date.now(),
        party,
    };
    if (!questPartyPoolWorker || !questPartyPoolWorkerReady) {
        if (pendingClearRecords.length < 1000)
            pendingClearRecords.push(snapshot);
        return;
    }
    questPartyPoolWorker.postMessage({ type: "record", snapshot });
}
exports.recordSuccessfulQuestNpcParty = recordSuccessfulQuestNpcParty;
function reloadQuestNpcPartyPool() {
    if (questPartyPoolWorker && questPartyPoolWorkerReady) {
        questPartyPoolWorker.postMessage({ type: "reload" });
    }
}
exports.reloadQuestNpcPartyPool = reloadQuestNpcPartyPool;
function removePlayerQuestNpcPartySnapshots(playerIds, timeoutMs = 10000) {
    const normalizedPlayerIds = [...new Set(playerIds
            .map(playerId => Math.trunc(Number(playerId)))
            .filter(playerId => Number.isSafeInteger(playerId) && playerId > 0))];
    if (normalizedPlayerIds.length === 0) {
        return Promise.resolve({ removedRows: 0, affectedQuestCount: 0 });
    }
    const removedPlayers = new Set(normalizedPlayerIds);
    pendingClearRecords = pendingClearRecords.filter(snapshot => !removedPlayers.has(snapshot.sourcePlayerId));
    cachedParties = cachedParties.filter(party => !removedPlayers.has(party.player_id));
    indexCachedPartiesByElement();
    cacheExpiresAt = 0;
    startQuestNpcPartyPoolWorker();
    const requestId = nextCleanupRequestId++;
    const message = { type: "remove_players", requestId, playerIds: normalizedPlayerIds };
    return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
            pendingCleanupRequests.delete(requestId);
            const queuedIndex = pendingCleanupMessages.findIndex(entry => entry.requestId === requestId);
            if (queuedIndex >= 0)
                pendingCleanupMessages.splice(queuedIndex, 1);
            reject(new Error(`Quest NPC party cleanup timed out after ${timeoutMs}ms`));
        }, Math.max(1000, timeoutMs));
        pendingCleanupRequests.set(requestId, {
            resolve,
            reject,
            timeout,
            playerIds: removedPlayers,
        });
        if (questPartyPoolWorker && questPartyPoolWorkerReady) {
            questPartyPoolWorker.postMessage(message);
        }
        else {
            pendingCleanupMessages.push(message);
        }
    });
}
exports.removePlayerQuestNpcPartySnapshots = removePlayerQuestNpcPartySnapshots;
function getCharacterElement(characterId) {
    if (!characterId)
        return null;
    const entry = content_master_1.serverCharacters[String(characterId)];
    return Number.isInteger(entry === null || entry === void 0 ? void 0 : entry.element) ? Number(entry.element) : null;
}
function getUniformPartyElement(party) {
    const characterIds = [
        party.character_id_1,
        party.character_id_2,
        party.character_id_3,
        party.unison_character_1,
        party.unison_character_2,
        party.unison_character_3,
    ].filter((characterId) => Number.isSafeInteger(characterId) && Number(characterId) > 0);
    if (characterIds.length < 3)
        return null;
    const elements = characterIds.map(getCharacterElement);
    if (elements.some(element => element === null))
        return null;
    return elements.every(element => element === elements[0]) ? elements[0] : null;
}
function indexCachedPartiesByElement() {
    var _a;
    cachedPartiesByElement = new Map();
    for (const party of cachedParties) {
        const element = getUniformPartyElement(party);
        if (element === null)
            continue;
        const parties = (_a = cachedPartiesByElement.get(element)) !== null && _a !== void 0 ? _a : [];
        parties.push(party);
        cachedPartiesByElement.set(element, parties);
    }
}
function getNpcPartySelectionOptions(questCategory, questId) {
    const base = { questCategory, questId };
    if (questCategory !== quest_1.QuestCategory.HARD_MULTI_EVENT)
        return base;
    const requiredElement = STEAM_ROBOT_DECISIVE_ELEMENTS[questId];
    if (requiredElement === undefined)
        return base;
    return Object.assign(Object.assign({}, base), { minimumBattlePower: 10000, requiredElement });
}
exports.getNpcPartySelectionOptions = getNpcPartySelectionOptions;
function toPlayerParty(row) {
    var _a, _b;
    return {
        name: row.name,
        characterIds: [row.character_id_1, row.character_id_2, row.character_id_3],
        unisonCharacterIds: [
            row.unison_character_1,
            row.unison_character_2,
            row.unison_character_3,
        ],
        equipmentIds: [row.equipment_1, row.equipment_2, row.equipment_3],
        abilitySoulIds: [row.ability_soul_1, row.ability_soul_2, row.ability_soul_3],
        edited: row.edited !== 0,
        options: { allowOtherPlayersToHealMe: true },
        category: row.category,
        currentBattlePower: (_a = row.current_battle_power) !== null && _a !== void 0 ? _a : 0,
        beforeBattlePower: (_b = row.before_battle_power) !== null && _b !== void 0 ? _b : 0,
    };
}
function hasCompleteMainCharacters(party) {
    return Array.isArray(party === null || party === void 0 ? void 0 : party.characters)
        && party.characters.length >= 3
        && party.characters.slice(0, 3).every((entry) => { var _a; return Array.isArray(entry) && entry[0] === 0 && ((_a = entry[1]) === null || _a === void 0 ? void 0 : _a.id); });
}
function refreshPlayerNpcPartyPoolSync(force = false) {
    const now = Date.now();
    if (!force && now < cacheExpiresAt)
        return cachedParties.length;
    // Only cache normal parties with three characters that still belong to the
    // source player. Equipment and unison data is checked again by
    // buildRealParty when the party is selected, so stale optional slots safely
    // become empty instead of breaking the multiplayer room.
    cachedParties = (0, db_1.getDb)().prepare(`
        SELECT
            p.slot, p.name,
            p.character_id_1, p.character_id_2, p.character_id_3,
            p.unison_character_1, p.unison_character_2, p.unison_character_3,
            p.equipment_1, p.equipment_2, p.equipment_3,
            p.ability_soul_1, p.ability_soul_2, p.ability_soul_3,
            p.edited, p.group_id, p.category,
            p.current_battle_power, p.before_battle_power,
            p.player_id
        FROM players_parties p
        INNER JOIN players_characters c1
            ON c1.player_id = p.player_id AND c1.id = p.character_id_1
        INNER JOIN players_characters c2
            ON c2.player_id = p.player_id AND c2.id = p.character_id_2
        INNER JOIN players_characters c3
            ON c3.player_id = p.player_id AND c3.id = p.character_id_3
        WHERE p.category = ?
          AND p.character_id_1 IS NOT NULL
          AND p.character_id_2 IS NOT NULL
          AND p.character_id_3 IS NOT NULL
          AND p.current_battle_power >= ?
        ORDER BY p.rowid DESC
        LIMIT ?
    `).all(types_1.PartyCategory.NORMAL, MIN_BATTLE_POWER_INCLUSIVE, CACHE_MAX_ENTRIES);
    indexCachedPartiesByElement();
    cacheExpiresAt = now + CACHE_TTL_MS;
    (0, game_logging_1.gameVerboseLog)(() => `[LOBBY] player NPC party pool refreshed: entries=${cachedParties.length} minPowerInclusive=${MIN_BATTLE_POWER_INCLUSIVE} ttlMs=${CACHE_TTL_MS}`);
    return cachedParties.length;
}
exports.refreshPlayerNpcPartyPoolSync = refreshPlayerNpcPartyPoolSync;
function invalidatePlayerNpcPartyPool() {
    cacheExpiresAt = 0;
}
exports.invalidatePlayerNpcPartyPool = invalidatePlayerNpcPartyPool;
function getRandomPlayerNpcPartiesSync(hostPlayerId, count, options = {}) {
    var _a, _b, _c, _d;
    const targetCount = Math.max(0, Math.trunc(count));
    const minimumBattlePower = Math.max(MIN_BATTLE_POWER_INCLUSIVE, Math.trunc((_a = options.minimumBattlePower) !== null && _a !== void 0 ? _a : MIN_BATTLE_POWER_INCLUSIVE));
    const questKey = options.questCategory !== undefined && options.questId !== undefined
        ? (0, quest_party_pool_shared_1.getQuestNpcPartyPoolKey)(options.questCategory, options.questId)
        : null;
    const historicalParties = questKey ? ((_b = questPartyPools.get(questKey)) !== null && _b !== void 0 ? _b : []) : [];
    if (targetCount > 0 && historicalParties.length > 0) {
        const available = historicalParties.filter(candidate => candidate.battlePower >= minimumBattlePower
            && (options.requiredElement === undefined
                || candidate.partyElement === options.requiredElement));
        const selected = [];
        while (available.length > 0 && selected.length < targetCount) {
            const offset = Math.floor(Math.random() * available.length);
            const [candidate] = available.splice(offset, 1);
            if (!hasCompleteMainCharacters(candidate.party))
                continue;
            selected.push({ sourcePlayerId: candidate.sourcePlayerId, party: candidate.party });
        }
        // Very new or rare quests can temporarily have only one historical
        // source. Reuse that valid clear snapshot instead of the live host.
        while (selected.length > 0 && selected.length < targetCount) {
            const candidate = selected[Math.floor(Math.random() * selected.length)];
            selected.push({ sourcePlayerId: candidate.sourcePlayerId, party: candidate.party });
        }
        if (selected.length >= targetCount)
            return selected;
    }
    // Compatibility fallback while a newly installed server is still building
    // per-quest clear history. Its database scan is lazy and TTL-cached.
    refreshPlayerNpcPartyPoolSync();
    const candidateParties = options.requiredElement === undefined
        ? cachedParties
        : ((_c = cachedPartiesByElement.get(options.requiredElement)) !== null && _c !== void 0 ? _c : []);
    if (targetCount === 0 || candidateParties.length === 0)
        return [];
    const availableIndexes = [];
    for (let index = 0; index < candidateParties.length; index++) {
        const candidate = candidateParties[index];
        if (((_d = candidate.current_battle_power) !== null && _d !== void 0 ? _d : 0) >= minimumBattlePower) {
            availableIndexes.push(index);
        }
    }
    const selected = [];
    const usedSourcePlayers = new Set();
    const deferredSamePlayer = [];
    while (availableIndexes.length > 0 && selected.length < targetCount) {
        const pickedOffset = Math.floor(Math.random() * availableIndexes.length);
        const [pickedIndex] = availableIndexes.splice(pickedOffset, 1);
        const candidate = candidateParties[pickedIndex];
        if (usedSourcePlayers.has(candidate.player_id)) {
            deferredSamePlayer.push(candidate);
            continue;
        }
        const party = (0, handshake_1.buildRealParty)(candidate.player_id, toPlayerParty(candidate));
        if (!hasCompleteMainCharacters(party))
            continue;
        selected.push({ sourcePlayerId: candidate.player_id, party });
        usedSourcePlayers.add(candidate.player_id);
    }
    // Small servers may only have one valid source player. In that case allow
    // two different parties from that player before falling back to the host.
    while (deferredSamePlayer.length > 0 && selected.length < targetCount) {
        const pickedOffset = Math.floor(Math.random() * deferredSamePlayer.length);
        const [candidate] = deferredSamePlayer.splice(pickedOffset, 1);
        const party = (0, handshake_1.buildRealParty)(candidate.player_id, toPlayerParty(candidate));
        if (!hasCompleteMainCharacters(party))
            continue;
        selected.push({ sourcePlayerId: candidate.player_id, party });
    }
    return selected;
}
exports.getRandomPlayerNpcPartiesSync = getRandomPlayerNpcPartiesSync;
function getPlayerNpcPartyPoolStats() {
    return {
        size: cachedParties.length,
        expiresAt: cacheExpiresAt,
        ttlMs: CACHE_TTL_MS,
        maxEntries: CACHE_MAX_ENTRIES,
        minBattlePowerInclusive: MIN_BATTLE_POWER_INCLUSIVE,
        questPoolCount: questPartyPools.size,
        questPoolEntryCount: [...questPartyPools.values()]
            .reduce((total, entries) => total + entries.length, 0),
    };
}
exports.getPlayerNpcPartyPoolStats = getPlayerNpcPartyPoolStats;
