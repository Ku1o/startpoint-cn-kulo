'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm')
const ts = require('typescript')
const compile = file => ts.transpileModule(fs.readFileSync(path.join(__dirname, '../admin/src', file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
}).outputText
const code = compile('pages/ContentOperations.tsx'), preferencesCode = compile('pages/content-discovery-preferences.ts')
const plain = value => JSON.parse(JSON.stringify(value))

// Exercise the real page's requests and callbacks with synthetic data only.
function fixture({ route = '', failListing = false } = {}) {
    let cursor = 0, dirty = true, tree, effects = [], slots = [], guard, locationSearch = route
    let discoveryFailures = 1, auditFailures = 1, heldSave
    const requests = [], patches = [], navigation = [], timers = new Map()
    const row = { key: 'gacha:12', type: 'gacha', id: 12, name: '测试角色池', originalStartMs: null, originalEndMs: null,
        presentation: { title: '测试角色池', typeLabel: '角色扭蛋', group: 'gacha' },
        primaryControl: { kind: 'publication', enabled: false, canToggle: true, status: 'disabled', label: '已关闭', reason: '仅原有领奖或兑换资格，暂不开放新参与' },
        rightsNotice: '开启开关不会发放资格。', deadlineControl: { canEdit: true, reason: '', endsAtMs: null },
        effectiveFlags: {}, limitations: ['合成资格限制'], state: null }
    const listing = { revision: 6, catalogDigest: 'synthetic-digest', total: 1, rows: [row], groups: [{ key: 'gacha', total: 1 }],
        statusCounts: { enabled: 0, disabled: 1, pending: 0, blocked: 0 }, types: ['gacha'] }
    const hooks = {
        useRef(initial) { const i = cursor++; if (!slots[i]) slots[i] = { current: initial }; return slots[i] },
        useState(initial) { const i = cursor++; if (!slots[i]) slots[i] = { value: typeof initial === 'function' ? initial() : initial }; return [slots[i].value, value => { const next = typeof value === 'function' ? value(slots[i].value) : value; if (!Object.is(next, slots[i].value)) { slots[i].value = next; dirty = true } }] },
        useEffect(callback, deps) { const i = cursor++, old = slots[i]; if (!old || deps.some((value, index) => !Object.is(value, old.deps[index]))) { slots[i] = { deps, cleanup: old?.cleanup }; effects.push(() => { slots[i].cleanup?.(); slots[i].cleanup = callback() }) } },
    }
    const jsx = (type, props) => ({ type, props: props || {} })
    const windowFixture = { setTimeout(callback) { const key = Symbol(); timers.set(key, callback); return key }, clearTimeout: key => timers.delete(key), localStorage: { getItem: () => null, setItem() {} } }
    const preferences = { exports: {} }; vm.runInNewContext(preferencesCode, { module: preferences, exports: preferences.exports, window: windowFixture })
    const moduleValue = { exports: {} }
    class ApiError extends Error { constructor(status) { super('Synthetic failure'); this.status = status } }
    vm.runInNewContext(code, { module: moduleValue, exports: moduleValue.exports, URLSearchParams, AbortController, window: windowFixture,
        require(name) {
            if (name === 'react') return hooks
            if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'Fragment' }
            if (name === 'react-router-dom') return { useLocation: () => ({ search: locationSearch }) }
            if (name === '../lib/editGuard') return { useAdminEditGuard: value => { guard = value }, useAdminNavigate: () => value => navigation.push({ value, guard: { ...guard } }), requestAdminLeave: action => { if (!guard.dirty && !guard.pending) action() } }
            if (name === './content-discovery-preferences') return preferences.exports
            if (name === 'antd' || name === 'lucide-react') return new Proxy({}, { get: (_, key) => key === 'message' ? { success() {}, error() {}, warning() {} } : String(key) })
            if (name === '../api/client') return { ApiError,
                async apiGet(url) {
                    requests.push(url)
                    if (url.startsWith('/api/content/?')) { if (failListing) throw new ApiError(503); return listing }
                    if (url.includes('/discovery')) { if (discoveryFailures-- > 0) throw new ApiError(503); return { characters: [{ id: 1, name: '普通池内角色', relation: 'pool' }], rewards: [], aliases: [], notes: [] } }
                    if (url.includes('/audit')) { if (auditFailures-- > 0) throw new ApiError(503); return { rows: [] } }
                    return { epoch: 2, updatedAtMs: 1 }
                },
                apiPatch(url, payload) { patches.push({ url, payload }); return new Promise((resolve, reject) => { heldSave = { resolve, reject } }) },
            }
            return {}
        },
    })
    const nodes = node => Array.isArray(node) ? node.flatMap(nodes) : node && typeof node === 'object' ? [node, ...nodes(node.props?.children)] : []
    const text = node => Array.isArray(node) ? node.map(text).join('') : node && typeof node === 'object' ? text(node.props?.children) : node == null || typeof node === 'boolean' ? '' : String(node)
    const find = predicate => { const item = nodes(tree).find(predicate); assert.ok(item, 'expected rendered control'); return item }
    const byText = value => find(node => node.type === 'Button' && text(node) === value)
    async function settle() {
        for (let i = 0; i < 40; i++) {
            if (dirty) { cursor = 0; dirty = false; tree = moduleValue.exports.default() }
            const pending = effects; effects = []; pending.forEach(effect => effect())
            const callbacks = [...timers.values()]; timers.clear(); callbacks.forEach(callback => callback())
            await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
            if (!dirty && !effects.length && !timers.size) return
        }
        throw new Error('fixture did not settle')
    }
    return { exports: moduleValue.exports, requests, patches, navigation, row, settle, find, byText, nodes: () => nodes(tree), text: () => text(tree),
        guard: () => guard, route: value => { locationSearch = value; dirty = true }, failSave: () => heldSave.reject(new ApiError(409)),
        async click(value) { byText(value).props.onClick(); await settle() },
    }
}

test('history entry links apply only reviewed URL filters and local edits remain independent', async () => {
    const ui = fixture({ route: '?search=gacha%3A12&type=gacha&group=gacha' }); await ui.settle()
    let params = new URL(ui.requests.find(url => url.startsWith('/api/content/?')), 'http://fixture').searchParams
    assert.equal(params.get('group'), 'gacha'); assert.equal(params.get('type'), 'gacha'); assert.equal(params.get('search'), 'gacha:12')
    ui.find(node => node.props?.['aria-label'] === '搜索活动、角色、奖励或别名').props.onChange({ target: { value: '普通角色' } }); await ui.settle()
    params = new URL(ui.requests.at(-1), 'http://fixture').searchParams
    assert.equal(params.get('search'), '普通角色')
    ui.route('?search=gacha%3A34&type=gacha&group=gacha'); await ui.settle()
    params = new URL(ui.requests.at(-1), 'http://fixture').searchParams; assert.equal(params.get('search'), 'gacha:34')
    assert.deepEqual(plain(ui.exports.contentRouteFilters('?search=x&group=untrusted&type=members')), { search: 'x' })
    assert.equal(ui.exports.contentRouteFilters(`?search=${'x'.repeat(201)}`).search, '')
})

test('card deadline action retains drafts and registers pending operations with navigation guard', async () => {
    const ui = fixture(); await ui.settle()
    ui.find(node => node.props?.['aria-label'] === '设置测试角色池开放时间').props.onClick(); await ui.settle()
    assert.equal(ui.guard().dirty, false)
    ui.find(node => node.props?.['aria-label'] === '开放方式').props.onChange('limited'); await ui.settle()
    assert.equal(ui.guard().dirty, true)
    const modal = () => ui.find(node => node.type === 'Modal' && node.props.title === '设置开放时间')
    modal().props.onCancel(); await ui.settle(); assert.equal(modal().props.open, true, 'cancel stays in the draft until leave guard approves')
    await ui.click('历史卡池资料'); assert.equal(ui.navigation[0].value, '/content/history'); assert.equal(ui.navigation[0].guard.dirty, true)
    ui.find(node => node.props?.['aria-label'] === '截止时间').props.onChange({ target: { value: '2099-02-03T12:30' } }); await ui.settle()
    const saving = modal().props.onOk(); await ui.settle()
    assert.equal(ui.guard().pending, true); assert.equal(ui.patches.length, 1)
    assert.equal(ui.patches[0].url, '/api/content/gacha%3A12/deadline')
    assert.equal(ui.patches[0].payload.expectedRevision, 6); assert.equal(ui.patches[0].payload.catalogDigest, 'synthetic-digest')
    assert.deepEqual(Object.keys(ui.patches[0].payload).sort(), ['catalogDigest', 'endsAtMs', 'expectedRevision', 'reason'])
    ui.failSave(); await saving; await ui.settle(); assert.equal(modal().props.open, false); assert.equal(ui.guard().pending, false)
})

test('qualification restrictions remain visible and failed detail panels retry independently', async () => {
    const ui = fixture(); await ui.settle()
    assert.match(ui.text(), /仅原有领奖或兑换资格，暂不开放新参与/); assert.match(ui.text(), /不会发放资格/)
    const button = ui.nodes().find(node => node.type === 'Button' && node.props.children?.[0] === '详情 '); assert.ok(button); button.props.onClick(); await ui.settle()
    assert.match(ui.text(), /合成资格限制/)
    const relatedCalls = () => ui.requests.filter(url => url.includes('/discovery')).length
    const auditCalls = () => ui.requests.filter(url => url.includes('/audit')).length
    assert.equal(relatedCalls(), 1); assert.equal(auditCalls(), 1)
    const discoveryError = ui.find(node => node.type === 'Alert' && node.props.action?.props?.children === '重试资料')
    discoveryError.props.action.props.onClick(); await ui.settle(); assert.equal(relatedCalls(), 2); assert.equal(auditCalls(), 1)
    const auditError = ui.find(node => node.type === 'Alert' && node.props.action?.props?.children === '重试记录')
    auditError.props.action.props.onClick(); await ui.settle(); assert.equal(auditCalls(), 2)
    assert.match(ui.text(), /卡池角色/); assert.doesNotMatch(ui.text(), /UP角色/)
    assert.ok(ui.text().indexOf('开放操作') < ui.text().indexOf('关联资料'))
    assert.equal(ui.exports.contentControlLabel({ status: 'disabled', label: '已到期' }), '已到期')
})

test('failed listing shows unknown count instead of a misleading empty catalog', async () => {
    const ui = fixture({ failListing: true }); await ui.settle()
    assert.match(ui.text(), /数量暂不可用/); assert.doesNotMatch(ui.text(), /共 0 项/)
    assert.equal(ui.nodes().some(node => node.props?.className === 'ops-counts'), false)
})
