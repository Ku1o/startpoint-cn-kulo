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
Object.defineProperty(exports, "__esModule", { value: true });
exports.settleMissionCategoriesAsync = exports.settleMissionCategories = exports.settleMissionCategoriesWithProgress = void 0;
const mission_1 = require("../../data/domains/mission");
const db_1 = require("../../data/db");
const degree_1 = require("../../data/domains/degree");
const registry_1 = require("./registry");
const rewards_1 = require("./rewards");
const stages_1 = require("./stages");
const patterns_1 = require("./patterns");
const grants_1 = require("./grants");
const master_data_1 = require("./master-data");
const sqlite_write_coordinator_1 = require("../sqlite-write-coordinator");
const evaluation_context_1 = require("./evaluation-context");
function isDailyCoreMission(pattern) {
    return /^single_battle_play(?:_[23])?$/.test(pattern)
        || /^multi_battle_play(?:_[23])?$/.test(pattern)
        || /^use_dash(?:_[23])?$/.test(pattern)
        || pattern === "daily_quest_stamina_use_2024_02";
}
function applyDailyCompletionProgress(missions) {
    const dailyMissions = missions.filter(mission => mission.category === 2);
    if (dailyMissions.length === 0)
        return;
    const completedCoreCount = dailyMissions.filter(mission => {
        const pattern = (0, patterns_1.getMissionPattern)(2, mission.missionId);
        return isDailyCoreMission(pattern)
            && (0, stages_1.isMissionProgressComplete)(2, mission.missionId, mission.progress);
    }).length;
    for (const mission of dailyMissions) {
        if (!(0, patterns_1.getMissionPattern)(2, mission.missionId).startsWith("daily_quest_all_clear"))
            continue;
        mission.progress = Math.max(mission.dbProgress, completedCoreCount);
    }
}
function evaluateMissionCategories(playerId, categories, evaluationTime) {
    var _a, _b, _c, _d;
    const evaluatedMissions = [];
    const evaluatedMissionKeys = new Set();
    const scopes = new Map();
    for (const entry of categories) {
        const scope = typeof entry === "number" ? { category: entry } : entry;
        scopes.set(`${scope.category}:${(_a = scope.eventId) !== null && _a !== void 0 ? _a : ""}`, scope);
    }
    const preparedScopes = [...scopes.values()].map(scope => {
        var _a;
        return ({
            scope,
            candidateMissionIds: (_a = scope.missionIds) !== null && _a !== void 0 ? _a : (0, stages_1.getMissionIdsByCategory)(scope.category),
        });
    }).filter(entry => entry.candidateMissionIds.length > 0);
    const persistedByCategory = (0, mission_1.getPlayerCategoryMissionsForCategoriesSync)(playerId, preparedScopes.map(entry => entry.scope.category));
    const readContext = new evaluation_context_1.MissionEvaluationReadContext(playerId);
    const player = readContext.player;
    for (const { scope, candidateMissionIds } of preparedScopes) {
        const { category, eventId } = scope;
        const computer = (0, registry_1.getComputer)(category);
        const context = computer.buildContext(playerId, category, evaluationTime, candidateMissionIds, readContext);
        const persisted = (_b = persistedByCategory[String(category)]) !== null && _b !== void 0 ? _b : {};
        for (const missionId of candidateMissionIds) {
            if (!(0, patterns_1.isMissionEnabledAt)(category, missionId, evaluationTime, eventId))
                continue;
            const missionKey = `${category}:${missionId}`;
            if (evaluatedMissionKeys.has(missionKey))
                continue;
            evaluatedMissionKeys.add(missionKey);
            const current = persisted[String(missionId)];
            const dbProgress = (_c = current === null || current === void 0 ? void 0 : current.progress) !== null && _c !== void 0 ? _c : 0;
            const computed = computer.compute(missionId, context, dbProgress);
            const finalTarget = (0, stages_1.getMissionFinalTargetProgress)(category, missionId);
            const monotonicProgress = Math.max(0, dbProgress, Number.isFinite(computed) ? computed : 0);
            evaluatedMissions.push({
                category,
                missionId,
                progress: finalTarget === undefined
                    ? monotonicProgress
                    : category === 2
                        ? Math.max(dbProgress, Math.min(monotonicProgress, finalTarget))
                        : Math.min(monotonicProgress, finalTarget),
                receivedStages: (_d = current === null || current === void 0 ? void 0 : current.stages) !== null && _d !== void 0 ? _d : [],
                dbProgress,
            });
        }
    }
    applyDailyCompletionProgress(evaluatedMissions);
    return { player, evaluatedMissions };
}
function emptyMissionSettlementResult() {
    return {
        missionInfo: [],
        itemList: {},
        characterList: [],
        equipmentList: [],
        degreeIds: [],
        passCardPoints: {},
    };
}
function prepareMissionPersistence(playerId, evaluatedMissions) {
    const progressUpdates = evaluatedMissions.filter(mission => mission.progress !== mission.dbProgress);
    const pendingRewards = [];
    const legacyDegreeIds = new Set();
    for (const mission of evaluatedMissions) {
        for (const stage of (0, stages_1.getCompletedStageNumbers)(mission.category, mission.missionId, mission.progress)) {
            const definition = (0, rewards_1.getCategoryMissionRewardStageDefinition)(mission.category, mission.missionId, stage);
            if (!definition)
                continue;
            if (!Array.isArray(mission.receivedStages)
                && mission.receivedStages[String(stage)] === true) {
                if (mission.category === 5) {
                    for (const reward of definition.rewards) {
                        if (reward.kind === 6 && reward.degreeId !== undefined) {
                            legacyDegreeIds.add(reward.degreeId);
                        }
                    }
                }
                continue;
            }
            pendingRewards.push({ mission, stage, definition });
        }
    }
    const ownedDegrees = legacyDegreeIds.size > 0
        ? new Set((0, degree_1.getPlayerDegreeIdsSync)(playerId))
        : new Set();
    return {
        progressUpdates,
        pendingRewards,
        missingLegacyDegreeIds: [...legacyDegreeIds].filter(degreeId => !ownedDegrees.has(degreeId)),
    };
}
function persistMissionEvaluation(playerId, player, prepared) {
    var _a;
    const granter = new grants_1.MissionRewardGranter(playerId, player);
    const missionInfo = [];
    (0, mission_1.updatePlayerCategoryMissionBatchSync)(playerId, prepared.progressUpdates
        .map(mission => ({
        category: mission.category,
        missionId: mission.missionId,
        progress: mission.progress,
    })));
    for (const degreeId of prepared.missingLegacyDegreeIds) {
        granter.grantDegreeOwnershipOnly(degreeId);
    }
    (0, mission_1.updatePlayerCategoryMissionStageBatchSync)(playerId, prepared.pendingRewards.map(({ mission, stage }) => ({
        category: mission.category,
        missionId: mission.missionId,
        stageId: stage,
        status: true,
    })));
    for (const { mission, definition } of prepared.pendingRewards) {
        const passCardEventId = mission.category >= 6 && mission.category <= 8
            ? (_a = (0, master_data_1.getMissionMasterDefinition)(mission.category, mission.missionId)) === null || _a === void 0 ? void 0 : _a.eventId
            : undefined;
        granter.grant(definition.rewards, { passCardEventId });
        missionInfo.push({
            mission_category_id: mission.category,
            mission_id: mission.missionId,
            mission_reward_id: definition.missionRewardId,
        });
    }
    granter.persistPlayer();
    return Object.assign({ missionInfo, itemList: granter.itemList, characterList: granter.characterList, equipmentList: granter.equipmentList, degreeIds: granter.degreeList, passCardPoints: granter.passCardPoints }, (granter.hasPlayerChanges() ? { userInfo: granter.getUserInfo() } : {}));
}
function evaluatedProgressOf(evaluatedMissions) {
    return evaluatedMissions.map(mission => ({
        category: mission.category,
        missionId: mission.missionId,
        progress: mission.progress,
    }));
}
function settleMissionCategoriesWithProgress(playerId, categories, evaluationTime) {
    const evaluation = evaluateMissionCategories(playerId, categories, evaluationTime);
    const prepared = prepareMissionPersistence(playerId, evaluation.evaluatedMissions);
    const settlement = prepared.progressUpdates.length === 0
        && prepared.pendingRewards.length === 0
        && prepared.missingLegacyDegreeIds.length === 0
        ? emptyMissionSettlementResult()
        : (0, db_1.getDb)().transaction(() => persistMissionEvaluation(playerId, evaluation.player, prepared))();
    return {
        settlement,
        evaluatedProgress: evaluatedProgressOf(evaluation.evaluatedMissions),
    };
}
exports.settleMissionCategoriesWithProgress = settleMissionCategoriesWithProgress;
function settleMissionCategories(playerId, categories, evaluationTime) {
    return settleMissionCategoriesWithProgress(playerId, categories, evaluationTime).settlement;
}
exports.settleMissionCategories = settleMissionCategories;
function settleMissionCategoriesAsync(playerId, categories, evaluationTime) {
    return __awaiter(this, void 0, void 0, function* () {
        return (0, sqlite_write_coordinator_1.withPlayerWriteQueue)(playerId, () => __awaiter(this, void 0, void 0, function* () {
            // The expensive context scan is deliberately outside the write lock.
            const evaluation = evaluateMissionCategories(playerId, categories, evaluationTime);
            const prepared = prepareMissionPersistence(playerId, evaluation.evaluatedMissions);
            if (prepared.progressUpdates.length === 0
                && prepared.pendingRewards.length === 0
                && prepared.missingLegacyDegreeIds.length === 0) {
                return emptyMissionSettlementResult();
            }
            return (0, sqlite_write_coordinator_1.runImmediateTransactionWithRetry)(() => persistMissionEvaluation(playerId, evaluation.player, prepared));
        }));
    });
}
exports.settleMissionCategoriesAsync = settleMissionCategoriesAsync;
