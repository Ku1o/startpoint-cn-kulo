"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.buildLeaderboardTermsText = exports.buildUnavailableNativeLeaderboardPayload = exports.buildNativeLeaderboardPayload = exports.getLeaderboardPlayedPartiesSync = exports.getOfficialLeaderboardPageSync = exports.nativeRow = void 0;
const content_master_1 = require("../content-master");
const player_1 = require("../../data/domains/player");
const leaderboard_1 = require("../../data/domains/leaderboard");
const rushEvent_1 = require("../../data/domains/rushEvent");
const stamina_1 = require("../stamina");
const competition_1 = require("./competition");
const settlement_1 = require("./settlement");
function officialRow(record) {
    return {
        rank_number: record.rankNumber,
        best_round: record.totalRounds,
        elapsed_time_ms: record.clientBattleMs,
        name: record.displayName,
        party_member_list: record.characterIds.flatMap((characterId, slot) => {
            var _a;
            return characterId === null ? [] : [{
                    character_id: characterId,
                    evolution_img_level: (_a = record.evolutionImgLevels[slot]) !== null && _a !== void 0 ? _a : 0,
                }];
        }),
        user_rank: (0, stamina_1.getRankDegree)(record.rankPoint),
    };
}
function formatTime(ms) {
    const value = Math.max(0, Math.trunc(ms));
    const minutes = Math.floor(value / 60000);
    const seconds = Math.floor(value / 1000) % 60;
    const centiseconds = Math.floor(value / 10) % 100;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(centiseconds).padStart(2, "0")}`;
}
function thumbnailPath(characterId, evolutionLevel) {
    if (characterId === null || (characterId >= 700000 && characterId <= 700099))
        return null;
    const entry = content_master_1.cdnCharacters[String(characterId)];
    const row = Array.isArray(entry) && Array.isArray(entry[0]) ? entry[0] : entry;
    const codeName = Array.isArray(row) && typeof row[0] === "string" ? row[0] : null;
    if (codeName === null || codeName === "")
        return null;
    const level = Math.max(0, Math.min(1, Math.trunc(evolutionLevel !== null && evolutionLevel !== void 0 ? evolutionLevel : 0)));
    return `character/${codeName}/ui/thumb_party_unison_${level}`;
}
function nativeRow(record) {
    var _a, _b, _c;
    const paths = record.characterIds.map((id, slot) => { var _a; return thumbnailPath(id, (_a = record.evolutionImgLevels[slot]) !== null && _a !== void 0 ? _a : 0); });
    return {
        rank: `${record.rankNumber}位`,
        visible: true,
        level: `RANK${(0, stamina_1.getRankDegree)(record.rankPoint)}`,
        name: record.displayName,
        count: `BEST RECORD: ${record.totalRounds}战`,
        time: `TIME: ${formatTime(record.clientBattleMs)}`,
        a: (_a = paths[0]) !== null && _a !== void 0 ? _a : null,
        b: (_b = paths[1]) !== null && _b !== void 0 ? _b : null,
        c: (_c = paths[2]) !== null && _c !== void 0 ? _c : null,
        id: record.playerId,
    };
}
exports.nativeRow = nativeRow;
function outOfRankRow(playerId) {
    const player = (0, player_1.getPlayerSync)(playerId);
    if (player === null)
        return null;
    return {
        rank: "排名外",
        visible: false,
        level: `RANK${(0, stamina_1.getRankDegree)(player.rankPoint)}`,
        name: player.name,
        count: "BEST RECORD: 0战",
        time: "TIME: --:--.--",
        a: null,
        b: null,
        c: null,
        id: playerId,
    };
}
function getOfficialLeaderboardPageSync(input) {
    const season = getSeason(input.competition.key);
    const total = (0, leaderboard_1.countLeaderboardRanksSync)(input.competition.key, season);
    const visibleTotal = Math.min(total, input.competition.displayLimit);
    const pageMax = Math.max(1, Math.ceil(visibleTotal / input.competition.pageSize));
    const requestedPage = Number.isFinite(input.page) ? Math.trunc(input.page) : 0;
    const page = Math.max(0, Math.min(requestedPage, pageMax - 1));
    const rows = (0, leaderboard_1.getLeaderboardRankPageSync)({
        competitionKey: input.competition.key,
        season,
        offset: page * input.competition.pageSize,
        limit: Math.min(input.competition.pageSize, Math.max(0, input.competition.displayLimit - page * input.competition.pageSize)),
    });
    const mine = (0, leaderboard_1.getLeaderboardPlayerRankSync)(input.competition.key, season, input.playerId);
    return {
        currentPage: page + 1,
        pageMax,
        total,
        myData: mine === null ? null : officialRow(mine),
        rows: rows.map(officialRow),
    };
}
exports.getOfficialLeaderboardPageSync = getOfficialLeaderboardPageSync;
function getLeaderboardPlayedPartiesSync(input) {
    const season = getSeason(input.competition.key);
    if (!Number.isInteger(input.rankNumber) || input.rankNumber < 1)
        return {};
    const [record] = (0, leaderboard_1.getLeaderboardRankPageSync)({
        competitionKey: input.competition.key,
        season,
        offset: input.rankNumber - 1,
        limit: 1,
    });
    if (record === undefined)
        return {};
    return Object.fromEntries((0, leaderboard_1.getLeaderboardRunRoundsSync)(record.id).map(round => [
        round.roundNumber,
        (0, rushEvent_1.serializePlayerRushEventPlayedParty)({
            characterIds: round.characterIds,
            unisonCharacterIds: round.unisonCharacterIds,
            equipmentIds: round.equipmentIds,
            abilitySoulIds: round.abilitySoulIds,
            evolutionImgLevels: round.evolutionImgLevels,
            unisonEvolutionImgLevels: round.unisonEvolutionImgLevels,
            round: round.roundNumber,
            battleType: 1,
        }),
    ]));
}
exports.getLeaderboardPlayedPartiesSync = getLeaderboardPlayedPartiesSync;
function buildNativeLeaderboardPayload(competition, playerId) {
    const season = getSeason(competition.key);
    const total = (0, leaderboard_1.countLeaderboardRanksSync)(competition.key, season);
    const records = (0, leaderboard_1.getLeaderboardRankPageSync)({
        competitionKey: competition.key,
        season,
        offset: 0,
        limit: competition.displayLimit,
    });
    const mine = playerId === null
        ? null
        : (0, leaderboard_1.getLeaderboardPlayerRankSync)(competition.key, season, playerId);
    const index = mine === null ? -1 : mine.rankNumber - 1;
    const visibleIndex = index >= 0 && index < records.length ? index : -1;
    return {
        enabled: true,
        name: competition.displayName,
        rows: records.map(nativeRow),
        item: mine === null
            ? (playerId === null ? null : outOfRankRow(playerId))
            : nativeRow(mine),
        page: visibleIndex < 0 ? 0 : Math.floor(visibleIndex / competition.pageSize),
        row: visibleIndex < 0 ? -1 : visibleIndex % competition.pageSize,
        index,
        time: "实时更新",
        total,
        reward: (0, settlement_1.getLeaderboardSettlementConfigSync)(competition.key).rewardTiers,
    };
}
exports.buildNativeLeaderboardPayload = buildNativeLeaderboardPayload;
function buildUnavailableNativeLeaderboardPayload() {
    return {
        enabled: false,
        name: "连战",
        rows: [],
        item: null,
        page: 0,
        row: -1,
        index: -1,
        time: "排行榜暂未开放",
        total: 0,
        reward: [],
    };
}
exports.buildUnavailableNativeLeaderboardPayload = buildUnavailableNativeLeaderboardPayload;
function getSeason(competitionKey) {
    return (0, competition_1.getLeaderboardCompetitionSeasonSync)(competitionKey);
}
function buildLeaderboardTermsText(competition) {
    const tiers = (0, settlement_1.getLeaderboardSettlementConfigSync)(competition.key).rewardTiers;
    const lines = tiers.map(tier => {
        const range = tier.toRank === null
            ? `第${tier.fromRank}名起`
            : tier.fromRank === tier.toRank
                ? `第${tier.fromRank}名`
                : `第${tier.fromRank}～${tier.toRank}名`;
        const rewards = [
            tier.itemId === null ? null : `${tier.itemName} × ${tier.itemCount}`,
            tier.degreeId === null ? null : `称号「${tier.degreeName}」`,
        ].filter((value) => value !== null);
        return `<p><b>${range}</b>　${rewards.join(" + ")}</p>`;
    });
    return `<h2>${competition.displayName} 排行报酬</h2>${lines.join("")}<p>排行榜按本期完整通关的 client_battle_ms 总和升序排列；每位玩家只保留最佳成绩。</p>`;
}
exports.buildLeaderboardTermsText = buildLeaderboardTermsText;
