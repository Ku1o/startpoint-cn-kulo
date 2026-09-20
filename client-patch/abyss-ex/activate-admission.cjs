/** Start this release's 24-hour predecessor grace once, at server activation. */
'use strict'
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto')
const IDS = { android: 'android-181-abyss-ex-20260917', ios: 'ios-184-abyss-ex-20260917' }
const OLD = { android: 'android-181-r10-20260915', ios: 'ios-184-admission-20260915' }
const read = p => JSON.parse(fs.readFileSync(p, 'utf8').replace(/^\uFEFF/, ''))
function write(p, value) {
  const temp = p + '.' + crypto.randomUUID() + '.tmp'
  fs.writeFileSync(temp, JSON.stringify(value, null, 2) + '\n', { mode: 0o600, flag: 'wx' })
  fs.renameSync(temp, p)
}
function activate(root, platforms = ['android', 'ios'], now = Date.now()) {
  if (!platforms.length || platforms.some(p => !Object.hasOwn(IDS, p)) || !Number.isFinite(now)) throw Error('Invalid activation request')
  const config = path.join(path.resolve(root), 'config')
  const policyPath = path.join(config, 'client-admission.json')
  const statePath = path.join(config, 'abyss-ex-admission-activation.json')
  const policy = read(policyPath), keys = read(path.join(config, 'client-admission.keys.json'))
  if (typeof policy.enforce !== 'boolean' || !Array.isArray(policy.builds)) throw Error('Invalid complete policy')
  const state = fs.existsSync(statePath) ? read(statePath) : { release: 'abyss-ex-20260917', platforms: {} }
  if (state.release !== 'abyss-ex-20260917' || !state.platforms) throw Error('Invalid activation state')
  const results = []
  for (const platform of platforms) {
    const newest = policy.builds.filter(b => b.id === IDS[platform])
    const oldest = policy.builds.filter(b => b.id === OLD[platform])
    if (newest.length !== 1 || oldest.length !== 1 || newest[0].platform !== platform || oldest[0].platform !== platform
        || !newest[0].enabled || newest[0].allowUntil !== null
        || !/^[a-f0-9]{64}$/.test(keys[IDS[platform]]) || !/^[a-f0-9]{64}$/.test(keys[OLD[platform]])) {
      throw Error('Complete paired release configuration is required')
    }
    let row = state.platforms[platform]
    if (!row) {
      const expires = new Date(Math.ceil(now / 1000) * 1000 + 86400000).toISOString().replace('.000Z', 'Z')
      row = state.platforms[platform] = { activatedAt: new Date(now).toISOString(), expiresAt: expires }
    }
    if (!Number.isFinite(Date.parse(row.expiresAt)) || !Number.isFinite(Date.parse(row.activatedAt))) throw Error('Invalid saved expiry')
    // Never extend a stricter existing deadline; repeated activation is idempotent.
    const oldExpiry = oldest[0].allowUntil
    if (oldExpiry !== null && !Number.isFinite(Date.parse(oldExpiry))) throw Error('Invalid predecessor expiry')
    if (oldExpiry !== null && Date.parse(oldExpiry) < Date.parse(row.expiresAt)) row.expiresAt = oldExpiry
    oldest[0].allowUntil = row.expiresAt
    results.push({ platform, oldBuild: OLD[platform], newBuild: IDS[platform], expiresAt: row.expiresAt })
  }
  // Save the deadline first so an interrupted run never restarts the clock.
  if (!fs.existsSync(statePath + '.policy-before.json')) fs.copyFileSync(policyPath, statePath + '.policy-before.json', fs.constants.COPYFILE_EXCL)
  write(statePath, state)
  write(policyPath, policy)
  return results
}
module.exports = { activate, IDS, OLD }
if (require.main === module) {
  const [root, selection = 'both', ...extra] = process.argv.slice(2)
  if (!root || extra.length || !['both', 'android', 'ios'].includes(selection)) {
    console.error('Usage: node activate-admission.cjs <server-root> [both|android|ios]'); process.exitCode = 1
  } else {
    try { console.log(JSON.stringify({ activated: activate(root, selection === 'both' ? ['android', 'ios'] : [selection]) }, null, 2)) }
    catch { console.error('Activation failed; check the complete paired config and directory permissions. No key material is logged.'); process.exitCode = 1 }
  }
}
