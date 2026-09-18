/** Real paired policy plus the production admission implementation; no live server. */
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto')
const { activate, IDS, OLD } = require('./activate-admission.cjs')
const pair = process.argv[2]
if (!pair || !path.isAbsolute(pair)) throw Error('Explicit private release directory required')
const sandbox = path.join(pair, 'protocol-verification-' + Date.now())
fs.mkdirSync(path.join(sandbox, 'config'), { recursive: true })
process.env.DATA_DIR = path.join(sandbox, 'data')
const { ClientAdmission, proofMessage } = require('../../out/lib/client-admission')
for (const f of ['client-admission.json', 'client-admission.keys.json']) fs.copyFileSync(path.join(pair, 'config', f), path.join(sandbox, 'config', f))
const cp = path.join(sandbox, 'config/client-admission.json'), kp = path.join(sandbox, 'config/client-admission.keys.json')
const keys = JSON.parse(fs.readFileSync(kp, 'utf8')), original = JSON.parse(fs.readFileSync(cp, 'utf8'))
let now = Date.parse('2026-09-20T04:00:00Z'), checks = 0
const check = value => { assert.ok(value); checks++ }
const gate = new ClientAdmission(cp, kp, () => now, () => {})
check(gate.reload())
function grant(id, platform, wrongKey = false) {
  const ip = 'offline-' + checks
  const c = gate.challenge({ protocol: 1, build: id, platform }, ip)
  if (!c.ok) return c
  const proof = crypto.createHmac('sha256', Buffer.from(wrongKey ? '00'.repeat(32) : keys[id], 'hex'))
    .update(proofMessage(id, c.data.challenge, c.data.nonce)).digest('hex')
  return gate.prove({ challenge: c.data.challenge, proof }, ip)
}
for (const platform of ['android', 'ios']) {
  check(grant(IDS[platform], platform).ok)
  check(grant(OLD[platform], platform).ok)
  check(!grant(IDS[platform], platform === 'android' ? 'ios' : 'android').ok)
  check(!grant(IDS[platform], platform, true).ok)
}
const a = activate(sandbox, ['android'], now)[0]
check(Date.parse(a.expiresAt) === now + 86400000)
check(gate.reload() && grant(OLD.android, 'android').ok && grant(OLD.ios, 'ios').ok)
now += 3600000
check(activate(sandbox, ['android'], now)[0].expiresAt === a.expiresAt)
const i = activate(sandbox, ['ios'], now)[0]
check(Date.parse(i.expiresAt) === now + 86400000)
check(gate.reload())
// Re-copying the original policy must not extend an already activated release.
fs.writeFileSync(cp, JSON.stringify(original))
const repeated = activate(sandbox, ['android', 'ios'], now + 1000)
check(repeated[0].expiresAt === a.expiresAt && repeated[1].expiresAt === i.expiresAt)
check(gate.reload())
now = Date.parse(a.expiresAt) - 1
check(grant(OLD.android, 'android').ok)
now++
check(!grant(OLD.android, 'android').ok && grant(OLD.ios, 'ios').ok)
check(grant(IDS.android, 'android').ok && grant(IDS.ios, 'ios').ok)
now = Date.parse(i.expiresAt)
check(!grant(OLD.ios, 'ios').ok)
check(grant(IDS.android, 'android').ok && grant(IDS.ios, 'ios').ok)
const policy = JSON.parse(fs.readFileSync(cp, 'utf8'))
check(policy.enforce === original.enforce && policy.updateMessage === original.updateMessage)
const iosGrant = grant(IDS.ios, 'ios'), androidGrant = grant(IDS.android, 'android')
policy.builds.find(b => b.id === IDS.android).enabled = false
fs.writeFileSync(cp, JSON.stringify(policy)); check(gate.reload())
check(!gate.check(androidGrant.data.token).ok && gate.check(iosGrant.data.token).ok)
gate.close()
fs.writeFileSync(path.join(pair, 'protocol-verification.json'), JSON.stringify({ checks, passed: true, real_server_class: true,
  simulated_clock: true, platform_isolation: true, grace_seconds: 86400, idempotent_activation: true, live_server_changed: false }, null, 2))
console.log('Passed ' + checks + ' paired admission / platform isolation / activation expiry checks.')
