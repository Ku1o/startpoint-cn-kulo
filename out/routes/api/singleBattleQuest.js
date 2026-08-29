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
exports.insertActiveQuest = exports.activeQuests = void 0;
const quest_active_1 = require("../../data/domains/quest_active");
const rushEvent_1 = require("../../data/domains/rushEvent");
const player_1 = require("../../data/domains/player");
const item_1 = require("../../data/domains/item");
const quest_1 = require("../../data/domains/quest");
const unison_unlock_1 = require("../../lib/validate/unison-unlock");
const db_1 = require("../../data/db");
const equipment_1 = require("../../data/domains/equipment");
const practice_battle_history_1 = require("../../data/domains/practice-battle-history");
const carnivalEvent_1 = require("../../data/domains/carnivalEvent");
const assets_1 = require("../../lib/assets");
const character_1 = require("../../lib/character");
const quest_2 = require("../../lib/quest");
const types_1 = require("../../lib/types");
const utils_1 = require("../../utils");
const rushEvent_2 = require("./rushEvent");
const types_2 = require("../../data/types");
const stamina_1 = require("../../lib/stamina");
const stamina_cost_1 = require("../../lib/stamina-cost");
const carnival_handler_1 = require("../../lib/quest/finish/carnival-handler");
const carnival_reward_handler_1 = require("../../lib/quest/finish/carnival-reward-handler");
const rush_handler_1 = require("../../lib/quest/finish/rush-handler");
const service_1 = require("../../lib/leaderboard/service");
const rogue_drops_1 = require("../../lib/quest/finish/rogue-drops");
const raid_handler_1 = require("../../lib/quest/finish/raid-handler");
const quest_calc_1 = require("../../lib/quest/finish/quest-calc");
const session_validator_1 = require("../../lib/quest/finish/session-validator");
const active_quest_resolver_1 = require("../../lib/quest/finish/active-quest-resolver");
const challenge_point_1 = require("../../lib/quest/finish/challenge-point");
const score_attack_handler_1 = require("../../lib/quest/finish/score-attack-handler");
const mission_1 = require("../../lib/mission");
const steam_robot_challenge_1 = require("../../lib/mission/steam-robot-challenge");
const mission_2 = require("../../lib/mission");
const battle_facts_1 = require("../../lib/mission/battle-facts");
const active_entry_facts_1 = require("../../lib/mission/active-entry-facts");
const active_reconciliation_1 = require("../../lib/mission/active-reconciliation");
const content_snapshot_1 = require("../../content/runtime/content-snapshot");
const mail_1 = require("../../data/domains/mail");
const fs_1 = require("fs");
const path_1 = __importDefault(require("path"));
const quest_entry_costs_json_1 = __importDefault(require("../../../assets/quest_entry_costs.json"));
const score_attack_border_reward_json_1 = __importDefault(require("../../../assets/score_attack_border_reward.json"));
const event_challenge_point_map_json_1 = __importDefault(require("../../../assets/event_challenge_point_map.json"));
const game_logging_1 = require("../../lib/game-logging");
const settlement_performance_1 = require("../../lib/settlement-performance");
const gauntlet_completion_classification_1 = require("../../lib/gauntlet-completion-classification");
const finish_response_cache_1 = require("../../lib/finish-response-cache");
const practice_battle_history_2 = require("../../lib/quest/practice-battle-history");
const mana_1 = require("../../lib/mana");
// Load carnival quest score data
let carnivalScoreLookup = {};
try {
    const scorePath = path_1.default.join(process.cwd(), "assets", "carnival_event_quest_scores.json");
    if ((0, fs_1.existsSync)(scorePath)) {
        carnivalScoreLookup = JSON.parse((0, fs_1.readFileSync)(scorePath, "utf-8"));
    }
}
catch (_a) { } // Init failed silently; carnival scoring won't work
const rush_1 = require("../../lib/rush");
const degree_1 = require("../../data/domains/degree");
const mode15_optional_1 = require("../../lib/mode15-optional");
const continueVmoneyCost = 50;
exports.activeQuests = {};
function insertActiveQuest(playerId, quest) {
    var _a, _b, _c, _d, _e;
    const startedAtMs = (_a = quest.startedAtMs) !== null && _a !== void 0 ? _a : (0, utils_1.getServerTime)() * 1000;
    exports.activeQuests[playerId] = Object.assign(Object.assign({}, quest), { startedAtMs });
    // Persist to DB for battle recovery across server restarts
    (0, quest_active_1.insertPlayerActiveQuestSync)(playerId, {
        playerId,
        playId: quest.playId,
        questId: quest.questId,
        category: quest.category,
        useBossBoostPoint: quest.useBossBoostPoint,
        useBoostPoint: quest.useBoostPoint,
        isAutoStartMode: quest.isAutoStartMode,
        isMulti: quest.isMulti,
        isMultiHost: (_b = quest.isMultiHost) !== null && _b !== void 0 ? _b : false,
        roomNumber: (_c = quest.roomNumber) !== null && _c !== void 0 ? _c : null,
        entryItemId: (_d = quest.entryItemId) !== null && _d !== void 0 ? _d : null,
        eventId: (_e = quest.eventId) !== null && _e !== void 0 ? _e : null,
        continueCount: quest.continueCount,
        startedAtMs,
    });
}
exports.insertActiveQuest = insertActiveQuest;
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.post("/finish", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!viewerId || isNaN(viewerId))
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        const sessionResult = yield (0, session_validator_1.validateSessionAndPlayer)(viewerId);
        if (!sessionResult)
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid viewer id."
            });
        const { playerId, playerData } = sessionResult;
        const finishCacheKey = (0, finish_response_cache_1.buildFinishResponseCacheKey)("single", viewerId, body);
        const cachedFinishResponse = (0, finish_response_cache_1.getCachedFinishResponse)(finishCacheKey);
        if (cachedFinishResponse !== undefined) {
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send(cachedFinishResponse);
        }
        // Resolve the active quest from memory, persisted recovery state, or
        // (for patched clients that skipped /start) a validated request hint.
        const resolvedActiveQuest = (0, active_quest_resolver_1.resolveActiveQuest)({
            playerId,
            hint: body,
            memory: exports.activeQuests,
        });
        const activeQuestData = resolvedActiveQuest === null || resolvedActiveQuest === void 0 ? void 0 : resolvedActiveQuest.quest;
        (0, game_logging_1.gameVerboseLog)(() => { var _a, _b; return `[FINISH] req: playerId=${playerId} questId=${body.quest_id} category=${body.category} activeExists=${activeQuestData !== undefined} source=${(_a = resolvedActiveQuest === null || resolvedActiveQuest === void 0 ? void 0 : resolvedActiveQuest.source) !== null && _a !== void 0 ? _a : "none"} multi=${(_b = activeQuestData === null || activeQuestData === void 0 ? void 0 : activeQuestData.isMulti) !== null && _b !== void 0 ? _b : false}`; });
        if (activeQuestData === undefined)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "No active quest to finish."
            });
        if ((resolvedActiveQuest === null || resolvedActiveQuest === void 0 ? void 0 : resolvedActiveQuest.source) !== "memory") {
            console.warn(`[FINISH] recovered active quest from ${resolvedActiveQuest === null || resolvedActiveQuest === void 0 ? void 0 : resolvedActiveQuest.source}: playerId=${playerId} questId=${activeQuestData.questId} category=${activeQuestData.category}`);
        }
        const questCategory = activeQuestData.category;
        const questId = activeQuestData.questId;
        (0, game_logging_1.gameVerboseLog)(() => `[FINISH] active: category=${questCategory} questId=${questId}`);
        const questData = (0, assets_1.getQuestFromCategorySync)(questCategory, questId);
        if (questData === null || !('rankPointReward' in questData)) {
            console.warn(`[BATTLE] finish failed: category=${questCategory} questId=${questId} found=${!!questData} hasRankReward=${questData ? ('rankPointReward' in questData) : 'N/A'}`);
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Quest doesn't exist."
            });
        }
        // calculate clear rank
        const clearTime = body.elapsed_time_ms;
        const isScoreAttackEvent = questCategory === types_1.QuestCategory.SCORE_ATTACK_EVENT;
        if (isScoreAttackEvent && (questData.bRankScore === undefined
            || questData.aRankScore === undefined
            || questData.sRankScore === undefined
            || questData.ssRankScore === undefined)) {
            return reply.status(500).send({
                "error": "Internal Server Error",
                "message": "Score attack rank thresholds are missing."
            });
        }
        const clearRank = isScoreAttackEvent
            ? (0, score_attack_handler_1.calculateScoreAttackClearRank)(body.score, {
                bRankScore: questData.bRankScore,
                aRankScore: questData.aRankScore,
                sRankScore: questData.sRankScore,
                ssRankScore: questData.ssRankScore,
            })
            : (0, quest_calc_1.calculateClearRank)(clearTime, questData);
        // calculate player rewards
        const beforeRankPoint = playerData.rankPoint;
        const displayMode15ManaAsFieldDrop = (0, mode15_optional_1.isMode15Quest)(questCategory, questId);
        const newRankPoint = beforeRankPoint + questData.rankPointReward;
        const manaObtained = questData.manaReward + body.add_mana;
        let newMana = (0, mana_1.calculateFreeManaGrant)(playerData, manaObtained).freeMana;
        // calculate boost point
        let newBoostPoint = playerData.boostPoint - (activeQuestData.useBoostPoint ? 1 : 0);
        let newBossBoostPoint = playerData.bossBoostPoint - (activeQuestData.useBossBoostPoint ? 1 : 0);
        let useBoostPoint = (activeQuestData.useBoostPoint && (newBoostPoint >= 0)) || (activeQuestData.useBossBoostPoint && (newBossBoostPoint >= 0));
        // check current quest progress
        const questProgress = (0, quest_1.getPlayerSingleQuestProgressSync)(playerId, questCategory, questId);
        const questPreviouslyCompleted = questProgress !== null;
        let questAccomplished = body.is_accomplished;
        let scoreAttackBorderTiers = [];
        if (isScoreAttackEvent) {
            try {
                scoreAttackBorderTiers = (0, score_attack_handler_1.resolveScoreAttackBorderTiers)(questData.eventId, questData.scoreAttackQuestId, score_attack_border_reward_json_1.default);
            }
            catch (error) {
                console.error(`[SCORE_ATTACK] invalid configuration: ${error.message}`);
                return reply.status(500).send({
                    "error": "Internal Server Error",
                    "message": "Score attack reward configuration is missing."
                });
            }
            questAccomplished = body.score >= scoreAttackBorderTiers[0].score;
        }
        const finishResponse = (0, settlement_performance_1.measureSettlementPhase)("single", "transaction", () => (0, db_1.getDb)().transaction(() => {
            var _a, _b, _c, _d, _e, _f, _g, _h, _j, _k, _l, _m, _o, _p, _q, _r, _s, _t, _u;
            (0, quest_active_1.deletePlayerActiveQuestSync)(playerId);
            const missionEvaluationTime = new Date((0, utils_1.getServerTime)() * 1000);
            let clearReward = null;
            let sPlusClearReward = null;
            const leaderId = (_a = body.statistics.party.characters[0]) === null || _a === void 0 ? void 0 : _a.id;
            if (questAccomplished) {
                // update quest progress
                if (questPreviouslyCompleted) {
                    // simply update the quest progress if it already exists.
                    const updateData = {
                        questId: questId,
                        finished: true,
                        bestElapsedTimeMs: questProgress.bestElapsedTimeMs === undefined || questProgress.bestElapsedTimeMs === null ? clearTime : Math.min(clearTime, questProgress.bestElapsedTimeMs),
                        highScore: questProgress.highScore === undefined ? body.score : Math.max(body.score, questProgress.highScore),
                        leaderCharacterId: leaderId !== null && leaderId !== void 0 ? leaderId : null
                    };
                    if (clearRank !== null) {
                        updateData.clearRank = questProgress.clearRank === undefined ? clearRank : Math.max(clearRank, questProgress.clearRank);
                    }
                    (0, quest_1.updatePlayerQuestProgressSync)(playerId, questCategory, updateData);
                }
                else {
                    // insert if it doesn't already exist.
                    const insertData = {
                        questId: questId,
                        finished: true,
                        bestElapsedTimeMs: clearTime,
                        highScore: body.score,
                        clearRank: clearRank !== null && clearRank !== void 0 ? clearRank : 5,
                        leaderCharacterId: leaderId !== null && leaderId !== void 0 ? leaderId : null
                    };
                    (0, quest_1.insertPlayerQuestProgressSync)(playerId, questCategory, insertData);
                }
                // Legacy saves may be missing the 1-6-1 story completion row even
                // though a later main quest was cleared. Repair it immediately so
                // unison becomes available without requiring another login.
                if (questCategory === types_1.QuestCategory.MAIN && questId >= 1006001) {
                    (0, unison_unlock_1.repairUnisonUnlockProgressSync)(playerId);
                }
                if (questCategory === types_1.QuestCategory.SOLO_TIME_ATTACK_EVENT) {
                    const newDegreeIds = (0, degree_1.grantPlayerSoloTimeAttackDegreesSync)(playerId, questId, clearTime);
                    if (newDegreeIds.length > 0) {
                        console.log(`[DEGREE] solo time attack granted: player=${playerId} quest=${questId} elapsed=${clearTime} degrees=${newDegreeIds.join(",")}`);
                    }
                }
            }
            // update player
            const oldRkDegree = (0, stamina_1.getRankDegree)(beforeRankPoint);
            const newDegreeId = (0, stamina_1.getRankDegree)(newRankPoint);
            const didLevelUp = newDegreeId > oldRkDegree;
            (0, player_1.updatePlayerSync)(Object.assign({ id: playerId, freeMana: newMana, rankPoint: newRankPoint, boostPoint: newBoostPoint, bossBoostPoint: newBossBoostPoint, totalManaObtained: ((_b = playerData.totalManaObtained) !== null && _b !== void 0 ? _b : 0) + manaObtained, maxComboAchieved: Math.max((_c = playerData.maxComboAchieved) !== null && _c !== void 0 ? _c : 0, (_e = (_d = body.statistics) === null || _d === void 0 ? void 0 : _d.max_combo_count) !== null && _e !== void 0 ? _e : 0) }, (didLevelUp ? { stamina: playerData.stamina + (0, stamina_1.getMaxStamina)(newDegreeId), staminaHealTime: new Date() } : {})));
            if ((0, player_1.adjustPlayerExpPoolSync)(playerId, questData.poolExpReward, 'single_battle_base_reward') === null) {
                throw new Error(`Failed to grant single battle EXP to player ${playerId}`);
            }
            clearReward = !isScoreAttackEvent && !questPreviouslyCompleted && questData.clearReward !== undefined
                ? (0, quest_2.givePlayerRewardSync)(playerId, questData.clearReward)
                : null;
            const isExpertSingleEvent = questCategory === types_1.QuestCategory.EXPERT_SINGLE_EVENT;
            const shouldGrantSPlusReward = isExpertSingleEvent
                ? (questProgress === null || questProgress === void 0 ? void 0 : questProgress.sPlusRewardReceived) !== true
                : (questProgress === null || questProgress === void 0 ? void 0 : questProgress.clearRank) !== 5;
            sPlusClearReward = !isScoreAttackEvent && (clearRank === 5)
                && shouldGrantSPlusReward && (questData.sPlusReward !== undefined)
                ? (0, quest_2.givePlayerRewardSync)(playerId, questData.sPlusReward)
                : null;
            if (isExpertSingleEvent && sPlusClearReward !== null) {
                (0, quest_1.updatePlayerQuestProgressSync)(playerId, questCategory, {
                    questId,
                    sPlusRewardReceived: true,
                });
                console.log(`[EXPERT_SINGLE_EVENT] SS reward granted: player=${playerId} quest=${questId} item=14040 count=3`);
            }
            if (didLevelUp) {
                playerData.stamina = playerData.stamina + (0, stamina_1.getMaxStamina)(newDegreeId);
                playerData.staminaHealTime = new Date();
                console.log(`[BATTLE-FINISH] player ${playerId} leveled up: ${oldRkDegree} -> ${newDegreeId}, stamina refilled`);
            }
            // Consume daily challenge point
            const dailyChallengePointList = (0, challenge_point_1.handleDailyChallengePoint)({
                questCategory,
                eventId: questData.eventId,
                playerId,
                challengePointMap: event_challenge_point_map_json_1.default,
                getEntries: (pid) => (0, player_1.getPlayerDailyChallengePointListSync)(pid),
                updatePoint: (pid, id, pt) => (0, player_1.updatePlayerDailyChallengePointSync)(pid, id, pt),
            });
            // reward score rewards
            if (isScoreAttackEvent) {
                (0, game_logging_1.gameVerboseLog)(() => `[SCORE_ATTACK] questId=${questId} body={score:${body.score}, elapsed:${body.elapsed_time_ms}, accomplished:${body.is_accomplished}, addMana:${body.add_mana}, continue:${body.continue_count}}`);
                (0, game_logging_1.gameVerboseLog)(() => `[SCORE_ATTACK] questData={localQuest:${questData.scoreAttackQuestId}, bRank:${questData.bRankScore}, aRank:${questData.aRankScore}, sRank:${questData.sRankScore}, ssRank:${questData.ssRankScore}, rankPt:${questData.rankPointReward}, charExp:${questData.characterExpReward}, mana:${questData.manaReward}, poolExp:${questData.poolExpReward}}`);
            }
            (0, game_logging_1.gameVerboseLog)(() => { var _a, _b; return `[BATTLE] scoreReward groupId=${questData.scoreRewardGroupId} groupLen=${(_b = (_a = questData.scoreRewardGroup) === null || _a === void 0 ? void 0 : _a.length) !== null && _b !== void 0 ? _b : 'null'} questId=${questId} category=${questCategory}`; });
            const scoreRewardsResult = (0, quest_2.givePlayerScoreRewardsSync)(playerId, questData.scoreRewardGroupId, questData.scoreRewardGroup, useBoostPoint, questData.element);
            let scoreAttackEventData = null;
            if (isScoreAttackEvent) {
                const previousHighScore = (_f = questProgress === null || questProgress === void 0 ? void 0 : questProgress.highScore) !== null && _f !== void 0 ? _f : 0;
                const mainCharacterIds = (0, score_attack_handler_1.collectScoreAttackMainCharacterIds)(body.statistics.party.characters);
                const resolved = (0, score_attack_handler_1.resolveNewScoreAttackBorderRewards)(scoreAttackBorderTiers, previousHighScore, body.score);
                for (const [itemIdText, count] of Object.entries(resolved.itemCounts)) {
                    scoreRewardsResult.items[itemIdText] = (0, item_1.givePlayerItemSync)(playerId, Number(itemIdText), count);
                }
                scoreAttackEventData = {
                    reward_ids: resolved.rewardIds,
                    main_character_ids: mainCharacterIds,
                };
                (0, game_logging_1.gameVerboseLog)(() => `[SCORE_ATTACK] borderRewards: event=${questData.eventId} folder=${questData.folderId} oldScore=${previousHighScore} newScore=${body.score} crossed=${resolved.rewardIds.length} items=${JSON.stringify(resolved.itemCounts)}`);
                (0, game_logging_1.gameVerboseLog)(() => { var _a, _b; return `[SCORE_ATTACK] afterReward: dropIds=${JSON.stringify(scoreRewardsResult.drop_score_reward_ids)}, drops=${scoreRewardsResult.drop_score_reward_ids.length}, items=${JSON.stringify(scoreRewardsResult.items)}, equipList=${(_b = (_a = scoreRewardsResult.equipment_list) === null || _a === void 0 ? void 0 : _a.length) !== null && _b !== void 0 ? _b : 0}`; });
                (0, game_logging_1.gameVerboseLog)(() => `[SCORE_ATTACK] response: accomplished=${questAccomplished}, clearRank=${clearRank}, score=${body.score}, elapsed=${body.elapsed_time_ms}, items=${JSON.stringify(scoreRewardsResult.items)}, clientCategory=${questCategory}`);
            }
            // reward character exp
            const bodyPartyStatistics = body.statistics.party;
            const partyCharacterIds = [...bodyPartyStatistics.characters, ...bodyPartyStatistics.unison_characters];
            if (questCategory === types_1.QuestCategory.PRACTICE) {
                (0, practice_battle_history_1.insertPlayerPracticeBattleHistorySync)((0, practice_battle_history_2.buildPracticeBattleHistoryRecord)({
                    playerId,
                    playId: activeQuestData.playId,
                    categoryId: questCategory,
                    questId,
                    finishKind: questAccomplished ? 0 : 1,
                    createdAt: missionEvaluationTime,
                    elapsedTimeMs: clearTime,
                    score: body.score,
                    clearRank: questAccomplished ? clearRank : null,
                    party: bodyPartyStatistics,
                    statistics: body.statistics,
                    equipmentList: (0, equipment_1.getPlayerEquipmentListSync)(playerId),
                }));
            }
            // Build finish context for mission trackers
            const finishCtx = {
                playerId, questCategory, questId,
                questAccomplished,
                clearTime: body.elapsed_time_ms,
                clearRank,
                party: body.statistics.party,
                statistics: body.statistics,
                player: playerData,
                questPreviouslyCompleted,
                questProgress,
                partySlot: playerData.partySlot,
            };
            // Mission progress is recorded once by recordMissionBattleFacts below.
            const singleBattleParty = (0, mission_1.collectPartyCharacterIds)(finishCtx.party);
            (0, mission_1.recordBattleMissionDimensionsSafe)(Object.assign(Object.assign({ type: "battle_finish", playerId,
                questCategory,
                questId, accomplished: questAccomplished, mode: "single", clearRank, clearTimeMs: clearTime, score: Number(body.score) || 0 }, singleBattleParty), { statistics: (0, mission_1.summarizeBattleStatistics)(finishCtx.statistics) }));
            const missionBattleFacts = (0, battle_facts_1.recordMissionBattleFacts)(finishCtx, missionEvaluationTime);
            const steamRobotMissionId = (0, steam_robot_challenge_1.trackSteamRobotChallengeMission)({
                playerId,
                questCategory,
                questId,
                questAccomplished,
                clearRank,
                statistics: finishCtx.statistics,
            });
            if (steamRobotMissionId !== null) {
                console.log(`[MISSION] steam robot challenge cleared: player=${playerId} quest=${questId} mission=${steamRobotMissionId}`);
            }
            const partyCharacterIdsArray = [];
            for (const value of partyCharacterIds.values()) {
                if (value !== null && value.id !== null)
                    partyCharacterIdsArray.push(value.id);
            }
            const addExpAmount = questData.characterExpReward;
            const rewardCharacterExpResult = (0, character_1.givePlayerCharactersExpSync)(playerId, partyCharacterIdsArray, addExpAmount, questData.fixedParty !== undefined);
            const dataHeaders = (0, utils_1.generateDataHeaders)({
                viewer_id: viewerId
            });
            // At the three solo-to-multiplayer boundaries, do not expose the
            // just-written Rush round in *this* generic quest-result response.
            // The legacy client uses that response to decide whether to draw
            // "Continue challenge"; exposing it would make the 5/10/15
            // placeholder open as a normal single-player Rush quest.
            //
            // The real marker is still persisted by the handler.  Pressing OK
            // returns to the Rush page, whose subsequent summary load receives
            // the real marker and correctly exposes the multiplayer Boss.
            const mode15BoundaryStage = Number(questId) % 1000;
            const withholdMode15BoundaryAdvance = questAccomplished
                && questCategory === types_1.QuestCategory.RUSH_EVENT
                && questData.rushEventId === mode15_optional_1.MODE15_RUSH_EVENT_ID
                && (mode15BoundaryStage === 4
                    || mode15BoundaryStage === 9
                    || mode15BoundaryStage === 14);
            const rushPartiesBeforeBoundaryAdvance = withholdMode15BoundaryAdvance
                ? (0, rush_1.getSerializedPlayerRushEventPlayedPartiesSync)(playerId, mode15_optional_1.MODE15_RUSH_EVENT_ID)
                : null;
            // handle event quest-specific data & rewards
            const { rushEventData, rushEventRewardsResult } = (0, rush_handler_1.handleRushEventFinish)({
                questCategory,
                questAccomplished,
                questData,
                clearTime,
                party: bodyPartyStatistics,
                playerId,
                questId,
                getEvoLevels: (pid, chars) => (0, character_1.getCharactersEvolutionImgLevels)(pid, chars),
                getFolderMaxRounds: rushEvent_2.getRushEventFolderMaxRounds,
                getRushEvent: (pid, eid) => (0, rushEvent_1.getPlayerRushEventSync)(pid, eid),
                updateRushEvent: (pid, data) => (0, rushEvent_1.updatePlayerRushEventSync)(pid, data),
                // Never save a content-less marker. The legacy result/quest UI
                // dereferences the first character of every recorded party; a row
                // made entirely of NULL values becomes character id 0 and crashes
                // immediately after boundary floors such as stage 5.
                insertParty: (pid, eid, p) => (0, rushEvent_1.insertPlayerRushEventPlayedPartySync)(pid, eid, p),
                insertClearedFolder: (pid, eid, fid) => (0, rushEvent_1.insertPlayerRushEventClearedFolderSync)(pid, eid, fid),
                deletePartyList: (pid, eid, bt) => (0, rushEvent_1.deletePlayerRushEventPlayedPartyListSync)(pid, eid, bt),
                getSerializedParties: (pid, eid) => (0, rush_1.getSerializedPlayerRushEventPlayedPartiesSync)(pid, eid),
                getFolderRewards: (eid, fid) => (0, assets_1.getRushEventFolderClearRewards)(eid, fid),
                giveRewards: (pid, r) => (0, quest_2.givePlayerRewardsSync)(pid, r),
            });
            (0, service_1.finishLeaderboardQuestSync)({
                playerId,
                quest: {
                    category: questCategory,
                    eventId: questData.rushEventId,
                    folderId: questData.rushEventFolderId,
                    round: questData.rushEventRound,
                    questId,
                    totalRounds: questData.rushEventId === undefined
                        || questData.rushEventFolderId === undefined
                        ? 0
                        : (0, rushEvent_2.getRushEventFolderMaxRounds)(questData.rushEventId, questData.rushEventFolderId),
                },
                accomplished: questAccomplished,
                clientBattleMs: clearTime,
                party: {
                    characterIds: bodyPartyStatistics.characters.map(value => { var _a; return (_a = value === null || value === void 0 ? void 0 : value.id) !== null && _a !== void 0 ? _a : null; }),
                    unisonCharacterIds: bodyPartyStatistics.unison_characters.map(value => { var _a; return (_a = value === null || value === void 0 ? void 0 : value.id) !== null && _a !== void 0 ? _a : null; }),
                    equipmentIds: bodyPartyStatistics.equipments.map(value => { var _a; return (_a = value === null || value === void 0 ? void 0 : value.id) !== null && _a !== void 0 ? _a : null; }),
                    abilitySoulIds: bodyPartyStatistics.ability_soul_ids,
                    evolutionImgLevels: (0, character_1.getCharactersEvolutionImgLevels)(playerId, bodyPartyStatistics.characters.map(value => { var _a; return (_a = value === null || value === void 0 ? void 0 : value.id) !== null && _a !== void 0 ? _a : null; })),
                    unisonEvolutionImgLevels: (0, character_1.getCharactersEvolutionImgLevels)(playerId, bodyPartyStatistics.unison_characters.map(value => { var _a; return (_a = value === null || value === void 0 ? void 0 : value.id) !== null && _a !== void 0 ? _a : null; })),
                },
            });
            if (questAccomplished
                && questCategory === types_1.QuestCategory.RUSH_EVENT
                && questData.rushEventId !== undefined
                && (0, gauntlet_completion_classification_1.repairGauntletCompletionClassificationSync)(playerId, questData.rushEventId)) {
                console.log(`[RUSH] completed classification repaired: `
                    + `player=${playerId} event=${questData.rushEventId}`);
            }
            if (rushEventData !== null && rushPartiesBeforeBoundaryAdvance !== null) {
                rushEventData.rush_battle_played_party_list = rushPartiesBeforeBoundaryAdvance.folderParties;
                rushEventData.endless_battle_played_party_list = rushPartiesBeforeBoundaryAdvance.endlessParties;
                console.log(`[MODE15] deferred Rush result visibility: player=${playerId} stage=${mode15BoundaryStage}`);
            }
            const rogueFolderMaxRounds = {};
            if (questData.rushEventId !== undefined
                && questData.rushEventFolderId !== undefined) {
                rogueFolderMaxRounds[questData.rushEventFolderId] =
                    (0, rushEvent_2.getRushEventFolderMaxRounds)(questData.rushEventId, questData.rushEventFolderId);
            }
            const rogueDrops = (0, rogue_drops_1.handleRoguePerRoundDrops)({
                questCategory,
                questAccomplished,
                playerId,
                questData,
                folderMaxRounds: rogueFolderMaxRounds,
                partyCharacterIds: partyCharacterIdsArray,
            });
            if (rogueDrops !== null
                && rushEventData !== null
                && rogueDrops.showInRewardList) {
                rushEventData.rush_battle_reward_list = [
                    ...rushEventData.rush_battle_reward_list,
                    ...rogueDrops.rewardListEntries,
                ];
            }
            // Record played party for RAID_EVENT
            const raidEventData = (0, raid_handler_1.handleRaidEventFinish)({
                questCategory,
                questAccomplished,
                activeEventId: activeQuestData.eventId,
                playId: activeQuestData.playId,
                party: bodyPartyStatistics,
                playerId,
                questId,
                getEvoLevelsFn: (pid, chars) => (0, character_1.getCharactersEvolutionImgLevels)(pid, chars),
                insertPartyFn: (pid, eid, p) => (0, rushEvent_1.insertPlayerRushEventPlayedPartySync)(pid, eid, p),
            });
            // handle carnival event score & records
            const carnivalInfo = carnivalScoreLookup[String(questId)];
            if (carnivalInfo)
                (0, carnivalEvent_1.migrateCarnivalEventFolderRecordsSync)(carnivalInfo.event_id);
            const carnivalEventData = (0, carnival_handler_1.handleCarnivalEventFinish)({
                questCategory,
                questAccomplished,
                questId,
                battleScore: body.score,
                clearTime,
                party: bodyPartyStatistics,
                playerId,
                carnivalLookup: carnivalScoreLookup,
                getRecordsFn: (pid, eid) => (0, carnivalEvent_1.getPlayerCarnivalEventRecordsSync)(pid, eid),
                upsertFn: (pid, eid, fid, score, chars, unisons) => (0, carnivalEvent_1.upsertPlayerCarnivalEventRecordSync)(pid, eid, fid, score, chars, unisons),
            });
            let carnivalRewardsResult = null;
            if (carnivalEventData && carnivalInfo) {
                const totalBestScore = (0, carnivalEvent_1.getPlayerCarnivalEventRecordsSync)(playerId, carnivalInfo.event_id)
                    .reduce((sum, record) => { var _a; return sum + ((_a = record.bestScore) !== null && _a !== void 0 ? _a : 0); }, 0);
                const granted = (0, carnival_reward_handler_1.grantCarnivalTotalScoreRewardsSync)(playerId, carnivalInfo.event_id, totalBestScore);
                carnivalEventData.reward_ids = granted.rewardIds;
                carnivalEventData.new_degree_ids = granted.newDegreeIds;
                carnivalRewardsResult = granted.rewards;
            }
            const mode15RewardsResult = (0, mode15_optional_1.settleMode15BattleSync)(playerId, questCategory, questId, questAccomplished);
            const itemList = Object.assign(Object.assign(Object.assign(Object.assign(Object.assign(Object.assign(Object.assign(Object.assign({}, (activeQuestData.entryItemId ? { [activeQuestData.entryItemId]: (_g = (0, item_1.getPlayerItemSync)(playerId, activeQuestData.entryItemId)) !== null && _g !== void 0 ? _g : 0 } : {})), ((_h = clearReward === null || clearReward === void 0 ? void 0 : clearReward.items) !== null && _h !== void 0 ? _h : {})), ((_j = sPlusClearReward === null || sPlusClearReward === void 0 ? void 0 : sPlusClearReward.items) !== null && _j !== void 0 ? _j : {})), scoreRewardsResult.items), ((_k = rushEventRewardsResult === null || rushEventRewardsResult === void 0 ? void 0 : rushEventRewardsResult.items) !== null && _k !== void 0 ? _k : {})), ((_l = rogueDrops === null || rogueDrops === void 0 ? void 0 : rogueDrops.rewardResult.items) !== null && _l !== void 0 ? _l : {})), ((_m = carnivalRewardsResult === null || carnivalRewardsResult === void 0 ? void 0 : carnivalRewardsResult.items) !== null && _m !== void 0 ? _m : {})), ((_o = mode15RewardsResult === null || mode15RewardsResult === void 0 ? void 0 : mode15RewardsResult.items) !== null && _o !== void 0 ? _o : {}));
            const characterList = [
                ...rewardCharacterExpResult.character_list,
                ...((clearReward === null || clearReward === void 0 ? void 0 : clearReward.character_list) || []),
                ...((sPlusClearReward === null || sPlusClearReward === void 0 ? void 0 : sPlusClearReward.character_list) || []),
                ...scoreRewardsResult.character_list,
                ...((rogueDrops === null || rogueDrops === void 0 ? void 0 : rogueDrops.rewardResult.character_list) || []),
                ...((rogueDrops === null || rogueDrops === void 0 ? void 0 : rogueDrops.expCharacterList) || []),
                ...((carnivalRewardsResult === null || carnivalRewardsResult === void 0 ? void 0 : carnivalRewardsResult.character_list) || []),
                ...((mode15RewardsResult === null || mode15RewardsResult === void 0 ? void 0 : mode15RewardsResult.character_list) || []),
            ];
            const missionSettlement = (0, settlement_performance_1.measureSettlementPhase)("single", "mission", () => ((0, mission_2.settleMissionCategories)(playerId, (0, battle_facts_1.buildBattleMissionSettlementScopes)(missionBattleFacts, Object.keys(itemList).map(Number), steamRobotMissionId === null ? [] : [steamRobotMissionId], partyCharacterIdsArray), missionEvaluationTime)));
            const awakeMissionSettlement = (0, settlement_performance_1.measureSettlementPhase)("single", "awake_mission", () => ((0, mission_2.settleAwakeMissionCandidates)(playerId, questAccomplished
                ? (0, mission_2.getAwakeBattleMissionIds)(partyCharacterIdsArray, missionBattleFacts.awakeMissionIds)
                : [], missionEvaluationTime)));
            const activeMissionSettlement = (0, settlement_performance_1.measureSettlementPhase)("single", "active_mission", () => ((0, active_reconciliation_1.reconcileActiveMissionFacts)({
                playerId,
                repository: (0, content_snapshot_1.getContentSnapshot)().repository,
                now: missionEvaluationTime,
                patterns: (0, battle_facts_1.getBattleActiveMissionPatterns)(questCategory),
            })));
            const finalPlayerData = (0, player_1.getPlayerSync)(playerId);
            const responseData = {
                "user_info": {
                    "free_mana": (_p = finalPlayerData === null || finalPlayerData === void 0 ? void 0 : finalPlayerData.freeMana) !== null && _p !== void 0 ? _p : newMana,
                    "exp_pool": (_q = finalPlayerData === null || finalPlayerData === void 0 ? void 0 : finalPlayerData.expPool) !== null && _q !== void 0 ? _q : rewardCharacterExpResult.exp_pool,
                    "exp_pooled_time": (0, utils_1.getServerTime)(playerData.expPooledTime),
                    "free_vmoney": (_r = finalPlayerData === null || finalPlayerData === void 0 ? void 0 : finalPlayerData.freeVmoney) !== null && _r !== void 0 ? _r : playerData.freeVmoney,
                    "rank_point": newRankPoint,
                    "degree_id": (_s = playerData.degreeId) !== null && _s !== void 0 ? _s : 1,
                    "stamina": playerData.stamina,
                    "stamina_heal_time": (0, utils_1.realToVirtual)(playerData.staminaHealTime),
                    "boost_point": newBoostPoint,
                    "boss_boost_point": newBossBoostPoint
                },
                "add_exp_list": [
                    ...rewardCharacterExpResult.add_exp_list,
                    ...((rogueDrops === null || rogueDrops === void 0 ? void 0 : rogueDrops.addExpList) || []),
                ],
                "character_list": characterList,
                "bond_token_status_list": Object.assign(Object.assign({}, rewardCharacterExpResult.bond_token_status_list), ((rogueDrops === null || rogueDrops === void 0 ? void 0 : rogueDrops.bondTokenStatusList) || {})),
                "rewards": {
                    "overflow_pool_exp": 0,
                    "converted_pool_exp": 0,
                    "reward_pool_exp": questData.poolExpReward,
                    // Rush result panels do not render reward_mana in the
                    // acquired-item area.  Mode15 presents the same credited
                    // amount through the native field-mana slot so the Mana
                    // icon and quantity are visible; user_info.free_mana
                    // remains authoritative and the award is not duplicated.
                    "reward_mana": displayMode15ManaAsFieldDrop ? 0 : questData.manaReward,
                    "field_mana": body.add_mana
                        + (displayMode15ManaAsFieldDrop ? questData.manaReward : 0)
                },
                "old_high_score": questProgress === null ? 0 : questProgress.highScore || 0,
                "joined_character_id_list": [
                    ...((clearReward === null || clearReward === void 0 ? void 0 : clearReward.joined_character_id_list) || []),
                    ...((sPlusClearReward === null || sPlusClearReward === void 0 ? void 0 : sPlusClearReward.joined_character_id_list) || []),
                    ...scoreRewardsResult.joined_character_id_list,
                    ...((carnivalRewardsResult === null || carnivalRewardsResult === void 0 ? void 0 : carnivalRewardsResult.joined_character_id_list) || []),
                    ...((mode15RewardsResult === null || mode15RewardsResult === void 0 ? void 0 : mode15RewardsResult.joined_character_id_list) || [])
                ],
                "before_rank_point": beforeRankPoint,
                "clear_rank": clearRank !== null && clearRank !== void 0 ? clearRank : 5,
                "drop_score_reward_ids": scoreRewardsResult.drop_score_reward_ids,
                "drop_rare_reward_ids": scoreRewardsResult.drop_rare_reward_ids,
                "drop_additional_reward_ids": [
                    ...((_t = rogueDrops === null || rogueDrops === void 0 ? void 0 : rogueDrops.additionalRewardEntries) !== null && _t !== void 0 ? _t : []),
                    ...((_u = mode15RewardsResult === null || mode15RewardsResult === void 0 ? void 0 : mode15RewardsResult.mode15_additional_reward_ids) !== null && _u !== void 0 ? _u : []),
                ],
                "drop_periodic_reward_ids": [],
                "equipment_list": [
                    ...scoreRewardsResult.equipment_list,
                    ...((clearReward === null || clearReward === void 0 ? void 0 : clearReward.equipment_list) || []),
                    ...((sPlusClearReward === null || sPlusClearReward === void 0 ? void 0 : sPlusClearReward.equipment_list) || []),
                    ...((rushEventRewardsResult === null || rushEventRewardsResult === void 0 ? void 0 : rushEventRewardsResult.equipment_list) || []),
                    ...((rogueDrops === null || rogueDrops === void 0 ? void 0 : rogueDrops.rewardResult.equipment_list) || []),
                    ...((carnivalRewardsResult === null || carnivalRewardsResult === void 0 ? void 0 : carnivalRewardsResult.equipment_list) || []),
                    ...((mode15RewardsResult === null || mode15RewardsResult === void 0 ? void 0 : mode15RewardsResult.equipment_list) || [])
                ],
                "category_id": body.category,
                "start_time": dataHeaders['servertime'],
                "is_multi": "single",
                "quest_name": "",
                "item_list": itemList,
                "rush_event": rushEventData,
                "raid_event": raidEventData,
                "carnival_event": carnivalEventData,
                "score_attack_event": scoreAttackEventData,
                "user_daily_challenge_point_list": dailyChallengePointList !== null && dailyChallengePointList !== void 0 ? dailyChallengePointList : [],
                "presigned_quest_category": []
            };
            if (raidEventData === null || raidEventData === void 0 ? void 0 : raidEventData.new_degree_ids.length) {
                responseData.degree_list = raidEventData.new_degree_ids.map(degreeId => ({
                    viewer_id: viewerId,
                    degree_id: degreeId,
                }));
            }
            (0, mission_2.mergeMissionSettlementResponse)(responseData, missionSettlement, viewerId);
            // Awake settlement re-publishes completed special unlocks itself,
            // including already-persisted rows whose earlier response was lost.
            (0, mission_2.mergeMissionSettlementResponse)(responseData, awakeMissionSettlement, viewerId);
            if (activeMissionSettlement.length > 0) {
                responseData.active_mission_list = activeMissionSettlement;
            }
            responseData.mail_arrived = (0, mail_1.getPlayerMailCountSync)(playerId, true) > 0;
            return {
                "data_headers": dataHeaders,
                "data": responseData,
            };
        })());
        delete exports.activeQuests[playerId];
        (0, finish_response_cache_1.cacheFinishResponse)(finishCacheKey, finishResponse);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send(finishResponse);
    }));
    fastify.post("/abort", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (isNaN(viewerId))
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        const sessionResult = yield (0, session_validator_1.validateSessionAndPlayer)(viewerId);
        if (!sessionResult)
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid viewer id."
            });
        const { playerId } = sessionResult;
        const headers = (0, utils_1.generateDataHeaders)({ viewer_id: body.viewer_id });
        // A defeated/abandoned single battle reaches /abort rather than
        // /finish(is_accomplished=false) on the legacy client. Resolve the
        // authoritative active quest before deleting it so Fantasy Rush can
        // apply the same fail-and-reset transition on both paths.
        const resolvedAbortQuest = (0, active_quest_resolver_1.resolveActiveQuest)({
            playerId,
            hint: body,
            memory: exports.activeQuests,
            allowRebuild: false,
        });
        const abortQuest = resolvedAbortQuest === null || resolvedAbortQuest === void 0 ? void 0 : resolvedAbortQuest.quest;
        let practiceHistoryRecord = null;
        if ((abortQuest === null || abortQuest === void 0 ? void 0 : abortQuest.category) === types_1.QuestCategory.PRACTICE) {
            if (body.category !== abortQuest.category
                || body.quest_id !== abortQuest.questId
                || body.play_id !== abortQuest.playId) {
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": "Active practice quest does not match abort request.",
                });
            }
            if (abortQuest.startedAtMs === undefined) {
                console.warn(`[PRACTICE-HISTORY] abort history skipped because start time is unavailable: `
                    + `player=${playerId} quest=${abortQuest.questId} play=${abortQuest.playId}`);
            }
            else {
                const abortedAtMs = (0, utils_1.getServerTime)() * 1000;
                try {
                    practiceHistoryRecord = (0, practice_battle_history_2.buildPracticeBattleHistoryRecord)({
                        playerId,
                        playId: abortQuest.playId,
                        categoryId: abortQuest.category,
                        questId: abortQuest.questId,
                        finishKind: body.finish_kind,
                        createdAt: new Date(abortedAtMs),
                        elapsedTimeMs: Math.max(0, abortedAtMs - abortQuest.startedAtMs),
                        score: null,
                        clearRank: null,
                        party: body.statistics.party,
                        statistics: body.statistics,
                        equipmentList: (0, equipment_1.getPlayerEquipmentListSync)(playerId),
                    });
                }
                catch (error) {
                    console.warn(`[PRACTICE-HISTORY] invalid abort history payload: player=${playerId} `
                        + `quest=${abortQuest.questId} error=${error.message}`);
                    return reply.status(400).send({
                        "error": "Bad Request",
                        "message": "Invalid practice battle abort data.",
                    });
                }
            }
        }
        // Keep the failure transition, history row, and active-quest deletion
        // atomic so a partial settlement cannot erase the recoverable battle.
        (0, db_1.getDb)().transaction(() => {
            if (abortQuest && (0, mode15_optional_1.isMode15Quest)(abortQuest.category, abortQuest.questId)) {
                (0, mode15_optional_1.settleMode15BattleSync)(playerId, abortQuest.category, abortQuest.questId, false);
            }
            if (practiceHistoryRecord !== null) {
                (0, practice_battle_history_1.insertPlayerPracticeBattleHistorySync)(practiceHistoryRecord);
            }
            (0, quest_active_1.deletePlayerActiveQuestSync)(playerId);
        })();
        delete exports.activeQuests[playerId];
        if (abortQuest && (0, mode15_optional_1.isMode15Quest)(abortQuest.category, abortQuest.questId)) {
            console.log(`[MODE15] single battle aborted; run reset: player=${playerId} category=${abortQuest.category} quest=${abortQuest.questId}`);
        }
        return reply.status(200).send({
            "data_headers": headers,
            "data": {
                "user_info": {},
                "category_id": body.category,
                "is_multi": "single",
                "start_time": headers['servertime'],
                "quest_name": ""
            }
        });
    }));
    fastify.post("/start", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _b, _c, _d;
        const body = request.body;
        const viewerId = body.viewer_id;
        const partyId = body.party_id;
        const questId = body.quest_id;
        const category = body.category;
        const useBoostPoint = body.use_boost_point;
        const useBossBoostPoint = body.use_boss_boost_point;
        const isAutoStartMode = body.is_auto_start_mode;
        if (isNaN(viewerId) || isNaN(partyId) || isNaN(questId) || isNaN(category) || useBoostPoint === undefined || useBossBoostPoint === undefined || isAutoStartMode === undefined)
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid request body."
            });
        const sessionResult = yield (0, session_validator_1.validateSessionAndPlayer)(viewerId);
        if (!sessionResult)
            return reply.status(400).send({
                "error": "Bad Request", "message": "Invalid viewer id."
            });
        const { playerId, playerData: player } = sessionResult;
        if (!(0, mode15_optional_1.isMode15Quest)(category, questId)) {
            // Carnival quests use their own saved party category.  Looking up
            // NORMAL here allowed Mode15-exclusive equipment in Carnival even
            // though the selected Carnival party actually contained it.
            const partyCategory = category === types_1.QuestCategory.CARNIVAL_EVENT
                ? types_2.PartyCategory.CARNIVAL
                : types_2.PartyCategory.NORMAL;
            const restricted = (0, mode15_optional_1.getMode15ExclusiveGlobalPartyItemsSync)(playerId, partyCategory, partyId);
            if (restricted.length > 0) {
                console.log(`[MODE15] exclusive equipment denied in single battle: player=${playerId} quest=${questId} questCategory=${category} partyCategory=${partyCategory} party=${partyId} items=${restricted.join(",")}`);
                reply.header("content-type", "application/x-msgpack");
                return reply.status(200).send({
                    // Quest-start clients natively map 4050 to their normal
                    // "out of period" rejection dialog.  4507 belongs to
                    // create-room failure and causes a fatal client error
                    // when returned from questStart.
                    data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: viewerId, result_code: 4050 }),
                    data: {},
                });
            }
        }
        // get quest data
        const questData = (0, assets_1.getQuestFromCategorySync)(category, questId);
        if (questData === null || !('rankPointReward' in questData)) {
            console.warn(`[BATTLE] start failed: category=${category} questId=${questId} found=${!!questData} hasRankReward=${questData ? ('rankPointReward' in questData) : 'N/A'}`);
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Quest doesn't exist."
            });
        }
        // Deduct entry cost (ticket/item)
        const questKey = `${category}_${questId}`;
        const configuredEntryCost = quest_entry_costs_json_1.default[questKey];
        let entryCost;
        const staminaInfo = (0, stamina_cost_1.getStaminaCost)(questKey);
        const nominalStaminaCost = Math.max(0, staminaInfo.cost);
        (0, game_logging_1.gameVerboseLog)(() => `[BATTLE] start free-entry: questId=${questId} questKey=${questKey} nominalEntryCost=${JSON.stringify(configuredEntryCost)} nominalStamina=${nominalStaminaCost}`);
        if (entryCost && entryCost.itemId > 0) {
            const playerItemCount = (_b = (0, item_1.getPlayerItemSync)(playerId, entryCost.itemId)) !== null && _b !== void 0 ? _b : 0;
            (0, game_logging_1.gameVerboseLog)(() => `[BATTLE] start deduct: itemId=${entryCost.itemId} playerHas=${playerItemCount} need=${entryCost.itemCount}`);
            if (playerItemCount < entryCost.itemCount) {
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": `Not enough entry items (need ${entryCost.itemCount} of ${entryCost.itemId}, have ${playerItemCount}).`
                });
            }
            (0, item_1.updatePlayerItemSync)(playerId, entryCost.itemId, playerItemCount - entryCost.itemCount);
        }
        // Deduct stamina cost
        const staminaCost = 0;
        let afterStamina = 0;
        if (staminaCost > 0) {
            const currentStamina = (0, stamina_1.computeRealTimeStamina)(player);
            if (currentStamina < staminaCost) {
                console.warn(`[BATTLE-START] player ${playerId} stamina insufficient: ${currentStamina} < ${staminaCost}`);
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": "Insufficient stamina."
                });
            }
            const newStamina = Math.max(0, currentStamina - staminaCost);
            (0, player_1.updatePlayerSync)({
                id: playerId,
                stamina: newStamina,
                staminaHealTime: new Date(),
                totalStaminaUsed: ((_c = player.totalStaminaUsed) !== null && _c !== void 0 ? _c : 0) + staminaCost
            });
            afterStamina = newStamina;
            (0, game_logging_1.gameVerboseLog)(() => `[BATTLE-START] stamina: ${currentStamina} -> ${newStamina} (cost: ${staminaCost}, rate: ${staminaInfo.rate})`);
        }
        else {
            // No stamina deduction, read current stamina for response
            const player = (0, player_1.getPlayerSync)(playerId);
            afterStamina = (_d = player === null || player === void 0 ? void 0 : player.stamina) !== null && _d !== void 0 ? _d : 0;
        }
        // add to active quests table
        delete exports.activeQuests[playerId];
        exports.activeQuests[playerId] = {
            questId: questId,
            category: category,
            useBoostPoint: useBoostPoint,
            useBossBoostPoint: useBossBoostPoint,
            isAutoStartMode: isAutoStartMode,
            isMulti: false,
            entryItemId: entryCost === null || entryCost === void 0 ? void 0 : entryCost.itemId,
            playId: body.play_id,
            continueCount: 0,
            startedAtMs: (0, utils_1.getServerTime)() * 1000,
        };
        let missionSettlement;
        (0, db_1.getDb)().transaction(() => {
            var _a, _b, _c, _d, _e;
            const playerUpdate = {
                id: playerId,
                totalStaminaUsed: ((_a = player.totalStaminaUsed) !== null && _a !== void 0 ? _a : 0) + nominalStaminaCost,
            };
            if (questData.fixedParty === undefined)
                playerUpdate.partySlot = partyId;
            (0, player_1.updatePlayerSync)(playerUpdate);
            const activeQuest = exports.activeQuests[playerId];
            (0, quest_active_1.insertPlayerActiveQuestSync)(playerId, {
                playerId,
                playId: activeQuest.playId,
                questId: activeQuest.questId,
                category: activeQuest.category,
                useBossBoostPoint: activeQuest.useBossBoostPoint,
                useBoostPoint: activeQuest.useBoostPoint,
                isAutoStartMode: activeQuest.isAutoStartMode,
                isMulti: activeQuest.isMulti,
                isMultiHost: (_b = activeQuest.isMultiHost) !== null && _b !== void 0 ? _b : false,
                roomNumber: (_c = activeQuest.roomNumber) !== null && _c !== void 0 ? _c : null,
                entryItemId: null,
                eventId: (_d = activeQuest.eventId) !== null && _d !== void 0 ? _d : null,
                continueCount: activeQuest.continueCount,
                startedAtMs: (_e = activeQuest.startedAtMs) !== null && _e !== void 0 ? _e : null,
            });
            (0, active_entry_facts_1.recordActiveMissionQuestChallengeFactSync)(playerId, category);
            missionSettlement = (0, mission_2.settleMissionCategories)(playerId, [1, 2, 10], new Date((0, utils_1.getServerTime)() * 1000));
        })();
        const dataHeaders = (0, utils_1.generateDataHeaders)({
            viewer_id: viewerId
        });
        reply.header("content-type", "application/x-msgpack");
        const responseData = {
            "user_info": {
                "last_main_quest_id": body.quest_id,
                "stamina": afterStamina,
                "stamina_heal_time": (0, utils_1.realToVirtual)(new Date())
            },
            "item_list": {},
            "category_id": body.category,
            "is_multi": "single",
            "start_time": dataHeaders['servertime'],
            "quest_name": "",
            "client_checks": (0, steam_robot_challenge_1.getSteamRobotMissionClientChecks)(category, questId)
        };
        if (missionSettlement) {
            (0, mission_2.mergeMissionSettlementResponse)(responseData, missionSettlement, viewerId);
        }
        responseData.mail_arrived = (0, mail_1.getPlayerMailCountSync)(playerId, true) > 0;
        return reply.status(200).send({
            "data_headers": dataHeaders,
            "data": responseData,
        });
    }));
    fastify.route({
        method: ["GET", "POST"],
        url: "/play_continue",
        handler: (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
            var _e, _f;
            // Some legacy builds submit this endpoint as GET, while newer builds
            // use POST. Normalize both forms so a revive is not treated as an
            // unknown route by the client.
            const raw = ((_e = (request.method === "GET" ? request.query : request.body)) !== null && _e !== void 0 ? _e : {});
            const viewerId = Number(raw.viewer_id);
            const questId = Number(raw.quest_id);
            const category = Number(raw.category);
            const playId = (_f = raw.play_id) !== null && _f !== void 0 ? _f : raw.paly_id;
            if (!Number.isSafeInteger(viewerId)
                || !Number.isSafeInteger(questId)
                || !Number.isSafeInteger(category))
                return reply.status(400).send({
                    "error": "Bad Request", "message": "Invalid request body."
                });
            const sessionResult = yield (0, session_validator_1.validateSessionAndPlayer)(viewerId);
            if (!sessionResult)
                return reply.status(400).send({
                    "error": "Bad Request", "message": "Invalid viewer id."
                });
            const { playerId, playerData: player } = sessionResult;
            // Continue may recover a persisted battle after a restart, but never
            // rebuild one from request data: doing so would create a new revive path.
            const resolvedContinueQuest = (0, active_quest_resolver_1.resolveActiveQuest)({
                playerId,
                hint: {
                    quest_id: questId,
                    category,
                    play_id: playId,
                },
                memory: exports.activeQuests,
                allowRebuild: false,
            });
            const activeQuestData = resolvedContinueQuest === null || resolvedContinueQuest === void 0 ? void 0 : resolvedContinueQuest.quest;
            if (activeQuestData === undefined)
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": "No active quest to continue."
                });
            const freeVmoney = player.freeVmoney;
            const vmoney = player.vmoney;
            const freeVmoneyCost = Math.min(freeVmoney, continueVmoneyCost);
            const paidVmoneyCost = continueVmoneyCost - freeVmoneyCost;
            if (vmoney < paidVmoneyCost)
                return reply.status(400).send({
                    "error": "Bad Request",
                    "message": "Not enough vmoney to continue"
                });
            const newFreeVmoney = freeVmoney - freeVmoneyCost;
            const newVmoney = vmoney - paidVmoneyCost;
            // update the player's vmoney balances
            (0, player_1.updatePlayerSync)({
                id: playerId,
                freeVmoney: newFreeVmoney,
                vmoney: newVmoney
            });
            // increment continue count for battle recovery
            activeQuestData.continueCount++;
            (0, quest_active_1.updatePlayerActiveQuestContinueCountSync)(playerId, activeQuestData.continueCount);
            reply.header("content-type", "application/x-msgpack");
            return reply.status(200).send({
                "data_headers": (0, utils_1.generateDataHeaders)({
                    viewer_id: viewerId
                }),
                "data": {
                    "user_info": {
                        "free_vmoney": newFreeVmoney,
                        "vmoney": newVmoney
                    },
                    "mail_arrived": false
                }
            });
        })
    });
});
exports.default = routes;
