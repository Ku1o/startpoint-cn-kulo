// Read actual reward accessors and pure Mode15 constants without loading player
// modules or a database. Source/out constants must agree before packaging.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ts = require('typescript');
const root = path.resolve(__dirname, '../..');
const assets = require(path.join(root, 'out/lib/assets'));
const types = require(path.join(root, 'out/lib/types'));

function modeConstants(code) {
    const context = { exports: {}, require: name => {
        if (name === './types') return types;
        // All other imports are only needed by uncalled gameplay functions.
        return new Proxy({}, { get: (_target, key) => {
            throw new Error(`Unexpected runtime access while reading constants: ${name}:${String(key)}`);
        }});
    }};
    vm.runInNewContext(code, context, { timeout: 5000 });
    const names = ['MODE15_SOLO_FIXED_REWARDS', 'MODE15_BOSS_TOKEN_REWARDS',
        'MODE15_DREAM_EMBLEM_ID', 'MODE15_TOKEN_ID', 'MODE15_FULL_CLEAR_TOKEN_ID',
        'MODE15_FULL_CLEAR_TICKET_ID', 'MODE15_RUSH_EVENT_ID'];
    return JSON.parse(JSON.stringify(Object.fromEntries(names.map(name => [name, context.exports[name]]))));
}
const modeSource = fs.readFileSync(path.join(root, 'src/lib/mode15.ts'), 'utf8');
const sourceConstants = modeConstants(ts.transpileModule(modeSource, {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
}).outputText);
assert.deepEqual(modeConstants(fs.readFileSync(path.join(root, 'out/lib/mode15.js'), 'utf8')), sourceConstants);
for (const snippet of ['const fullClear = ref.stage === 15 && !options.rescue;',
    'ref.category === QuestCategory.RUSH_EVENT && !options.rescue',
    'id: MODE15_DREAM_EMBLEM_ID, count: 200', 'id: MODE15_FULL_CLEAR_TOKEN_ID, count: 1',
    'id: MODE15_FULL_CLEAR_TICKET_ID, count: 1']) {
    assert.ok(modeSource.includes(snippet), `Review changed Fantasy settlement: ${snippet}`);
}
const mode = {
    fixed: sourceConstants.MODE15_SOLO_FIXED_REWARDS,
    bossTokens: sourceConstants.MODE15_BOSS_TOKEN_REWARDS,
    tokenId: sourceConstants.MODE15_TOKEN_ID,
    eventId: sourceConstants.MODE15_RUSH_EVENT_ID,
    final: [{ type: 0, id: sourceConstants.MODE15_DREAM_EMBLEM_ID, count: 200 },
        { type: 0, id: sourceConstants.MODE15_FULL_CLEAR_TOKEN_ID, count: 1 },
        { type: 0, id: sourceConstants.MODE15_FULL_CLEAR_TICKET_ID, count: 1 }],
};
const expert = Object.keys(require(path.join(root, 'assets/expert_single_event_quest.json')))
    .map(id => ({ id: Number(id), quest: assets.getQuestFromCategorySync(types.QuestCategory.EXPERT_SINGLE_EVENT, id) }));
const finish = fs.readFileSync(path.join(root, 'src/routes/api/singleBattleQuest.ts'), 'utf8');
for (const snippet of ['questProgress?.sPlusRewardReceived !== true', 'sPlusRewardReceived: true', '(clearRank === 5)']) {
    assert.ok(finish.includes(snippet), `Review changed SS reward eligibility: ${snippet}`);
}
const quests = Object.fromEntries([1001001, 1002001, 1003001, 1004001, 1005001, 1006001]
    .map(id => [id, assets.getHardMultiEventQuest(id)]));
quests[1060005] = assets.getBossBattleQuestSync(1060005);
const rare = {};
for (const quest of Object.values(quests)) for (const row of quest.scoreRewardGroup) {
    if (row.type === 1) rare[row.id] = assets.getRareScoreRewardGroup(row.id);
}
const folders = require(path.join(root, 'assets/rush_event_quest_folder.json'));
assert.deepEqual(folders['700098']['1'], mode.final, 'Fantasy full-clear reward data drift');
console.log(JSON.stringify({ mode, rogue: assets.getRogueEventConfig(700099), expert, quests, rare,
    folderBase: folders['700099']['1'] }));
