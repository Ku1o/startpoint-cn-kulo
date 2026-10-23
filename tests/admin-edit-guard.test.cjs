'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const root = path.resolve(__dirname, '..')

function compile(relative, imports, globals = {}) {
    const code = ts.transpileModule(fs.readFileSync(path.join(root, relative), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText
    const module = { exports: {} }
    vm.runInNewContext(code, { module, exports: module.exports, URL, Response, FormData, AbortController, TextDecoder, ...globals, require: name => {
        if (!(name in imports)) throw new Error(name)
        return imports[name]
    } })
    return module.exports
}

function guardFixture() {
    const effects = [], refs = [], dialogs = [], listeners = new Map(), navigations = []
    let slot = 0
    const react = {
        useRef(value) { return refs[slot++] ?? (refs[slot - 1] = { current: value }) },
        useEffect(callback) { effects.push(callback) }, useCallback: callback => callback,
    }
    const guard = compile('admin/src/lib/editGuard.tsx', {
        react, antd: { Modal: { info: config => dialogs.push({ type: 'info', config }), confirm: config => dialogs.push({ type: 'confirm', config }) } },
        'react-router-dom': { useNavigate: () => (...args) => navigations.push(args) },
    }, { window: { addEventListener: (name, callback) => listeners.set(name, callback), removeEventListener: name => listeners.delete(name) } })
    return { guard, effects, dialogs, listeners, navigations, rerender() { slot = 0 } }
}

test('edit registration survives StrictMode effect replay and is fully removed on cleanup', () => {
    const fixture = guardFixture(), { guard, effects } = fixture
    guard.useAdminEditGuard({ dirty: true, pending: false, label: '合成草稿' })
    let cleanup = effects[0]()
    assert.equal(guard.getAdminEditState().dirty, true)
    cleanup(); assert.equal(guard.getAdminEditState().dirty, false)
    cleanup = effects[0]()
    assert.equal(guard.getAdminEditState().labels.length, 1)
    cleanup(); assert.equal(guard.getAdminEditState().labels.length, 0)
})

test('navigation confirms dirty edits, blocks pending writes, and checks again at confirmation time', () => {
    const { guard, effects, dialogs } = guardFixture()
    let calls = 0
    guard.useAdminEditGuard({ dirty: true, pending: false, label: '合成草稿' })
    const cleanupDirty = effects[0]()
    guard.requestAdminLeave(() => { calls++ })
    assert.equal(calls, 0); assert.equal(dialogs[0].type, 'confirm')
    dialogs[0].config.onOk(); assert.equal(calls, 1)
    guard.requestAdminLeave(() => { calls++ })
    guard.useAdminEditGuard({ dirty: false, pending: true, label: '合成保存' })
    const cleanupPending = effects[1]()
    dialogs[1].config.onOk(); assert.equal(calls, 1)
    guard.requestAdminLeave(() => { calls++ })
    assert.equal(dialogs.at(-1).type, 'info'); assert.equal(calls, 1)
    cleanupPending(); cleanupDirty()
    guard.requestAdminLeave(() => { calls++ }); assert.equal(calls, 2)
})

test('beforeunload protects current edits and an explicit confirmed unload avoids a second prompt', () => {
    const { guard, effects, listeners } = guardFixture()
    guard.useAdminEditGuard({ dirty: true, pending: false, label: '合成草稿' }); const cleanup = effects[0]()
    guard.useAdminBeforeUnload(); const remove = effects[1]()
    let prevented = 0
    const event = { preventDefault() { prevented++ }, returnValue: undefined }
    listeners.get('beforeunload')(event)
    assert.equal(prevented, 1); assert.equal(event.returnValue, '')
    guard.allowAdminUnload(); listeners.get('beforeunload')(event)
    assert.equal(prevented, 1)
    cleanup(); remove(); assert.equal(listeners.size, 0)
})

test('guarded programmatic navigation retains route until edits are explicitly discarded', () => {
    const { guard, effects, dialogs, navigations } = guardFixture()
    guard.useAdminEditGuard({ dirty: true, pending: false, label: '合成草稿' }); const cleanup = effects[0]()
    guard.useAdminNavigate()('/accounts')
    assert.equal(navigations.length, 0)
    dialogs[0].config.onOk(); assert.equal(navigations[0][0], '/accounts')
    cleanup()
})

test('API errors preserve business JSON and suppress HTML/large or malformed error payloads', async () => {
    let response
    const api = compile('admin/src/api/client.ts', { './auth': { setLoginExpired() {} } }, { fetch: async () => response })
    response = new Response(JSON.stringify({ error: '该存档正在战斗，请稍后重试。' }), { status: 409, headers: { 'content-type': 'application/json' } })
    await assert.rejects(api.apiGet('/fixture'), error => error.message === '该存档正在战斗，请稍后重试。')
    response = new Response('<html><body>' + 'stack trace'.repeat(5000) + '</body></html>', { status: 502, headers: { 'content-type': 'text/html' } })
    await assert.rejects(api.apiGet('/fixture'), error => /HTTP 502/.test(error.message) && error.message.length < 100 && !error.message.includes('html'))
    let pulls = 0, cancelled = false
    response = new Response(new ReadableStream({ pull(controller) { pulls++; controller.enqueue(new TextEncoder().encode('x'.repeat(1024))) }, cancel() { cancelled = true } }), { status: 503, headers: { 'content-type': 'application/json' } })
    await assert.rejects(api.apiGet('/fixture'), error => error.message.length < 100 && /HTTP 503/.test(error.message))
    assert.equal(cancelled, true); assert.ok(pulls < 30)
    response = new Response('{bad-json', { status: 400, headers: { 'content-type': 'application/json' } })
    await assert.rejects(api.apiGet('/fixture'), error => /请求参数无效/.test(error.message))
})
