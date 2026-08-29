"use strict";
// Compute awake mission summary for /load response
// Returns active_mission_list (Array format for data.active_mission_list)
Object.defineProperty(exports, "__esModule", { value: true });
exports.computeAwakeSummary = void 0;
const mission_1 = require("../../data/domains/mission");
const character_1 = require("../../data/domains/character");
const character_awake_1 = require("../../data/domains/character_awake");
const registry_1 = require("./registry");
const stages_1 = require("./stages");
const character_queries_1 = require("./character-queries");
const utils_1 = require("../../utils");
function computeAwakeSummary(playerId, snapshot = {}) {
    var _a, _b, _c, _d;
    const activeMissions = (0, mission_1.getPlayerCategoryMissionsSync)(playerId, 9);
    const playerChars = (_a = snapshot.characterList) !== null && _a !== void 0 ? _a : (0, character_1.getPlayerCharactersSync)(playerId);
    const awakeMissionIds = (0, stages_1.getMissionIdsByCategory)(9);
    const charMissionMap = new Map();
    for (const mid of awakeMissionIds) {
        const charId = (0, character_queries_1.getCharacterIdFromMission)(mid);
        if (!charMissionMap.has(charId))
            charMissionMap.set(charId, []);
        charMissionMap.get(charId).push(mid);
    }
    const computer = (0, registry_1.getComputer)(9);
    const ctx = computer.buildContext(playerId, 9, (0, utils_1.getServerDate)());
    const activeMissionList = [];
    const manaBoardAwakeMap = (0, character_awake_1.getPlayerCharacterAwakeUnlocksSync)(playerId);
    for (const [charKId, missionIds] of charMissionMap) {
        if (!playerChars[charKId])
            continue;
        for (const missionId of missionIds) {
            const dbProgress = (_c = (_b = activeMissions[String(missionId)]) === null || _b === void 0 ? void 0 : _b.progress) !== null && _c !== void 0 ? _c : 0;
            const progress = computer.compute(missionId, ctx, dbProgress);
            const allStageIds = (0, stages_1.getMissionStageIds)(9, missionId);
            const persistedStages = (_d = activeMissions[String(missionId)]) === null || _d === void 0 ? void 0 : _d.stages;
            const stages = allStageIds.map(sid => ({
                stage: sid,
                received: !Array.isArray(persistedStages) && (persistedStages === null || persistedStages === void 0 ? void 0 : persistedStages[String(sid)]) === true,
            }));
            activeMissionList.push({
                mission_id: missionId,
                progress_value: progress,
                stages,
            });
        }
    }
    return { activeMissionList, manaBoardAwakeMap };
}
exports.computeAwakeSummary = computeAwakeSummary;
