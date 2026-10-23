'use strict'
require('ts-node/register/transpile-only')
const { test } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path')

test('the complete real historical manifest explains all parent cards without preparing or enabling them', async t => {
    const temporaryRoot = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || path.join(__dirname, '../tmp'))
    fs.mkdirSync(temporaryRoot, { recursive: true })
    const temporary = fs.mkdtempSync(path.join(temporaryRoot, 'history-management-'))
    Object.assign(process.env, { DATA_DIR: temporary, TEMP: temporary, TMP: temporary, SQLITE_TMPDIR: temporary,
        CN_WRITER_THREAD: '0', ADMIN_PANEL_PASSWORD: 'history-management-synthetic-password' })
    const Sqlite = require('better-sqlite3'), db = new Sqlite(':memory:')
    const data = require('../src/data/db'); data.setDbOverride(db)
    const operations = require('../src/lib/content-operations')
    const original = operations.contentOperations
    const store = operations.createContentOperationsStore(db)
    require('../src/lib/content-operations-store').initializeContentOperationsSchema(db)
    operations.contentOperations = () => store
    const app = require('fastify')({ logger: false })
    require('../src/lib/management-auth').installManagementAuth(app)
    await app.register(require('../src/routes/web_api/content').default, { prefix: '/api/content' })
    await app.ready()
    t.after(async () => {
        await app.close(); operations.contentOperations = original; data.setDbOverride(null); db.close()
        fs.rmSync(temporary, { recursive: true })
    })
    const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
    const cookie = login.headers['set-cookie'].split(';')[0]
    const get = url => app.inject({ url, headers: { cookie } })
    const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, '../assets/content_history_readiness.json'), 'utf8'))
    assert.equal(manifest.rows.length, 1020)
    const rows = [], first = (await get('/api/content/?limit=200')).json()
    assert.equal(first.total, manifest.rows.length)
    rows.push(...first.rows)
    for (let offset = 200; offset < first.total; offset += 200) {
        const response = await get(`/api/content/?offset=${offset}&limit=200`)
        assert.equal(response.statusCode, 200, response.body)
        rows.push(...response.json().rows)
    }
    assert.deepEqual(new Set(rows.map(row => row.key)), new Set(manifest.rows.map(row => row.key)))
    assert.equal(new Set(rows.map(row => row.type)).size, 23)
    const shopPages = manifest.rows.filter(row => row.type === 'collect_item_event' && row.nativePage?.kind === 'collect_item_exchange_shop')
    assert.equal(shopPages.length, 23)
    const presentation = require('../src/lib/content-presentation')
    for (const native of shopPages) {
        const row = rows.find(value => value.key === native.key), original = presentation.getContentPresentation(native.key)
        assert.equal(row.type, 'collect_item_event')
        assert.equal(row.presentation.group, 'exchange')
        assert.equal(row.presentation.typeLabel, '活动兑换')
        assert.equal(row.presentation.subtitle, native.nativePage.description)
        assert.equal(row.presentation.title, original.title)
        assert.equal(row.presentation.imageUrl, original.imageUrl)
    }
    assert.ok(rows.filter(row => row.type === 'collect_item_event' && !shopPages.some(page => page.key === row.key))
        .every(row => row.presentation.group === 'missions'))
    const exchange = (await get('/api/content/?group=exchange&limit=200')).json()
    assert.ok(shopPages.every(page => exchange.rows.some(row => row.key === page.key)))
    assert.ok(exchange.typeOptions.some(type => type.value === 'collect_item_event' && type.label === '活动兑换'))
    const associated = rows.filter(row => row.linkedActivity && row.type === 'world_story_event')
    assert.equal(associated.length, 9)
    for (const row of associated) {
        assert.equal(row.presentation.group, 'exchange')
        assert.equal(row.presentation.typeLabel, '箱池关联关卡')
        assert.equal(row.linkedActivity.relationshipMatches, true)
        assert.equal(row.linkedActivity.description, '游戏内从关联箱池的任务按钮进入活动关卡')
        assert.equal(row.presentation.title, presentation.getContentPresentation(row.key).title)
        assert.ok(exchange.rows.some(value => value.key === row.key))
        assert.ok(rows.some(value => value.key === row.linkedActivity.boxKey && value.type === 'box_gacha'))
    }
    assert.ok(rows.every(row => row.state === null && row.primaryControl.canToggle === false))
    assert.ok(rows.every(row => ['pending', 'blocked'].includes(row.primaryControl.status)))
    assert.ok(rows.every(row => row.primaryControl.reason && row.primaryControl.label === (row.primaryControl.status === 'pending' ? '待接入' : '无法开放')))
    assert.equal(first.statusCounts.pending + first.statusCounts.blocked, 1020)
    assert.equal(first.statusCounts.enabled, 0)
    assert.equal(first.statusCounts.disabled, 0)
    assert.equal(store.revision(), 0)
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM content_operations_state').get().n, 0)
    for (const status of ['pending', 'blocked']) {
        const response = (await get(`/api/content/?status=${status}&limit=200`)).json()
        assert.equal(response.total, rows.filter(row => row.primaryControl.status === status).length)
        assert.ok(response.rows.every(row => row.primaryControl.status === status))
    }
})
