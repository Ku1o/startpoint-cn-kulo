'use strict'
require('ts-node/register/transpile-only')
const { test, before, after } = require('node:test'), assert = require('node:assert/strict')
const path = require('node:path'), fs = require('node:fs'), os = require('node:os')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const temporary = fs.mkdtempSync(path.join(root, 'linked-publication-'))
Object.assign(process.env, { DATA_DIR: temporary, TEMP: temporary, TMP: temporary, SQLITE_TMPDIR: temporary,
    CN_WRITER_THREAD: '0', ADMIN_PANEL_PASSWORD: 'synthetic-linked-activity-password' })
const load = name => require(path.join(__dirname, '..', 'src', name))
const db = new (require('better-sqlite3'))(':memory:')
const { ContentOperationsStore, ContentOperationError, initializeContentOperationsSchema } = load('lib/content-operations-store')
initializeContentOperationsSchema(db)
load('data/db').setDbOverride(db)
const rows = [ ['world_story_event', 200100], ['box_gacha', 108], ['box_gacha', 109] ].map(([type, id]) => ({
    key: `${type}:${id}`, type, id, name: `合成活动 ${id}`, source: 'Synthetic fixture', definitionDigest: `fixture-${type}-${id}`,
    originalStartMs: 0, originalEndMs: 1, originalExchangeEndMs: null, windowCandidate: false, browseCandidate: false,
}))
const catalog = { schemaVersion: 1, source: { assetVersion: 'synthetic', manifestSha256: 'synthetic' },
    baselineTimeMs: 0, baselineEvidence: 'Synthetic only', missing: [], resources: {}, rows,
    questMap: { '9:200100001': 'world_story_event:200100' } }
const store = new ContentOperationsStore(db, catalog, () => ['visible', 'enter', 'claim', 'exchange'])
const operations = load('lib/content-operations'), originalStore = operations.contentOperations
operations.contentOperations = () => store
const history = load('lib/content-history-readiness'), originalReader = history.contentHistoryReadinessReader
let relationshipMatches = true
history.contentHistoryReadinessReader = () => ({ ...originalReader(),
    boxAssociation: key => ['world_story_event:200100', 'box_gacha:108'].includes(key)
        ? { parentKey: 'world_story_event:200100', boxKey: 'box_gacha:108', relationshipMatches,
            description: '游戏内从关联箱池的任务按钮进入活动关卡' } : undefined })
const action = enabled => ({ enabled, readiness: 'verified', evidence: 'Synthetic independently reviewed action', endsAtMs: null })
const body = extra => ({ expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'Synthetic publication test', ...extra })
function configure(key, enter = true) {
    store.update(key, body({ actionOverrides: { visible: action(true), enter: { ...action(enter),
        ...(key.startsWith('world_') ? { questKeys: ['9:200100001'] } : {}) },
        claim: { ...action(true), ...(key.startsWith('world_') ? { questKeys: ['9:200100001'] } : {}) }, exchange: action(true) } }), Date.now())
    if (store.state(key).published !== false) store.setPublished(key, body({ published: false }), Date.now())
}
let app, cookie
const patch = (key, published, extra = {}) => app.inject({ method: 'PATCH', url: `/api/content/${encodeURIComponent(key)}/publication`,
    headers: { cookie }, payload: body({ published, ...extra }) })
const snapshot = () => ({ state: db.prepare('SELECT * FROM content_operations_state ORDER BY content_key').all(),
    meta: db.prepare('SELECT * FROM content_operations_meta').all(), audit: db.prepare('SELECT * FROM content_operations_audit ORDER BY revision').all() })
before(async () => {
    configure('box_gacha:108'); configure('box_gacha:109')
    app = require('fastify')({ logger: false })
    load('lib/management-auth').installManagementAuth(app)
    await app.register(load('routes/web_api/content').default, { prefix: '/api/content' }); await app.ready()
    const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
    assert.equal(login.statusCode, 200, login.body); cookie = login.headers['set-cookie'].split(';')[0]
})
after(async () => {
    await app?.close(); operations.contentOperations = originalStore; history.contentHistoryReadinessReader = originalReader
    load('data/db').setDbOverride(null); db.close(); fs.rmSync(temporary, { recursive: true })
})
test('unconfigured parent prevents Box publication and is never created or approved', async () => {
    const saved = snapshot()
    const response = await patch('box_gacha:108', true)
    assert.equal(response.statusCode, 409, response.body)
    assert.equal(store.state('world_story_event:200100'), null)
    assert.deepEqual(snapshot(), saved)
    configure('world_story_event:200100')
})
test('one World publication atomically opens both controls while preserving scopes and rights', async () => {
    const before = store.state('world_story_event:200100'), revision = store.revision()
    const response = await patch('world_story_event:200100', true)
    assert.equal(response.statusCode, 200, response.body)
    assert.equal(response.json().revision, revision + 2); assert.equal(response.json().linkedStates.length, 1)
    assert.equal(store.allowed('box_gacha:108', 'enter', Date.now()), true)
    assert.deepEqual(store.state('world_story_event:200100').actionOverrides, before.actionOverrides)
    assert.equal(store.state('box_gacha:109').published, false)
})
test('Box publication uses the same group and closing preserves claim/exchange plus exact scope', async () => {
    const before = store.state('world_story_event:200100').actionOverrides
    const response = await patch('box_gacha:108', false)
    assert.equal(response.statusCode, 200, response.body)
    for (const key of ['world_story_event:200100', 'box_gacha:108']) {
        assert.equal(store.allowed(key, 'visible', Date.now()), false)
        assert.equal(store.allowed(key, 'claim', Date.now()), true)
        assert.equal(store.allowed(key, 'exchange', Date.now()), true)
    }
    assert.deepEqual(store.state('world_story_event:200100').actionOverrides, before)
})
test('a failure on the second write rolls back state, meta and both audit effects', async () => {
    const original = store.setPublished, before = snapshot(); let calls = 0
    store.setPublished = function (...args) { if (++calls === 2) throw new ContentOperationError('Synthetic second-write rejection', 409); return original.apply(this, args) }
    try { const response = await patch('world_story_event:200100', true); assert.equal(response.statusCode, 409, response.body) }
    finally { store.setPublished = original }
    assert.equal(calls, 2); assert.deepEqual(snapshot(), before)
})
test('stale CAS, unverified participation and changed source association cannot partly publish', async () => {
    let before = snapshot()
    assert.equal((await patch('world_story_event:200100', true, { expectedRevision: store.revision() - 1 })).statusCode, 409)
    assert.deepEqual(snapshot(), before)
    relationshipMatches = false
    assert.equal((await patch('world_story_event:200100', true)).statusCode, 409)
    assert.deepEqual(snapshot(), before); relationshipMatches = true
    configure('box_gacha:108', false); before = snapshot()
    assert.equal((await patch('world_story_event:200100', true)).statusCode, 409)
    assert.deepEqual(snapshot(), before)
    const listing = (await app.inject({ url: '/api/content/?limit=200', headers: { cookie } })).json()
    const world = listing.rows.find(row => row.key === 'world_story_event:200100'), box = listing.rows.find(row => row.key === 'box_gacha:108')
    assert.equal(world.primaryControl.status, 'pending')
    assert.ok(world.primaryControl.reason.includes(box.presentation.title) && world.primaryControl.reason.includes('新参与'))
    configure('box_gacha:108')
})
test('an already closed or corrupt peer cannot prevent the active World being closed', async () => {
    assert.equal((await patch('world_story_event:200100', true)).statusCode, 200)
    const boxJson = db.prepare('SELECT value_json FROM content_operations_state WHERE content_key=?').get('box_gacha:108').value_json
    db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run('{', 'box_gacha:108')
    const response = await patch('world_story_event:200100', false)
    assert.equal(response.statusCode, 200, response.body)
    assert.equal(store.state('world_story_event:200100').published, false)
    db.prepare('UPDATE content_operations_state SET value_json=? WHERE content_key=?').run(boxJson, 'box_gacha:108')
    store.setPublished('box_gacha:108', body({ published: false }), Date.now())
})
test('group cards expose the native Box route, retain individual keys and other Boxes stay independent', async () => {
    const response = await app.inject({ url: '/api/content/?limit=200', headers: { cookie } })
    assert.equal(response.statusCode, 200, response.body)
    const world = response.json().rows.find(row => row.key === 'world_story_event:200100')
    assert.equal(world.presentation.typeLabel, '箱池关联关卡'); assert.equal(world.presentation.group, 'exchange')
    assert.equal(world.linkedActivity.description, '游戏内从关联箱池的任务按钮进入活动关卡')
    assert.equal(world.primaryControl.canToggle, true)
    const revision = store.revision(), other = await patch('box_gacha:109', true)
    assert.equal(other.statusCode, 200, other.body); assert.equal(store.revision(), revision + 1)
    assert.equal(store.state('world_story_event:200100').published, false)
})
test('closed, missing and changed-association peers never prevent taking the World offline', async () => {
    for (const condition of ['closed', 'missing', 'association']) {
        assert.equal((await patch('world_story_event:200100', true)).statusCode, 200)
        const saved = db.prepare('SELECT value_json FROM content_operations_state WHERE content_key=?').get('box_gacha:108').value_json
        if (condition === 'closed') store.setPublished('box_gacha:108', body({ published: false }), Date.now())
        if (condition === 'missing') db.prepare('DELETE FROM content_operations_state WHERE content_key=?').run('box_gacha:108')
        if (condition === 'association') relationshipMatches = false
        const response = await patch('world_story_event:200100', false)
        assert.equal(response.statusCode, 200, `${condition}: ${response.body}`)
        assert.equal(store.state('world_story_event:200100').published, false)
        relationshipMatches = true
        if (condition === 'missing') db.prepare('INSERT INTO content_operations_state(content_key,value_json) VALUES(?,?)').run('box_gacha:108', saved)
        if (store.state('box_gacha:108').published !== false) store.setPublished('box_gacha:108', body({ published: false }), Date.now())
    }
})
