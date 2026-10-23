'use strict'
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm')
const ts = require('typescript')
const rulesModule = { exports: {} }
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.resolve(__dirname, '../admin/src/lib/newsFormRules.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, { module: rulesModule, exports: rulesModule.exports })
test('announcement IDs accept only positive safe integers within the client bound', () => {
    const { isNewsId, parseNewsIdInput, NEWS_ID_MAX } = rulesModule.exports
    for (const value of [1, 987000001, NEWS_ID_MAX]) assert.equal(isNewsId(value), true)
    for (const value of [0, -1, 1.5, NaN, Infinity, NEWS_ID_MAX + 1, Number.MAX_SAFE_INTEGER, '1', null, undefined]) assert.equal(isNewsId(value), false)
    for (const value of ['', null, undefined]) assert.equal(parseNewsIdInput(value), null)
    for (const value of ['1', '987000001', String(NEWS_ID_MAX)]) assert.equal(parseNewsIdInput(value), Number(value))
    for (const value of ['0', '-1', '1.5', '2147483648', 'abc', '1a', '-', '+', ' ', '1e2', '0x10', '1 2']) assert.throws(() => parseNewsIdInput(value), /整数编号/)
})
function harness() {
    const state = [], refs = [], mutations = [], effects = [], calls = [], forms = [{ setFieldsValue(value) { calls.push(['popupFields', value]) } }, { resetFields() {}, setFieldValue() {} }]
    let cursor = 0, refCursor = 0, queryData = { version: 1, popup: { enabled: false, news_id: null, mode: 'every_login', start_time: null, end_time: null }, news: [], load_error: null, source_path: 'fixture', active_popup_id: null }
    const jsx = (type, props) => ({ type, props: props || {} })
    const react = { useState(initial) { const index = cursor++; if (!(index in state)) state[index] = initial; return [state[index], value => { state[index] = typeof value === 'function' ? value(state[index]) : value }] },
        useRef(initial) { const index = refCursor++; return refs[index] || (refs[index] = { current: initial }) }, useMemo: callback => callback(), useEffect: callback => effects.push(callback) }
    let formIndex = 0
    const Form = { Item: 'FormItem', useForm: () => [forms[formIndex++ % 2]] }
    const antd = new Proxy({ Form, Typography: { Text: 'Text' }, message: { success() {}, error() { return { then(resolve) { resolve() } } } } }, { get: (target, key) => key in target ? target[key] : String(key) })
    const queryClient = { cancelQueries: async key => { calls.push(['cancel', key]) }, setQueryData(key, data) { calls.push(['setData', key]); queryData = data },
        invalidateQueries: async key => { calls.push(['invalidate', key]) } }
    const imports = { react, 'react/jsx-runtime': { jsx, jsxs: jsx }, antd, '@ant-design/icons': { PlusOutlined: 'Plus', ReloadOutlined: 'Reload' },
        '@tanstack/react-query': { useQuery(options) { calls.push(['queryOptions', options]); return { data: queryData, isLoading: false, isError: false } },
            useMutation(options) { mutations.push(options); return { isPending: false, isError: false, reset() {}, mutate() {} } }, useQueryClient: () => queryClient },
        dayjs: () => ({ format: () => '2026-10-22 00:00:00' }), '../api/client': {
            apiGet: (url, options) => { calls.push(['get', url, options]); return Promise.resolve(queryData) },
            apiPost: (url, payload) => { calls.push(['post', url, payload]); return Promise.resolve(queryData) },
            apiPatch: (url, payload) => { calls.push(['patch', url, payload]); return Promise.resolve(queryData) },
        },
        '../components/AdminPage': { AdminPage: 'AdminPage', StateCard: 'StateCard' }, '../components/NewsHtmlEditor': { __esModule: true, default: 'NewsHtmlEditor' },
        '../lib/newsHtml': { sanitizeNewsDocument: value => value }, '../lib/editGuard': { useAdminEditGuard() {} },
        '../lib/newsFormRules': rulesModule.exports }
    const filename = path.resolve(__dirname, '../admin/src/pages/News.tsx'), module = { exports: {} }
    const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { reportDiagnostics: true,
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } })
    assert.equal(code.diagnostics.filter(d => d.category === ts.DiagnosticCategory.Error).length, 0)
    vm.runInNewContext(code.outputText, { module, exports: module.exports, require(name) { if (name in imports) return imports[name]; if (name.endsWith('.css')) return {}; throw new Error(name) } }, { filename })
    return { calls, mutations, state, effects, result: () => ({ ...queryData, popup: { ...queryData.popup, mode: 'once_per_news' } }),
        render() { cursor = 0; refCursor = 0; formIndex = 0; mutations.length = 0; effects.length = 0; return module.exports.default() } }
}
const walk = node => !node || typeof node !== 'object' ? [] : [node, ...Object.values(node.props || {}).flatMap(value => Array.isArray(value) ? value.flatMap(walk) : walk(value))]

test('News GET passes Query AbortSignal', async () => {
    const h = harness(); h.render()
    const signal = new AbortController().signal
    await h.calls.find(call => call[0] === 'queryOptions')[1].queryFn({ signal })
    const request = h.calls.find(call => call[0] === 'get')
    assert.equal(request[1], '/api/news/'); assert.equal(request[2].signal, signal)
})

test('raw announcement IDs convert to a numeric JSON field only after explicit validation; empty alone requests automatic ID', async () => {
    const h = harness(); h.render(); h.calls.length = 0
    const values = { title: 'fixture', id: '123', date: null, added_time: null, html: '', published: true }
    await h.mutations[1].mutationFn({ values, targetId: null })
    assert.equal(h.calls.at(-1)[2].id, 123); assert.equal(typeof h.calls.at(-1)[2].id, 'number')
    await h.mutations[1].mutationFn({ values: { ...values, id: '' }, targetId: null })
    assert.equal(h.calls.at(-1)[2].id, undefined)
    for (const id of ['0', '-1', '1.5', '2147483648', 'abc', '1a', '-', ' ']) {
        const count = h.calls.length
        assert.throws(() => h.mutations[1].mutationFn({ values: { ...values, id }, targetId: null }), /整数编号/)
        assert.equal(h.calls.length, count)
    }
})

test('News error callbacks do not return the toast thenable to TanStack pending state', () => {
    const h = harness(); h.render()
    for (const mutation of h.mutations) assert.equal(mutation.onError(new Error('synthetic')), undefined)
})

test('all full-overview mutations cancel stale GET and replace cache without a redundant GET/invalidation', async () => {
    for (const index of [0, 1, 2, 3]) {
        const h = harness(); h.render(); h.calls.length = 0
        await h.mutations[index].onSuccess(h.result(), index === 0 ? { version: 0 } : { session: 999, version: 0, targetId: 1, knownIds: [], values: {} })
        assert.deepEqual(h.calls.map(call => call[0]), ['cancel', 'setData'])
        assert.equal(JSON.stringify(h.calls[0][1]), JSON.stringify({ queryKey: ['newsOverview'] }))
        assert.equal(JSON.stringify(h.calls[1][1]), JSON.stringify(['newsOverview']))
    }
})

test('receipt reset has no full overview and still invalidates for an actual refresh', async () => {
    const h = harness(); h.render(); h.calls.length = 0
    await h.mutations[4].onSuccess({ deleted: 2 })
    assert.deepEqual(h.calls.map(call => call[0]), ['invalidate'])
})

test('cache replacement does not clear or reinitialize a newer popup draft', async () => {
    const h = harness(), tree = h.render(); h.effects.forEach(callback => callback())
    const popup = walk(tree).find(node => node.props?.className === 'news-popup-form')
    popup.props.onValuesChange(); h.calls.length = 0
    await h.mutations[0].onSuccess(h.result(), { version: 0 })
    assert.equal(h.state[2], true, 'newer popup draft stays dirty')
    h.render(); h.effects.forEach(callback => callback())
    assert.equal(h.calls.filter(call => call[0] === 'popupFields').length, 0, 'new overview does not replace the dirty form')
})
