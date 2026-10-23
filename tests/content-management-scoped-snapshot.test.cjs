'use strict'
require('ts-node/register/transpile-only')
const { test } = require('node:test')
const assert = require('node:assert/strict')
const { mkdtempSync, mkdirSync, writeFileSync } = require('node:fs')
const path = require('node:path')
const Sqlite = require('better-sqlite3')
const { ContentOperationsStore, initializeContentOperationsSchema, CONTENT_ACTIONS } = require('../src/lib/content-operations-store')
const { contentManagementCatalog, contentManagementCatalogSignature } = require('../src/lib/content-management-catalog')

const row = (type, id, extra = {}) => ({ key: `${type}:${id}`, type, id, name: `Synthetic ${type} ${id}`,
    originalStartMs: 1, originalEndMs: 2, originalExchangeEndMs: null, windowCandidate: false, browseCandidate: false,
    source: 'synthetic', definitionDigest: `${type}:${id}`, ...extra })
function fixture(t, parentCount = 30, memberCount = 900) {
    const reads = [], db = new Sqlite(':memory:')
    t.after(() => db.close()); initializeContentOperationsSchema(db)
    db.exec("CREATE TABLE retained_progress(value TEXT); INSERT INTO retained_progress VALUES('earned-paid-qualified')")
    const native = { parentKey: 'world_story_event:200100', boxKey: 'box_gacha:108', relationshipMatches: true }
    const catalog = { schemaVersion: 1, source: { assetVersion: 'synthetic', manifestSha256: 'synthetic' }, baselineTimeMs: 0,
        baselineEvidence: 'synthetic', missing: [], resources: {}, questMap: {}, rows: [
            ...Array.from({ length: parentCount }, (_, id) => row('gacha', 900000 + id)),
            ...Array.from({ length: memberCount }, (_, id) => row('event_item_shop', 500000 + id)),
            row('world_story_event', 200100, { parentKey: 'event_item_shop:500000' }), row('box_gacha', 108),
            row('pass_card_event', 1), row('pass_card_event', 2),
        ] }
    const store = new ContentOperationsStore(db, catalog, () => CONTENT_ACTIONS, undefined, undefined, undefined, undefined, undefined,
        { available: true, associations: [native] })
    const save = (key, changes = {}) => db.prepare('INSERT OR REPLACE INTO content_operations_state VALUES(?,?)').run(key, JSON.stringify({
        key, instanceId: `${key}:original`, readiness: 'verified', evidence: 'Synthetic reviewed scope ' + 'x'.repeat(4000),
        flags: { visible: true, enter: true, claim: true, exchange: true }, endsAtMs: null,
        revision: 0, published: true, catalogDigest: store.digest, contentDigest: store.contentDigests.get(key), ...changes,
    }))
    for (const value of catalog.rows) save(value.key)
    const prepare = db.prepare.bind(db)
    db.prepare = sql => {
        const statement = prepare(sql)
        if (/^SELECT content_key,value_json FROM content_operations_state/.test(sql)) {
            const all = statement.all.bind(statement)
            statement.all = (...args) => {
                const values = all(...args)
                reads.push({ sql, controls: values.length, bytes: values.reduce((sum, value) => sum + Buffer.byteLength(value.value_json), 0) })
                return values
            }
        }
        return statement
    }
    return { db, store, catalog, native, save, reads }
}

test('scoped parent reads capture only selected controls while the omitted scope retains the complete legacy contract', t => {
    const { db, store, catalog, reads } = fixture(t)
    const keys = Object.freeze(catalog.rows.filter(row => row.type !== 'event_item_shop').map(row => row.key))
    const full = store.managementSnapshot(), expected = full.all({}, row => row.type !== 'event_item_shop')
    const scoped = store.managementSnapshot(keys)
    assert.deepEqual(scoped.all(), expected)
    assert.equal(reads.length, 2)
    assert.equal(reads[0].controls, catalog.rows.length)
    assert.equal(reads[1].controls, keys.length + 1, 'non-parent native dependency is included without all unrelated members')
    assert.match(reads[1].sql, /WHERE content_key IN/)
    assert.ok(reads[1].bytes < reads[0].bytes / 10)
    assert.equal(full.all().total, catalog.rows.length)
    assert.equal(db.prepare('SELECT value FROM retained_progress').get().value, 'earned-paid-qualified')
    const listing = scoped.all(); listing.types.push('only-this-response')
    assert.equal(scoped.all().types.includes('only-this-response'), false)
})

test('scope dependencies include native peers, parent chains and other passes; outside-scope lookup fails closed', t => {
    const { store, native, save, reads } = fixture(t)
    save(native.parentKey, { published: false })
    const scoped = store.managementSnapshot(Object.freeze([native.boxKey]))
    assert.equal(scoped.row(native.boxKey).effectiveFlags.visible, false)
    assert.equal(scoped.state(native.parentKey).published, false)
    assert.equal(scoped.state('event_item_shop:500000').readiness, 'verified')
    assert.equal(reads[0].controls, 3)
    assert.equal(scoped.all().total, 1, 'dependency controls do not become extra listed rows')
    assert.throws(() => scoped.state('event_item_shop:500001'), error => error.statusCode === 409)
    assert.throws(() => scoped.row('gacha:900000'), error => error.statusCode === 409)
    assert.throws(() => store.managementSnapshot(['unknown:9']), /未知内容/)
    assert.deepEqual(store.managementSnapshot([]).all().rows, [])
    const pass = store.managementSnapshot(Object.freeze(['pass_card_event:1']))
    assert.equal(pass.state('pass_card_event:2').readiness, 'verified')
    assert.equal(pass.all().total, 1)
})

test('scoped reads retain coherent old states, exact peer expiry and current write CAS', t => {
    const { db, store, native, save } = fixture(t)
    const realNow = Date.now
    let now = 1000; Date.now = () => now
    try {
        save(native.parentKey, { endsAtMs: 1001 })
        const scoped = store.managementSnapshot(Object.freeze([native.boxKey]))
        assert.equal(scoped.row(native.boxKey).effectiveFlags.visible, true)
        assert.equal(scoped.nextChangeAtMs, 1002)
        now = 1002
        assert.equal(scoped.row(native.boxKey).effectiveFlags.visible, true)
        assert.equal(store.managementSnapshot([native.boxKey]).row(native.boxKey).effectiveFlags.visible, false)
        const revision = scoped.revision
        store.setPublished('gacha:900000', { published: false, expectedRevision: revision, catalogDigest: store.digest, reason: 'synthetic close' }, now)
        assert.throws(() => store.setPublished('gacha:900001', { published: false, expectedRevision: revision,
            catalogDigest: store.digest, reason: 'stale synthetic close' }, now), error => error.statusCode === 409)
        assert.equal(db.prepare('SELECT value FROM retained_progress').get().value, 'earned-paid-qualified')
    } finally { Date.now = realNow }
})

test('static catalog metadata is reused only for matching sources and never keeps state or mutable response permissions', t => {
    const { store, save } = fixture(t)
    let described = 0
    const presentationReader = {}, historyReader = {}
    const source = { signature: 'version-a', presentationReader, historyReader }
    const describe = row => { described++; return { group: row.type === 'gacha' ? 'gacha' : 'events', typeLabel: row.type,
        title: 'original title ' + row.key } }
    const first = contentManagementCatalog(store, source, describe), count = described
    assert.equal(contentManagementCatalog(store, { ...source }, () => assert.fail('matching metadata is reused')), first)
    save('gacha:900000', { published: false })
    assert.equal(contentManagementCatalog(store, source, describe), first)
    assert.equal(first.presentation(store.rows.get('gacha:900000')).state, undefined)
    assert.throws(() => { first.presentation(store.rows.get('gacha:900000')).title = 'polluted' }, TypeError)
    assert.throws(() => first.typeOptions('all').push({ value: 'fake', label: 'fake' }), TypeError)
    const second = contentManagementCatalog(store, { ...source, signature: 'version-b' }, describe)
    assert.notEqual(second, first); assert.equal(described, count * 2)
    assert.notEqual(contentManagementCatalog(store, { ...source, signature: 'version-b', historyReader: {} }, describe), second)
    const snapshot = store.managementSnapshot(second.parentKeys)
    assert.equal(snapshot.row('gacha:900000').effectiveFlags.visible, false)
})

test('large static catalogs are not retained and metadata file changes invalidate source identity', t => {
    const { store } = fixture(t, 2050, 1)
    let descriptions = 0
    const source = { signature: 'large', presentationReader: {}, historyReader: {} }
    const describe = row => { descriptions++; return { group: 'events', typeLabel: row.type } }
    contentManagementCatalog(store, source, describe); const once = descriptions
    contentManagementCatalog(store, source, describe); assert.equal(descriptions, once * 2)
    const root = process.env.STARPOINT_TEST_TMP_ROOT
    assert.ok(root, 'Task-local temporary root is required')
    mkdirSync(root, { recursive: true })
    const directory = mkdtempSync(path.join(root, 'catalog-signature-'))
    const before = contentManagementCatalogSignature(directory)
    writeFileSync(path.join(directory, 'content_catalog.json'), '{}')
    const after = contentManagementCatalogSignature(directory)
    assert.notEqual(after, before)
    writeFileSync(path.join(directory, 'content_catalog.json'), '{"changed":true}')
    assert.notEqual(contentManagementCatalogSignature(directory), after)
    const beforeManifest = contentManagementCatalogSignature(directory)
    mkdirSync(path.join(directory, 'asset-patch'))
    writeFileSync(path.join(directory, 'asset-patch/manifest.json'), '{"patches":[]}')
    assert.notEqual(contentManagementCatalogSignature(directory), beforeManifest)
    const manifestSignature = contentManagementCatalogSignature(directory)
    writeFileSync(path.join(directory, 'asset-patch/manifest.json'), '{"patches":["changed"]}')
    assert.notEqual(contentManagementCatalogSignature(directory), manifestSignature)
})

test('real history reader factories create independent request views without invalidating the static metadata cache', t => {
    const { store } = fixture(t, 5, 1)
    const { contentHistoryReadinessReader: historyReader } = require('../src/lib/content-history-readiness')
    const { getContentPresentation: presentationReader } = require('../src/lib/content-presentation')
    const firstReader = historyReader(), secondReader = historyReader()
    assert.notEqual(firstReader, secondReader)
    const source = { signature: contentManagementCatalogSignature(), presentationReader, historyReader }
    const first = contentManagementCatalog(store, source, row => presentationReader(row))
    const second = contentManagementCatalog(store, { ...source }, () => assert.fail('a new request reader is not a new metadata source'))
    assert.equal(second, first)
    assert.equal(typeof secondReader.get('gacha:900000', ['visible']).status, 'string')
})
