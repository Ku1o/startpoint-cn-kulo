"use strict";
// Mission progress endpoints — get and update
// Uses lib/mission/ computer registry for compute dispatch
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
const mission_1 = require("../../data/domains/mission");
const session_1 = require("../../data/domains/session");
const db_1 = require("../../data/db");
const mail_1 = require("../../data/domains/mail");
const utils_1 = require("../../utils");
const index_1 = require("../../lib/mission/index");
const client_progress_1 = require("../../lib/mission/client-progress");
const activeAccount_1 = require("../../data/activeAccount");
const progress_1 = require("../../lib/mission/progress");
const game_logging_1 = require("../../lib/game-logging");
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.post("/get_mission_progress", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _a, _b, _c;
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!viewerId || isNaN(viewerId))
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid request body."
            });
        const session = yield (0, session_1.getSession)(viewerId.toString());
        if (!session)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid viewer id."
            });
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(session.accountId);
        if (playerId === null)
            return reply.status(500).send({
                "error": "Internal Server Error",
                "message": "No players bound to account."
            });
        // Cache computer+context per category to avoid redundant builds
        const computerCache = new Map();
        function getCtx(category, missionIds) {
            const cacheKey = missionIds === undefined
                ? String(category)
                : `${category}:${missionIds.join(",")}`;
            let entry = computerCache.get(cacheKey);
            if (!entry) {
                const computer = (0, index_1.getComputer)(category);
                const ctx = computer.buildContext(playerId, category, evaluationTime, missionIds);
                entry = { ctx };
                computerCache.set(cacheKey, entry);
            }
            return entry.ctx;
        }
        const requestList = body.category_list || [{ category: 1 }];
        const requestCategories = requestList.map(c => c.category);
        const evaluationTime = new Date((0, utils_1.getServerTime)() * 1000);
        const automaticScopes = requestList
            .filter(entry => [1, 2, 3, 4, 5, 6, 7, 8, 10].includes(entry.category))
            .map(entry => ({ category: entry.category, eventId: entry.event_id }));
        const automaticSettlement = automaticScopes.length > 0
            ? (0, index_1.settleMissionCategories)(playerId, automaticScopes, evaluationTime)
            : null;
        const missionProgressList = [];
        const categoryMissionCache = new Map();
        const awakeProgressByCharacter = new Map();
        for (const requestEntry of requestList) {
            const category = requestEntry.category;
            const computer = (0, index_1.getComputer)(category);
            let categoryMissions = categoryMissionCache.get(category);
            if (!categoryMissions) {
                categoryMissions = (0, mission_1.getPlayerCategoryMissionsSync)(playerId, category);
                categoryMissionCache.set(category, categoryMissions);
            }
            const allIds = (0, index_1.getMissionIdsByCategory)(category).filter(missionId => (0, index_1.isMissionEnabledAt)(category, missionId, evaluationTime, requestEntry.event_id));
            const charId = requestEntry.character_id === undefined ? undefined : String(requestEntry.character_id);
            const requestedIds = charId && category === 9
                ? allIds.filter(missionId => (0, index_1.getCharacterIdFromMission)(missionId) === charId)
                : allIds;
            const ctx = getCtx(category, requestedIds);
            for (const missionId of requestedIds) {
                const dbProgress = (_b = (_a = categoryMissions[String(missionId)]) === null || _a === void 0 ? void 0 : _a.progress) !== null && _b !== void 0 ? _b : 0;
                const computed = computer.compute(missionId, ctx, dbProgress);
                const finalTarget = (0, index_1.getMissionFinalTargetProgress)(category, missionId);
                const monotonicProgress = Math.max(0, dbProgress, Number.isFinite(computed) ? computed : 0);
                const progress = finalTarget === undefined
                    ? monotonicProgress
                    : Math.min(monotonicProgress, finalTarget);
                const stage = (0, index_1.getCurrentStage)(category, missionId, progress);
                missionProgressList.push({
                    mission_category: category,
                    mission_id: missionId,
                    progress_value: Number(progress),
                    stage: stage
                });
                if (category === 9 && charId !== undefined) {
                    const awakeProgress = (_c = awakeProgressByCharacter.get(charId)) !== null && _c !== void 0 ? _c : [];
                    awakeProgress.push({ missionId, progress: Number(progress) });
                    awakeProgressByCharacter.set(charId, awakeProgress);
                }
            }
        }
        (0, game_logging_1.gameVerboseLog)(() => `[MISSION] get_progress viewer=${viewerId} categories=${requestCategories} missions=${missionProgressList.length}`);
        const missionInfo = [];
        const itemList = {};
        let characterList = [];
        const equipmentList = [];
        const degreeIds = [];
        let userInfo;
        for (const awakeProgress of awakeProgressByCharacter.values()) {
            const settlement = (0, index_1.settleAwakeMissionRewards)(playerId, awakeProgress);
            missionInfo.push(...settlement.missionInfo);
            Object.assign(itemList, settlement.itemList);
            characterList.push(...settlement.characterList);
            equipmentList.push(...settlement.equipmentList);
            for (const degreeId of settlement.degreeIds) {
                if (!degreeIds.includes(degreeId))
                    degreeIds.push(degreeId);
            }
            if (settlement.userInfo)
                userInfo = settlement.userInfo;
        }
        const requestedAwakeProgress = [...awakeProgressByCharacter.values()].flat();
        if (requestedAwakeProgress.length > 0) {
            // The client caches Awake availability separately from the mission
            // page.  Reconcile from the progress already computed above, then
            // always re-publish the scoped character state so a lost earlier
            // response never forces a relogin.
            const unlocks = (0, index_1.reconcileAwakeUnlocksFromProgress)(playerId, requestedAwakeProgress).all;
            characterList = (0, index_1.refreshAwakeUnlockCharacterList)(playerId, characterList, unlocks, [...awakeProgressByCharacter.keys()].map(Number));
        }
        const responseData = {
            mission_progress_list: missionProgressList,
            mission_info: missionInfo,
            item_list: itemList,
            character_list: characterList,
            equipment_list: equipmentList,
            degree_list: degreeIds.map(degreeId => ({ viewer_id: viewerId, degree_id: degreeId })),
        };
        if (userInfo)
            responseData.user_info = userInfo;
        if (automaticSettlement) {
            (0, index_1.mergeMissionSettlementResponse)(responseData, automaticSettlement, viewerId);
        }
        responseData.mail_arrived = (0, mail_1.getPlayerMailCountSync)(playerId, true) > 0;
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": responseData
        });
    }));
    fastify.post("/update_mission_progress", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = body.viewer_id;
        if (!viewerId || isNaN(viewerId))
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid request body."
            });
        const session = yield (0, session_1.getSession)(viewerId.toString());
        if (!session)
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid viewer id."
            });
        const playerId = (0, activeAccount_1.resolvePlayerIdSync)(session.accountId);
        if (playerId === null)
            return reply.status(500).send({
                "error": "Internal Server Error",
                "message": "No players bound to account."
            });
        // Update mission progress counters in DB (fire-and-forget from client)
        const missionParams = body.mission_param_list || [];
        let updatedCount = 0;
        const evaluationTime = new Date((0, utils_1.getServerTime)() * 1000);
        (0, db_1.getDb)().transaction(() => {
            var _a, _b;
            const categoryMissionCache = new Map();
            for (const param of missionParams) {
                const delta = (0, progress_1.addMissionProgressDelta)(0, param.progress_value);
                if (typeof param.mission_pattern !== "string" || delta === null)
                    continue;
                const matches = (0, client_progress_1.resolveClientProgressTargets)(param.mission_pattern, evaluationTime);
                for (const match of matches) {
                    let categoryMissions = categoryMissionCache.get(match.category);
                    if (!categoryMissions) {
                        categoryMissions = (0, mission_1.getPlayerCategoryMissionsSync)(playerId, match.category);
                        categoryMissionCache.set(match.category, categoryMissions);
                    }
                    const current = categoryMissions[String(match.missionId)];
                    const previousProgress = (_a = current === null || current === void 0 ? void 0 : current.progress) !== null && _a !== void 0 ? _a : 0;
                    const finalTarget = (0, index_1.getMissionFinalTargetProgress)(match.category, match.missionId);
                    const unboundedProgress = previousProgress + delta;
                    const nextProgress = finalTarget === undefined
                        ? unboundedProgress
                        : Math.min(unboundedProgress, finalTarget);
                    (0, mission_1.updatePlayerCategoryMissionSync)(playerId, match.category, match.missionId, nextProgress);
                    categoryMissions[String(match.missionId)] = {
                        progress: nextProgress,
                        stages: (_b = current === null || current === void 0 ? void 0 : current.stages) !== null && _b !== void 0 ? _b : [],
                    };
                    updatedCount++;
                }
            }
        })();
        const characterList = (0, index_1.reconcileAwakeUnlockCharacterList)(playerId, []);
        const responseData = {
            "mission_info": [],
            "degree_list": [],
            character_list: characterList,
            "mail_arrived": (0, mail_1.getPlayerMailCountSync)(playerId, true) > 0
        };
        // Client-reported title facts (voice, illustration and town taps) used
        // to remain pending until the title page was opened.  Settle them in
        // this response so the client can display the acquisition immediately.
        const degreeSettlement = (0, index_1.settleMissionCategories)(playerId, [5], evaluationTime);
        (0, index_1.mergeMissionSettlementResponse)(responseData, degreeSettlement, viewerId);
        (0, game_logging_1.gameVerboseLog)(() => `[MISSION] update_progress viewer=${viewerId} params=${missionParams.length} db_updates=${updatedCount}`);
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            "data_headers": (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            "data": responseData
        });
    }));
});
exports.default = routes;
