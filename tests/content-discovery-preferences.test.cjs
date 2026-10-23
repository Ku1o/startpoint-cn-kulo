'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), ts = require('typescript')
const source = fs.readFileSync(path.join(__dirname, '../admin/src/pages/content-discovery-preferences.ts'), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } })
const fixture = { exports: {} }
vm.runInNewContext(compiled.outputText, { module: fixture, exports: fixture.exports })
const { DISCOVERY_STORAGE_KEY, normalizeDiscoveryPreferences: normalize, readDiscoveryPreferences: read, writeDiscoveryPreferences: write, favoritePreference: favorite, recentPreference: recent, isContentParentKey } = fixture.exports
const plain = value => JSON.parse(JSON.stringify(value))
const defaults = () => normalize(undefined)

test('versioned preferences accept only whitelisted parent identities and harmless layout', () => {
    assert.deepEqual(plain(normalize({ version: 99, view: 'series', favorites: ['gacha:1'] })), plain(defaults()))
    assert.equal(isContentParentKey('gacha:1'), true)
    assert.equal(isContentParentKey('world_story_event:1'), true)
    for (const key of ['gacha:01', 'gacha:-1', 'gacha:9007199254740992', 'arbitrary:1', 'mission_event:1', 'general_shop:1', 'event_item_shop:1', 'boss_coin_shop:1', '__proto__', 'gacha:1/publication', 'gacha:1,story_event:2', { key: 'gacha:1' }]) assert.equal(isContentParentKey(key), false)
    const value = normalize({ version: 1, view: 'unsafe', favorites: ['gacha:1', 'gacha:1', 'arbitrary:2', 42], recent: ['gacha:2'], status: 'disabled', password: 'secret', rows: [{ name: 'old name' }] })
    assert.deepEqual(plain(value), { version: 1, view: 'cards', favorites: ['gacha:1'], recent: ['gacha:2'] })
})

test('favorite and recent arrays are deduplicated and bounded without full row persistence', () => {
    const keys = Array.from({ length: 250 }, (_, i) => `gacha:${i + 1}`)
    const value = normalize({ version: 1, view: 'series', favorites: ['gacha:1', ...keys], recent: ['gacha:1', ...keys] })
    assert.equal(value.favorites.length, 200)
    assert.equal(value.recent.length, 30)
    assert.equal(new Set(value.favorites).size, 200)
    assert.equal(new Set(value.recent).size, 30)
    assert.equal(favorite(value, 'gacha:999').favorites.includes('gacha:999'), false, 'full favorite list does not silently evict another favorite')
    assert.equal(favorite(value, 'gacha:1').favorites.length, 199)
    const next = recent(value, 'gacha:15')
    assert.equal(next.recent[0], 'gacha:15')
    assert.equal(next.recent.filter(key => key === 'gacha:15').length, 1)
    assert.equal(next.recent.length, 30)
    assert.deepEqual(plain(favorite(value, 'arbitrary:1')), plain(value))
})

test('corrupt, future, excessive and blocked storage safely fall back to current-page memory', () => {
    for (const raw of ['{bad json', 'null', '[]', JSON.stringify({ version: 2 }), 'x'.repeat(64001)]) {
        const state = read({ getItem: () => raw, setItem() {} })
        assert.equal(state.persistent, false)
        assert.deepEqual(plain(state.preferences), plain(defaults()))
    }
    assert.equal(read().persistent, false)
    assert.equal(read({ getItem() { throw new Error('blocked') }, setItem() {} }).persistent, false)
    assert.equal(write(defaults(), { getItem() {}, setItem() { throw new Error('quota') } }), false)
    assert.equal(write(defaults()), false)
    assert.equal(read({ getItem: () => null, setItem() {} }).persistent, true)
})

test('normal storage round trips only normalized schema fields, and memory survives rejected writes', () => {
    const data = new Map(), storage = { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value) }
    const value = { ...recent(favorite(defaults(), 'gacha:1'), 'gacha:9'), password: 'do not persist', name: 'old name' }
    assert.equal(write(value, storage), true)
    assert.deepEqual(Object.keys(JSON.parse(data.get(DISCOVERY_STORAGE_KEY))), ['version', 'view', 'favorites', 'recent'])
    assert.deepEqual(plain(read(storage).preferences), { version: 1, view: 'cards', favorites: ['gacha:1'], recent: ['gacha:9'] })
    const before = plain(value)
    assert.equal(write(value, { getItem() {}, setItem() { throw new Error('quota') } }), false)
    assert.deepEqual(plain(value), before)
})
