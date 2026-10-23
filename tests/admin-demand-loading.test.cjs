const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const vm = require("node:vm")
const test = require("node:test")
const ts = require("typescript")
const admin = path.resolve(__dirname, "../admin")
const { QueryClient, QueryObserver } = require(path.join(admin, "node_modules/@tanstack/query-core"))
const dayjs = require(path.join(admin, "node_modules/dayjs"))
const tick = () => new Promise(resolve => setImmediate(resolve))

function find(tree, predicate) {
    if (Array.isArray(tree)) { for (const item of tree) { const result = find(item, predicate); if (result) return result } }
    else if (tree && typeof tree === "object") {
        if (predicate(tree)) return tree
        return find(tree.props?.children, predicate)
    }
}
function environment(payloads, client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
    const env = { payloads, client, requests: [], writeAttempts: [], mutationOptions: [], aborted: [], blocked: new Set(), pending: new Map(), states: [], refs: [], forms: [], observers: [], pid: 101 }
    const react = {
        useState(initial) { const i = env.stateCursor++; if (!(i in env.states)) env.states[i] = typeof initial === "function" ? initial() : initial
            return [env.states[i], value => { env.states[i] = typeof value === "function" ? value(env.states[i]) : value }] },
        useRef(initial) { const i = env.refCursor++; return env.refs[i] ||= { current: initial } },
        useMemo: fn => fn(), useEffect() {},
    }
    const api = { apiGet(url, { signal } = {}) {
        assert.ok(signal instanceof AbortSignal, `GET must consume cancellation: ${url}`)
        env.requests.push(url)
        if (!(url in payloads)) return Promise.reject(new Error(`Unexpected GET: ${url}`))
        if (!env.blocked.has(url)) return Promise.resolve(structuredClone(payloads[url]))
        return new Promise((resolve, reject) => {
            env.pending.set(url, () => resolve(structuredClone(payloads[url])))
            signal.addEventListener("abort", () => { env.aborted.push(url); reject(new DOMException("Aborted", "AbortError")) }, { once: true })
        })
    }, apiPost(...args) { env.writeAttempts.push(args); return Promise.resolve({ok:true}) }, apiPatch(...args) { env.writeAttempts.push(args); return Promise.resolve({ok:true}) }, apiDelete() { throw new Error("No deletes allowed") }, apiUpload() { throw new Error("No uploads allowed") } }
    const query = {
        useQueryClient: () => client,
        useQuery(options) {
            const i = env.queryCursor++
            if (!env.observers[i]) {
                const observer = new QueryObserver(client, options)
                env.observers[i] = observer
                observer.subscribe(() => {})
            } else env.observers[i].setOptions(options)
            return env.observers[i].getCurrentResult()
        },
        useMutation: options => { env.mutationOptions[env.mutationCursor++] = options; return { isPending: false, mutate() { throw new Error("No mutations allowed") }, mutateAsync() { throw new Error("No mutations allowed") } } },
    }
    const form = () => ({ values: {}, setFieldsValue(values) { Object.assign(this.values, values) }, getFieldValue(key) { return this.values[key] },
        resetFields(keys=Object.keys(this.values)) { for (const key of keys) { if (key==="number") this.values[key]=1; else delete this.values[key] } }, submit() {} })
    const antd = new Proxy({
        Form: { useForm() { const i = env.formCursor++; return [env.forms[i] ||= form()] }, useWatch: (key, target) => Array.isArray(key)&&key.length===0?target.values:target.values[key], Item: "Form.Item" },
        Typography: { Text: "Text", Title: "Title", Paragraph: "Paragraph" },
        Input: Object.assign(function Input() {}, { Search: "Input.Search", TextArea: "Input.TextArea" }),
        Space: Object.assign(function Space() {}, { Compact: "Space.Compact" }),
        message: { error() { return { then() { throw new Error("Mutation must not await toast dismissal") } } }, info() {}, success() {}, warning() {} },
        Modal: Object.assign(function Modal() {}, { confirm() {} }),
    }, { get: (target, key) => target[key] ?? String(key) })
    const loaded = {}
    function load(relative) {
        if (loaded[relative]) return loaded[relative]
        const exports = loaded[relative] = {}
        const imports = {
            react, antd, dayjs: { __esModule: true, default: dayjs },
            "react/jsx-runtime": { jsx: (type, props, key) => ({ type, props: props || {}, key }), jsxs: (type, props, key) => ({ type, props: props || {}, key }), Fragment: "Fragment" },
            "@tanstack/react-query": query,
            "@ant-design/icons": new Proxy({}, { get: (_t, key) => String(key) }),
            "react-router-dom": { useParams: () => ({ playerId: String(env.pid) }), useNavigate: () => () => {} },
            "../api/client": api, "./client": api,
            "../components/AdminPage": { AdminPage: "AdminPage", StateCard: "StateCard" },
        }
        const output = ts.transpileModule(fs.readFileSync(path.join(admin, "src", relative), "utf8"), {
            compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
        }).outputText
        vm.runInNewContext(output, { exports, AbortSignal, Set, console, require(name) {
            if (name.endsWith(".css")) return {}
            if (name === "../lib/adminFormat") return load("lib/adminFormat.ts")
            if (name === "./MailPlayerMutation") return load("pages/MailPlayerMutation.ts")
            if (name === "../api/lookups") return load("api/lookups.ts")
            if (name === "../lib/mailRules") return load("lib/mailRules.ts")
            if (name === "../lib/adminNumbers") return load("lib/adminNumbers.ts")
            if (name === "../lib/editGuard") return { useAdminEditGuard(state) { env.guardState=state }, useAdminNavigate: () => () => {} }
            if (!(name in imports)) throw new Error(`Unexpected import: ${name}`)
            return imports[name]
        } }, { filename: relative })
        return exports
    }
    env.load = load
    env.render = component => { env.stateCursor = 0; env.refCursor = 0; env.formCursor = 0; env.queryCursor = 0; env.mutationCursor = 0; return component() }
    env.stop = () => { for (const observer of env.observers) observer.destroy(); env.observers = [] }
    env.dispose = () => { env.stop(); client.clear() }
    return env
}
function playerPayloads() {
    return {
        "/api/player/101/detail?section=player": { player: { id: 101, accountId: 1, name: "Synthetic", expPool: 100 } },
        "/api/player/101/detail?section=characters": { characters: [{ code: 1, joinTime: "2026-01-01T00:00:00.000Z" }] },
        "/api/player/101/detail?section=items": { items: [{ id: 100, count: 7 }] },
        "/api/lookup/characters": { 1: { name: "Synthetic", title: "", rarity: "3", element: "fire" } },
        "/api/lookup/items": { 100: "Synthetic item" },
    }
}

test("player tabs request only base/current collection and cancel obsolete unobserved requests", async () => {
    const payloads = playerPayloads(), e = environment(payloads)
    test.after(() => e.dispose())
    e.blocked.add("/api/player/101/detail?section=characters")
    const C = e.load("pages/PlayerDetail.tsx").PlayerDetail
    e.render(C); await tick(); let tree = e.render(C)
    assert.deepEqual([...e.requests].sort(), ["/api/player/101/detail?section=characters", "/api/player/101/detail?section=player", "/api/lookup/characters"].sort())
    assert.ok(!e.requests.some(url => url.includes("questProgress")))
    const tabs = find(tree, n => n.type === "Tabs")
    assert.equal(tabs.props.items.find(t => t.key === "items").label, "道具", "unread tab must not claim count 0")
    tabs.props.onChange("items"); e.render(C); await tick(); tree = e.render(C)
    assert.ok(e.aborted.includes("/api/player/101/detail?section=characters"))
    assert.ok(e.requests.includes("/api/player/101/detail?section=items"))
    assert.ok(!e.requests.some(url => /equipment|questProgress|drawnQuests/.test(url)))
    assert.equal(find(tree, n => n.type === "Tabs").props.items.find(t => t.key === "items").label, "道具 (1)")
})

test("Mail reuses PlayerDetail character lookup and reads only the lightweight full target summary", async () => {
    const payloads = playerPayloads(), e = environment(payloads)
    const C = e.load("pages/PlayerDetail.tsx").PlayerDetail
    e.render(C); await tick(); e.render(C)
    assert.equal(e.requests.filter(url => url === "/api/lookup/characters").length, 1)
    e.stop()
    payloads["/api/server/accounts/targets"] = { accounts: [], accountCount: 0, saveCount: 0 }
    payloads["/api/mail/history"] = []
    payloads["/api/mail/daily"] = { config: { enabled: false } }
    const mail = environment(payloads, e.client)
    test.after(() => { mail.dispose(); e.dispose() })
    const Mail = mail.load("pages/Mail.tsx").default
    mail.render(Mail); mail.forms[0].values.type = 5; mail.render(Mail); await tick(); mail.render(Mail)
    assert.equal(mail.requests.filter(url => url === "/api/lookup/characters").length, 0)
    assert.ok(mail.requests.includes("/api/server/accounts/targets"))
    assert.ok(!mail.requests.includes("/api/server/accounts"))
    assert.ok(!mail.requests.includes("/api/lookup/items"))
})

test("historical catalog reads once, reuses fresh cache and explicitly refreshes without current-time or opening inference", async () => {
    const catalogUrl = "/api/server/clairvoyance/gacha?view=catalog"
    const catalog = version => ({ cdnVersion: "synthetic", baseline: "synthetic", scope: "short-up-character-gacha", catalogVersion: version,
        timeline: [
            { id: 1, name: `${version}-past`, rateUpCharacters: [], startDate: "2000-01-01", endDate: "2000-01-02" },
            { id: 2, name: `${version}-future`, rateUpCharacters: [], startDate: "2099-01-01", endDate: "2099-01-02" },
        ], searchIndex: [] })
    const payloads = { [catalogUrl]: catalog("v1") }, e = environment(payloads)
    let cached
    test.after(() => { cached?.dispose(); e.dispose() })
    const C = e.load("pages/TimeControl.tsx").default
    e.render(C); await tick(); let tree = e.render(C)
    assert.deepEqual(e.requests, [catalogUrl], "history page must not poll current clock, current pools or reload signal")
    assert.equal(e.observers.length, 1)
    assert.equal(e.observers[0].options.staleTime, 5 * 60_000)
    assert.equal(e.observers[0].options.refetchInterval, undefined)
    assert.equal(e.mutationOptions.length, 0, "history page has no reload or date mutation")
    const table = find(tree, n => n.type === "Table")
    assert.equal(table.props.dataSource.length, 2, "past and future rows remain historical reference entries")
    assert.ok(!table.props.columns.some(column => /当前|开放|生效/.test(column.title)))
    const period = table.props.columns.find(column => column.title === "原始档期")
    assert.equal(period.render(null, table.props.dataSource[0]), "2000-01-01 - 2000-01-02")
    assert.equal(period.render(null, table.props.dataSource[1]), "2099-01-01 - 2099-01-02")
    e.stop()
    cached = environment(payloads, e.client)
    const Cached = cached.load("pages/TimeControl.tsx").default
    cached.render(Cached); await tick(); tree = cached.render(Cached)
    assert.deepEqual(cached.requests, [], "fresh catalog cache is reused on a later visit")
    assert.equal(find(tree, n => n.type === "Table").props.dataSource[0].name, "v1-past")
    payloads[catalogUrl] = catalog("v2")
    const refresh = find(tree.props.actions, n => n.props.children === "刷新资料")
    assert.ok(refresh, "explicit catalog refresh remains reachable")
    refresh.props.onClick(); await tick(); tree = cached.render(Cached)
    assert.deepEqual(cached.requests, [catalogUrl])
    assert.equal(find(tree, n => n.type === "Table").props.dataSource[0].name, "v2-past")
    assert.equal(cached.writeAttempts.length, 0)
})

test("time search retains all 433 entries, paginates beyond twenty and resets after new/empty/unmatched input", async () => {
    const payloads = {
        "/api/server/clairvoyance/gacha?view=catalog":{catalogVersion:"search-fixture",timeline:Array.from({length:413},(_,i)=>({id:i+1,name:`卡池${i+1}`})),
            searchIndex:Array.from({length:433},(_,i)=>({characterId:i+1,name:`合成角色${String(i+1).padStart(4,"0")}`,title:"",gachas:[]}))},
    }
    const e=environment(payloads);test.after(()=>e.dispose());const C=e.load("pages/TimeControl.tsx").default
    e.render(C);await tick();e.render(C);await tick();let tree=e.render(C)
    const input=()=>find(tree,n=>n.props["aria-label"]==="搜索 UP 角色")
    input().props.onChange({target:{value:"合成"}});tree=e.render(C)
    let pagination=find(tree,n=>n.type==="Pagination")
    assert.equal(pagination.props.total,433)
    assert.equal(find(tree,n=>n.type==="Table").props.dataSource.length,413)
    pagination.props.onChange(2);tree=e.render(C)
    assert.ok(find(tree,n=>n.props.children==="合成角色0021"))
    assert.ok(!find(tree,n=>n.props.children==="合成角色0001"))
    input().props.onChange({target:{value:"合成角色0433"}});tree=e.render(C)
    pagination=find(tree,n=>n.type==="Pagination");assert.equal(pagination.props.current,1);assert.equal(pagination.props.total,1)
    assert.ok(find(tree,n=>n.props.children==="合成角色0433"))
    input().props.onChange({target:{value:"不存在"}});tree=e.render(C)
    assert.ok(find(tree,n=>typeof n.props.description==="string"&&n.props.description.startsWith("没有匹配的 UP 角色")))
    input().props.onChange({target:{value:""}});tree=e.render(C)
    assert.equal(find(tree,n=>n.type==="Card"&&n.props.title==="按 UP 角色查找").props.extra.props.children.join(""),"433 位角色")
    assert.deepEqual(e.requests,["/api/server/clairvoyance/gacha?view=catalog"])
})

test("player number boundaries reject malformed edits before API calls and preserve accepted zero/null/time-offset range", async () => {
    const e=environment(playerPayloads());test.after(()=>e.dispose());const C=e.load("pages/PlayerDetail.tsx").PlayerDetail
    e.render(C);await tick();let tree=e.render(C)
    const number=e.load("lib/adminNumbers.ts")
    assert.equal(number.playerNumberError("timeOffset",31_536_000_000_000),null)
    assert.equal(number.playerNumberError("timeOffset",-31_536_000_000_000),null)
    assert.ok(number.playerNumberError("timeOffset",31_536_000_000_001))
    assert.equal(number.playerNumberError("tutorialStep",null),null)
    assert.ok(number.playerNumberError("expPool",null))
    for(const value of [1.5,NaN,Infinity,-1,2147483648,null]) {
        await assert.rejects(Promise.resolve().then(()=>e.mutationOptions[0].mutationFn({field:"expPool",value})))
    }
    assert.equal(e.writeAttempts.length,0)
    const field=find(tree,n=>n.key==="expPool")
    find(field,n=>typeof n.props.onChange==="function").props.onChange(1.5);tree=e.render(C)
    assert.equal(find(find(tree,n=>n.key==="expPool"),n=>typeof n.props.onClick==="function").props.disabled,true)
    await e.mutationOptions[0].mutationFn({field:"expPool",value:0})
    assert.equal(e.writeAttempts[0][1].value,0)
    await assert.rejects(Promise.resolve().then(()=>e.mutationOptions[3].mutationFn({id:100,count:1.5})))
    assert.equal(e.writeAttempts.length,1)
    await e.mutationOptions[3].mutationFn({id:100,count:0})
    assert.equal(e.writeAttempts[1][1].count,0)
})

test("mail preview and daily save reject fractional/out-of-range values before requests while fixed attachment rules remain", async () => {
    const payloads={
        "/api/server/accounts/targets":{accounts:[{id:1,viewerId:"synthetic",note:null,bindings:[],saveCount:1,players:[{id:101,name:"Synthetic",comment:""}]}]},
        "/api/mail/history":[], "/api/mail/daily":{config:{enabled:false,amount:100,sendHour:5,sendMinute:0,subject:"Synthetic",description:""}},
    }
    const e=environment(payloads);test.after(()=>e.dispose());const module=e.load("pages/Mail.tsx"),C=module.default
    e.render(C);await tick();let tree=e.render(C)
    const form=find(tree,n=>n.props.form===e.forms[0])
    for(const number of [1.5,NaN,Infinity,0,-1,2147483648]) {
        form.props.onFinish({targetMode:"all",type:4,number});assert.equal(e.states[2],null)
    }
    assert.equal(e.writeAttempts.length,0)
    assert.ok(module.mailInputError({type:5,type_id:1,number:2}))
    assert.ok(module.mailInputError({type:1,type_id:100,number:100}))
    assert.equal(module.mailInputError({type:1,type_id:100,number:99}),null)
    assert.equal(module.mailInputError({type:13,type_id:1,number:0}),null)
    const daily={...payloads["/api/mail/daily"].config}
    for(const override of [{amount:1.5},{amount:2147483648},{sendHour:24},{sendMinute:-1}]) {
        await assert.rejects(Promise.resolve().then(()=>e.mutationOptions[0].mutationFn({values:{...daily,...override},revision:0})))
    }
    assert.equal(e.writeAttempts.length,0)
})

test("quantity-only and recipient-only drafts register dirty; successful mail keeps its retained target as the clean baseline", async () => {
    const p=environment(playerPayloads());test.after(()=>p.dispose());const Player=p.load("pages/PlayerDetail.tsx").PlayerDetail
    p.render(Player);await tick();let tree=p.render(Player)
    find(tree,n=>n.type==="Tabs").props.onChange("items");p.render(Player);await tick();tree=p.render(Player)
    assert.equal(p.guardState.dirty,false)
    const itemQuantity=()=>find(find(tree,n=>n.type==="Tabs").props.items.find(tab=>tab.key==="items").children,n=>n.props["aria-label"]==="设置道具数量")
    itemQuantity().props.onChange(5);tree=p.render(Player)
    assert.equal(p.guardState.dirty,true,"quantity without an item id is still an edited draft")
    itemQuantity().props.onChange(1);p.render(Player);assert.equal(p.guardState.dirty,false)
    const payloads={"/api/server/accounts/targets":{accounts:[]},"/api/mail/history":[],"/api/mail/daily":{config:{enabled:false}}}
    const m=environment(payloads);test.after(()=>m.dispose());const Mail=m.load("pages/Mail.tsx").default
    m.render(Mail);await tick();m.forms[0].setFieldsValue({number:1,targetMode:"all"});m.render(Mail)
    assert.equal(m.guardState.dirty,false)
    m.forms[0].setFieldsValue({number:2});m.render(Mail);assert.equal(m.guardState.dirty,true)
    m.forms[0].setFieldsValue({number:1,targetMode:"account",accountId:1});m.render(Mail);assert.equal(m.guardState.dirty,true)
    m.forms[0].setFieldsValue({type:4,number:1});m.render(Mail)
    await m.mutationOptions[2].onSuccess({sent:1},{values:{targetMode:"account",accountId:1,type:4,number:1}})
    m.render(Mail)
    assert.equal(m.forms[0].values.accountId,1)
    assert.equal(m.forms[0].values.targetMode,"account")
    assert.equal(m.guardState.dirty,false,"successful send resets attachment draft but retains target without a false leave warning")
})

test("Mail, PlayerDetail and DataMaintenance error callbacks return void even when error toast is thenable", async () => {
    const payloads={...playerPayloads(),
        "/api/server/accounts/targets":{accounts:[]},"/api/mail/history":[],"/api/mail/daily":{config:{enabled:false}},
        "/api/server/defaultSave":{exists:false},
    }
    for(const [file,exportName] of [["pages/Mail.tsx","default"],["pages/PlayerDetail.tsx","PlayerDetail"],["pages/DataMaintenance.tsx","default"]]) {
        const e=environment(payloads);test.after(()=>e.dispose());const C=e.load(file)[exportName]
        e.render(C);await tick();e.render(C)
        assert.ok(e.mutationOptions.length>0)
        for(const [index,options] of e.mutationOptions.entries()) {
            assert.equal(typeof options.onError,"function",`${file} mutation ${index} must provide error feedback`)
            assert.equal(options.onError(new Error("synthetic failure")),undefined,`${file} mutation ${index} must settle without waiting for toast`)
        }
        assert.equal(e.writeAttempts.length,0)
    }
})
