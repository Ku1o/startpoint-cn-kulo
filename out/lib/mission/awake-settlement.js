"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.settleAwakeMissionRewards = exports.settleAwakeMissionCandidates = exports.getAwakeBattleMissionIds = void 0;
const character_awake_1 = require("../../data/domains/character_awake");
const mission_1 = require("../../data/domains/mission");
const player_1 = require("../../data/domains/player");
const db_1 = require("../../data/db");
const character_helpers_1 = require("../character-helpers");
const grants_1 = require("./grants");
const rewards_1 = require("./rewards");
const stages_1 = require("./stages");
const stages_2 = require("./stages");
const character_queries_1 = require("./character-queries");
const registry_1 = require("./registry");
function getAwakeBattleMissionIds(characterIds, directlyChangedMissionIds = []) {
    const targetCharacterIds = new Set(characterIds.filter(characterId => Number.isSafeInteger(characterId) && characterId > 0));
    const missionIds = new Set(directlyChangedMissionIds.filter(missionId => Number.isSafeInteger(missionId) && missionId > 0));
    for (const missionId of (0, stages_2.getMissionIdsByCategory)(9)) {
        if (targetCharacterIds.has(Number((0, character_queries_1.getCharacterIdFromMission)(missionId)))) {
            missionIds.add(missionId);
        }
    }
    return [...missionIds];
}
exports.getAwakeBattleMissionIds = getAwakeBattleMissionIds;
function settleAwakeMissionCandidates(playerId, missionIds, evaluationTime) {
    const uniqueMissionIds = [...new Set(missionIds)];
    if (uniqueMissionIds.length === 0) {
        return {
            missionInfo: [], itemList: {}, characterList: [], equipmentList: [],
            degreeIds: [], passCardPoints: {},
        };
    }
    const persisted = (0, mission_1.getPlayerCategoryMissionsSync)(playerId, 9);
    const computer = (0, registry_1.getComputer)(9);
    const context = computer.buildContext(playerId, 9, evaluationTime, uniqueMissionIds);
    const progressList = uniqueMissionIds.map(missionId => {
        var _a, _b;
        const dbProgress = (_b = (_a = persisted[String(missionId)]) === null || _a === void 0 ? void 0 : _a.progress) !== null && _b !== void 0 ? _b : 0;
        const computed = computer.compute(missionId, context, dbProgress);
        const monotonicProgress = Math.max(0, dbProgress, Number.isFinite(computed) ? computed : 0);
        const finalTarget = (0, stages_2.getMissionFinalTargetProgress)(9, missionId);
        return {
            missionId,
            progress: finalTarget === undefined
                ? monotonicProgress
                : Math.min(monotonicProgress, finalTarget),
        };
    });
    return settleAwakeMissionRewards(playerId, progressList);
}
exports.settleAwakeMissionCandidates = settleAwakeMissionCandidates;
function settleAwakeMissionRewards(playerId, progressList) {
    const progressByMissionId = new Map();
    for (const entry of progressList) {
        const currentProgress = progressByMissionId.get(entry.missionId);
        if (currentProgress === undefined || entry.progress > currentProgress) {
            progressByMissionId.set(entry.missionId, entry.progress);
        }
    }
    const aggregatedProgressList = [...progressByMissionId].map(([missionId, progress]) => ({
        missionId,
        progress,
    }));
    const player = (0, player_1.getPlayerSync)(playerId);
    if (!player)
        throw new Error(`Player ${playerId} not found during CharacterAwake settlement.`);
    const persistedMissions = (0, mission_1.getPlayerCategoryMissionsSync)(playerId, 9);
    const granter = new grants_1.MissionRewardGranter(playerId, player);
    const missionInfo = [];
    const unlockMap = new Map();
    const unlockCandidateCharacterIds = aggregatedProgressList.map(entry => Number((0, character_queries_1.getCharacterIdFromMission)(entry.missionId)));
    let persistedUnlocks = null;
    (0, db_1.getDb)().transaction(() => {
        var _a, _b, _c, _d, _e;
        for (const entry of aggregatedProgressList) {
            (0, mission_1.updatePlayerCategoryMissionSync)(playerId, 9, entry.missionId, entry.progress);
        }
        for (const entry of aggregatedProgressList) {
            const persistedStages = (_a = persistedMissions[String(entry.missionId)]) === null || _a === void 0 ? void 0 : _a.stages;
            for (const stage of (0, stages_1.getCompletedStageNumbers)(9, entry.missionId, entry.progress)) {
                const definition = (0, rewards_1.getAwakeMissionRewardStageDefinition)(entry.missionId, stage);
                if (!definition)
                    continue;
                // Special rewards are authoritative state, not consumable
                // grants. Re-assert and publish them even when the mission
                // stage was received earlier and its original response was
                // lost. The monotonic upsert keeps this idempotent.
                if (definition.specialReward) {
                    const special = definition.specialReward;
                    persistedUnlocks !== null && persistedUnlocks !== void 0 ? persistedUnlocks : (persistedUnlocks = (0, character_awake_1.getPlayerCharacterAwakeUnlocksByCharacterIdsSync)(playerId, unlockCandidateCharacterIds));
                    const characterKey = String(special.characterId);
                    const persistedLevels = (_b = persistedUnlocks.get(characterKey)) !== null && _b !== void 0 ? _b : {};
                    if (((_c = persistedLevels[special.boardIndex]) !== null && _c !== void 0 ? _c : 0) < special.awakeLevel) {
                        (0, character_awake_1.upsertPlayerCharacterAwakeUnlockSync)(playerId, special.characterId, special.boardIndex, special.awakeLevel);
                        persistedLevels[special.boardIndex] = special.awakeLevel;
                        persistedUnlocks.set(characterKey, persistedLevels);
                    }
                    const levels = (_d = unlockMap.get(characterKey)) !== null && _d !== void 0 ? _d : {};
                    levels[special.boardIndex] = Math.max((_e = levels[special.boardIndex]) !== null && _e !== void 0 ? _e : 0, special.awakeLevel);
                    unlockMap.set(characterKey, levels);
                }
                if (!Array.isArray(persistedStages) && (persistedStages === null || persistedStages === void 0 ? void 0 : persistedStages[String(stage)]) === true)
                    continue;
                (0, mission_1.updatePlayerCategoryMissionStageSync)(playerId, 9, stage, entry.missionId, true);
                granter.grant(definition.rewards);
                missionInfo.push({
                    mission_category_id: 9,
                    mission_id: entry.missionId,
                    mission_reward_id: definition.missionRewardId,
                });
            }
        }
        granter.persistPlayer();
    })();
    const unlockCharacterList = unlockMap.size === 0
        ? []
        : (0, character_helpers_1.buildScopedManaBoardAwakeCharacterList)(playerId, unlockMap);
    const characterList = [
        ...granter.characterList,
        ...unlockCharacterList,
    ];
    return Object.assign({ missionInfo, itemList: granter.itemList, characterList, equipmentList: granter.equipmentList, degreeIds: granter.degreeList, passCardPoints: {} }, (granter.hasPlayerChanges() ? { userInfo: granter.getUserInfo() } : {}));
}
exports.settleAwakeMissionRewards = settleAwakeMissionRewards;
