'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict')
const path = require('node:path'), fs = require('node:fs'), { createHash } = require('node:crypto')
require('ts-node/register/transpile-only')
const root = path.resolve(__dirname, '..')
const { loadContentNativeIdentities } = require('../src/lib/content-native-identities-runtime')
const aggregate = maps => createHash('sha256').update(JSON.stringify({ quests: [...maps.quests], shops: [...maps.shops] })).digest('hex')

test('changed business resources reject initialization before non-native controls can be used', () => {
    const resources = require('../src/lib/content-resource-source'), read = resources.readContentResourceSourceSync
    resources.readContentResourceSourceSync = () => { throw Error('changed business resources') }
    try { assert.throws(() => loadContentNativeIdentities(), /changed business resources/) }
    finally { resources.readContentResourceSourceSync = read }
})

test('the reviewed 356 source retains all native keys and deterministic identity order', () => {
    const maps = loadContentNativeIdentities()
    assert.equal(maps.quests.size, 268); assert.equal(maps.shops.size, 8771)
    // The business revision rebinds provenance; native quest/shop rules are unchanged.
    assert.equal(aggregate(maps), '468e04a1708608f2fcfb6eab0e41311d5715909c6be3688ad8c54fc14928f1a0')
    const next = loadContentNativeIdentities()
    maps.quests.clear(); maps.shops.clear()
    assert.equal(next.quests.size, 268); assert.equal(next.shops.size, 8771)
})

test('identities reuse the same rule objects as gameplay without reading or re-parsing their JSON again', () => {
    const files = ['content_history_quest_rules.json', 'content_history_shop_rules.json'].map(n => path.join(root, 'assets', n))
    for (const file of files) require(file)
    const read = fs.readFileSync
    fs.readFileSync = function (file, ...args) {
        assert.ok(!files.includes(path.resolve(String(file))), 'rules must reuse the loaded gameplay modules')
        return read.call(this, file, ...args)
    }
    try { assert.equal(loadContentNativeIdentities().shops.size, 8771) }
    finally { fs.readFileSync = read }
})

test('a native purchase-limit change invalidates its product and parent identities', () => {
    const rules = require('../assets/content_history_shop_rules.json')
    const [key, rule] = Object.entries(rules.products).find(([, value]) => value.native && value.native.max_frequency !== null)
    const before = loadContentNativeIdentities(), previous = rule.native.max_frequency
    try {
        rule.native.max_frequency++
        const after = loadContentNativeIdentities()
        assert.notEqual(after.shops.get(key), before.shops.get(key))
        assert.notEqual(after.shops.get(rule.parentKey), before.shops.get(rule.parentKey))
        assert.deepEqual([...after.quests], [...before.quests])
    } finally { rule.native.max_frequency = previous }
})

test('a native reward change invalidates the owning quest group', () => {
    const rules = require('../assets/content_history_quest_rules.json')
    const rule = Object.values(rules.quests).find(value => typeof value.fields?.clearRewardId === 'number')
    assert.ok(rule)
    const before = loadContentNativeIdentities(), previous = rule.fields.clearRewardId
    try {
        rule.fields.clearRewardId++
        const after = loadContentNativeIdentities()
        assert.notEqual(after.quests.get(rule.parentKey), before.quests.get(rule.parentKey))
        assert.deepEqual([...after.shops], [...before.shops])
    } finally { rule.fields.clearRewardId = previous }
})
