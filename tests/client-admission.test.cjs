const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), crypto = require('node:crypto')
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-admission-'))
process.env.DATA_DIR = path.join(dir, 'data')
require('ts-node/register/transpile-only')
const { ClientAdmission, installClientAdmission, proofMessage } = require(process.env.ADMISSION_TEST_BUILT === '1' ? '../out/lib/client-admission' : '../src/lib/client-admission')
const Fastify = require('fastify'), { pack, unpack } = require('msgpackr')
let now = Date.now(), warnings = 0, checks = 0
const configPath = path.join(dir, 'policy.json'), keysPath = path.join(dir, 'keys.json')
const keys = { buildA: crypto.randomBytes(32).toString('hex'), buildB: crypto.randomBytes(32).toString('hex') }
const policy = { enforce: true, updateMessage: '请到群聊下载新版安装包。', builds: Object.keys(keys).map(id => ({ id, name: id, enabled: true, allowUntil: null })) }
const save = () => { fs.writeFileSync(configPath, JSON.stringify(policy)); fs.writeFileSync(keysPath, JSON.stringify(keys)) }
const check = (value, message) => { assert.ok(value, message); checks++ }
save()
const gate = new ClientAdmission(configPath, keysPath, () => now, () => warnings++)
check(gate.reload(), 'initial policy')
function exchange(build = 'buildA', ip = 'local') {
  const c = gate.challenge({ protocol: 1, build }, ip)
  assert.equal(c.ok, true)
  const body = { challenge: c.data.challenge, proof: crypto.createHmac('sha256', Buffer.from(keys[build], 'hex')).update(proofMessage(build, c.data.challenge, c.data.nonce)).digest('hex') }
  return { result: gate.prove(body, ip), body }
}
async function main() {
  check(!gate.check('').ok, 'legacy denied')
  const a = exchange(), b = exchange('buildB')
  check(a.result.ok && b.result.ok, 'multiple builds simultaneously admitted')
  check(!gate.prove(a.body, 'local').ok, 'challenge cannot be replayed')
  const token = a.result.data.token
  check(gate.check(token).ok, 'ticket valid before login')
  check(!gate.check(token, '', true).ok, 'pre-login ticket cannot access player data or TCP')
  gate.bind(token, 'account-session-A')
  check(gate.check(token, 'account-session-A', true).ok, 'session binding')
  check(!gate.check(token, 'account-session-B', true).ok, 'session substitution rejected')
  check(!gate.check(token, '', true).ok, 'missing bound session rejected')
  const c = gate.challenge({ protocol: 1, build: 'buildA' }, 'wrong-proof')
  check(!gate.prove({ challenge: c.data.challenge, proof: '00'.repeat(32) }, 'wrong-proof').ok, 'bad proof rejected')
  const oldExpiry = a.result.data.expires_at; now += 20 * 60000
  const renewed = gate.renew(token, 'account-session-A', 'local')
  check(renewed.ok && renewed.data.token === token && renewed.data.expires_at > oldExpiry, 'renew preserves TCP ticket')
  policy.builds[0].allowUntil = new Date(now + 5000).toISOString().replace('.000', '')
  // Use seconds precision, explicit timezone.
  policy.builds[0].allowUntil = new Date(now + 5000).toISOString().replace(/\.\d{3}Z$/, 'Z')
  save(); check(gate.reload() && gate.check(token).ok, 'grace period stays allowed')
  now += 6000; check(!gate.check(token).ok, 'expiry enforced without reload')
  policy.builds[0].allowUntil = null; policy.builds[0].enabled = false; save(); gate.reload()
  check(!gate.check(token).ok && gate.check(b.result.data.token).ok, 'revocation only targets selected build')
  policy.builds[0].enabled = true; save(); gate.reload()
  check(!gate.check(token).ok, 're-enable does not resurrect revoked tickets')
  fs.writeFileSync(configPath, '{'); check(!gate.reload() && gate.check(b.result.data.token).ok, 'partial copy retains last valid policy')
  gate.reload(); check(warnings === 1, 'invalid configuration log deduplicated')
  const missing = new ClientAdmission('missing-policy', 'missing-keys', () => now, () => {})
  missing.reload(); check(!missing.check('').ok, 'missing initial policy fails closed')
  save(); gate.reload()
  const beforeRotation = exchange().result.data.token
  keys.buildA = crypto.randomBytes(32).toString('hex'); save(); gate.reload()
  check(!gate.check(beforeRotation).ok, 'key rotation invalidates old tickets')
  const badTime = policy.builds[0].allowUntil
  policy.builds[0].allowUntil = '2026-09-20 20:00'; save(); check(!gate.reload(), 'ambiguous timezone rejected')
  policy.builds[0].allowUntil = badTime; save(); gate.reload()
  policy.enforce = false; save(); gate.reload()
  check(gate.check('', '', true).ok, 'explicit transition supports legacy clients')
  check(!gate.check('forged', '', true).ok, 'invalid supplied ticket never downgraded to legacy')
  policy.enforce = true; save(); gate.reload()
  const app = Fastify({ logger: false }); let mutations = 0
  installClientAdmission(app, gate)
  app.addHook('onSend', async (_req, reply, payload) => reply.getHeader('content-type') === 'application/x-msgpack' && typeof payload === 'object' ? pack(payload) : payload)
  app.post('/player-auth/login', async () => ({ ok: true, data: { token: 'http-login-session' } }))
  app.post('/api/index.php/tool/signup', async () => { mutations++; return { allowed: true } })
  app.post('/api/index.php/assetintitle/version_info_in_title', async () => ({ allowed: true }))
  app.post('/api/index.php/asset/get_path', async (_req, reply) => { reply.type('application/json'); reply.send({ data: { diff: null } }) })
  app.post('/api/index.php/single_battle_quest/finish', async () => { mutations++; return { allowed: true } })
  app.get('/admin/health', async () => ({ ok: true }))
  const post = (url, payload = {}, headers = {}) => app.inject({ method: 'POST', url, payload, headers })
  let res = await post('/api/index.php/tool/signup', {}, { device: 'ios', requestedby: 'ios', 'user-agent': 'iOS;' })
  check(unpack(res.rawPayload).data_headers.client_admission.ok === false && mutations === 0, 'platform spoof does not bypass gate')
  res = await post('/player-auth/login'); check(res.json().ok === false, 'login route protected')
  let challenge = (await post('/client-admission/challenge', { build: 'buildA', protocol: 1 })).json().data
  const proof = crypto.createHmac('sha256', Buffer.from(keys.buildA, 'hex')).update(proofMessage('buildA', challenge.challenge, challenge.nonce)).digest('hex')
  const grant = (await post('/client-admission/prove', { challenge: challenge.challenge, proof })).json()
  check(grant.ok, 'real HTTP challenge / proof')
  const headers = { 'x-sp-admission': grant.data.token }
  check((await post('/api/index.php/assetintitle/version_info_in_title', {}, headers)).json().allowed, 'title bootstrap requires ticket without account')
  check((await post('/api/index.php/asset/get_path', {}, headers)).json().data.diff === null, 'legacy async resource reply is not delayed by global serialization hooks')
  check(unpack((await post('/api/index.php/tool/signup', {}, headers)).rawPayload).data_headers.client_admission.ok === false, 'preauth signup blocked')
  check((await post('/player-auth/login', {}, headers)).json().ok, 'admitted login succeeds')
  headers['x-sp-session'] = 'http-login-session'
  check((await post('/api/index.php/tool/signup', {}, headers)).json().allowed, 'login response automatically binds ticket')
  const before = mutations
  delete headers['x-sp-session']
  check(unpack((await post('/api/index.php/single_battle_quest/finish', {}, headers)).rawPayload).data_headers.client_admission.ok === false && mutations === before, 'no-session settlement rejected before mutation')
  headers['x-sp-session'] = 'http-login-session'
  policy.builds = policy.builds.filter(b => b.id !== 'buildA'); save(); gate.reload()
  check(unpack((await post('/api/index.php/single_battle_quest/finish', {}, headers)).rawPayload).data_headers.client_admission.ok === false && mutations === before, 'deleting build revokes existing HTTP session')
  check((await app.inject('/admin/health')).json().ok, 'management remains accessible')
  const limitedGate = new ClientAdmission(configPath, keysPath, () => now, () => {}); limitedGate.reload()
  for (let i = 0; i < 121; i++) res = limitedGate.challenge({ build: 'buildB', protocol: 1 }, 'flood')
  check(res.code === 'RATE_LIMITED', 'handshake flood limited')
  const perfToken = exchange('buildB', 'perf').result.data.token; gate.bind(perfToken, 'perf-session')
  const start = performance.now()
  for (let i = 0; i < 100000; i++) assert.ok(gate.checkActivity(perfToken, 'perf-session').ok)
  const elapsed = performance.now() - start
  await app.close()
  console.log(JSON.stringify({ passed: true, checks, hotPathChecks: 100000, hotPathTotalMs: Math.round(elapsed), hotPathMicrosecondsPerCheck: elapsed / 100, isolatedData: dir }))
}
main().catch(e => { console.error(e); process.exitCode = 1 })
