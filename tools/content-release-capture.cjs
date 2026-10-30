'use strict'
// Fixed read-only effective-accessor producer. No Git, database, service, or writes.
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), crypto = require('node:crypto')
const assert = require('node:assert/strict')
const sha = value => crypto.createHash('sha256').update(value).digest('hex')
const stable = value => Array.isArray(value) ? '[' + value.map(stable).join(',') + ']'
  : value && typeof value === 'object' ? '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + stable(value[key])).join(',') + '}'
    : JSON.stringify(value)
const PRODUCER_SHA256 = sha(fs.readFileSync(__filename)), issued = new WeakSet()
const provenance = new Set(['definitionEvidence', 'exactDefinitionEvidence', 'currentParentDefinitionEvidence', 'serverDefinitionDigest', 'legacyCarrierReview'])
const shops = { treasure_shop: 2, event_item_shop: 4, boss_coin_shop: 7, general_shop: 8, star_grain_shop: 9 }
function fileHash(file) {
  const hash = crypto.createHash('sha256'), buffer = Buffer.allocUnsafe(65536), fd = fs.openSync(file, 'r')
  try { let count; while ((count = fs.readSync(fd, buffer, 0, buffer.length, null))) hash.update(buffer.subarray(0, count)) }
  finally { fs.closeSync(fd) }
  return hash.digest('hex')
}
const signature = stat => `${stat.dev}:${stat.ino}:${stat.size}:${stat.mtimeMs}:${stat.ctimeMs}`
function openSource(sourceRoot) {
  const root = fs.realpathSync(sourceRoot), modules = new Map(), used = new Map(), archives = new Map(), tables = new Map()
  const compiled = fs.existsSync(path.join(root, 'out/lib/content-operations.js')), codeRoot = compiled ? 'out/lib' : 'src/lib'
  const pristine = fs.existsSync(path.join(root, '.cdn')) ? fs.realpathSync(path.join(root, '.cdn')) : null
  let capturedBytes = 0
  const inside = (base, file) => file === base || file.startsWith(base + path.sep)
  function resolveRead(file) {
    const absolute = path.resolve(String(file))
    let relative
    if (inside(root, absolute)) relative = path.relative(root, absolute).replaceAll('\\', '/')
    else if (pristine && inside(pristine, absolute)) relative = '.cdn/' + path.relative(pristine, absolute).replaceAll('\\', '/')
    else throw Error('Capture read outside explicit source: ' + absolute)
    if (/^(?:config\/|\.env(?:\.|$)|\.database\/)/.test(relative) || /\.(?:db|sqlite|sqlite3)(?:-(?:wal|shm))?$/i.test(relative))
      throw Error('Capture cannot read private state: ' + relative)
    const physical = fs.realpathSync(absolute), stat = fs.statSync(physical)
    if (!inside(root, physical) && !(pristine && inside(pristine, physical))) throw Error('Capture source alias escapes approved roots')
    if (stat.isFile()) {
      const book = physical.endsWith('.zip') ? archives : used, prior = book.get(relative)
      if (prior && (prior.physical !== physical || prior.signature !== signature(stat))) throw Error('Capture input changed: ' + relative)
      if (!prior) {
        if (!physical.endsWith('.zip')) {
          capturedBytes += stat.size
          if (stat.size > 96 * 1024 * 1024 || capturedBytes > 384 * 1024 * 1024) throw Error('Capture input byte budget exceeded')
        }
        book.set(relative, { relative, physical, bytes: stat.size, signature: signature(stat),
          ...(physical.endsWith('.zip') ? {} : { sha256: fileHash(physical) }) })
      }
    }
    return physical
  }
  const reader = new Proxy(fs, { get(_target, key) {
    if (['readFileSync', 'statSync', 'lstatSync', 'realpathSync', 'openSync'].includes(key)) return (file, ...args) => {
      if (key === 'openSync' && args[0] !== 'r') throw Error('Capture cannot open a writable descriptor')
      const actual = resolveRead(file)
      if (key === 'readFileSync' && actual.endsWith('.zip')) throw Error('Whole archive reads are forbidden; use the bounded member parser')
      return fs[key](actual, ...args)
    }
    if (key === 'existsSync') return file => { try { resolveRead(file); return true } catch (error) { if (error.code === 'ENOENT') return false; throw error } }
    if (['readSync', 'closeSync', 'fstatSync'].includes(key)) return fs[key].bind(fs)
    if (key === 'constants') return fs.constants
    throw Error('Capture filesystem operation is not read-only: ' + String(key))
  } })
  function resolveModule(file) {
    for (const candidate of [file, file + '.ts', file + '.js', file + '.json', path.join(file, 'index.ts'), path.join(file, 'index.js')]) {
      try { if (fs.statSync(resolveRead(candidate)).isFile()) return candidate }
      catch (error) { if (error.code !== 'ENOENT' && error.code !== 'ENOTDIR') throw error }
    }
    throw Error('Actual source module unavailable: ' + file)
  }
  function load(request) {
    const file = resolveModule(request), relative = path.relative(root, file).replaceAll('\\', '/')
    if (['src/data/db.ts', 'src/data/db.js', 'out/data/db.js'].includes(relative)) return { getDb() { throw Error('Default database access is forbidden during capture') } }
    if (modules.has(file)) return modules.get(file).exports
    const bytes = fs.readFileSync(resolveRead(file)), mod = { exports: {} }; modules.set(file, mod)
    if (file.endsWith('.json')) { mod.exports = JSON.parse(bytes.toString('utf8')); return mod.exports }
    function requireActual(name) {
      if (name === 'node:fs' || name === 'fs') return reader
      if (name === 'better-sqlite3') return function () { throw Error('Capture cannot open a database') }
      if (['node:path', 'path', 'node:crypto', 'crypto', 'node:zlib', 'zlib', 'node:util', 'util', 'node:assert/strict', 'assert/strict', 'node:async_hooks', 'async_hooks'].includes(name)) return require(name)
      if (name.startsWith('.')) return load(path.resolve(path.dirname(file), name))
      throw Error('Capture external/process module is forbidden: ' + name)
    }
    let js = bytes.toString('utf8')
    if (file.endsWith('.ts')) {
      // Compiled deployment/old-runtime captures need no compiler dependency.
      // A source-only archived tree uses the existing local TypeScript toolchain.
      const ts = require('typescript')
      js = ts.transpileModule(js, { compilerOptions: {
        module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText
    }
    new vm.Script(js, { filename: file }).runInNewContext({ module: mod, exports: mod.exports, require: requireActual,
      __filename: file, __dirname: path.dirname(file), Buffer, TextEncoder, TextDecoder, URL,
      console, process: Object.freeze({ env: Object.freeze({ NODE_ENV: 'test' }), cwd: () => root, platform: process.platform }),
      setTimeout() { throw Error('Capture timers are forbidden') }, setInterval() { throw Error('Capture timers are forbidden') },
    }, { timeout: 10000 })
    return mod.exports
  }
  const get = file => load(path.join(root, codeRoot, file))
  const json = name => { if (!tables.has(name)) tables.set(name, load(path.join(root, 'assets', name))); return tables.get(name) }
  // The constructor computes source identities without any state or default DB.
  const db = Object.freeze({ readonly: true, inTransaction: true, prepare() { throw Error('Capture may not query player or operations databases') } })
  const store = get('content-operations').createContentOperationsStore(db), exactCache = new Map()
  function questValues(row) {
    const getters = get('assets'), rules = get('content-quest-rules'), original = rules.applyContentQuestRules, result = {}
    for (const key of store.questMembers.get(row.key) || []) {
      const [category, id] = key.split(':').map(Number); let trace
      rules.applyContentQuestRules = (c, i, raw) => { const effective = original(c, i, raw); trace = { serverRow: raw, effectiveRow: effective }; return effective }
      try {
        const actual = getters.getQuestFromCategorySync(category, id)
        assert(actual && trace, 'Actual quest/rules unavailable: ' + key)
        const rare = {}
        for (const reward of actual.scoreRewardGroup || []) if (reward.type === 1) {
          const value = getters.getRareScoreRewardGroup(reward.id)
          assert(value, 'Actual rare rewards unavailable: ' + key + '/' + reward.id); rare[reward.id] = value
        }
        result[key] = { ...trace, actualQuestAndRewards: actual, actualRareRewards: rare }
      } finally { rules.applyContentQuestRules = original }
    }
    return result
  }
  function missionValues(row) {
    const members = [...(store.missionMembers.get(row.key) || [])], direct = { mission_regular: 1, mission_daily: 2, mission_event: 3, mission_collect_item: 4, mission_degree: 5, mission_weekly: 10 }
    if (!members.length && Object.hasOwn(direct, row.type)) members.push(direct[row.type] + ':' + row.id)
    if (!members.length) return {}
    const files = { 0: 'mission_active_reward.json', 1: 'mission_regular_reward.json', 2: 'mission_daily_reward.json', 3: 'mission_event_reward.json', 4: 'mission_collect_item_reward.json', 5: 'mission_degree_reward.json', 6: 'mission_pass_daily_reward.json', 7: 'mission_pass_week_reward.json', 8: 'mission_pass_event_reward.json', 10: 'mission_weekly_reward.json' }, api = get('mission/rewards'), result = {}
    for (const member of members) {
      const [category, id] = member.split(':').map(Number); assert(files[category], 'Unsupported mission category: ' + member)
      const stages = json(files[category])[String(id)]; assert(stages, 'Actual mission stages unavailable: ' + member)
      result[member] = Object.fromEntries(Object.keys(stages).map(stage => {
        const value = category === 0 ? api.getMissionRewardStageDefinition(id, Number(stage)) : api.getCategoryMissionRewardStageDefinition(category, id, Number(stage))
        assert(value, 'Actual mission reward unavailable: ' + member + '/' + stage); return [stage, value]
      }))
    }
    return result
  }
  function describe(key) {
    const row = store.rows.get(key); assert(row, 'Actual source key unavailable: ' + key)
    const engine = get('content-definition-evidence'), raw = engine.captureExactDefinition(row, root, exactCache)
    // Loader bytes are pinned in inputReceipt and rechecked during application.
    // Their effective outputs, rather than unrelated whole-file changes, define
    // business equivalence between program versions.
    const dependencies = { ...(raw?.dependencies || {}) }
    let implemented = !!raw
    if (Object.hasOwn(shops, row.type)) {
      const actual = get('assets').getShopItemSync(shops[row.type], row.id)
      assert(actual, 'Actual effective shop item unavailable: ' + key)
      dependencies.actualShopItem = actual; implemented = true
    }
    // Always augment a parent capture: captureExactDefinition alone covers its
    // shop membership, not its actual quests, clear/score/rare rewards.
    if (store.questMembers.get(key)?.size) { dependencies.actualQuestsAndRewards = questValues(row); implemented = true }
    const missions = missionValues(row)
    if (Object.keys(missions).length) { dependencies.actualMissionRewards = missions; implemented = true }
    if (row.type === 'gacha') {
      const getters = get('assets'), value = getters.getGachaSync(row.id), rules = get('gacha-rules'); assert(value, 'Actual gacha unavailable: ' + key)
      assert(typeof getters.getGachaCampaignIdSync === 'function', 'Actual gacha campaign mapping accessor unavailable: ' + key)
      const campaignId = getters.getGachaCampaignIdSync(row.id)
      assert(campaignId === null || Number.isSafeInteger(campaignId), 'Actual gacha campaign mapping is invalid: ' + key)
      const paymentTypes = rules.GACHA_PAYMENT_TYPES, execTypes = rules.GACHA_EXEC_TYPES
      assert(paymentTypes && ['FREE_VMONEY', 'VMONEY', 'TICKET', 'CAMPAIGN'].every(name => Number.isSafeInteger(paymentTypes[name]) && paymentTypes[name] > 0),
        'Complete actual gacha payment enum unavailable: ' + key)
      const payments = [...new Set(Object.values(paymentTypes).filter(value => Number.isSafeInteger(value) && value > 0))]
      const executions = [...new Set(Object.values(execTypes || {}).filter(value => Number.isSafeInteger(value) && value > 0))]
      assert(executions.length, 'Actual gacha execution enum unavailable: ' + key)
      dependencies.actualGacha = value
      dependencies.actualGachaCampaignId = campaignId
      dependencies.actualPaymentTypes = paymentTypes; dependencies.actualExecutionTypes = execTypes
      dependencies.actualPaymentMatrix = Object.fromEntries(payments.map(payment => [payment, Object.fromEntries(executions.map(exec => {
        const allowed = rules.isGachaExecAllowed(value, payment, exec)
        assert(typeof allowed === 'boolean', 'Actual payment decision unavailable: ' + key + '/' + payment + '/' + exec)
        return [exec, allowed]
      }))]))
      implemented = true
    } else if (row.type === 'box_gacha') {
      const value = get('assets').getBoxGachaSync(row.id); assert(value, 'Actual box unavailable: ' + key)
      const policy = get('box-gacha-policy').getBoxOperationRules(row, value.boxes); assert(policy, 'Actual box policy unavailable: ' + key)
      dependencies.actualBox = value; dependencies.actualBoxRules = [...policy]; implemented = true
    } else if (row.type === 'pass_card_event') {
      const api = get('pass-card'), event = api.getPassCardEventDefinition(row.id); assert(event, 'Actual pass unavailable: ' + key)
      dependencies.actualPass = event
      dependencies.actualPassRewards = Object.keys(json('pass_card_reward.json')).map(id => api.getPassCardRewardDefinition(Number(id))).filter(value => value?.eventId === row.id)
      implemented = true
    } else if (row.type === 'start_dash_exchange_campaign' || row.type === 'special_exchange_campaign') {
      const match = engine.matchCampaignDefinition(row, root); assert(match?.matchesCatalog, 'Actual campaign resource proof unavailable: ' + key)
      const definitions = get('exchange-campaign-definitions')
      const value = (row.type === 'start_dash_exchange_campaign' ? definitions.START_DASH_EXCHANGE_DEFINITIONS : definitions.SPECIAL_EXCHANGE_DEFINITIONS)[String(row.id)]
      assert(value, 'Actual campaign unavailable: ' + key); dependencies.actualCampaign = value; dependencies.actualCampaignProof = match; implemented = true
    } else if (row.type === 'multi_special_exchange_campaign') {
      const value = get('multi-special-exchange').getMultiSpecialExchangeCampaignDefinition(row.id)
      assert(value, 'Actual multi-exchange unavailable: ' + key); dependencies.actualMultiExchange = value; implemented = true
    } else if (['raid_event', 'world_story_event'].includes(row.type) && !store.questMembers.get(key)?.size) {
      const link = get('content-box-associations').getContentBoxAssociation(key); assert(link?.relationshipMatches && link.boxKey, 'Actual box lifecycle unavailable: ' + key)
      const box = get('assets').getBoxGachaSync(Number(link.boxKey.split(':')[1])); assert(box, 'Actual linked box unavailable: ' + key)
      dependencies.actualBoxLifecycle = { parentKey: link.parentKey, boxKey: link.boxKey, relationshipMatches: link.relationshipMatches }
      dependencies.actualLinkedBox = box; implemented = true
    }
    assert(implemented && Object.keys(dependencies).length, 'No implemented actual accessor for ' + key + ' type=' + row.type)
    return { key, contentDigest: store.contentDigests.get(key), runtimeDigest: store.runtimeDefinitions.get(key)?.digest,
      runtimeMatches: store.runtimeDefinitions.get(key)?.matchesCatalog === true,
      businessRow: Object.fromEntries(Object.entries(row).filter(([field]) => !provenance.has(field))),
      dependencies: Object.fromEntries(Object.entries(dependencies).map(([selector, value]) => [selector, sha(stable(value))])),
      captureEngineSha256: PRODUCER_SHA256, operatorCapabilities: [...store.capabilities(row)], clientCapabilities: [...(store.clientCapabilities?.(row) || [])],
      questMembers: [...(store.questMembers.get(key) || [])], missionMembers: [...(store.missionMembers.get(key) || [])] }
  }
  function verify() {
    for (const entry of used.values()) if (fs.realpathSync(entry.physical) !== entry.physical || fileHash(entry.physical) !== entry.sha256) throw Error('Captured source input changed: ' + entry.relative)
    for (const entry of archives.values()) if (signature(fs.statSync(entry.physical)) !== entry.signature) throw Error('Captured archive changed: ' + entry.relative)
    if (sha(fs.readFileSync(__filename)) !== PRODUCER_SHA256) throw Error('Capture producer changed')
  }
  return { root, store, describe, verify, receipt() { verify(); return { producerSha256: PRODUCER_SHA256,
    files: [...used.values()].sort((a, b) => a.relative.localeCompare(b.relative)), archives: [...archives.values()].sort((a, b) => a.relative.localeCompare(b.relative)) } } }
}
function createReleaseCaptureSession({ previousSource, currentSource = path.resolve(__dirname, '..') }) {
  const previousRoot = fs.realpathSync(previousSource), currentRoot = fs.realpathSync(currentSource)
  if (previousRoot === currentRoot) throw Error('Previous and current sources must be distinct pinned source roots')
  const session = Object.freeze({ previousSourceRoot: previousRoot, currentSourceRoot: currentRoot,
    capture(keys) {
      assert(Array.isArray(keys) && keys.length && keys.length <= 20000 && new Set(keys).size === keys.length, 'Invalid capture key set')
      function view(root) {
        const source = openSource(root)
        const records = {}, pending = []
        for (const key of keys) {
          try { records[key] = source.describe(key) }
          catch (error) { pending.push({ key, type: source.store.rows.get(key)?.type, reason: String(error.message).slice(0, 600) }) }
        }
        if (pending.length) {
          const error = new Error('Actual accessor capture is blocked for ' + pending.length + ' keys; no identity migration is proved')
          error.pendingIdentityReviews = pending; throw error
        }
        const inputReceipt = source.receipt()
        return { kind: 'pinned-original-store-capture', catalogDigest: source.store.digest, keys: records, inputReceipt }
      }
      // Separate module caches and sequential views bound the memory retained by
      // original master readers. Neither view ever obtains a database connection.
      return { before: view(previousRoot), current: view(currentRoot) }
    },
  })
  issued.add(session); return session
}
module.exports = { createReleaseCaptureSession, isReleaseCaptureSession: value => issued.has(value), PRODUCER_SHA256 }
