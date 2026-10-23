'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const Module = require('node:module')
const ts = require('typescript')
const Sqlite = require('better-sqlite3')

// Compile this one source module in memory, without touching the running server's out/ tree.
const filename = path.resolve(__dirname, '../src/lib/content-operations-store.ts')
const source = fs.readFileSync(filename, 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS,
  target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true })
assert.equal(compiled.diagnostics.filter(item => item.category === ts.DiagnosticCategory.Error).length, 0)
const moduleValue = new Module(filename, module)
moduleValue.filename = filename
moduleValue.paths = Module._nodeModulePaths(path.dirname(filename))
moduleValue._compile(compiled.outputText, filename)
const { ContentOperationsStore, initializeContentOperationsSchema } = moduleValue.exports

const now = Date.parse('2026-10-21T00:00:00Z')
const makeRow = (key, parentKey) => ({ key, type: key.split(':')[0], id: Number(key.split(':')[1]), name: key,
  source: 'fixture', originalStartMs: 1, originalEndMs: 2, originalExchangeEndMs: 3,
  windowCandidate: true, browseCandidate: true, ...(parentKey ? { parentKey } : {}) })
function fixture(t) {
  const db = new Sqlite(':memory:')
  t.after(() => db.close())
  initializeContentOperationsSchema(db)
  db.exec('CREATE TABLE player_progress(id INTEGER PRIMARY KEY, value INTEGER NOT NULL); INSERT INTO player_progress VALUES(1,47)')
  const catalog = { schemaVersion: 1, source: { assetVersion: 'fixture', manifestSha256: 'fixture' },
    baselineTimeMs: 1, baselineEvidence: 'fixture', resources: {}, missing: [], questMap: {}, rows: [
      makeRow('gacha:1'), makeRow('pass_card_event:11'), makeRow('pass_card_event:12'),
      makeRow('rush_event:2'), makeRow('event_item_shop:21', 'rush_event:2'),
    ] }
  const capabilities = row => row.type === 'event_item_shop' ? ['visible', 'exchange']
    : row.type === 'rush_event' ? ['visible', 'enter', 'exchange']
      : row.type === 'pass_card_event' ? ['visible', 'enter', 'claim'] : ['visible', 'enter', 'exchange']
  const defaults = (row, action) => action === 'claim' && row.type === 'pass_card_event' ? true
    : action === 'exchange' && row.type === 'gacha' ? true : null
  const store = new ContentOperationsStore(db, catalog, capabilities, undefined, undefined, undefined, undefined, defaults)
  const patch = (key, actionOverrides) => store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
    reason: 'fixture exact review', actionOverrides: Object.fromEntries(Object.entries(actionOverrides).map(([action, enabled]) =>
      [action, { enabled, readiness: 'verified', evidence: `exact ${action} review`, endsAtMs: null }])) }, now)
  const publish = (key, published) => store.setPublished(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
    published, reason: `fixture ${published ? 'publish' : 'unpublish'}` }, now)
  return { db, store, patch, publish }
}

test('one atomic switch suspends entry, retains accrued exchange and restores exact reviewed actions', t => {
  const { db, store, patch, publish } = fixture(t)
  patch('gacha:1', { visible: true, enter: true, exchange: true })
  const before = store.state('gacha:1')
  const down = publish('gacha:1', false)
  assert.equal(down.revision, before.revision + 1)
  assert.deepEqual(down.actionOverrides, before.actionOverrides)
  assert.equal(store.allowed('gacha:1', 'visible', now), false)
  assert.equal(store.allowed('gacha:1', 'enter', now), false)
  assert.equal(store.allowed('gacha:1', 'exchange', now), true)
  const snap = store.snapshot(now).states.find(row => row.key === 'gacha:1')
  assert.equal(snap.actions.visible.enabled, false)
  assert.equal(snap.actions.enter.enabled, false)
  assert.equal(snap.actions.exchange.enabled, true)
  const up = publish('gacha:1', true)
  assert.deepEqual(up.actionOverrides, before.actionOverrides)
  assert.equal(up.instanceId, before.instanceId)
  assert.equal(store.allowed('gacha:1', 'enter', now), true)
  assert.equal(db.prepare('SELECT value FROM player_progress WHERE id=1').get().value, 47)
  const audit = store.audit({ key: 'gacha:1' }).rows
  assert.equal(audit[0].after.published, true)
  assert.equal(audit[1].after.published, false)
})

test('unpublished activity parent blocks new shop exchange without deleting child review', t => {
  const { store, patch, publish } = fixture(t)
  patch('rush_event:2', { visible: true, exchange: true })
  patch('event_item_shop:21', { visible: true, exchange: true })
  publish('rush_event:2', false)
  assert.equal(store.allowed('rush_event:2', 'exchange', now), false)
  assert.equal(store.allowed('event_item_shop:21', 'exchange', now), true)
  assert.equal(store.snapshot(now).states.find(row => row.key === 'rush_event:2').actions.exchange.enabled, false)
  publish('rush_event:2', true)
  assert.equal(store.allowed('rush_event:2', 'exchange', now), true)
  assert.equal(store.allowed('rush_event:2', 'enter', now), null) // no reviewed battle action was invented
})

test('one visible pass at a time; both exact configurations can be stored offline', t => {
  const { store, patch, publish } = fixture(t)
  patch('pass_card_event:11', { visible: true, enter: true, claim: true })
  publish('pass_card_event:11', false)
  patch('pass_card_event:12', { visible: true, enter: true, claim: true })
  publish('pass_card_event:12', false)
  publish('pass_card_event:11', true)
  assert.throws(() => publish('pass_card_event:12', true), /只支持一个通行证入口/)
  assert.equal(store.allowed('pass_card_event:12', 'claim', now), true)
  publish('pass_card_event:11', false)
  publish('pass_card_event:12', true)
  assert.equal(store.activeManagedPass(now), 'pass_card_event:12')
})

test('reopen rejects missing or stale reviewed entry without changing revision', t => {
  const { store, patch, publish } = fixture(t)
  assert.throws(() => publish('gacha:1', false), /尚无有效/)
  patch('gacha:1', { visible: true, enter: true })
  publish('gacha:1', false)
  const revision = store.revision()
  assert.throws(() => store.setPublished('gacha:1', { expectedRevision: revision, catalogDigest: 'wrong',
    published: true, reason: 'stale catalog' }, now), /目录已变化/)
  assert.throws(() => store.setPublished('gacha:1', { expectedRevision: revision - 1, catalogDigest: store.digest,
    published: true, reason: 'stale revision' }, now), /状态已被其他操作更新/)
  assert.equal(store.revision(), revision)
  store.runtimeDefinitions.set('gacha:1', { digest: 'changed', matchesCatalog: false })
  assert.throws(() => store.setPublished('gacha:1', { expectedRevision: revision, catalogDigest: store.digest,
    published: true, reason: 'stale source' }, now), /入口未完成核查|动作失效/)
  assert.equal(store.revision(), revision)
})
