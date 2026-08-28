"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.handleRaidEventFinish = void 0;
const types_1 = require("../../../data/types");
const types_2 = require("../../types");
const raidEventGlobal_1 = require("../../raidEventGlobal");
const activity_degree_rewards_1 = require("../../activity-degree-rewards");
function handleRaidEventFinish(params) {
    const { questCategory, questAccomplished, activeEventId, playId, party, playerId, questId, getEvoLevelsFn, insertPartyFn, } = params;
    if (questCategory !== types_2.QuestCategory.RAID_EVENT || !activeEventId)
        return null;
    const characterIds = party.characters.map(val => { var _a; return (_a = val === null || val === void 0 ? void 0 : val.id) !== null && _a !== void 0 ? _a : null; });
    const unisonCharacterIds = party.unison_characters.map(val => { var _a; return (_a = val === null || val === void 0 ? void 0 : val.id) !== null && _a !== void 0 ? _a : null; });
    const evolutionImgLevels = getEvoLevelsFn(playerId, characterIds);
    const unisonEvolutionImgLevels = getEvoLevelsFn(playerId, unisonCharacterIds);
    insertPartyFn(playerId, activeEventId, {
        characterIds, unisonCharacterIds,
        equipmentIds: party.equipments.map(val => { var _a; return (_a = val === null || val === void 0 ? void 0 : val.id) !== null && _a !== void 0 ? _a : null; }),
        abilitySoulIds: party.ability_soul_ids,
        evolutionImgLevels,
        unisonEvolutionImgLevels,
        battleType: types_1.RushEventBattleType.FOLDER,
        round: questId
    });
    let boss = (0, raidEventGlobal_1.getRaidEventGlobalBossSync)(activeEventId);
    let questKillCount = (0, raidEventGlobal_1.getRaidEventQuestKillCountSync)(activeEventId, questId);
    let newDegreeIds = [];
    if (questAccomplished) {
        const result = (0, raidEventGlobal_1.recordRaidEventClearSync)({
            eventId: activeEventId,
            playId,
            playerId,
            questId,
        });
        boss = result.boss;
        questKillCount = result.questKillCount;
        newDegreeIds = (0, activity_degree_rewards_1.grantEligibleRaidEventDegreesSync)(playerId, activeEventId);
        console.log(`[RAID] clear: eventId=${activeEventId} questId=${questId} ` +
            `playId=${playId} counted=${result.counted} weight=${result.questWeight} ` +
            `weighted=${boss.weightedKillCount}/${boss.requiredKillCount} ` +
            `hp=${boss.hpPercentage} total=${boss.totalKillCount}`);
    }
    return {
        auto_start_point: 0,
        is_out_of_period: false,
        quest_boss: {
            kill_count: questKillCount,
        },
        raid_boss: {
            hp_percentage: boss.hpPercentage,
            total_kill_count: boss.totalKillCount,
        },
        new_degree_ids: newDegreeIds,
    };
}
exports.handleRaidEventFinish = handleRaidEventFinish;
