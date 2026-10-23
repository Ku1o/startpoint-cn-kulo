'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm')
const ts = require('typescript')
const { createRequire } = require('node:module')
const adminRequire = createRequire(path.join(__dirname, '../admin/package.json'))
const source = fs.readFileSync(path.join(__dirname, '../admin/src/pages/ContentOperations.tsx'), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } })
const preferenceSource = fs.readFileSync(path.join(__dirname, '../admin/src/pages/content-discovery-preferences.ts'), 'utf8')
const preferenceCompiled = ts.transpileModule(preferenceSource, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } })
const plain = value => JSON.parse(JSON.stringify(value))

// Run the actual page with isolated hook, network and timer fixtures. No server or database is opened.
function harness({ legacy = false, empty = false, detailsError = false, storageValue, storageThrows = false, storageQuota = false, toggleError = false, toggleWait, renamed = false, largeDetails = false, originalDates, deadline } = {}) {
    let cursor = 0, dirty = false, tree, requests = [], signals = [], patches = [], effects = [], slots = [], timers = new Map(), timerId = 0
    const storage = new Map(storageValue === undefined ? [] : [['starpoint-content-discovery:v1', storageValue]])
    const windowFixture = { localStorage: { getItem: key => { if (storageThrows) throw new Error('blocked'); return storage.get(key) ?? null }, setItem: (key, value) => { if (storageThrows || storageQuota) throw new Error('quota'); storage.set(key, value) } }, setTimeout: callback => { timers.set(++timerId, callback); return timerId }, clearTimeout: id => timers.delete(id) }
    const preferenceModule = { exports: {} }
    vm.runInNewContext(preferenceCompiled.outputText, { module: preferenceModule, exports: preferenceModule.exports, window: windowFixture })
    const row = { key: 'gacha:12', name: '测试卡池', type: 'gacha', id: 12, state: null, originalStartMs: 1704067200000, originalEndMs: 1706745600000,
        effectiveFlags: {}, presentation: { title: '测试卡池', subtitle: '包含期间限定角色', group: 'gacha', typeLabel: '角色扭蛋' },
        primaryControl: { kind: 'publication', enabled: false, canToggle: true, status: 'disabled' }, ...originalDates,
        ...(deadline ? { deadlineControl: { canEdit: true, reason: '', endsAtMs: null, ...deadline } } : {}),
        ...(!legacy ? { discovery: { seriesKey: 'test', seriesTitle: '测试系列', editionLabel: '第2期 · 复刻', highlights: [{ label: 'UP角色', names: ['阿尔克'], total: 1 }], matchReasons: ['UP角色：阿尔克'], notes: [] } } : {}) }
    if (renamed) row.presentation.title = '改名后的当前卡池'
    const listing = params => {
        assert.equal(params.get('projection'), 'cards', 'all panel lists and expanded series use the bounded card contract')
        const selected = !empty && (!params.has('keys') || params.get('keys').split(',').includes(row.key))
        const base = { revision: 12, catalogDigest: 'isolated', total: selected ? 1 : 0, rows: selected ? [row] : [], types: ['gacha', 'quest'],
        groups: [{ key: 'events', total: 2 }, { key: 'gacha', total: 3 }], typeOptions: [{ value: 'gacha', label: '角色扭蛋' }, { value: 'quest', label: '剧情活动' }],
        ...(!legacy ? { searchInfo: { query: params.get('search'), terms: (params.get('search') || '').split(' ').filter(Boolean), unfilteredTotal: 5, scopeTotal: params.get('group') === 'all' ? 5 : 2, verificationNotice: '部分检索资料待重新核验' } } : {}) }
        if (!selected) return params.get('view') === 'series' ? { ...base, view: 'series', seriesGroups: [], contentTotal: 0 } : base
        if (params.get('view') === 'series') return { ...base, view: 'series', rows: [], total: 25, contentTotal: 49, seriesGroups: [{ key: params.get('offset') === '24' ? 'bbbbbbbbbbbbbbbbbbbbbbbb' : 'aaaaaaaaaaaaaaaaaaaaaaaa', title: params.get('offset') === '24' ? '第二页同名系列' : '测试同名系列', total: 25, enabled: 9, disabled: 10, pending: 5, blocked: 1, firstStartMs: row.originalStartMs, lastStartMs: row.originalEndMs }] }
        if (params.has('series')) return { ...base, revision: 77, catalogDigest: 'child-page', total: 25, rows: [{ ...row, ...(params.get('offset') === '24' ? { key: 'gacha:13', id: 13, presentation: { ...row.presentation, title: '第25期卡池' } } : {}) }] }
        return base
    }
    const apiGet = async (url, options) => {
        requests.push(url)
        signals.push({ url, signal: options?.signal })
        if (url.startsWith('/api/content/?')) return listing(new URL(url, 'http://fixture').searchParams)
        if (url.includes('/discovery')) {
            if (detailsError) throw new Error('isolated unavailable')
            if (largeDetails) return { characters: Array.from({ length: 50 }, (_, i) => ({ id: i + 1, name: `角色${i + 1}`, relation: 'pool', ...(i === 40 ? { aliases: ['流星勇者'] } : {}) })), rewards: Array.from({ length: 35 }, (_, i) => ({ kind: 'item', id: i + 1, name: `奖励${i + 1}`, relation: 'drop' })), aliases: [], notes: [] }
            return { characters: [{ id: 1, name: '阿尔克', relation: 'up' }, { id: 2, name: '史黛拉', relation: 'exchange' }], rewards: [{ kind: 'item', id: 1, name: '星导石', relation: 'firstClear' }, { kind: 'equipment', id: 2, name: '勇者之剑', relation: 'up' }, { kind: 'equipment', id: 3, name: '勇者之盾', relation: 'pool' }], aliases: ['勇者复刻'], notes: ['根据原始资料整理'] }
        }
        if (url.startsWith('/api/content/audit')) return { rows: [] }
        return { epoch: 2, updatedAtMs: 1 }
    }
    const hooks = {
        useRef(initial) { const index = cursor++; if (!slots[index]) slots[index] = { current: initial }; return slots[index] },
        useState(initial) {
            const index = cursor++
            if (!slots[index]) slots[index] = { value: typeof initial === 'function' ? initial() : initial }
            return [slots[index].value, value => {
                const next = typeof value === 'function' ? value(slots[index].value) : value
                if (!Object.is(next, slots[index].value)) { slots[index].value = next; dirty = true }
            }]
        },
        useEffect(callback, deps) {
            const index = cursor++, old = slots[index]
            if (!old || deps.some((value, i) => !Object.is(value, old.deps[i]))) {
                slots[index] = { deps, cleanup: old?.cleanup }
                effects.push(() => { slots[index].cleanup?.(); slots[index].cleanup = callback() })
            }
        },
    }
    const jsx = (type, props) => ({ type, props: props || {} })
    const moduleValue = { exports: {} }
    vm.runInNewContext(compiled.outputText, {
        module: moduleValue, exports: moduleValue.exports, URLSearchParams, AbortController,
        window: windowFixture,
        require(name) {
            if (name === 'react') return hooks
            if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'Fragment' }
            if (name === 'antd' || name === 'lucide-react') return new Proxy({}, { get: (_, key) => key === 'message' ? { success() {}, error() {}, warning() {} } : String(key) })
            if (name === 'dayjs') return { default: adminRequire('dayjs') }
            if (name === 'react-router-dom') return { useLocation: () => ({ search: '' }) }
            if (name === '../lib/editGuard') return { useAdminNavigate: () => () => {}, useAdminEditGuard() {}, requestAdminLeave: action => action() }
            if (name === './content-discovery-preferences') return preferenceModule.exports
            if (name === '../api/client') return { apiGet, apiPatch: async (url, payload) => { patches.push({ url, payload }); if (toggleWait) await toggleWait(); if (toggleError) throw new Error('isolated rejected'); return {} }, ApiError: class extends Error {} }
            return {}
        },
    })
    const page = moduleValue.exports.default
    async function settle() {
        for (let i = 0; i < 30; i++) {
            if (!tree || dirty) { cursor = 0; dirty = false; tree = page() }
            const pending = effects; effects = []; pending.forEach(effect => effect())
            const pendingTimers = [...timers.values()]; timers.clear(); pendingTimers.forEach(callback => callback())
            await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
            if (!dirty && !effects.length && !timers.size) return
        }
        throw new Error('fixture did not settle')
    }
    function nodes(node) {
        if (Array.isArray(node)) return node.flatMap(value => nodes(value))
        if (!node || typeof node !== 'object') return []
        return [node, ...nodes(node.props?.children)]
    }
    const find = predicate => { const node = nodes(tree).find(predicate); assert.ok(node, 'expected rendered control'); return node }
    const text = node => Array.isArray(node) ? node.map(text).join('') : node && typeof node === 'object' ? text(node.props?.children) : node == null || typeof node === 'boolean' ? '' : String(node)
    return { exports: moduleValue.exports, preferences: preferenceModule.exports, row, requests, signals, patches, storage, settle, find, nodes: () => nodes(tree), text: () => text(tree), lastParams: () => new URL([...requests].reverse().find(url => url.startsWith('/api/content/?')), 'http://fixture').searchParams,
        async change(label, value) { find(node => node.props?.['aria-label'] === label).props.onChange(value); await settle() },
        async click(predicate) { find(predicate).props.onClick(); await settle() } }
}

test('changing filters aborts the obsolete request while keeping the new listing active', async () => {
    const ui = harness(); await ui.settle()
    const old = ui.signals.find(item => item.url.startsWith('/api/content/?')).signal
    assert.ok(old instanceof AbortSignal)
    assert.equal(old.aborted, false)
    await ui.change('按开放状态筛选', 'disabled')
    assert.equal(old.aborted, true)
    const current = ui.signals.filter(item => item.url.startsWith('/api/content/?')).at(-1).signal
    assert.equal(current.aborted, false)
})

test('card and compact layout changes reuse the same query without cancelling its active request', async () => {
    const ui = harness(); await ui.settle()
    const listings = () => ui.signals.filter(item => item.url.startsWith('/api/content/?'))
    const initial = listings().length, active = listings().at(-1).signal
    for (const label of ['紧凑列表', '卡片', '紧凑列表']) {
        await ui.click(node => node.type === 'Button' && node.props.children === label)
        assert.equal(listings().length, initial, 'display-only layout changes must not fetch identical data')
        assert.equal(active.aborted, false)
    }
    await ui.click(node => node.type === 'Button' && node.props.children === '刷新内容')
    assert.equal(listings().length, initial + 1, 'an explicit refresh still fetches the current query')
    assert.equal(active.aborted, true)
})

test('changing the parent series query never requests the old expanded series under the new filters', async () => {
    const changes = [
        ['category', ui => ui.click(node => node.type === 'button' && node.props.className?.startsWith('ops-group ') && JSON.stringify(node.props.children).includes('扭蛋卡池'))],
        ['status', ui => ui.change('按开放状态筛选', 'disabled')],
        ['type', ui => ui.change('按内容类型筛选', 'gacha')],
        ['search', ui => ui.change('搜索活动、角色、奖励或别名', { target: { value: '勇者' } })],
        ['sort', ui => ui.change('内容排序', 'dateAsc')],
        ['local filter', ui => ui.change('本机内容范围', 'favorites')],
        ['parent page', async ui => { ui.find(node => node.type === 'Pagination' && node.props.className === 'ops-pagination').props.onChange(2); await ui.settle() }],
    ]
    for (const [label, change] of changes) {
        const ui = harness(); await ui.settle()
        await ui.click(node => node.type === 'Button' && node.props.children === '同名系列')
        await ui.click(node => node.type === 'button' && node.props.className === 'ops-series-heading')
        const children = () => ui.signals.filter(item => item.url.startsWith('/api/content/?') && new URL(item.url, 'http://fixture').searchParams.has('series'))
        assert.equal(children().length, 1, label)
        const old = children()[0].signal
        await change(ui)
        assert.equal(children().length, 1, `${label} must close the old expansion without starting an obsolete child query`)
        assert.equal(old.aborted, true, label)
        assert.equal(ui.lastParams().has('series'), false, label)
    }
})

test('starting search clears old category filters; later explicit filters remain visible and reach API', async () => {
    const ui = harness(); await ui.settle()
    assert.equal(ui.lastParams().get('group'), 'events')
    await ui.change('按开放状态筛选', 'disabled')
    await ui.change('按内容类型筛选', 'quest')
    await ui.change('搜索活动、角色、奖励或别名', { target: { value: '阿尔克 星导石' } })
    assert.equal(ui.lastParams().get('group'), 'all')
    assert.equal(ui.lastParams().get('status'), 'all')
    assert.equal(ui.lastParams().has('type'), false)
    assert.match(ui.text(), /全部内容搜索结果/)
    assert.match(ui.text(), /全部内容命中 5 项，当前范围 5 项，筛选后 1 项/)
    assert.match(ui.text(), /阿尔克、星导石（需同时匹配）/)
    await ui.change('按开放状态筛选', 'enabled')
    await ui.change('按内容类型筛选', 'gacha')
    assert.equal(ui.lastParams().get('status'), 'enabled')
    assert.equal(ui.lastParams().get('type'), 'gacha')
    assert.match(ui.text(), /状态：已开启/)
    assert.match(ui.text(), /类型：角色扭蛋/)
    await ui.change('搜索范围', 'group')
    assert.equal(ui.lastParams().get('group'), 'events')
    assert.match(ui.text(), /范围：活动/)
    await ui.click(node => node.type === 'Button' && node.props.children === '一键清除')
    assert.equal(ui.lastParams().get('search'), '')
    assert.equal(ui.lastParams().get('status'), 'all')
    assert.equal(ui.lastParams().has('type'), false)
})

test('category navigation remains usable during browse and explicitly narrows a global search', async () => {
    const ui = harness(); await ui.settle()
    await ui.click(node => node.type === 'button' && node.props.className?.startsWith('ops-group ') && JSON.stringify(node.props.children).includes('扭蛋卡池'))
    assert.equal(ui.lastParams().get('group'), 'gacha')
    await ui.change('搜索活动、角色、奖励或别名', { target: { value: '勇者' } })
    assert.equal(ui.lastParams().get('group'), 'all')
    await ui.click(node => node.type === 'button' && node.props.className?.startsWith('ops-group ') && JSON.stringify(node.props.children).includes('任务与通行证'))
    assert.equal(ui.lastParams().get('group'), 'missions')
    assert.match(ui.text(), /范围：任务与通行证/)
})

test('card always renders original dates beside subtitle; metadata and readable details load independently', async () => {
    const ui = harness(); await ui.settle()
    assert.match(ui.text(), /包含期间限定角色/)
    assert.match(ui.text(), /原活动档期2024年1月1日 — 2024年2月1日/)
    assert.match(ui.text(), /第2期 · 复刻/)
    await ui.change('搜索活动、角色、奖励或别名', { target: { value: '阿尔克' } })
    assert.match(ui.text(), /命中原因：UP角色：阿尔克/)
    await ui.click(node => node.type === 'Button' && Array.isArray(node.props.children) && node.props.children[0] === '详情 ')
    assert.ok(ui.requests.includes('/api/content/gacha%3A12/discovery'))
    assert.match(ui.text(), /可兑换角色命中 1 \/ 共 1 项史黛拉/)
    assert.match(ui.text(), /首次通关奖励命中 1 \/ 共 1 项星导石/)
    assert.match(ui.text(), /奖励与兑换/)
    assert.match(ui.text(), /UP装备命中 1 \/ 共 1 项勇者之剑/)
    assert.match(ui.text(), /池内可获得装备命中 1 \/ 共 1 项勇者之盾/)
    assert.match(ui.text(), /别名勇者复刻/)
    assert.doesNotMatch(ui.text(), /firstClear|gacha:12/)
    assert.equal(ui.find(node => node.type === 'Alert' && node.props.className === 'ops-verification-notice').props.message, '部分检索资料待重新核验')
})

test('unknown dates and relations do not invent editions or expose relation keys; old listing fields are optional', async () => {
    const ui = harness({ legacy: true, detailsError: true }); await ui.settle()
    assert.equal(ui.exports.originalPeriod({ originalStartMs: null, originalEndMs: null }), '暂无可靠档期资料')
    assert.equal(ui.exports.discoveryRelationLabel('secret_internal_key'), '其他相关角色')
    assert.equal(ui.exports.discoveryRelationLabel('secret_internal_key', true), '其他奖励')
    assert.deepEqual(plain(ui.exports.discoveryGroups([{ name: '阿尔克', relation: 'up' }, { name: '阿尔克', relation: 'up' }])), [['UP角色', ['阿尔克']]])
    assert.doesNotMatch(ui.text(), /第2期/)
    await ui.change('搜索活动、角色、奖励或别名', { target: { value: '阿尔克' } })
    assert.match(ui.text(), /当前范围找到 1 项/)
    await ui.click(node => node.type === 'Button' && Array.isArray(node.props.children) && node.props.children[0] === '详情 ')
    assert.match(ui.find(node => node.type === 'Alert' && /暂时无法读取关联资料/.test(node.props.message)).props.message, /稍后重新打开详情/)
})

test('no-result message explains explicit restrictions and offers global search', async () => {
    const ui = harness({ empty: true }); await ui.settle()
    await ui.change('搜索活动、角色、奖励或别名', { target: { value: '阿尔克' } })
    await ui.change('搜索范围', 'group')
    const empty = ui.find(node => node.type === 'Empty')
    assert.match(empty.props.description, /其他分类或状态下存在匹配内容/)
    await ui.click(node => node.type === 'Button' && node.props.children === '搜索全部内容')
    assert.equal(ui.lastParams().get('group'), 'all')
})

test('original activity dates stay on UTC+8 calendar boundaries across browser time zones', () => {
    const ui = harness(), previous = process.env.TZ
    const row = { originalStartMs: Date.parse('2024-01-01T16:30:00Z'), originalEndMs: Date.parse('2024-02-01T15:59:00Z') }
    try {
        for (const zone of ['UTC', 'Pacific/Honolulu', 'Asia/Tokyo']) {
            process.env.TZ = zone
            assert.equal(ui.exports.originalPeriod(row), '2024年1月2日 — 2024年2月1日', zone)
        }
    } finally {
        if (previous === undefined) delete process.env.TZ
        else process.env.TZ = previous
    }
})

test('series and child pagination stay server driven with all filters and independent content CAS', async () => {
    const ui = harness(); await ui.settle()
    await ui.change('搜索活动、角色、奖励或别名', { target: { value: '勇者' } })
    await ui.change('按开放状态筛选', 'disabled')
    await ui.change('按内容类型筛选', 'gacha')
    await ui.click(node => node.type === 'Button' && node.props.children === '同名系列')
    assert.equal(ui.lastParams().get('view'), 'series')
    assert.match(ui.text(), /25 个同名系列 · 49 项内容/)
    assert.equal(ui.nodes().filter(node => node.type === 'Switch').length, 0, 'collapsed group has no collective switch')
    await ui.click(node => node.type === 'button' && node.props.className === 'ops-series-heading')
    assert.equal(ui.lastParams().get('series'), 'aaaaaaaaaaaaaaaaaaaaaaaa')
    assert.equal(ui.lastParams().has('view'), false)
    assert.equal(ui.lastParams().get('search'), '勇者')
    assert.equal(ui.lastParams().get('status'), 'disabled')
    assert.equal(ui.lastParams().get('type'), 'gacha')
    ui.find(node => node.type === 'Pagination' && node.props.className === 'ops-pagination').props.onChange(2); await ui.settle()
    assert.equal(ui.lastParams().get('offset'), '24')
    assert.equal(ui.lastParams().get('view'), 'series')
    assert.match(ui.text(), /第二页同名系列/)
    await ui.click(node => node.type === 'button' && node.props.className === 'ops-series-heading')
    assert.equal(ui.lastParams().get('series'), 'bbbbbbbbbbbbbbbbbbbbbbbb')
    assert.equal(ui.lastParams().get('offset'), '0')
    ui.find(node => node.type === 'Pagination' && node.props.className === 'ops-series-pagination').props.onChange(2); await ui.settle()
    assert.equal(ui.lastParams().get('offset'), '24')
    assert.equal(ui.lastParams().has('view'), false)
    assert.equal(ui.lastParams().get('series'), 'bbbbbbbbbbbbbbbbbbbbbbbb')
    await ui.click(node => node.type === 'Button' && Array.isArray(node.props.children) && node.props.children[0] === '详情 ')
    await ui.click(node => node.type === 'Button' && node.props.children === '开启这项内容')
    assert.equal(ui.patches.length, 0)
    await ui.find(node => node.type === 'Modal' && node.props.open && node.props.okText === '确认开启').props.onOk(); await ui.settle()
    assert.equal(ui.patches.length, 1)
    assert.equal(ui.patches[0].url, '/api/content/gacha%3A13/publication')
    assert.equal(ui.patches[0].payload.expectedRevision, 77)
    assert.equal(ui.patches[0].payload.catalogDigest, 'child-page')
    assert.deepEqual(JSON.parse(ui.storage.get('starpoint-content-discovery:v1')).recent, ['gacha:13'])
})

test('empty favorites sends explicit empty keys and never expands to the whole catalog', async () => {
    const ui = harness(); await ui.settle()
    await ui.change('本机内容范围', 'favorites')
    assert.equal(ui.lastParams().has('keys'), true)
    assert.equal(ui.lastParams().get('keys'), '')
    assert.equal(ui.nodes().filter(node => node.type === 'Switch').length, 0)
    assert.match(ui.find(node => node.type === 'Empty').props.description, /本机收藏暂时为空/)
    assert.match(ui.text(), /本机范围：本机收藏/)
    await ui.click(node => node.type === 'Button' && node.props.children === '同名系列')
    assert.equal(ui.lastParams().get('keys'), '')
    assert.equal(ui.nodes().filter(node => node.props.className === 'ops-series-heading').length, 0)
})

test('recent order, date sort and new global search have explicit non-hidden request semantics', async () => {
    const ui = harness({ storageValue: JSON.stringify({ version: 1, view: 'compact', favorites: [], recent: ['gacha:12', 'gacha:9'] }) }); await ui.settle()
    assert.equal(ui.nodes().filter(node => node.props.className?.includes('ops-compact-row')).length, 1)
    await ui.change('本机内容范围', 'recent')
    assert.equal(ui.lastParams().get('keys'), 'gacha:12,gacha:9')
    assert.equal(ui.lastParams().get('keyOrder'), 'true')
    await ui.change('内容排序', 'dateAsc')
    assert.equal(ui.lastParams().get('sort'), 'dateAsc')
    assert.equal(ui.lastParams().has('keyOrder'), false)
    await ui.change('搜索活动、角色、奖励或别名', { target: { value: '勇者' } })
    assert.equal(ui.lastParams().has('keys'), false, 'new global query clears stale local filter')
    await ui.change('本机内容范围', 'recent')
    await ui.change('内容排序', 'relevance')
    assert.equal(ui.lastParams().get('keys'), 'gacha:12,gacha:9')
    assert.equal(ui.lastParams().has('keyOrder'), false, 'keywords use matching priority')
})

test('details never count as local operations; only successful independent toggles are recorded', async () => {
    const ui = harness(); await ui.settle()
    await ui.click(node => node.type === 'Button' && Array.isArray(node.props.children) && node.props.children[0] === '详情 ')
    assert.equal(ui.storage.has('starpoint-content-discovery:v1'), false)
    await ui.change('开启测试卡池', true)
    assert.equal(ui.patches.length, 0)
    await ui.find(node => node.type === 'Modal' && node.props.open && node.props.okText === '确认开启').props.onOk(); await ui.settle()
    assert.deepEqual(JSON.parse(ui.storage.get('starpoint-content-discovery:v1')).recent, ['gacha:12'])
    const rejected = harness({ toggleError: true }); await rejected.settle()
    await rejected.change('开启测试卡池', true)
    await rejected.find(node => node.type === 'Modal' && node.props.open && node.props.okText === '确认开启').props.onOk(); await rejected.settle()
    assert.equal(rejected.patches.length, 1)
    assert.equal(rejected.storage.has('starpoint-content-discovery:v1'), false)
})

test('favorites use live stable identity after rename; unknown stored keys never become toggle targets', async () => {
    const ui = harness({ renamed: true, storageValue: JSON.stringify({ version: 1, view: 'cards', favorites: ['gacha:9999', 'gacha:12'], recent: [] }) }); await ui.settle()
    await ui.change('本机内容范围', 'favorites')
    assert.equal(ui.lastParams().get('keys'), 'gacha:9999,gacha:12')
    assert.equal(ui.nodes().filter(node => node.type === 'Switch').length, 1)
    assert.match(ui.text(), /改名后的当前卡池/)
    await ui.change('开启改名后的当前卡池', true)
    await ui.find(node => node.type === 'Modal' && node.props.open && node.props.okText === '确认开启').props.onOk(); await ui.settle()
    assert.equal(ui.patches[0].url, '/api/content/gacha%3A12/publication')
    const unknown = harness({ storageValue: JSON.stringify({ version: 1, view: 'cards', favorites: ['gacha:9999'], recent: [] }) }); await unknown.settle()
    await unknown.change('本机内容范围', 'favorites')
    assert.equal(unknown.nodes().filter(node => node.type === 'Switch').length, 0)
    assert.equal(unknown.patches.length, 0)
})

test('corrupt or unavailable browser storage safely retains current-page favorites in memory', async () => {
    for (const options of [{ storageValue: '{bad json' }, { storageThrows: true }]) {
        const ui = harness(options); await ui.settle()
        assert.match(ui.text(), /仅在当前页面保留/)
        await ui.click(node => node.type === 'Button' && node.props['aria-label'] === '收藏测试卡池')
        await ui.change('本机内容范围', 'favorites')
        assert.equal(ui.lastParams().get('keys'), 'gacha:12')
        assert.equal(ui.nodes().filter(node => node.type === 'Switch').length, 1)
        if (options.storageValue) {
            assert.doesNotMatch(ui.text(), /仅在当前页面保留/, 'normal writes recover persistent storage after corrupt saved JSON')
            assert.deepEqual(JSON.parse(ui.storage.get('starpoint-content-discovery:v1')).favorites, ['gacha:12'])
        }
    }
    const quota = harness({ storageQuota: true }); await quota.settle()
    assert.doesNotMatch(quota.text(), /仅在当前页面保留/)
    await quota.click(node => node.type === 'Button' && node.props['aria-label'] === '收藏测试卡池')
    assert.match(quota.text(), /仅在当前页面保留/)
    await quota.change('本机内容范围', 'favorites')
    assert.equal(quota.lastParams().get('keys'), 'gacha:12', 'quota failure preserves in-memory favorite')
})

test('large detail relations are locally searchable, bounded by default and expandable without losing records', async () => {
    const ui = harness({ largeDetails: true }); await ui.settle()
    await ui.change('搜索活动、角色、奖励或别名', { target: { value: '勇者' } })
    await ui.click(node => node.type === 'Button' && Array.isArray(node.props.children) && node.props.children[0] === '详情 ')
    const count = () => ui.nodes().filter(node => node.props.className === 'ops-related-item').length
    assert.equal(count(), 48, 'each relation initially shows at most 24 items')
    assert.match(ui.text(), /命中 85 \/ 共 85 条关联资料/)
    await ui.click(node => node.type === 'Button' && node.props['aria-label'] === '卡池角色展开全部')
    assert.equal(count(), 74, 'expanded relation preserves all 50 characters plus 24 rewards')
    const requestsBefore = ui.requests.length
    await ui.change('查找关联角色或奖励', { target: { value: '流星勇者' } })
    assert.equal(count(), 1)
    assert.match(ui.text(), /角色41别名：流星勇者/)
    assert.match(ui.text(), /命中 1 \/ 共 85 条关联资料/)
    assert.equal(ui.requests.length, requestsBefore, 'detail search does not alter server search or refetch listing')
    await ui.change('查找关联角色或奖励', { target: { value: '不存在的关联资料' } })
    assert.equal(count(), 0)
    assert.match(ui.find(node => node.type === 'Empty').props.description, /没有匹配的关联角色或奖励/)
    ui.find(node => node.type === 'Drawer').props.onClose(); await ui.settle()
    await ui.click(node => node.type === 'Button' && Array.isArray(node.props.children) && node.props.children[0] === '详情 ')
    assert.equal(ui.find(node => node.props['aria-label'] === '查找关联角色或奖励').props.value, '')
    assert.equal(count(), 48, 'reopening detail resets local query and expanded relations')
    const sameNames = ui.exports.discoveryDetailGroups([{ id: 1, name: '同名角色', relation: 'pool' }, { id: 2, name: '同名角色', relation: 'pool', aliases: ['另一个称号'] }], '')
    assert.equal(sameNames[0].items.length, 2, 'same visible names do not merge distinct identities')
})

test('confirmed 2011 source years are visibly unverified in cards, compact rows, detail and series spans without rewriting dates', async () => {
    const suspect = Date.parse('2011-06-15T00:00:00+08:00'), ordinary = Date.parse('2021-01-01T00:00:00+08:00')
    const first = harness()
    for (const dates of [{ originalStartMs: suspect, originalEndMs: ordinary }, { originalStartMs: ordinary, originalEndMs: suspect }]) {
        const before = plain(dates)
        assert.equal(first.exports.originalPeriodNeedsReview(dates), true)
        assert.match(first.exports.originalPeriod(dates), /^原始档期待核实（源记录：/)
        assert.match(first.exports.originalPeriod(dates), /2011年6月15日/)
        assert.match(first.exports.originalSeriesPeriod(dates.originalStartMs, dates.originalEndMs), /^原始档期跨度待核实（源记录：/)
        assert.deepEqual(plain(dates), before, 'display warning does not rewrite either source date')
    }
    assert.equal(first.exports.originalPeriodNeedsReview({ originalStartMs: ordinary, originalEndMs: ordinary }), false)
    assert.equal(first.exports.originalPeriod({ originalStartMs: ordinary, originalEndMs: ordinary }), '2021年1月1日 — 2021年1月1日')
    assert.equal(first.exports.originalSeriesPeriod(ordinary, ordinary), '原档期跨度：2021年1月1日 — 2021年1月1日')
    assert.equal(first.exports.originalPeriodNeedsReview({ originalStartMs: null, originalEndMs: null }), false)
    const ui = harness({ originalDates: { originalStartMs: suspect, originalEndMs: ordinary } }); await ui.settle()
    assert.match(ui.text(), /原始档期待核实（源记录：2011年6月15日 — 2021年1月1日）/)
    await ui.click(node => node.type === 'Button' && node.props.children === '紧凑列表')
    assert.match(ui.text(), /原始档期待核实（源记录：2011年6月15日 — 2021年1月1日）/)
    await ui.click(node => node.type === 'Button' && Array.isArray(node.props.children) && node.props.children[0] === '详情 ')
    assert.match(ui.find(node => node.type === 'dd' && node.props.className === 'ops-period-needs-review').props.children, /原始档期待核实（源记录：/)
    ui.find(node => node.type === 'Drawer').props.onClose(); await ui.settle()
    await ui.click(node => node.type === 'Button' && node.props.children === '同名系列')
    assert.match(ui.text(), /原始档期跨度待核实（源记录：2011年6月15日 — 2021年1月1日）/)
    assert.equal(ui.row.originalStartMs, suspect)
    assert.equal(ui.row.originalEndMs, ordinary)
    assert.equal(ui.patches.length, 0)
})

test('deadline input is strictly interpreted on UTC+8 and rejects malformed, impossible or past dates', () => {
    const ui = harness(), now = Date.parse('2030-01-01T00:00:00Z')
    const expected = Date.parse('2030-01-02T16:30:00Z')
    assert.equal(ui.exports.parseContentDeadline('limited', '2030-01-03T00:30', now), expected)
    assert.equal(ui.exports.deadlineInputValue(expected), '2030-01-03T00:30')
    assert.equal(ui.exports.parseContentDeadline('permanent', '', now), null)
    for (const value of ['', '2030-02-30T12:00', '2030-01-01T08:00', '2030-01-02', '2030-01-02T12:00Z'])
        assert.throws(() => ui.exports.parseContentDeadline('limited', value, now))
    assert.match(ui.exports.contentDeadlineText({ endsAtMs: expected }), /2030年1月3日.*00:30/)
    assert.equal(ui.exports.contentDeadlineText({ endsAtMs: null }), '常驻开放')
    assert.equal(ui.exports.contentDeadlineText({ canEdit: false, endsAtMs: null }), '暂不可设置', 'unreviewed or unqualified content must not appear permanent')
    assert.equal(ui.exports.contentDeadlineText({ canEdit: false, endsAtMs: expected }), '暂不可设置')
})

test('expired toggle can still edit its reviewed deadline without publishing, resetting scopes or recording a switch', async () => {
    const ui = harness({ deadline: { endsAtMs: Date.now() - 60000 } })
    ui.row.primaryControl.canToggle = false
    await ui.settle()
    await ui.click(node => node.type === 'Button' && Array.isArray(node.props.children) && node.props.children[0] === '详情 ')
    const button = ui.find(node => node.type === 'Button' && node.props.children === '设置开放时间')
    assert.equal(button.props.disabled, false)
    await ui.click(node => node === button)
    await ui.change('截止时间', { target: { value: '2035-01-02T12:30' } })
    await ui.find(node => node.type === 'Modal' && node.props.title === '设置开放时间').props.onOk(); await ui.settle()
    assert.equal(ui.patches.length, 1)
    assert.equal(ui.patches[0].url, '/api/content/gacha%3A12/deadline')
    assert.deepEqual(plain(ui.patches[0].payload), { expectedRevision: 12, catalogDigest: 'isolated', endsAtMs: Date.parse('2035-01-02T12:30:00+08:00'), reason: '管理面板调整开放时间：测试卡池' })
    assert.equal(ui.storage.size, 0, 'deadline edits do not create a recent successful-switch entry')
    assert.equal(ui.find(node => node.type === 'Modal' && node.props.title === '设置开放时间').props.open, false)
})

test('deadline form retains invalid input for correction and rejects unsupported or unreviewed content', async () => {
    const ui = harness({ deadline: {} }); await ui.settle()
    await ui.click(node => node.type === 'Button' && Array.isArray(node.props.children) && node.props.children[0] === '详情 ')
    await ui.click(node => node.type === 'Button' && node.props.children === '设置开放时间')
    await ui.change('开放方式', 'limited')
    await ui.find(node => node.type === 'Modal' && node.props.title === '设置开放时间').props.onOk(); await ui.settle()
    assert.equal(ui.patches.length, 0)
    assert.match(ui.text(), /请选择完整的截止日期和时间/)
    assert.equal(ui.find(node => node.type === 'Modal' && node.props.title === '设置开放时间').props.open, true)
    assert.throws(() => ui.exports.contentDeadlineRequest({ ...ui.row, deadlineControl: { canEdit: false } }, 12, 'isolated', null))
})

test('series deadline form uses the selected child identity and revision rather than its summary page', async () => {
    const ui = harness({ deadline: {} }); await ui.settle()
    await ui.click(node => node.type === 'Button' && node.props.children === '同名系列')
    await ui.click(node => node.type === 'button' && node.props.className === 'ops-series-heading')
    ui.find(node => node.type === 'Pagination' && node.props.className === 'ops-series-pagination').props.onChange(2); await ui.settle()
    await ui.click(node => node.type === 'Button' && Array.isArray(node.props.children) && node.props.children[0] === '详情 ')
    await ui.click(node => node.type === 'Button' && node.props.children === '设置开放时间')
    await ui.find(node => node.type === 'Modal' && node.props.title === '设置开放时间').props.onOk(); await ui.settle()
    assert.equal(ui.patches[0].url, '/api/content/gacha%3A13/deadline')
    assert.equal(ui.patches[0].payload.expectedRevision, 77)
    assert.equal(ui.patches[0].payload.catalogDigest, 'child-page')
    assert.equal(ui.patches[0].payload.endsAtMs, null)
})


test('switches in every list view require confirmation and cancellation sends no write', async () => {
    for (const view of ['cards', 'compact', 'series']) {
        const ui = harness({ storageValue: JSON.stringify({ version: 1, view, favorites: [], recent: [] }) }); await ui.settle()
        if (view === 'series') await ui.click(node => node.type === 'button' && node.props.className === 'ops-series-heading')
        await ui.change('开启测试卡池', true)
        assert.equal(ui.patches.length, 0)
        assert.equal(ui.find(node => node.type === 'Switch').props.checked, false)
        const modal = ui.find(node => node.type === 'Modal' && node.props.open && node.props.okText === '确认开启')
        assert.match(JSON.stringify(modal.props.children), /测试卡池/)
        modal.props.onCancel(); await ui.settle()
        assert.equal(ui.patches.length, 0)
        assert.equal(ui.storage.has('starpoint-content-discovery:v1') && JSON.parse(ui.storage.get('starpoint-content-discovery:v1')).recent.length > 0, false)
        assert.equal(ui.find(node => node.type === 'Modal' && node.props.okText === '确认关闭').props.open, false)
    }
})

test('confirmation captures the intended action and CAS; repeated acceptance cannot send duplicate writes', async () => {
    let release
    const ui = harness({ toggleWait: () => new Promise(resolve => { release = resolve }) }); await ui.settle()
    await ui.change('开启测试卡池', true)
    const modal = ui.find(node => node.type === 'Modal' && node.props.open && node.props.okText === '确认开启')
    // A newer listing must not silently reverse the reviewed action.
    ui.row.primaryControl.enabled = true
    const first = modal.props.onOk(), second = modal.props.onOk(); await ui.settle()
    assert.equal(ui.patches.length, 1)
    assert.deepEqual(plain(ui.patches[0].payload), { expectedRevision: 12, catalogDigest: 'isolated', reason: '管理面板开启：测试卡池', published: true })
    const pending = ui.find(node => node.type === 'Modal' && node.props.open && node.props.okText === '确认开启')
    assert.equal(pending.props.confirmLoading, true)
    assert.equal(pending.props.okButtonProps.disabled, true)
    pending.props.onCancel(); await ui.settle()
    assert.equal(ui.find(node => node.type === 'Modal' && node.props.open && node.props.okText === '确认开启').props.open, true)
    release(); await Promise.all([first, second]); await ui.settle()
    assert.equal(ui.nodes().some(node => node.type === 'Modal' && node.props.open && node.props.okText === '确认开启'), false)
})

test('detail closure is confirmed and exchange-only controls keep their reviewed payload', async () => {
    const ui = harness(); ui.row.primaryControl.enabled = true; ui.row.primaryControl.status = 'enabled'; await ui.settle()
    await ui.click(node => node.type === 'Button' && Array.isArray(node.props.children) && node.props.children[0] === '详情 ')
    await ui.click(node => node.type === 'Button' && node.props.children === '关闭这项内容')
    assert.equal(ui.patches.length, 0)
    const modal = ui.find(node => node.type === 'Modal' && node.props.open && node.props.okText === '确认关闭')
    assert.equal(modal.props.okButtonProps.danger, true)
    await modal.props.onOk(); await ui.settle()
    assert.equal(ui.patches[0].payload.published, false)
    const exchange = harness(); exchange.row.primaryControl.kind = 'exchange'
    exchange.row.state = { controlled: true, actionOverrides: { exchange: { enabled: false, readiness: 'verified', evidence: 'fixture', endsAtMs: null, questKeys: ['a'] } } }
    // Use the existing request builder as the expected exchange contract; confirmation must preserve it.
    const expected = plain(exchange.exports.contentToggleRequest(exchange.row, 12, 'isolated'))
    await exchange.settle(); await exchange.change('开启测试卡池', true)
    assert.equal(exchange.patches.length, 0)
    const confirmation = exchange.find(node => node.type === 'Modal' && node.props.open && node.props.okText === '确认开启')
    assert.match(JSON.stringify(confirmation.props.children), /仅调整奖励兑换开关/)
    await confirmation.props.onOk(); await exchange.settle()
    assert.deepEqual(plain(exchange.patches[0]), { url: expected.path, payload: expected.payload })
})
