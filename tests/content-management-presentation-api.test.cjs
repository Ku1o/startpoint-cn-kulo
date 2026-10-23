'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const path = require('node:path'), fs = require('node:fs'), os = require('node:os')
const load = name => require(path.join(__dirname, '..', compiled ? 'out' : 'src', name))
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict')
const temporaryRoot = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(temporaryRoot, { recursive: true })
const temporary = fs.mkdtempSync(path.join(temporaryRoot, 'content-presentation-api-'))
Object.assign(process.env, { DATA_DIR: temporary, TEMP: temporary, TMP: temporary, SQLITE_TMPDIR: temporary,
    CN_WRITER_THREAD: '0', ADMIN_PANEL_PASSWORD: 'presentation-api-synthetic-password' })
const Sqlite = require('better-sqlite3'), db = new Sqlite(':memory:')
const { ContentOperationsStore, initializeContentOperationsSchema } = load('lib/content-operations-store')
initializeContentOperationsSchema(db)
db.exec('CREATE TABLE retained_progress(id INTEGER PRIMARY KEY,value INTEGER); INSERT INTO retained_progress VALUES(1,731)')
load('data/db').setDbOverride(db)
const row = (type, id, name, extra = {}) => ({ key: `${type}:${id}`, type, id, name,
    originalStartMs: Date.UTC(2019, 0, 1), originalEndMs: Date.UTC(2020, 0, 1), originalExchangeEndMs: null,
    windowCandidate: false, browseCandidate: false, source: 'synthetic fixture', definitionDigest: `${type}-${id}`, ...extra })
const gachaRows = Array.from({ length: 225 }, (_, index) => row('gacha', 900000 + index, `合成历史卡池 ${String(index).padStart(3, '0')}`,
    index === 223 ? { originalStartMs: Date.UTC(2021, 0, 1) } : index === 224 ? { originalStartMs: null } : {}))
const parentRows = [
    ...gachaRows,
    row('gacha', 2, 'fixture original title deliberately differs'),
    row('gacha', 100, '合成乐享扭蛋'),
    row('gacha', 80000, '合成个人星辰扭蛋'),
    row('gacha', 700000, '合成个人回归扭蛋', { personalWindow: true }),
    row('advent_event', 900100, '合成历史活动'),
    row('advent_event', 900101, '合成尚未支持活动'),
    row('tower_dungeon_event', 1, 'fixture old tower label'),
    row('solo_time_attack_event', 1, 'fixture old solo label'),
    row('active_mission_event', 900200, '合成历史任务'),
    row('pass_card_event', 900300, '合成当前通行证'),
    row('pass_card_event', 900301, '合成已关闭通行证'),
    row('special_exchange_campaign', 11, '合成已有资格兑换'),
    row('start_dash_exchange_campaign', 1, '合成开局兑换'),
]
const memberRows = [row('event_item_shop', 991, '不应混入日常列表的商品', { parentKey: 'advent_event:900100' }),
    row('mission_event', 992, '不应混入日常列表的任务成员', { parentKey: 'active_mission_event:900200' })]
const catalog = { schemaVersion: 1, source: { assetVersion: 'presentation-fixture', manifestSha256: 'fixture' },
    baselineTimeMs: 0, baselineEvidence: 'Synthetic API fixture only', missing: [], resources: {},
    questMap: { '7:900100001': 'advent_event:900100', '7:900100002': 'advent_event:900100' },
    rows: [...parentRows, ...memberRows] }
const capabilities = value => value.key === 'advent_event:900101' ? []
    : value.key === 'gacha:100' ? ['visible', 'enter', 'claim', 'exchange']
    : value.key === 'gacha:700000' ? ['exchange']
    : ['special_exchange_campaign', 'start_dash_exchange_campaign'].includes(value.type) ? ['exchange']
        : ['visible', 'enter', 'exchange']
const store = new ContentOperationsStore(db, catalog, capabilities)
const operations = load('lib/content-operations'), originalStore = operations.contentOperations
operations.contentOperations = () => store
const presentation = load('lib/content-presentation')
const historyReadiness = load('lib/content-history-readiness')
const originalHistoryReader = historyReadiness.getContentHistoryReadiness
const originalHistorySnapshotReader = historyReadiness.contentHistoryReadinessReader
const staticPassed = { status: 'passed', blockers: [] }
const staticBlocked = message => ({ status: 'blocked', blockers: [{ code: 'synthetic_blocker', message }] })
const historyRows = new Map([
    ['gacha:900000', { key: 'gacha:900000', actions: { visible: staticBlocked('合成后续核查限制'), enter: staticPassed } }],
    ['gacha:900001', { key: 'gacha:900001', actions: { visible: staticBlocked('合成后续核查限制'), enter: staticPassed } }],
    ['gacha:900010', { key: 'gacha:900010', actions: { visible: staticPassed, enter: staticPassed } }],
    ['gacha:900011', { key: 'gacha:900011', actions: { visible: staticPassed, enter: staticBlocked('必需的战斗资源缺失') } }],
    ['gacha:900012', { key: 'gacha:900012', staticStatus: 'blocked', actions: { visible: staticPassed, enter: staticPassed, claim: staticBlocked('累计奖励规则尚未实现') } }],
    ['gacha:900013', { key: 'gacha:900013', actions: { visible: staticPassed,
        enter: { status: 'unreviewed', blockers: [{ code: 'native_route_review', message: '尚需核对箱池入口与原生关卡路由' }] } } }],
])
const originalImageReader = presentation.readContentPresentationImage
const originalThumbnailReader = presentation.readContentPresentationThumbnail
const thumbnailHash = 'a'.repeat(64), webp = Buffer.from('RIFF\x10\x00\x00\x00WEBPsynthetic')
let app, cookie, imageReads = 0, thumbnailReads = 0
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lWQAAAAASUVORK5CYII=', 'base64')
const action = (enabled, extra = {}) => ({ enabled, readiness: 'verified', evidence: 'Synthetic exact reviewed action', endsAtMs: null, ...extra })
const body = extra => ({ expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'Synthetic presentation test', ...extra })
const get = url => app.inject({ url, headers: { cookie } })
const patch = (key, input, suffix = '') => app.inject({ method: 'PATCH', url: `/api/content/${encodeURIComponent(key)}${suffix}`,
    headers: { cookie }, payload: input })

before(async () => {
    historyReadiness.contentHistoryReadinessReader = () => {
        const reader = originalHistorySnapshotReader()
        return { ...reader, get: (key, actions) => historyRows.has(key)
            ? historyReadiness.explainContentHistoryReadiness(historyRows.get(key), actions) : reader.get(key, actions) }
    }
    store.update('gacha:900000', body({ actionOverrides: { visible: action(true), enter: action(true) } }), Date.now())
    store.update('gacha:900001', body({ actionOverrides: { visible: action(true), enter: action(true) } }), Date.now())
    store.update('gacha:100', body({ actionOverrides: { visible: action(true), enter: action(true), claim: action(true) } }), Date.now())
    store.update('gacha:80000', body({ actionOverrides: { visible: action(true), enter: action(true) } }), Date.now())
    store.setPublished('gacha:900001', body({ published: false }), Date.now())
    store.update('advent_event:900100', body({ actionOverrides: {
        visible: action(true), enter: action(true, { questKeys: ['7:900100001'] }),
    } }), Date.now())
    store.update('special_exchange_campaign:11', body({ actionOverrides: { exchange: action(true) } }), Date.now())
    store.update('start_dash_exchange_campaign:1', body({ actionOverrides: { exchange: action(false) } }), Date.now())
    store.update('pass_card_event:900301', body({ actionOverrides: { visible: action(true), enter: action(true) } }), Date.now())
    store.setPublished('pass_card_event:900301', body({ published: false }), Date.now())
    store.update('pass_card_event:900300', body({ actionOverrides: { visible: action(true), enter: action(true) } }), Date.now())
    const expiredNow = Date.now() - 20000
    store.update('gacha:900002', body({ actionOverrides: { visible: action(true, { endsAtMs: expiredNow + 1000 }) } }), expiredNow)
    presentation.readContentPresentationImage = async key => {
        imageReads++
        return key === 'gacha:2' ? { bytes: png, contentType: 'image/png', etag: '"synthetic-png"' } : null
    }
    presentation.readContentPresentationThumbnail = hash => {
        thumbnailReads++
        return hash === thumbnailHash ? { bytes: webp, contentType: 'image/webp', etag: `"${thumbnailHash}"` } : null
    }
    app = require('fastify')({ logger: false })
    load('lib/management-auth').installManagementAuth(app)
    await app.register(load('routes/web_api/content').default, { prefix: '/api/content' })
    await app.ready()
    const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
    assert.equal(login.statusCode, 200, login.body)
    cookie = login.headers['set-cookie'].split(';')[0]
})

after(async () => {
    if (app) await app.close()
    operations.contentOperations = originalStore
    presentation.readContentPresentationImage = originalImageReader
    presentation.readContentPresentationThumbnail = originalThumbnailReader
    historyReadiness.getContentHistoryReadiness = originalHistoryReader
    historyReadiness.contentHistoryReadinessReader = originalHistorySnapshotReader
    assert.equal(db.prepare('SELECT value FROM retained_progress WHERE id=1').get().value, 731)
    load('data/db').setDbOverride(null)
    db.close()
    assert.equal(path.dirname(temporary), temporaryRoot)
    fs.rmSync(temporary, { recursive: true })
})

test('default listing preserves every historical parent and excludes member rows before pagination/counting', async () => {
    const revision = store.revision()
    const firstResponse = await get('/api/content/?limit=200')
    assert.equal(firstResponse.statusCode, 200, firstResponse.body)
    const first = firstResponse.json()
    assert.equal(first.view, 'parents')
    assert.equal(first.total, parentRows.length)
    const last = (await get('/api/content/?offset=200&limit=200')).json()
    const keys = [...first.rows, ...last.rows].map(value => value.key)
    assert.equal(new Set(keys).size, parentRows.length)
    assert.deepEqual(new Set(keys), new Set(parentRows.map(value => value.key)))
    const combined = [...first.rows, ...last.rows]
    const priority = { enabled: 0, disabled: 1, pending: 2, blocked: 3 }
    for (let index = 1; index < combined.length; index++) {
        assert.ok(priority[combined[index - 1].primaryControl.status] <= priority[combined[index].primaryControl.status], 'status priority is applied before slicing pages')
    }
    for (const status of ['enabled', 'disabled', 'pending', 'blocked']) {
        const grouped = combined.filter(value => value.primaryControl.status === status).map(value => value.key)
        assert.deepEqual(grouped, parentRows.filter(value => grouped.includes(value.key)).map(value => value.key), 'equal status keeps original catalog order')
    }
    assert.ok(first.rows.every(value => value.presentation.title && value.presentation.groupLabel && value.presentation.typeLabel))
    assert.equal(first.groups.find(group => group.key === 'all').total, first.total)
    assert.equal(first.groups.filter(group => group.key !== 'all').reduce((sum, group) => sum + group.total, 0), first.total)
    assert.equal(first.statusCounts.enabled + first.statusCounts.disabled + first.statusCounts.unsupported, first.total)
    assert.equal(first.statusCounts.pending + first.statusCounts.blocked, first.statusCounts.unsupported)
    const allLegacy = (await get('/api/content/?includeMembers=true&limit=200')).json()
    assert.equal(allLegacy.view, 'members')
    assert.equal(allLegacy.total, parentRows.length + memberRows.length)
    assert.equal((await get('/api/content/?includeMembers=true&type=event_item_shop')).json().rows[0].key, memberRows[0].key)
    assert.equal(store.revision(), revision, 'listing and facets cannot create or revise operational permissions')
})

test('an already active pass keeps the existing one-pass publication protection visible', async () => {
    const listing = (await get('/api/content/?type=pass_card_event')).json()
    const active = listing.rows.find(value => value.key === 'pass_card_event:900300')
    const inactive = listing.rows.find(value => value.key === 'pass_card_event:900301')
    assert.equal(active.primaryControl.status, 'enabled')
    assert.equal(active.primaryControl.canToggle, true)
    assert.equal(inactive.primaryControl.status, 'disabled')
    assert.equal(inactive.primaryControl.canToggle, false)
    assert.match(inactive.primaryControl.reason, /先关闭/)
    const before = store.revision()
    assert.equal((await patch(inactive.key, body({ published: true }), '/publication')).statusCode, 409)
    assert.equal(store.revision(), before)
})

test('four statuses separate missing integration from concrete blockers without granting static approval', async () => {
    const before = store.revision()
    const getOne = async key => (await get(`/api/content/?search=${encodeURIComponent(key)}`)).json().rows.find(row => row.key === key)
    const readyStatic = await getOne('gacha:900010')
    assert.equal(readyStatic.primaryControl.status, 'pending')
    assert.equal(readyStatic.primaryControl.label, '待接入')
    assert.equal(readyStatic.primaryControl.canToggle, false)
    assert.equal(readyStatic.state, null, 'static audit must never create controls')
    assert.doesNotMatch(readyStatic.primaryControl.reason, /资源缺/)
    const blocked = await getOne('gacha:900011')
    assert.equal(blocked.primaryControl.status, 'blocked')
    assert.equal(blocked.primaryControl.label, '无法开放')
    assert.equal(blocked.primaryControl.reason, '必需的战斗资源缺失')
    const unrelated = await getOne('gacha:900012')
    assert.equal(unrelated.primaryControl.status, 'pending')
    assert.deepEqual(unrelated.limitations, ['领取奖励：累计奖励规则尚未实现'])
    const unreviewed = await getOne('gacha:900013')
    assert.equal(unreviewed.primaryControl.status, 'pending')
    assert.equal(unreviewed.primaryControl.label, '待接入')
    assert.equal(unreviewed.primaryControl.reason, '尚需核对箱池入口与原生关卡路由')
    const active = await getOne('gacha:900000'), inactive = await getOne('gacha:900001')
    assert.equal(active.primaryControl.status, 'enabled')
    assert.equal(active.primaryControl.canToggle, true, 'a later static blocker cannot prevent closing an active control')
    assert.equal(inactive.primaryControl.status, 'disabled')
    assert.equal(inactive.primaryControl.canToggle, true, 'an existing store-reviewed closed control retains its operator capability')
    const pending = (await get('/api/content/?status=pending&limit=200')).json()
    const unavailable = (await get('/api/content/?status=blocked&limit=200')).json()
    const legacy = (await get('/api/content/?status=unsupported&limit=200')).json()
    assert.equal(pending.total + unavailable.total, legacy.total)
    assert.ok(pending.rows.every(row => row.primaryControl.status === 'pending'))
    assert.ok(unavailable.rows.every(row => row.primaryControl.status === 'blocked'))
    assert.equal(store.revision(), before)
})

test('paid crazy selection rights and deferred personal qualification remain clear across daily publication changes', async () => {
    const getOne = async key => (await get(`/api/content/?search=${encodeURIComponent(key)}`)).json().rows.find(row => row.key === key)
    const before = store.state('gacha:100'), claimBefore = { ...before.actionOverrides.claim }
    const close = await patch('gacha:100', body({ published: false }), '/publication')
    assert.equal(close.statusCode, 200, close.body)
    const crazy = await getOne('gacha:100')
    assert.equal(crazy.primaryControl.status, 'disabled')
    assert.equal(crazy.primaryControl.canToggle, true)
    assert.equal(crazy.effectiveFlags.enter, false)
    assert.equal(crazy.effectiveFlags.claim, true)
    assert.match(crazy.rightsNotice, /已使用乐享扭蛋券.*续完本轮扭蛋/)
    assert.deepEqual(store.state('gacha:100').actionOverrides.claim, claimBefore)
    assert.equal((await patch('gacha:100', body({ published: true }), '/publication')).statusCode, 200)
    const stars = await getOne('gacha:80000'), comeback = await getOne('gacha:700000')
    assert.equal(stars.primaryControl.status, 'enabled', 'an existing operator state is preserved')
    assert.equal(stars.primaryControl.canToggle, true)
    for (const personal of [stars, comeback]) assert.match(personal.rightsNotice, /保留已有进度和兑换.*不新增个人扭蛋资格.*不会发放资格/)
    assert.equal(comeback.state, null, 'qualification explanation cannot prepare or grant a control')
})

test('official display titles are searchable before pagination and category/status facets keep correct totals', async () => {
    const official = presentation.getContentPresentation(parentRows.find(value => value.key === 'gacha:2'))
    assert.ok(official.title)
    const found = (await get(`/api/content/?search=${encodeURIComponent(official.title)}&limit=1`)).json()
    assert.ok(found.total > 0)
    const allFound = (await get(`/api/content/?search=${encodeURIComponent(official.title)}&limit=200`)).json()
    assert.ok(allFound.rows.some(value => value.key === 'gacha:2'), 'official title must not be filtered out by the raw catalog name')
    const enabled = (await get('/api/content/?group=gacha&status=enabled&offset=0&limit=1')).json()
    assert.equal(enabled.total, 3)
    assert.equal(enabled.rows[0].key, 'gacha:900000')
    assert.equal(enabled.groups.find(group => group.key === 'gacha').total, enabled.total)
    assert.equal(enabled.statusCounts.enabled, enabled.total)
    assert.equal(enabled.statusCounts.disabled, 2)
    assert.equal(enabled.statusCounts.total, gachaRows.length + 4, 'status tabs count the category before the selected status filter')
    assert.equal((await get('/api/content/?group=gacha&status=enabled&offset=3&limit=1')).json().rows.length, 0)
    const closed = (await get('/api/content/?group=gacha&status=disabled')).json()
    assert.equal(closed.total, 2)
    assert.deepEqual(closed.rows.map(row => row.key).sort(), ['gacha:900001', 'gacha:900002'])
    const expired = closed.rows.find(row => row.key === 'gacha:900002')
    assert.deepEqual(Object.keys(expired.state.actionOverrides), ['visible'], 'expiry must not manufacture an enter review')
    assert.equal(expired.primaryControl.status, 'disabled')
    assert.equal(expired.primaryControl.canToggle, false, 'the expired visible review must be extended before publication')
    assert.equal(expired.deadlineControl.canEdit, true)
    assert.deepEqual(expired.deadlineControl.actionLabels, ['入口显示'])
    assert.equal(expired.state.actionOverrides.enter, undefined)
    assert.equal((await get('/api/content/?search=gacha%3A900002&status=unsupported')).json().rows.length, 0)
    const unwired = (await get('/api/content/?search=advent_event%3A900101')).json().rows[0]
    assert.equal(unwired.primaryControl.status, 'pending')
    assert.equal(unwired.primaryControl.canToggle, false)
    const originalPresentation = presentation.getContentPresentation
    try {
        presentation.getContentPresentation = value => {
            const result = originalPresentation(value)
            return (typeof value === 'string' ? value : value.key) === 'gacha:900000'
                ? { ...result, originalTitle: '合成オリジナル名称' } : result
        }
        const originalName = (await get(`/api/content/?search=${encodeURIComponent('合成オリジナル名称')}`)).json()
        assert.equal(originalName.total, 1)
        assert.equal(originalName.rows[0].key, 'gacha:900000', 'an original native title remains searchable when the display title differs')
    } finally { presentation.getContentPresentation = originalPresentation }
})

test('type options use the card display labels and stay complete for the selected group under other filters', async () => {
    const expected = group => {
        const labels = new Map()
        for (const value of parentRows) {
            const display = presentation.getContentPresentation(value)
            if (group !== 'all' && display.group !== group) continue
            if (!labels.has(value.type)) labels.set(value.type, new Set())
            labels.get(value.type).add(display.typeLabel)
        }
        return [...labels].map(([value, labels]) => ({ value, label: [...labels].join(' / ') }))
    }
    for (const group of ['all', 'events', 'gacha', 'missions', 'exchange']) {
        const base = (await get(`/api/content/?group=${group}&limit=1`)).json()
        assert.deepEqual(base.typeOptions, expected(group))
        assert.equal(new Set(base.typeOptions.map(value => value.value)).size, base.typeOptions.length)
        const filtered = (await get(`/api/content/?group=${group}&search=definitely-not-a-title&status=enabled&type=unknown&readiness=blocked&julyOnly=true&limit=1`)).json()
        assert.equal(filtered.total, 0)
        assert.deepEqual(filtered.typeOptions, base.typeOptions, 'search/status/type/readiness/date cannot erase the current category type options')
    }
    const eventOptions = (await get('/api/content/?group=events')).json().typeOptions
    for (const type of ['tower_dungeon_event', 'solo_time_attack_event']) {
        assert.equal(eventOptions.find(value => value.value === type).label,
            presentation.getContentPresentation(parentRows.find(value => value.type === type)).typeLabel)
    }
    const legacy = (await get('/api/content/?includeMembers=true&type=event_item_shop&limit=1')).json()
    assert.equal(legacy.rows[0].key, memberRows[0].key)
    assert.ok(legacy.types.includes('mission_event'))
    assert.ok(legacy.typeOptions.some(value => value.value === 'event_item_shop'))
    assert.ok(!(await get('/api/content/?group=all')).json().typeOptions.some(value => value.value === 'event_item_shop'))
    const oldExplicit = (await get('/api/content/?type=event_item_shop&limit=1')).json()
    assert.equal(oldExplicit.view, 'members')
    assert.equal(oldExplicit.total, legacy.total)
    assert.deepEqual(oldExplicit.rows, legacy.rows, 'old explicit member-type queries retain the original listing without changing the default parent view')
    const explicitParent = (await get('/api/content/?type=event_item_shop&includeMembers=false')).json()
    assert.equal(explicitParent.view, 'parents')
    assert.equal(explicitParent.total, 0)
})

test('existing publication CAS and exact reviewed scope survive daily close/reopen', async () => {
    const key = 'advent_event:900100'
    const listing = (await get(`/api/content/?search=${encodeURIComponent(key)}`)).json()
    const before = store.state(key), scopes = JSON.stringify(before.actionOverrides)
    assert.equal(listing.rows[0].primaryControl.kind, 'publication')
    assert.equal(listing.rows[0].primaryControl.enabled, true)
    const close = await patch(key, { expectedRevision: listing.revision, catalogDigest: listing.catalogDigest, reason: 'Synthetic close', published: false }, '/publication')
    assert.equal(close.statusCode, 200, close.body)
    assert.equal(JSON.stringify(store.state(key).actionOverrides), scopes)
    const blockedStale = await patch(key, { expectedRevision: listing.revision, catalogDigest: listing.catalogDigest, reason: 'Synthetic stale', published: true }, '/publication')
    assert.equal(blockedStale.statusCode, 409)
    const closed = (await get(`/api/content/?search=${encodeURIComponent(key)}`)).json()
    assert.equal(closed.rows[0].primaryControl.status, 'disabled')
    assert.equal(closed.rows[0].primaryControl.canToggle, true)
    const open = await patch(key, { expectedRevision: closed.revision, catalogDigest: closed.catalogDigest, reason: 'Synthetic reopen', published: true }, '/publication')
    assert.equal(open.statusCode, 200, open.body)
    assert.equal(JSON.stringify(store.state(key).actionOverrides), scopes)
    assert.equal(store.state(key).instanceId, before.instanceId)
})

test('reviewed exchange-only campaigns use the existing single-action API without manufacturing qualification', async () => {
    const listing = (await get('/api/content/?group=exchange')).json()
    const special = listing.rows.find(value => value.key === 'special_exchange_campaign:11')
    const startDash = listing.rows.find(value => value.key === 'start_dash_exchange_campaign:1')
    assert.equal(special.primaryControl.kind, 'exchange')
    assert.equal(special.primaryControl.enabled, true)
    assert.equal(startDash.primaryControl.kind, 'exchange')
    assert.equal(startDash.primaryControl.status, 'disabled')
    const original = store.state(special.key).actionOverrides.exchange
    const result = await patch(special.key, body({ actionOverrides: { exchange: {
        enabled: false, readiness: original.readiness, evidence: original.evidence, endsAtMs: original.endsAtMs,
        ...(original.questKeys !== undefined ? { questKeys: original.questKeys } : {}),
        ...(original.missionKeys !== undefined ? { missionKeys: original.missionKeys } : {}),
    } } }))
    assert.equal(result.statusCode, 200, result.body)
    const updated = (await get(`/api/content/?search=${encodeURIComponent(special.key)}`)).json().rows[0]
    assert.equal(updated.primaryControl.status, 'disabled')
    assert.equal(updated.primaryControl.canToggle, true)
    assert.equal(store.state(special.key).actionOverrides.exchange.evidence, original.evidence)
    assert.equal(db.prepare('SELECT value FROM retained_progress WHERE id=1').get().value, 731)
})

test('list, image and writes retain cookie management authentication; image route is a key whitelist', async () => {
    for (const request of [
        { url: '/api/content/' }, { url: '/api/content/gacha%3A2/image' },
        { method: 'PATCH', url: '/api/content/gacha%3A900000/publication', payload: body({ published: false }) },
    ]) assert.equal((await app.inject(request)).statusCode, 401)
    assert.equal(imageReads, 0, 'unauthenticated image requests must never invoke the reader')
    assert.equal((await get('/api/content/missing%3A1/image')).statusCode, 404)
    assert.equal(imageReads, 0, 'unknown keys must never invoke the image reader')
    const image = await get('/api/content/gacha%3A2/image')
    assert.equal(image.statusCode, 200)
    assert.match(image.headers['content-type'], /^image\/png/)
    assert.match(image.headers['cache-control'], /^private/)
    assert.deepEqual(image.rawPayload, png)
    assert.equal((await app.inject({ url: '/api/content/gacha%3A2/image', headers: { cookie, 'if-none-match': image.headers.etag } })).statusCode, 304)
    assert.equal((await get('/api/content/gacha%3A900000/image')).statusCode, 404)
    assert.equal((await get('/api/content/gacha%3A2/image?path=arbitrary')).statusCode, 400)
})

test('thumbnail route retains authentication, immutable private caching,304 and strict hash/query validation', async () => {
    const url = `/api/content/thumbnail/${thumbnailHash}.webp`, before = thumbnailReads
    assert.equal((await app.inject({ url })).statusCode, 401)
    assert.equal(thumbnailReads, before)
    const image = await get(url)
    assert.equal(image.statusCode, 200); assert.deepEqual(image.rawPayload, webp)
    assert.match(image.headers['content-type'], /^image\/webp/)
    assert.equal(image.headers['cache-control'], 'private, max-age=86400, immutable')
    const cached = await app.inject({ url, headers: { cookie, 'if-none-match': image.headers.etag } })
    assert.equal(cached.statusCode, 304); assert.equal(cached.rawPayload.length, 0)
    for (const suffix of ['../outside', '__proto__', thumbnailHash.toUpperCase() + '.webp', thumbnailHash + '.png'])
        assert.ok([400, 404].includes((await get('/api/content/thumbnail/' + suffix)).statusCode))
    assert.equal((await get('/api/content/thumbnail/' + '0'.repeat(64) + '.webp')).statusCode, 404)
    assert.equal((await get(url + '?path=outside')).statusCode, 400)
})

test('new filters validate strictly and retain old query and audit contracts', async () => {
    for (const query of ['group=unknown', 'status=unknown', 'status=enabled&status=disabled', 'includeMembers=yes',
        'includeMembers=true&group=gacha', 'includeMembers=true&status=enabled',
        'type=event_item_shop&group=exchange', 'type=mission_event&status=unsupported', 'limit=0', 'offset=-1']) {
        assert.equal((await get(`/api/content/?${query}`)).statusCode, 400, query)
    }
    const oldSearch = (await get('/api/content/?search=gacha%3A900000&type=gacha&limit=1')).json()
    assert.equal(oldSearch.total, 1)
    assert.equal(oldSearch.rows[0].key, 'gacha:900000')
    assert.ok(oldSearch.catalogDigest)
    assert.ok(Number.isSafeInteger(oldSearch.revision))
    const revision = store.revision()
    assert.equal((await patch('gacha:900000', body({ primaryControl: { enabled: true } }))).statusCode, 400)
    assert.equal(store.revision(), revision, 'presentation fields are not a new write authority')
    const audit = await get('/api/content/audit?limit=2')
    assert.equal(audit.statusCode, 200, audit.body)
    assert.equal(audit.json().rows.length, 2)
})

test('global keyword counts precede explicit filters and search relevance precedes current open status', async () => {
    const discovery = load('lib/content-discovery'), original = discovery.contentDiscoveryReader
    const scores = new Map([['gacha:900001', 900], ['gacha:900010', 500], ['advent_event:900100', 100]])
    const revision = store.revision()
    discovery.contentDiscoveryReader = () => ({ verificationNotice: undefined,
        meta: value => ({ seriesKey: value.type, seriesTitle: value.presentation.title }),
        view: value => ({ seriesKey: value.type, seriesTitle: value.presentation.title, highlights: [], notes: [], matchReasons: [] }),
        details: () => ({ characters: [], rewards: [], aliases: [], notes: [] }),
        match: (value, terms) => ({ matched: scores.has(value.key) && terms.length === 2 && terms[0] === '勇气' && terms[1] === '剑', score: scores.get(value.key) || 0, reasons: ['兑换奖励：勇气之剑'] }) })
    try {
        const search = encodeURIComponent('勇气 剑')
        const global = (await get(`/api/content/?search=${search}&group=all&limit=1`)).json()
        assert.equal(global.total, 3); assert.equal(global.searchInfo.unfilteredTotal, 3); assert.equal(global.searchInfo.scopeTotal, 3)
        assert.equal(global.rows[0].key, 'gacha:900001', 'a better disabled match stays above a lower-ranked enabled activity')
        assert.deepEqual(global.searchInfo.terms, ['勇气', '剑'])
        const filtered = (await get(`/api/content/?search=${search}&group=gacha&type=gacha&status=disabled&limit=1`)).json()
        assert.equal(filtered.searchInfo.unfilteredTotal, 3); assert.equal(filtered.searchInfo.scopeTotal, 2)
        assert.equal(filtered.rows[0].key, 'gacha:900001'); assert.equal(filtered.rows[0].discovery.matchReasons[0], '兑换奖励：勇气之剑')
        assert.equal((await get(`/api/content/?search=${encodeURIComponent('勇气 不存在')}`)).json().total, 0)
        assert.equal(store.revision(), revision)
    } finally { discovery.contentDiscoveryReader = original }
})

test('discovery details authenticate before reading, reject unknown keys/queries and never mutate controls', async () => {
    const discovery = load('lib/content-discovery'), original = discovery.contentDiscoveryReader
    let reads = 0; const revision = store.revision()
    discovery.contentDiscoveryReader = () => { reads++; return { details: () => ({ characters: [{ id: 1, name: '合成勇者', relation: 'up' }], rewards: [], aliases: [], notes: [] }) } }
    try {
        assert.equal((await app.inject({ url: '/api/content/gacha%3A2/discovery' })).statusCode, 401); assert.equal(reads, 0)
        assert.equal((await get('/api/content/missing%3A1/discovery')).statusCode, 404); assert.equal(reads, 0)
        assert.equal((await get('/api/content/gacha%3A2/discovery?file=outside')).statusCode, 400); assert.equal(reads, 0)
        const details = await get('/api/content/gacha%3A2/discovery')
        assert.equal(details.statusCode, 200); assert.equal(details.json().characters[0].name, '合成勇者')
        assert.equal(reads, 1); assert.equal(store.revision(), revision)
    } finally { discovery.contentDiscoveryReader = original }
})

test('series pagination summarises all matching editions before slicing and expansion retains independent child rows', async () => {
    const discovery = load('lib/content-discovery'), original = discovery.contentDiscoveryReader, groupKey = 'a'.repeat(24)
    const synthetic = new Set(gachaRows.map(value => value.key)), revision = store.revision()
    discovery.contentDiscoveryReader = () => ({ verificationNotice: undefined,
        meta: value => ({ seriesKey: synthetic.has(value.key) ? groupKey : require('node:crypto').createHash('sha256').update(value.key).digest('hex').slice(0,24), seriesTitle: synthetic.has(value.key) ? '同名历史卡池' : value.presentation.title }),
        view: value => ({ seriesKey: synthetic.has(value.key) ? groupKey : require('node:crypto').createHash('sha256').update(value.key).digest('hex').slice(0,24), seriesTitle: synthetic.has(value.key) ? '同名历史卡池' : value.presentation.title, highlights: [], notes: [], matchReasons: [] }),
        details: () => ({ characters: [], rewards: [], aliases: [], notes: [] }),
        match: () => ({ matched: true, score: 0, reasons: [] }) })
    try {
        const summary=(await get('/api/content/?group=gacha&view=series&limit=200')).json()
        assert.equal(summary.view,'series');assert.equal(summary.rows.length,0)
        const group=summary.seriesGroups.find(value=>value.key===groupKey)
        assert.equal(group.total,225);assert.equal(group.enabled+group.disabled+group.pending+group.blocked,225)
        assert.equal(summary.contentTotal,parentRows.filter(value=>value.type==='gacha').length)
        const position=summary.seriesGroups.findIndex(value=>value.key===groupKey)
        const one=(await get(`/api/content/?group=gacha&view=series&offset=${position}&limit=1`)).json()
        assert.equal(one.seriesGroups[0].key,groupKey);assert.equal(one.seriesGroups[0].total,225)
        const first=(await get(`/api/content/?group=gacha&series=${groupKey}&limit=200`)).json()
        const last=(await get(`/api/content/?group=gacha&series=${groupKey}&offset=200&limit=200`)).json()
        assert.equal(first.total,225);assert.equal(first.rows.length,200);assert.equal(last.rows.length,25)
        assert.deepEqual(new Set([...first.rows,...last.rows].map(value=>value.key)),synthetic)
        assert.ok([...first.rows,...last.rows].every(value=>value.primaryControl && value.state!==undefined))
        assert.equal(store.revision(),revision,'grouping must never mutate or combine control state')
    } finally { discovery.contentDiscoveryReader=original }
})

test('empty favourites stay empty, recent order is explicit, dates sort safely and new filters reject malformed values',async()=>{
    const empty=(await get('/api/content/?keys=')).json();assert.equal(empty.total,0);assert.equal(empty.rows.length,0)
    assert.equal(empty.statusCounts.total,0);assert.ok(empty.groups.every(group=>group.total===0))
    const keys='gacha:900010,gacha:900001,gacha:999999999'
    const ordered=(await get(`/api/content/?keys=${encodeURIComponent(keys)}&keyOrder=true`)).json()
    assert.deepEqual(ordered.rows.map(value=>value.key),['gacha:900010','gacha:900001'])
    const dates='gacha:900000,gacha:900223,gacha:900224'
    const desc=(await get(`/api/content/?keys=${encodeURIComponent(dates)}&sort=dateDesc`)).json()
    assert.deepEqual(desc.rows.map(value=>value.key),['gacha:900223','gacha:900000','gacha:900224'])
    const explicitDate=(await get(`/api/content/?keys=${encodeURIComponent(dates)}&keyOrder=true&sort=dateDesc`)).json()
    assert.deepEqual(explicitDate.rows.map(value=>value.key),desc.rows.map(value=>value.key),'explicit date ordering beats stored recent order')
    const asc=(await get(`/api/content/?keys=${encodeURIComponent(dates)}&sort=dateAsc`)).json()
    assert.deepEqual(asc.rows.map(value=>value.key),['gacha:900000','gacha:900223','gacha:900224'])
    for(const query of ['view=cards','series=__proto__','keys=../outside','keys=gacha:1,,gacha:2','keyOrder=true','keyOrder=yes','sort=arbitrary','includeMembers=true&view=series',`keys=${Array(201).fill('gacha:1').join(',')}`])
        assert.equal((await get('/api/content/?'+query)).statusCode,400,query)
})

test('explicit dates keep equal and missing dates stable across states, search, series and pagination', async () => {
    const discovery = load('lib/content-discovery'), originalDiscovery = discovery.contentDiscoveryReader
    const isolatedDb = new Sqlite(':memory:')
    initializeContentOperationsSchema(isolatedDb)
    const date = Date.UTC(2020, 0, 1)
    const fixtureRows = Array.from({ length: 10 }, (_, index) => row('gacha', 910000 + index, `日期排序夹具 ${index}`, {
        originalStartMs: index < 4 ? date : index < 8 ? null : date + (index === 8 ? -86400000 : 86400000),
    }))
    const fixtureStore = new ContentOperationsStore(isolatedDb, { ...catalog, rows: fixtureRows, questMap: {} }, capabilities)
    const fixtureBody = extra => ({ expectedRevision: fixtureStore.revision(), catalogDigest: fixtureStore.digest,
        reason: 'Synthetic date ordering test', ...extra })
    const key = index => fixtureRows[index].key
    const groupIds = ['a', 'b', 'b', 'a', 'c', 'd', 'd', 'c', 'e', 'f'].map(value => value.repeat(24))
    const indexOf = value => fixtureRows.findIndex(row => row.key === value.key)
    const meta = value => ({ seriesKey: groupIds[indexOf(value)], seriesTitle: `系列 ${groupIds[indexOf(value)][0]}` })
    const read = async query => {
        const response = await get(`/api/content/?${query}`)
        assert.equal(response.statusCode, 200, response.body)
        return response.json()
    }
    const keysOf = values => values.map(value => value.key)
    for (const index of [2, 3, 6, 7]) {
        fixtureStore.update(key(index), fixtureBody({ actionOverrides: { visible: action(true), enter: action(true) } }), Date.now())
        if (index === 2 || index === 6) fixtureStore.setPublished(key(index), fixtureBody({ published: false }), Date.now())
    }
    for (const index of [1, 5]) historyRows.set(key(index), { key: key(index), actions: {
        visible: staticPassed, enter: staticBlocked('合成日期排序限制'),
    } })
    operations.contentOperations = () => fixtureStore
    discovery.contentDiscoveryReader = () => ({ verificationNotice: undefined, meta,
        view: value => ({ ...meta(value), highlights: [], notes: [], matchReasons: [] }),
        details: () => ({ characters: [], rewards: [], aliases: [], notes: [] }),
        match: value => ({ matched: true, score: indexOf(value) + 1, reasons: ['合成搜索命中'] }) })
    try {
        const revision = fixtureStore.revision()
        const defaultRows = (await read('')).rows
        assert.deepEqual(keysOf(defaultRows), [3, 7, 2, 6, 0, 4, 8, 9, 1, 5].map(key), 'default order still prioritises status')
        assert.deepEqual(defaultRows.filter(value => value.originalStartMs === date).map(value => value.primaryControl.status),
            ['enabled', 'disabled', 'pending', 'blocked'])
        assert.deepEqual(keysOf((await read('search=fixture')).rows), [9, 8, 7, 6, 5, 4, 3, 2, 1, 0].map(key),
            'default search still prioritises relevance')
        const recentKeys = fixtureRows.map(value => value.key).reverse().join(',')
        assert.deepEqual(keysOf((await read(`keys=${encodeURIComponent(recentKeys)}&keyOrder=true`)).rows), recentKeys.split(','))
        for (const [sort, indices, groups] of [
            ['dateAsc', [8, 0, 1, 2, 3, 9, 4, 5, 6, 7], ['e', 'a', 'b', 'f', 'c', 'd']],
            ['dateDesc', [9, 0, 1, 2, 3, 8, 4, 5, 6, 7], ['f', 'a', 'b', 'e', 'c', 'd']],
        ]) {
            const expected = indices.map(key)
            for (const prefix of ['', 'search=fixture&', `keys=${encodeURIComponent(recentKeys)}&keyOrder=true&`]) {
                const query = `${prefix}sort=${sort}`
                assert.deepEqual(keysOf((await read(query)).rows), expected, query)
                assert.deepEqual(keysOf((await read(`${query}&offset=2&limit=2`)).rows), expected.slice(2, 4), query)
            }
            const summary = await read(`search=fixture&sort=${sort}&view=series`)
            const expectedGroups = groups.map(value => value.repeat(24))
            assert.equal(summary.total, 6); assert.equal(summary.contentTotal, 10)
            assert.deepEqual(keysOf(summary.seriesGroups), expectedGroups)
            assert.equal(summary.seriesGroups.find(value => value.key === groupIds[0]).preview.key, key(0), 'equal-date series preview retains catalog order')
            assert.equal(summary.seriesGroups.find(value => value.key === groupIds[4]).preview.key, key(4), 'missing-date series preview retains catalog order')
            const page = await read(`search=fixture&sort=${sort}&view=series&offset=2&limit=2`)
            assert.deepEqual(keysOf(page.seriesGroups), expectedGroups.slice(2, 4))
            for (const [group, children] of [[groupIds[0], [0, 3]], [groupIds[4], [4, 7]]]) {
                const childQuery = `search=fixture&sort=${sort}&series=${group}`
                assert.deepEqual(keysOf((await read(childQuery)).rows), children.map(key))
                assert.deepEqual(keysOf((await read(`${childQuery}&offset=1&limit=1`)).rows), [key(children[1])])
            }
        }
        assert.equal(fixtureStore.revision(), revision, 'sorting cannot mutate operational state')
    } finally {
        operations.contentOperations = () => store
        discovery.contentDiscoveryReader = originalDiscovery
        for (const index of [1, 5]) historyRows.delete(key(index))
        isolatedDb.close()
    }
})

test('reviewed ComeBack exchange-only control toggles existing qualification without opening the draw', async () => {
    const key = 'gacha:700000'
    const beforeProgress = db.prepare('SELECT * FROM retained_progress').all()
    store.update(key, body({ actionOverrides: { exchange: action(true) } }), Date.now())
    const read = async () => (await get(`/api/content/?search=${encodeURIComponent(key)}`)).json().rows.find(row => row.key === key)
    const open = await read()
    assert.equal(open.primaryControl.kind, 'exchange')
    assert.equal(open.primaryControl.status, 'enabled')
    assert.equal(open.primaryControl.canToggle, true)
    assert.match(open.primaryControl.reason, /已有资格兑换.*不会发放新资格/)
    assert.notEqual(store.allowed(key, 'enter', Date.now()), true)
    const original = store.state(key).actionOverrides.exchange
    const review = enabled => ({ enabled, readiness: original.readiness, evidence: original.evidence, endsAtMs: original.endsAtMs })
    const closed = await patch(key, body({ actionOverrides: { exchange: review(false) } }))
    assert.equal(closed.statusCode, 200, closed.body)
    assert.equal((await read()).primaryControl.status, 'disabled')
    assert.notEqual(store.allowed(key, 'enter', Date.now()), true)
    assert.deepEqual(db.prepare('SELECT * FROM retained_progress').all(), beforeProgress)
    const reopened = await patch(key, body({ actionOverrides: { exchange: review(true) } }))
    assert.equal(reopened.statusCode, 200, reopened.body)
    assert.equal((await read()).primaryControl.status, 'enabled')
    assert.notEqual(store.allowed(key, 'enter', Date.now()), true)
})
