const test = require('node:test');
const assert = require('node:assert/strict');
const table = require('../assets/character_quest_lookup.json');
const { getCharacterStoryQuestIds } = require('../out/lib/mission/character-queries');
const entries = Object.entries(table);

function originalLookup(characterId) {
    const id = String(characterId) === '1' ? '10' : String(characterId);
    return entries.filter(([key, rows]) => key.startsWith(id) && rows.length > 0).map(([key]) => parseInt(key));
}

test('the static story index equals the previous scan for every existing prefix and the protagonist alias', () => {
    const prefixes = new Set(['', '1', '10', 'missing', '-1']);
    for (const [key] of entries) for (let n = 1; n <= key.length; n++) prefixes.add(key.substring(0, n));
    for (const prefix of prefixes) assert.deepEqual(getCharacterStoryQuestIds(prefix), originalLookup(prefix), prefix);
    assert.deepEqual(getCharacterStoryQuestIds(1), originalLookup(1));
});

test('callers cannot mutate the shared master-data index through a returned array', () => {
    const expected = originalLookup('');
    const returned = getCharacterStoryQuestIds('');
    returned.splice(0, returned.length, 999);
    assert.deepEqual(getCharacterStoryQuestIds(''), expected);
});
