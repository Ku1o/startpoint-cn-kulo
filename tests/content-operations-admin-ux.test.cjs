'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm')
const ts = require('typescript'), Sqlite = require('better-sqlite3')
const source = fs.readFileSync(path.join(__dirname, '../admin/src/pages/ContentOperations.tsx'), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true })
assert.equal(compiled.diagnostics.filter(item => item.category === ts.DiagnosticCategory.Error).length, 0)
const moduleValue = { exports: {} }
vm.runInNewContext(compiled.outputText, { module: moduleValue, exports: moduleValue.exports, require: () => ({}) })
const { contentToggleRequest, auditDescription, contentStatusName, contentActionLabel } = moduleValue.exports
const { ContentOperationsStore, initializeContentOperationsSchema, CONTENT_ACTIONS } = require('../out/lib/content-operations-store')
const plain = value => JSON.parse(JSON.stringify(value))
const now = Date.parse('2026-10-21T00:00:00Z')
function fixture(t) {
    const db = new Sqlite(':memory:'); t.after(() => db.close()); initializeContentOperationsSchema(db)
    const key = 'gacha:1', row = { key, type: 'gacha', id: 1, name: 'test', source: 'fixture', originalStartMs: 1, originalEndMs: 2, originalExchangeEndMs: 3, windowCandidate: true, browseCandidate: true }
    const catalog = { schemaVersion: 1, source: { assetVersion: 'fixture', manifestSha256: 'fixture' }, baselineTimeMs: 1, baselineEvidence: 'fixture', resources: {}, missing: [], questMap: { '1:1': key, '1:2': key }, missionMap: { '7:1': key, '7:2': key }, rows: [row] }
    const store = new ContentOperationsStore(db, catalog, () => CONTENT_ACTIONS)
    const review = (enabled, extra = {}) => ({ enabled, readiness: 'verified', evidence: 'synthetic reviewed exact action', endsAtMs: null, ...extra })
    store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'synthetic fixture', actionOverrides: { visible: review(true), enter: review(false, { questKeys: [], missionKeys: [] }), claim: review(true, { questKeys: ['1:2'], missionKeys: ['7:1'] }), exchange: review(true, { questKeys: ['1:1'], missionKeys: ['7:1', '7:2'] }) } }, now)
    const view = kind => ({ key, name: '测试卡池', type: 'gacha', presentation: { title: '测试卡池' }, state: store.state(key), primaryControl: { kind, enabled: kind === 'publication' ? store.state(key).published !== false : store.state(key).actionOverrides.exchange.enabled, canToggle: true } })
    return { key, db, store, view }
}
test('ordinary publication off/on preserves reviewed action scopes and player progress', t => {
    const { key, db, store, view } = fixture(t)
    db.exec('CREATE TABLE synthetic_player_progress(value TEXT); INSERT INTO synthetic_player_progress VALUES (\'earned-and-claimed\')')
    const before = store.state(key), actionsBefore = plain(before.actionOverrides)
    for (let index = 0; index < 2; index++) {
        const request = plain(contentToggleRequest(view('publication'), store.revision(), store.digest))
        assert.equal(request.path, '/api/content/gacha%3A1/publication')
        store.setPublished(key, request.payload, now)
        assert.deepEqual(plain(store.state(key).actionOverrides), actionsBefore)
        assert.equal(store.state(key).instanceId, before.instanceId)
        assert.equal(db.prepare('SELECT value FROM synthetic_player_progress').get().value, 'earned-and-claimed')
    }
    assert.equal(store.state(key).published, true)
})
test('exchange-only ordinary toggle preserves exact empty and nonempty scopes plus other actions', t => {
    const { key, store, view } = fixture(t), before = plain(store.state(key))
    const request = plain(contentToggleRequest(view('exchange'), store.revision(), store.digest))
    assert.equal(request.path, '/api/content/gacha%3A1')
    assert.deepEqual(Object.keys(request.payload.actionOverrides), ['exchange'])
    assert.equal(Object.hasOwn(request.payload.actionOverrides.exchange, 'questKeys'), false)
    assert.equal(Object.hasOwn(request.payload.actionOverrides.exchange, 'missionKeys'), false)
    store.update(key, request.payload, now)
    const after = plain(store.state(key))
    for (const action of ['visible', 'enter', 'claim']) assert.deepEqual(after.actionOverrides[action], before.actionOverrides[action])
    assert.equal(after.actionOverrides.exchange.enabled, false)
    assert.deepEqual(after.actionOverrides.exchange.questKeys, ['1:1'])
    assert.deepEqual(after.actionOverrides.exchange.missionKeys, ['7:1', '7:2'])
    assert.equal(after.instanceId, before.instanceId)
})
test('unavailable cards do not produce a toggle request', () => {
    assert.throws(() => contentToggleRequest({ primaryControl: { canToggle: false, kind: 'publication' } }, 1, 'fixture'))
    assert.throws(() => contentToggleRequest({ primaryControl: { canToggle: true, kind: null } }, 1, 'fixture'))
})
test('history explains publication and exchange changes without internal action keys', () => {
    assert.equal(auditDescription({ before: { published: true }, after: { published: false } }), '关闭内容入口')
    assert.equal(auditDescription({ before: { published: false }, after: { published: true } }), '开启内容入口')
    assert.equal(auditDescription({ before: { actionOverrides: { exchange: { enabled: false } } }, after: { actionOverrides: { exchange: { enabled: true } } } }), '开放兑换奖励')
})
test('daily operation labels distinguish pending integration from concrete blockers', () => {
    assert.deepEqual(['enabled', 'disabled', 'pending', 'blocked'].map(contentStatusName), ['已开启', '已关闭', '待接入', '无法开放'])
    assert.doesNotMatch(source, /value: "unsupported"|counts\.unsupported|<code|<pre/)
})
test('crazy claim describes completion of a paid flow and keeps the other action labels', () => {
    assert.equal(contentActionLabel('gacha:100', 'claim'), '续完已付乐享扭蛋')
    assert.equal(contentActionLabel('gacha:2', 'claim'), '领取奖励')
    assert.equal(contentActionLabel('gacha:100', 'enter'), '参与玩法')
    assert.match(source, /row\.rightsNotice/)
    assert.match(source, /selected\.rightsNotice/)
})
