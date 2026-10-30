'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto')
const ts = require('typescript'), Sqlite = require('better-sqlite3')
const producer = require('../tools/content-release-capture.cjs')
const original = require.extensions['.ts']
require.extensions['.ts'] = (mod, filename) => {
  const result = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true }, reportDiagnostics: true })
  assert.equal(result.diagnostics.filter(item => item.category === ts.DiagnosticCategory.Error).length, 0)
  mod._compile(result.outputText, filename)
}
let release, guards, Store
try {
  release = require('../src/lib/content-release-supplement.ts')
  guards = require('../src/lib/deployment-maintenance-guard.ts')
  Store = require('../src/lib/content-operations-store.ts')
} finally { if (original) require.extensions['.ts'] = original; else delete require.extensions['.ts'] }
const { CONTENT_RELEASE_PARENT: parent, CONTENT_RELEASE_PRODUCTS: products, CONTENT_RELEASE_QUESTS: quests,
  CONTENT_RELEASE_GACHA: gacha,
  } = release
const now = Date.parse('2026-10-30T00:00:00Z'), sha = value => crypto.createHash('sha256').update(value).digest('hex')
const canonical = value => Array.isArray(value) ? `[${value.map(canonical).join(',')}]`
  : value && typeof value === 'object' ? `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`
    : JSON.stringify(value)
const evidence = sha('reviewed synthetic source contract'), clone = value => JSON.parse(JSON.stringify(value))
const releaseSource = { assetVersion: '1.4.350', manifestSha256: sha('actual synthetic350 manifest bytes') }
const legacyKeys = ['gacha:42']
const build = (s, e, r) => release.buildContentReleasePlanSync(s, e, r, releaseSource, legacyKeys)
const apply = (s, p, d, c, n, capture) => release.applyContentReleaseSupplementSync(s, p, d, c, n, releaseSource, legacyKeys, capture)
const inspect = s => release.inspectContentReleaseSupplementSync(s, releaseSource, legacyKeys)
const validate = (s, p, d) => release.validateContentReleasePlanSync(s, p, d, releaseSource, legacyKeys)
const keys = [parent, ...products, gacha, 'gacha:42']
function catalog(version = '1.4.135', definition = 'new') {
  return { schemaVersion: 1, source: { assetVersion: version, manifestSha256: sha(version) }, baselineTimeMs: 1,
    baselineEvidence: 'synthetic', missing: [], resources: {}, questMap: Object.fromEntries(quests.map(key => [key, parent])),
    rows: keys.map(key => ({ key, type: key.split(':')[0], id: Number(key.split(':')[1]), name: key,
      source: 'synthetic', originalStartMs: 1, originalEndMs: null, originalExchangeEndMs: null,
      windowCandidate: true, browseCandidate: true, serverDefinitionDigest: sha(definition + key),
      ...(key.startsWith('event_item_shop:') ? { parentKey: parent } : {}) })) }
}
function store(db, data = catalog()) {
  return new Store.ContentOperationsStore(db, data, row => row.type === 'event_item_shop' ? ['visible', 'exchange'] : ['visible', 'enter', 'exchange'],
    row => ({ digest: sha('native:' + row.key), matchesCatalog: true }))
}
function fixture(t, legacyCatalog = catalog()) {
  const base = path.resolve(process.env.CONTENT_RELEASE_TEST_ROOT || path.join(__dirname, '../tmp/content-release-tests'))
  fs.mkdirSync(base, { recursive: true })
  const directory = fs.mkdtempSync(path.join(base, 'fixture-')), database = path.join(directory, 'synthetic.db')
  const db = new Sqlite(database)
  t.after(() => { if (db.open) db.close() })
  Store.initializeContentOperationsSchema(db)
  for (const name of ['content_operations_initialization', 'content_operations_deployment', 'content_box_exchange_deployment']) {
    db.exec(`CREATE TABLE ${name}(id INTEGER PRIMARY KEY,plan_digest TEXT,catalog_digest TEXT)`)
    db.prepare(`INSERT INTO ${name} VALUES(1,?,?)`).run(sha(name), sha('old catalog'))
  }
  db.exec("CREATE TABLE players(id INTEGER PRIMARY KEY,save TEXT); INSERT INTO players VALUES(1,'inventory,claim,stock,progress'); CREATE TABLE server_clock_state(id INTEGER PRIMARY KEY,value TEXT); INSERT INTO server_clock_state VALUES(1,'real,legacyOffset=-5123'); CREATE TABLE town(id INTEGER,value TEXT); INSERT INTO town VALUES(1,'selected theme')")
  patch(store(db, legacyCatalog), 'gacha:42', { visible: false })
  return { db, directory, database, store: store(db), backups: 0 }
}
function patch(s, key, values, extra = {}) {
  return s.update(key, { expectedRevision: s.revision(), catalogDigest: s.digest, reason: 'synthetic reviewed decision',
    actionOverrides: Object.fromEntries(Object.entries(values).map(([action, enabled]) => [action,
      { enabled, endsAtMs: null, readiness: 'verified', evidence: 'synthetic exact action', ...extra,
        ...(action === 'enter' && key === parent ? { questKeys: quests } : {}) }])) }, now - 100000)
}
async function maintain(f, callback) {
  const fingerprint = guards.getDeploymentDatabaseFingerprintSync(f.db)
  const backup = path.join(f.directory, `backup-${++f.backups}.db`)
  await f.db.backup(backup)
  return guards.withDeploymentMaintenanceTransactionSync(f.db, { kind: 'approved-stopped-database',
    databasePath: f.database, backupPath: backup, expectedDatabaseFingerprint: fingerprint,
    expectedBackupSha256: sha(fs.readFileSync(backup)) }, callback)
}
function sourceFixture(directory, data) {
  fs.mkdirSync(path.join(directory, 'src/lib'), { recursive: true }); fs.mkdirSync(path.join(directory, 'assets'), { recursive: true })
  const write = (name, value) => fs.writeFileSync(path.join(directory, name), typeof value === 'string' ? value : JSON.stringify(value))
  write('assets/content_catalog.json', data)
  write('src/lib/content-operations-store.ts', fs.readFileSync(path.join(__dirname, '../src/lib/content-operations-store.ts'), 'utf8'))
  write('src/lib/content-july-reference.ts', 'export function isFixedJulyCandidate() { return false }')
  write('src/lib/content-operations.ts', `import data from '../../assets/content_catalog.json'; import {createHash} from 'node:crypto'; import {ContentOperationsStore} from './content-operations-store';
    export function createContentOperationsStore(db) { return new ContentOperationsStore(db,data,row=>row.type==='event_item_shop'?['visible','exchange']:['visible','enter','exchange'],row=>({digest:createHash('sha256').update('native:'+row.key).digest('hex'),matchesCatalog:true})) }`)
  // Deliberately incomplete raw evidence: the fixed producer must ALSO call
  // the actual shop and quest/reward accessors, including rare reward closure.
  write('src/lib/content-definition-evidence.ts', `export function captureExactDefinition(row) { return row.type==='advent_event'||row.type==='event_item_shop'?{dependencies:{rawDefinition:'unchanged'},loaders:{}}:null }`)
  write('src/lib/content-quest-rules.ts', 'export function applyContentQuestRules(category,id,raw) { return raw }')
  write('src/lib/gacha-rules.ts', 'export const GACHA_PAYMENT_TYPES={FREE_VMONEY:1,VMONEY:2,TICKET:3,CAMPAIGN:4}; export const GACHA_EXEC_TYPES={single:1,ten:2}; export function isGachaExecAllowed(g,p,e) { return g.payments.includes(p)&&[1,2].includes(e) }')
  write('assets/actual_shop.json', Object.fromEntries(products.map(key => [key.split(':')[1], { costs: [{ id: 1, amount: 4 }], rewards: [{ type: 0, id: 2, count: 1 }], stock: 99 }])))
  write('assets/actual_quests.json', Object.fromEntries(quests.map(key => [key, { clearReward: { item: 3, count: 2 }, scoreRewardGroup: [{ type: 1, id: 7 }] }])))
  write('assets/actual_rare.json', { 7: [{ type: 0, id: 9, count: 1 }] })
  write('assets/actual_gacha.json', { 42: { id: 42, price: 150, payments: [1, 2], contents: [1, 2] }, 990005: { id: 990005, price: 1, payments: [3], contents: [3] } })
  write('assets/actual_campaign.json', { 42: 70 })
  write('src/lib/assets.ts', `import shops from '../../assets/actual_shop.json'; import quests from '../../assets/actual_quests.json'; import rare from '../../assets/actual_rare.json'; import gachas from '../../assets/actual_gacha.json'; import campaigns from '../../assets/actual_campaign.json'; import {applyContentQuestRules} from './content-quest-rules';
    export function getShopItemSync(t,id) { return shops[String(id)]??null }
    export function getGachaSync(id) { return gachas[String(id)]??null }
    export function getGachaCampaignIdSync(id) { return campaigns[String(id)]??null }
    export function getQuestFromCategorySync(c,id) { return applyContentQuestRules(c,id,quests[c+':'+id]) }
    export function getRareScoreRewardGroup(id) { return rare[String(id)]??null }`)
}
function actualCapture(f, previousCatalog, currentCatalog = f.store.catalog) {
  const previousSource = path.join(f.directory, 'previous-source'), currentSource = path.join(f.directory, 'current-source')
  sourceFixture(previousSource, previousCatalog); sourceFixture(currentSource, currentCatalog)
  return producer.createReleaseCaptureSession({ previousSource, currentSource })
}
function resign(plan) { const { digest, ...body } = plan; return { ...body, digest: sha(canonical(body)) } }

test('350 plan creates exactly 31 products, ten quest scopes and the pool without new pool exchange', async t => {
  const f = fixture(t), plan = build(f.store, evidence), before = guards.getDeploymentDatabaseFingerprintSync(f.db)
  assert.equal(plan.createKeys.length, 33)
  assert.equal(plan.products.length, 31); assert.equal(plan.questKeys.length, 10)
  assert(!plan.products.includes('event_item_shop:9730002'))
  assert(!plan.createKeys.includes('event_item_shop:9700130'))
  assert.equal(guards.getDeploymentDatabaseFingerprintSync(f.db), before, 'preview is read-only')
  const result = await maintain(f, context => apply(f.store, plan, plan.digest, context, now))
  assert.equal(result.applied, true); assert.equal(result.revision, 34)
  assert.equal(plan.source.assetVersion, '1.4.350')
  assert.equal(f.store.catalog.source.assetVersion, '1.4.135', 'original catalog export is distinct from the release chain')
  assert.equal(f.store.allowed(gacha, 'visible', now), true)
  assert.equal(f.store.allowed(gacha, 'enter', now), true)
  assert.equal(f.store.allowed(gacha, 'exchange', now), false)
  for (const key of products) {
    const state = f.store.state(key)
    assert(!Object.hasOwn(state, 'published'))
    for (const action of ['visible', 'exchange']) assert.equal(f.store.allowed(key, action, now), true)
    assert.equal(f.store.allowed(key, 'enter', now), null)
    assert.equal(state.actionOverrides.claim, undefined)
  }
  for (const key of quests) assert.equal(f.store.scopedAllowed(parent, 'quest', key, 'enter', now), true)
  assert.equal(f.store.scopedAllowed(parent, 'quest', '7:300097006', 'enter', now), false)
  assert.equal(f.db.prepare('SELECT save FROM players').get().save, 'inventory,claim,stock,progress')
  assert.equal(f.db.prepare('SELECT value FROM server_clock_state').get().value, 'real,legacyOffset=-5123')
  assert.equal(inspect(f.store).ready, true)
  assert.throws(() => build(f.store, evidence), /已经应用/)
})

test('existing closed parent, product, scopes and finite deadlines win; later closes survive repeats', async t => {
  const f = fixture(t)
  patch(f.store, parent, { visible: true, enter: true, exchange: true }, { endsAtMs: now + 10000 })
  f.store.setPublished(parent, { published: false, expectedRevision: f.store.revision(), catalogDigest: f.store.digest, reason: 'manual close' }, now)
  patch(f.store, products[0], { visible: false, exchange: false }, { endsAtMs: now + 10000 })
  patch(f.store, gacha, { visible: false, enter: false, exchange: true }, { endsAtMs: now + 10000 })
  const parentBefore = clone(f.store.state(parent)), productBefore = clone(f.store.state(products[0]))
  const plan = build(f.store, evidence)
  const poolBefore = clone(f.store.state(gacha))
  assert.deepEqual(plan.preservedKeys, [parent, products[0], gacha])
  assert.equal(plan.preservedControls.find(row => row.key === gacha).state.actionOverrides.enter.enabled, false)
  await maintain(f, context => apply(f.store, plan, plan.digest, context, now))
  assert.deepEqual(f.store.state(parent), parentBefore)
  assert.deepEqual(f.store.state(products[0]), productBefore)
  assert.deepEqual(f.store.state(gacha), poolBefore)
  patch(f.store, products[1], { visible: false, exchange: false })
  f.db.prepare('UPDATE players SET save=?').run('new progress after release')
  const fingerprint = guards.getDeploymentDatabaseFingerprintSync(f.db), revision = f.store.revision()
  const result = await maintain(f, context => apply(f.store, plan, plan.digest, context, now + 20000))
  assert.equal(result.applied, false); assert.equal(f.store.revision(), revision)
  assert.equal(guards.getDeploymentDatabaseFingerprintSync(f.db), fingerprint)
  assert.equal(f.store.allowed(products[1], 'visible', now), false)
  assert.equal(inspect(f.store).ready, true)
})

test('identity-only rebinding preserves expired reviews, manual closure, instances and all other fields', async t => {
  const f = fixture(t, catalog('1.4.349', 'old')), old = store(f.db, catalog('1.4.349', 'old')), legacy = 'gacha:42'
  patch(old, legacy, { visible: true, enter: true, exchange: false }, { endsAtMs: now - 1000 })
  old.setPublished(legacy, { published: false, expectedRevision: old.revision(), catalogDigest: old.digest, reason: 'manual old close' }, now - 50000)
  const before = clone(old.state(legacy)), review = actualCapture(f, old.catalog)
  assert.throws(() => build(f.store, evidence), /固定实际访问器/)
  const plan = build(f.store, evidence, review)
  assert.equal(plan.bindings.length, 1)
  await maintain(f, context => apply(f.store, plan, plan.digest, context, now, review))
  const after = clone(f.store.state(legacy))
  const semantic = value => { delete value.revision; delete value.catalogDigest; delete value.contentDigest
    for (const action of Object.values(value.actionOverrides || {})) { delete action.catalogDigest; delete action.contentDigest }
    return value }
  assert.deepEqual(semantic(after), semantic(before))
  assert.equal(f.store.allowed(legacy, 'visible', now), false)
  assert.equal(inspect(f.store).ready, true)
})

test('declaration JSON, changed actual gacha rules, stale source and forbidden additions are rejected', t => {
  const f = fixture(t, catalog('1.4.349', 'old')), old = store(f.db, catalog('1.4.349', 'old')), legacy = 'gacha:42'
  patch(old, legacy, { visible: false })
  const review = actualCapture(f, old.catalog), declared = review.capture([legacy])
  assert.throws(() => build(f.store, evidence, declared), /声明JSON/)
  const file = path.join(review.currentSourceRoot, 'assets/actual_gacha.json'), data = JSON.parse(fs.readFileSync(file, 'utf8'))
  data[42].price++; fs.writeFileSync(file, JSON.stringify(data))
  assert.throws(() => build(f.store, evidence, review), /业务字段/)
  data[42].price--; fs.writeFileSync(file, JSON.stringify(data))
  const plan = build(f.store, evidence, review), broadened = clone(plan)
  broadened.products.push('event_item_shop:9730002')
  const forged = resign(broadened)
  assert.throws(() => validate(f.store, forged, forged.digest), /精确范围/)
  assert.throws(() => release.buildContentReleasePlanSync(f.store, evidence, review,
    { assetVersion: '1.4.348', manifestSha256: sha('old manifest') }, legacyKeys), /350/)
  const badScope = store(f.db); badScope.questMembers.get(parent).add('7:300097006')
  assert.throws(() => build(badScope, evidence, review), /关卡范围/)
})

test('full failure injection restores every revision, audit and receipt; changed targets require a new preview', async t => {
  const f = fixture(t), plan = build(f.store, evidence), before = guards.getDeploymentDatabaseFingerprintSync(f.db)
  const injected = new Error('synthetic failure after every write')
  await assert.rejects(maintain(f, context => { apply(f.store, plan, plan.digest, context, now); throw injected }), error => error === injected)
  assert.equal(guards.getDeploymentDatabaseFingerprintSync(f.db), before)
  assert.equal(f.store.revision(), 1)
  assert.equal(f.db.prepare("SELECT 1 FROM sqlite_master WHERE name='content_release_supplements'").get(), undefined)
  f.db.prepare('UPDATE players SET save=?').run('concurrent new progress')
  const changed = guards.getDeploymentDatabaseFingerprintSync(f.db)
  await assert.rejects(maintain(f, context => apply(f.store, plan, plan.digest, context, now)), /目标数据已变化/)
  assert.equal(guards.getDeploymentDatabaseFingerprintSync(f.db), changed)
  assert.throws(() => apply(f.store, plan, plan.digest, { kind: 'deployment-maintenance-transaction' }, now), /Active maintenance/)
})

test('CLI supplementary envelope binds explicit target, compiled module and reviewed digest', t => {
  const f = fixture(t), plan = build(f.store, evidence)
  const cli = require('../scripts/time-content-deployment.cjs'), output = path.join(f.directory, 'plan.json')
  const root = path.join(f.directory, 'project'), modulePath = path.join(root, 'out/lib/content-release-supplement.js')
  fs.mkdirSync(path.dirname(modulePath), { recursive: true }); fs.writeFileSync(modulePath, '// synthetic compiled module identity')
  const envelope = { format: 1, kind: 'reviewed-content-release-supplement', targetDatabase: f.database,
    captureProducerSha256: producer.PRODUCER_SHA256,
    sourceModuleSha256: sha(fs.readFileSync(modulePath)), plan }
  fs.writeFileSync(output, JSON.stringify(envelope))
  assert.equal(cli.loadSupplement({ supplement: output, planDigest: plan.digest }, { root, database: f.database }).digest, plan.digest)
  assert.throws(() => cli.loadSupplement({ supplement: output }, { root, database: f.database }), /plan-digest/)
  assert.throws(() => cli.loadSupplement({ supplement: output, planDigest: plan.digest }, { root, database: path.join(f.directory, 'other.db') }), /不匹配/)
  fs.appendFileSync(modulePath, '\n// changed source')
  assert.throws(() => cli.loadSupplement({ supplement: output, planDigest: plan.digest }, { root, database: f.database }), /不匹配/)
  assert.equal(guards.getDeploymentDatabaseFingerprintSync(f.db), plan.databaseFingerprint)
})

test('a valid old marker cannot hide missing legacy controls before or after the supplement', async t => {
  const f = fixture(t), plan = build(f.store, evidence)
  f.db.prepare('DELETE FROM content_operations_state WHERE content_key=?').run('gacha:42')
  assert.throws(() => build(f.store, evidence), /必需控制项缺失/)
  await assert.rejects(maintain(f, context => apply(f.store, plan, plan.digest, context, now)), /目标数据已变化/)
  assert.equal(f.db.prepare("SELECT 1 FROM sqlite_master WHERE name='content_release_supplements'").get(), undefined)
  const complete = fixture(t), next = build(complete.store, evidence)
  await maintain(complete, context => apply(complete.store, next, next.digest, context, now))
  complete.db.prepare('DELETE FROM content_operations_state WHERE content_key=?').run('gacha:42')
  assert.equal(inspect(complete.store).ready, false)
})

test('the original pinned deployment supplies the complete mandatory 9599-key contract', () => {
  const mandatory = release.readContentDeploymentRequiredKeysSync()
  assert.equal(mandatory.length, 9599)
  assert.equal(new Set(mandatory).size, 9599)
  assert(!mandatory.includes(parent)); assert(!mandatory.includes(gacha))
})

test('actual shop price and rare quest rewards cannot hide behind unchanged raw definition evidence', t => {
  const f = fixture(t, catalog('1.4.349', 'old')), old = store(f.db, catalog('1.4.349', 'old'))
  patch(old, products[0], { visible: false, exchange: false }); patch(old, parent, { visible: false, enter: false, exchange: false })
  const capture = actualCapture(f, old.catalog)
  const file = path.join(capture.currentSourceRoot, 'assets/actual_shop.json'), shop = JSON.parse(fs.readFileSync(file, 'utf8'))
  shop[products[0].split(':')[1]].costs[0].amount++
  fs.writeFileSync(file, JSON.stringify(shop))
  assert.throws(() => build(f.store, evidence, capture), /业务字段/)
  shop[products[0].split(':')[1]].costs[0].amount--; fs.writeFileSync(file, JSON.stringify(shop))
  const rareFile = path.join(capture.currentSourceRoot, 'assets/actual_rare.json'), rare = JSON.parse(fs.readFileSync(rareFile, 'utf8'))
  rare[7][0].count++; fs.writeFileSync(rareFile, JSON.stringify(rare))
  assert.throws(() => build(f.store, evidence, capture), /业务字段/)
})

test('application re-captures actual old/current getters and rejects a changed input or forged plan capture', async t => {
  const f = fixture(t, catalog('1.4.349', 'old')), old = store(f.db, catalog('1.4.349', 'old'))
  patch(old, products[0], { visible: false, exchange: false })
  const capture = actualCapture(f, old.catalog), plan = build(f.store, evidence, capture)
  const file = path.join(capture.currentSourceRoot, 'assets/actual_shop.json'), data = JSON.parse(fs.readFileSync(file, 'utf8'))
  data[products[0].split(':')[1]].costs[0].amount++; fs.writeFileSync(file, JSON.stringify(data))
  const unchangedTarget = guards.getDeploymentDatabaseFingerprintSync(f.db)
  await assert.rejects(maintain(f, context => apply(f.store, plan, plan.digest, context, now, capture)), /实际旧源或当前访问器捕获已变化/)
  assert.equal(guards.getDeploymentDatabaseFingerprintSync(f.db), unchangedTarget)
  data[products[0].split(':')[1]].costs[0].amount--; fs.writeFileSync(file, JSON.stringify(data))
  const forged = clone(plan)
  forged.identityReview.current.keys[products[0]].dependencies.actualShopItem = sha('declaration omits price')
  forged.identityReview.before.keys[products[0]].dependencies.actualShopItem = sha('declaration omits price')
  const signed = resign(forged)
  await assert.rejects(maintain(f, context => apply(f.store, signed, signed.digest, context, now, capture)), /实际旧源或当前访问器捕获已变化/)
})

test('ticket/campaign-only rule changes and missing payment enums cannot escape the actual matrix', t => {
  const f = fixture(t, catalog('1.4.349', 'old')), old = store(f.db, catalog('1.4.349', 'old'))
  const capture = actualCapture(f, old.catalog), file = path.join(capture.currentSourceRoot, 'src/lib/gacha-rules.ts')
  const original = fs.readFileSync(file, 'utf8')
  const baseline = build(f.store, evidence, capture)
  assert.equal(baseline.bindings.length, 1)
  for (const payment of [3, 4]) {
    fs.writeFileSync(file, original.replace('return g.payments.includes(p)', `if(p===${payment})return true;return g.payments.includes(p)`))
    assert.throws(() => build(f.store, evidence, capture), /业务字段/)
  }
  fs.writeFileSync(file, original.replace('export const GACHA_PAYMENT_TYPES', 'const GACHA_PAYMENT_TYPES'))
  assert.throws(() => build(f.store, evidence, capture), error => error.pendingIdentityReviews?.some(row => row.key === 'gacha:42' && /payment enum/.test(row.reason)))
})

test('actual campaign assignment, including default null, is an independent gacha dependency', t => {
  const f = fixture(t, catalog('1.4.349', 'old')), old = store(f.db, catalog('1.4.349', 'old'))
  const capture = actualCapture(f, old.catalog), file = path.join(capture.currentSourceRoot, 'assets/actual_campaign.json')
  assert.equal(build(f.store, evidence, capture).bindings.length, 1)
  fs.writeFileSync(file, JSON.stringify({ 42: 71 }))
  assert.throws(() => build(f.store, evidence, capture), /业务字段/)
  fs.writeFileSync(file, '{}')
  assert.throws(() => build(f.store, evidence, capture), /业务字段/)
})

test('preview domain import cannot mkdir or open the default database and restores its loader context', t => {
  const f = fixture(t), root = path.join(f.directory, 'preview-import'), tool = require('../tools/prepare-content-release.cjs')
  fs.mkdirSync(path.join(root, 'out/lib'), { recursive: true }); fs.mkdirSync(path.join(root, 'out/data'), { recursive: true })
  const initializer = path.join(root, 'out/data/index.js'), domain = path.join(root, 'out/lib/content-operations.js')
  fs.writeFileSync(initializer, "const fs=require('node:fs'),path=require('node:path');fs.mkdirSync(path.resolve(__dirname,'../../.database'));module.exports={}")
  fs.writeFileSync(path.join(root, 'out/data/db.js'), "require('./index');exports.getDb=()=>{throw Error('default opener reached')}")
  fs.writeFileSync(domain, "const {getDb}=require('../data/db');exports.createContentOperationsStore=db=>({db});exports.badDefaultAccess=()=>getDb()")
  const loader = require('node:module'), original = loader._load
  tool.withReadOnlyContentContext(root, () => {
    const api = require(domain)
    assert.equal(api.createContentOperationsStore(f.db).db, f.db)
    assert.throws(() => api.badDefaultAccess(), /Default database access is forbidden/)
    assert.throws(() => require(initializer), /initializer import is forbidden/)
  })
  assert.equal(loader._load, original)
  assert(!fs.existsSync(path.join(root, '.database')))
  assert.equal(require.cache[initializer], undefined)
})
