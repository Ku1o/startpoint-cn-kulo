'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), crypto = require('node:crypto'), Module = require('node:module')
const ts = require('typescript'), Sqlite = require('better-sqlite3'), producer = require('../tools/content-release-capture.cjs')
const original = require.extensions['.ts']
require.extensions['.ts'] = (mod, filename) => mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText, filename)
let api, Store, guards
try { api = require('../src/lib/content-gacha-revision.ts'); Store = require('../src/lib/content-operations-store.ts'); guards = require('../src/lib/deployment-maintenance-guard.ts') }
finally { if (original) require.extensions['.ts'] = original; else delete require.extensions['.ts'] }
const sha = value => crypto.createHash('sha256').update(value).digest('hex')
const canonical = value => Array.isArray(value) ? '[' + value.map(canonical).join(',') + ']'
  : value && typeof value === 'object' ? '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}' : JSON.stringify(value)
const hash = value => sha(canonical(value)), copy = value => JSON.parse(JSON.stringify(value)), keys = ['gacha:42', 'gacha:990001', 'gacha:990002']
const source = { assetVersion: '1.4.356', manifestSha256: sha(JSON.stringify({ cdn_version: '1.4.356' })) }, legacySource = { assetVersion: '1.4.350', manifestSha256: sha('reviewed 350 manifest') }
const now = Date.parse('2026-11-02T00:00:00Z'), evidence = sha('synthetic exact two-pool review')
const logicals = ['master/gacha_odds/cnmod_abyss_limited_gacha_character_5.orderedmap', 'master/gacha_odds/cnmod_ashen_verdict_gacha_character_5.orderedmap']
function gacha(odds = 2000) {
  return { type: 0, singleCost: 1, multiCost: 10, pageKind: 0, pool: {
    1: [{ id: 139994, rank: 5, odds, isRateUp: true, isLimited: true, isExchangeable: false, trialReadingForced: false, rarity: 1000 }],
    2: [{ id: 200001, odds: 35, rarity: 1000 }], 3: [{ id: 300001, odds: 9, rarity: 1000 }],
  } }
}
function add(value, odds) {
  const next = copy(value)
  next.pool[1].push({ id: 179981, rank: 5, odds, isRateUp: true, isLimited: true, isExchangeable: true, trialReadingForced: false, rarity: 0 })
  const total = next.pool[1].reduce((sum, row) => sum + row.odds, 0)
  for (const row of next.pool[1]) row.rarity = row.odds / total * 1000
  return next
}
function write(root, file, value) {
  fs.mkdirSync(path.dirname(path.join(root, file)), { recursive: true })
  fs.writeFileSync(path.join(root, file), typeof value === 'string' ? value : JSON.stringify(value))
}
function makeSource(root, next) {
  write(root, 'assets/asset-patch/manifest.json', { cdn_version: next ? '1.4.356' : '1.4.355' })
  const pools = { 990001: next ? add(gacha(), 1000) : gacha(), 990002: next ? add(gacha(10000), 10000) : gacha(10000) }
  const base = copy({ 42: gacha(500), ...pools })
  if (!next) base[990002].pool[1].push({ id: 999999, odds: 0, rarity: 0 })
  write(root, 'assets/gacha.json', base)
  write(root, 'assets/gacha_cnmod.json', { 990001: pools[990001] })
  write(root, 'assets/gacha_rank_p5b.json', { 990002: pools[990002] })
  const files = ['assets/gacha.json', 'assets/gacha_cnmod.json', 'assets/gacha_rank_p5b.json']
  const serverResources = Object.fromEntries(files.map(file => [file, { sha256: sha(fs.readFileSync(path.join(root, file))) }]))
  const resources = Object.fromEntries(logicals.map((logical, i) => [logical, { archive: 'assets/asset-patch/active/synthetic.zip', member: 'production/upload/' + i, sha256: sha((next ? 'new' : 'old') + logical) }]))
  const catalog = { schemaVersion: 1, source: { assetVersion: '1.4.135', manifestSha256: sha('original master export') }, baselineTimeMs: 1, baselineEvidence: 'synthetic', missing: [], questMap: {}, resources, serverResources,
    rows: keys.map((key, index) => ({ key, type: 'gacha', id: Number(key.split(':')[1]), name: key, source: 'master/gacha/gacha.orderedmap', originalStartMs: 1,
      originalEndMs: null, originalExchangeEndMs: null, windowCandidate: true, browseCandidate: true, definitionDigest: sha(key),
      definitionSources: index ? [logicals[index - 1]] : [], serverDefinitionDigest: sha(JSON.stringify([[files[index], serverResources[files[index]].sha256]])),
      definitionEvidence: { status: 'matched', serverSources: [files[index]], issues: [] } })) }
  write(root, 'assets/content_catalog.json', catalog)
  write(root, 'assets/content_resource_source.json', { schemaVersion: 1, source: next ? source : legacySource, resources: Object.fromEntries(Object.entries(resources).map(([key, value]) => [key, { archive: value.archive, sha256: value.sha256 }])) })
  for (const file of ['content-operations-store.ts', 'content-operations-defaults.ts', 'content-native-presentation-rules.ts', 'cached-statement.ts', 'types/quest.ts'])
    write(root, 'src/lib/' + file, fs.readFileSync(path.join(__dirname, '../src/lib', file), 'utf8'))
  write(root, 'src/lib/content-july-reference.ts', 'export function isFixedJulyCandidate() { return false }')
  write(root, 'src/lib/memory-diagnostics.ts', 'export function registerMemoryCounters(){return ()=>{}}')
  write(root, 'src/lib/content-operations.ts', `import data from '../../assets/content_catalog.json';import {ContentOperationsStore} from './content-operations-store';
    export function createContentOperationsStore(db){return new ContentOperationsStore(db,data,()=>['visible','enter','exchange'],r=>({digest:r.serverDefinitionDigest,matchesCatalog:true}))}`)
  write(root, 'src/lib/content-definition-evidence.ts', 'export function captureExactDefinition(){return null}')
  write(root, 'src/lib/gacha-rules.ts', 'export const GACHA_PAYMENT_TYPES={FREE_VMONEY:1,VMONEY:2,TICKET:3,CAMPAIGN:4};export const GACHA_EXEC_TYPES={single:1,ten:2};export function isGachaExecAllowed(g,p,e){return [1,2,3,4].includes(p)&&[1,2].includes(e)}')
  write(root, 'src/lib/assets.ts', `import base from '../../assets/gacha.json';import a from '../../assets/gacha_cnmod.json';import b from '../../assets/gacha_rank_p5b.json';const gachas={...base,...a,...b};export function getGachaSync(id){return gachas[id]??null}export function getGachaCampaignIdSync(){return null}`)
  return catalog
}
function makeStore(db, catalog) { return new Store.ContentOperationsStore(db, catalog, () => ['visible', 'enter', 'exchange'], r => ({ digest: r.serverDefinitionDigest, matchesCatalog: true })) }
function fixture(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'starpoint-gacha356-')), previous = path.join(directory, 'before'), current = path.join(directory, 'current')
  const oldCatalog = makeSource(previous, false), catalog = makeSource(current, true), database = path.join(directory, 'synthetic.db'), db = new Sqlite(database)
  t.after(() => { if (db.open) db.close(); const physical = fs.realpathSync(directory); assert(physical.startsWith(fs.realpathSync(os.tmpdir()) + path.sep)); fs.rmSync(physical, { recursive: true }) })
  Store.initializeContentOperationsSchema(db)
  const old = makeStore(db, oldCatalog)
  for (const key of keys) old.update(key, { expectedRevision: old.revision(), catalogDigest: old.digest, reason: 'synthetic operator decision',
    actionOverrides: { visible: { enabled: key !== 'gacha:990001', endsAtMs: key === 'gacha:990002' ? now - 1 : key === 'gacha:42' ? now + 10000 : null, readiness: 'verified', evidence: 'retained original review' },
      exchange: { enabled: true, endsAtMs: null, readiness: 'verified', evidence: 'earned point exchange' } } }, now - 100)
  db.exec("CREATE TABLE players(id INTEGER PRIMARY KEY,point INTEGER,progress TEXT); INSERT INTO players VALUES(1,345,'earned-before-update');")
  const baseline = ['content_operations_initialization', 'content_operations_deployment', 'content_box_exchange_deployment']
  for (const table of baseline) { db.exec(`CREATE TABLE ${table}(id INTEGER PRIMARY KEY,plan_digest TEXT)`); db.prepare(`INSERT INTO ${table} VALUES(1,?)`).run(sha(table)) }
  const baselineSha = hash(baseline.map(table => [table, db.prepare(`SELECT * FROM ${table} ORDER BY id`).all()]))
  db.exec('CREATE TABLE content_release_supplements(release_id TEXT PRIMARY KEY,plan_digest TEXT,catalog_digest TEXT,applied_revision INTEGER,keys_json TEXT,baseline_sha256 TEXT,source_sha256 TEXT)')
  db.prepare('INSERT INTO content_release_supplements VALUES(?,?,?,?,?,?,?)').run('halloween-300097-v1', sha('original reviewed plan'), old.digest, old.revision(), JSON.stringify(keys), baselineSha, legacySource.manifestSha256)
  const store = makeStore(db, catalog), session = producer.createReleaseCaptureSession({ previousSource: previous, currentSource: current })
  return { db, database, directory, previous, current, store, session, old, backups: 0 }
}
const build = f => f.db.transaction(() => api.buildGachaRevisionPlanSync(f.store, evidence, f.session, source, keys))()
const inspect = f => api.inspectGachaRevisionSync(f.store, source, keys)
async function maintain(f, run) {
  const fingerprint = guards.getDeploymentDatabaseFingerprintSync(f.db), backup = path.join(f.directory, `backup-${++f.backups}.db`)
  await f.db.backup(backup)
  return guards.withDeploymentMaintenanceTransactionSync(f.db, { kind: 'approved-stopped-database', databasePath: f.database, backupPath: backup,
    expectedDatabaseFingerprint: fingerprint, expectedBackupSha256: sha(fs.readFileSync(backup)) }, run)
}
const apply = (f, plan, context, session = f.session) => api.applyGachaRevisionSync(f.store, plan, plan.digest, context, now, session, source, keys)
const resign = plan => { const { digest, ...body } = plan; return { ...body, digest: hash(body) } }
function semantics(state) { const value = copy(state); delete value.revision; delete value.catalogDigest; delete value.contentDigest; if (value.actionOverrides) { delete value.evidence; for (const row of Object.values(value.actionOverrides)) { delete row.catalogDigest; delete row.contentDigest } } return value }

test('356 revision preserves old receipt, operator settings, points and progress; repeat after later edits is read-only', async t => {
  const f = fixture(t), before = guards.getDeploymentDatabaseFingerprintSync(f.db), legacy = f.db.prepare('SELECT * FROM content_release_supplements').get(), controls = keys.map(k => semantics(f.old.state(k)))
  const plan = build(f)
  assert.equal(guards.getDeploymentDatabaseFingerprintSync(f.db), before)
  assert.equal(plan.bindings.length, 3)
  assert.equal((await maintain(f, context => apply(f, plan, context))).applied, true)
  assert.deepEqual(keys.map(k => semantics(f.store.state(k))), controls)
  assert.deepEqual(f.db.prepare('SELECT * FROM content_release_supplements').get(), legacy)
  assert.deepEqual(f.db.prepare('SELECT * FROM players').get(), { id: 1, point: 345, progress: 'earned-before-update' })
  assert.equal(inspect(f).ready, true)
  assert.equal(f.store.allowed('gacha:42', 'visible', now), true)
  assert.equal(f.store.allowed('gacha:42', 'visible', now + 10001), false)
  assert.equal(f.store.allowed('gacha:990002', 'visible', now), false)
  f.store.setPublished('gacha:990002', { expectedRevision: f.store.revision(), catalogDigest: f.store.digest, reason: 'later operator close', published: false }, now + 1)
  const later = guards.getDeploymentDatabaseFingerprintSync(f.db)
  assert.equal((await maintain(f, context => apply(f, plan, context, undefined))).applied, false)
  assert.equal(guards.getDeploymentDatabaseFingerprintSync(f.db), later)
})

test('exact delta rejects price, payment, retained odds, flags and arbitrary rarity edits', () => {
  for (const change of [g => { g.singleCost++ }, g => { g.pageKind++ }, g => { g.pool[1][0].odds++ }, g => { g.pool[1][0].isExchangeable = true }, g => { g.pool[1][0].rarity++ }, g => { g.pool[1][1].odds++ }, g => { g.pool[2][0].odds++ }]) {
    const old = gacha(), next = add(old, 1000); change(next)
    assert.throws(() => api.validateGacha179981DeltaSync('gacha:990001', old, next))
  }
  api.validateGacha179981DeltaSync('gacha:990001', gacha(), add(gacha(), 1000))
  api.validateGacha179981DeltaSync('gacha:990002', gacha(), add(gacha(), 10000))
})

test('forged capture JSON, unrelated base changes and changed actual payment behavior cannot generate a plan', t => {
  const f = fixture(t)
  assert.throws(() => f.db.transaction(() => api.buildGachaRevisionPlanSync(f.store, evidence, { capture: () => ({}) }, source, keys))(), /实际访问器/)
  const file = path.join(f.current, 'assets/gacha.json'), data = JSON.parse(fs.readFileSync(file)); data[42].singleCost++
  fs.writeFileSync(file, JSON.stringify(data))
  assert.throws(() => build(f), /其他卡池变化/)
})

test('diagnostic registration pins source bytes without probes; missing source and other diagnostic calls reject', t => {
  const f = fixture(t), diagnostic = path.join(f.previous, 'src/lib/memory-diagnostics.ts')
  fs.writeFileSync(diagnostic, "throw Error('must never start probes');export function registerMemoryCounters(){}")
  const captured = f.session.capture(keys)
  const pinned = captured.before.inputReceipt.files.find(row => row.relative === 'src/lib/memory-diagnostics.ts')
  assert.equal(pinned.sha256, sha(fs.readFileSync(diagnostic)))
  fs.appendFileSync(path.join(f.previous, 'src/lib/cached-statement.ts'), '\nimport {memoryDiagnosticsEnabled} from "./memory-diagnostics";memoryDiagnosticsEnabled();')
  assert.throws(() => f.session.capture(keys), /diagnostic operation is forbidden/)
  fs.unlinkSync(diagnostic)
  assert.throws(() => f.session.capture(keys), /Actual source module unavailable/)
})

test('absolute native JSON reads remain pinned and cannot escape into private configuration', t => {
  const f = fixture(t), file = path.join(f.previous, 'src/lib/assets.ts')
  fs.appendFileSync(file, '\nrequire(' + JSON.stringify(path.join(f.previous, 'assets/content_catalog.json')) + ');')
  assert(f.session.capture(keys).before.inputReceipt.files.some(row => row.relative === 'assets/content_catalog.json'))
  write(f.previous, 'config/private.json', { synthetic: true })
  fs.appendFileSync(file, '\nrequire(' + JSON.stringify(path.join(f.previous, 'config/private.json')) + ');')
  assert.throws(() => f.session.capture(keys), error => error.pendingIdentityReviews?.some(row => /Capture cannot read private state/.test(row.reason)))
})

test('a real payment-matrix change remains blocked with unchanged gacha JSON and metadata', t => {
  const f = fixture(t), file = path.join(f.current, 'src/lib/gacha-rules.ts')
  fs.writeFileSync(file, fs.readFileSync(file, 'utf8').replace('return [1,2,3,4].includes(p)&&[1,2].includes(e)', 'return false'))
  assert.throws(() => build(f), /实际依赖发生变化/)
})

test('CAS drift and a second-binding failure leave the database unchanged', async t => {
  const f = fixture(t), plan = build(f), bad = copy(plan)
  bad.bindings[1].nextContentDigest = sha('wrong digest')
  const forged = resign(bad), before = guards.getDeploymentDatabaseFingerprintSync(f.db)
  await assert.rejects(() => maintain(f, context => apply(f, forged, context)), /发生变化/)
  assert.equal(guards.getDeploymentDatabaseFingerprintSync(f.db), before)
  f.db.prepare('UPDATE players SET point=point+1').run()
  const later = guards.getDeploymentDatabaseFingerprintSync(f.db)
  await assert.rejects(() => maintain(f, context => apply(f, plan, context)), /目标数据库已变化/)
  assert.equal(guards.getDeploymentDatabaseFingerprintSync(f.db), later)
})

test('old receipt mutation is rejected and standard maintenance dispatch requires the new verified receipt', async t => {
  const f = fixture(t), plan = build(f)
  await maintain(f, context => apply(f, plan, context))
  const filename = path.resolve(__dirname, '../scripts/time-content-deployment.cjs'), mod = new Module(filename, module)
  mod.filename = filename; mod.paths = module.paths
  mod.require = name => name === '../out/lib/content-gacha-revision' ? { inspectGachaRevisionSync: store => api.inspectGachaRevisionSync(store, source, keys) } : require(name)
  mod._compile(fs.readFileSync(filename, 'utf8'), filename)
  const context = { readServerClockStateSync: () => ({ snapshot: { mode: 'real' } }), createContentOperationsStore: () => f.store }
  assert.equal(mod.exports.inspectDatabase(f.db, context).ready, true)
  f.db.prepare('UPDATE content_release_supplements SET plan_digest=?').run(sha('rewritten old proof'))
  assert.equal(mod.exports.inspectDatabase(f.db, context).ready, false)
})
