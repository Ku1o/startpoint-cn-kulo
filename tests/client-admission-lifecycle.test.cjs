const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path'), crypto = require('node:crypto')
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-admission-lifecycle-'))
process.env.DATA_DIR = path.join(dir, 'data')
require('ts-node/register/transpile-only')
const { ClientAdmission, installClientAdmission, proofMessage } = require(process.env.ADMISSION_TEST_BUILT === '1' ? '../out/lib/client-admission' : '../src/lib/client-admission')
const auth = require('../src/lib/player-login'), loginRoutes = require('../src/routes/cn/playerLogin')
const { getDb } = require('../src/data/db')
auth.initializePlayerLogin()
const account = auth.registerPlayerLogin('AdmissionLifecycle', 'LocalTrialOnly123', true), accountSession = account.token
const Fastify = require('fastify'), { pack, unpack } = require('msgpackr')
const config = path.join(dir, 'config.json'), keyPath = path.join(dir, 'keys.json'), minute = 60000
let now = Date.parse('2026-09-15T00:00:00Z'), checks = 0, mutations = 0
const keys = { android: crypto.randomBytes(32).toString('hex'), ios: crypto.randomBytes(32).toString('hex') }
const policy = { enforce: true, updateMessage: '请到群聊更新。', builds: Object.keys(keys).map(platform => ({ id: platform, name: platform, platform, enabled: true, allowUntil: null })) }
const save = () => { fs.writeFileSync(config, JSON.stringify(policy)); fs.writeFileSync(keyPath, JSON.stringify(keys)) }
save()
let gate = new ClientAdmission(config, keyPath, () => now, () => {}); gate.reload()
const app = Fastify({ logger: false })
// Delegate to a new empty grant store for the process-restart case, without changing HTTP hooks.
const proxy = new Proxy({}, { get: (_target, name) => typeof gate[name] === 'function' ? gate[name].bind(gate) : gate[name] })
installClientAdmission(app, proxy)
loginRoutes.installPlayerLoginGuard(app)
app.register(loginRoutes.default)
app.addHook('onSend', async (_req, reply, payload) => reply.getHeader('content-type') === 'application/x-msgpack' && typeof payload === 'object' ? pack(payload) : payload)
app.post('/api/index.php/load', async () => { mutations++; return { loaded: true } })
const check = (v, msg) => { assert.ok(v, msg); checks++ }
const post = (url, payload = {}, headers = {}) => app.inject({ method: 'POST', url, payload, headers })
async function exchange(platform = 'android', signingKey = keys[platform]) {
  const c = (await post('/client-admission/challenge', { build: platform, platform, protocol: 1 })).json()
  if (!c.ok) return c
  const proof = crypto.createHmac('sha256', Buffer.from(signingKey, 'hex')).update(proofMessage(platform, c.data.challenge, c.data.nonce)).digest('hex')
  return (await post('/client-admission/prove', { challenge: c.data.challenge, proof })).json()
}
const headers = token => ({ 'x-sp-admission': token, 'x-sp-session': accountSession })
const renew = (token, session = accountSession) => post('/client-admission/renew', {}, { ...headers(token), 'x-sp-session': session }).then(r => r.json())
async function main() {
  check(!(await exchange('ios', keys.android)).ok, 'Android key cannot prove iOS build')
  check(!(await post('/client-admission/challenge', { build: 'android', platform: 'ios', protocol: 1 })).json().ok, 'platform must match configured build')
  for (const platform of ['android', 'ios']) {
    const grant = await exchange(platform), token = grant.data.token
    check(grant.ok && grant.data.platform === platform && grant.data.expires_in_ms === 30 * minute && grant.data.renew_after_ms === 25 * minute, 'server-relative timing contract for ' + platform)
    check((await post('/player-auth/resume', { token: accountSession }, headers(token))).json().ok, 'real account resume binds ' + platform)
    for (let i = 0; i < 8; i++) { now += 20 * minute; check((await post('/api/index.php/load', {}, headers(token))).json().loaded, 'HTTP active lease survives repeated expiry for ' + platform) }
    now += 29 * minute
    check(!(await renew(token, 'wrong-session')).ok, 'wrong session cannot refresh')
    now += 2 * minute
    const before = mutations, expired = unpack((await post('/api/index.php/load', {}, headers(token))).rawPayload).data_headers.client_admission
    check(!expired.ok && expired.action === 'renew' && mutations === before, 'expired request does not mutate player state')
    policy.builds.find(b => b.id === platform).name += ' comment'; save(); gate.reload()
    const recovered = await renew(token)
    check(recovered.ok && recovered.data.token === token, 'metadata reload preserves authenticated renewal grace')
    const duplicate = await renew(token)
    check(duplicate.ok && duplicate.data.token === token, 'retry after lost renew response preserves token')
    check((await post('/api/index.php/load', {}, headers(token))).json().loaded, 'gameplay resumes after authenticated renewal')
    now += 36 * minute
    check((await renew(token)).action === 'handshake', 'grace is bounded')
    const fresh = await exchange(platform)
    check(fresh.ok && fresh.data.token !== token, 'long suspension can obtain fresh ticket')
    const resumed = (await post('/player-auth/resume', { token: accountSession }, headers(fresh.data.token))).json()
    check(resumed.ok && resumed.data.profile.viewer_id === account.profile.viewer_id, 'long suspension preserves actual account identity through resume')
  }
  const unbound = await exchange(); now += 31 * minute
  check(!(await renew(unbound.data.token, '')).ok, 'unbound tickets have no late-renew grace')
  const deadline = await exchange('ios'); gate.bind(deadline.data.token, accountSession)
  policy.builds[1].allowUntil = new Date(now + minute).toISOString().replace('.000Z', 'Z'); save(); gate.reload()
  now += 2 * minute
  check(!(await renew(deadline.data.token)).ok && !gate.checkActivity(deadline.data.token, accountSession).ok, 'activity and grace cannot bypass build deadline')
  policy.builds[1].allowUntil = null; save(); gate.reload()
  const oldChallenge = (await post('/client-admission/challenge', { build: 'ios', protocol: 1 })).json().data
  policy.builds[1].enabled = false; save(); gate.reload()
  policy.builds[1].enabled = true; save(); gate.reload()
  const oldProof = crypto.createHmac('sha256', Buffer.from(keys.ios, 'hex')).update(proofMessage('ios', oldChallenge.challenge, oldChallenge.nonce)).digest('hex')
  check(!(await post('/client-admission/prove', { challenge: oldChallenge.challenge, proof: oldProof })).json().ok, 'revocation invalidates pending challenges')
  const rotated = await exchange('ios'); gate.bind(rotated.data.token, accountSession); now += 31 * minute
  keys.ios = crypto.randomBytes(32).toString('hex'); save(); gate.reload()
  check(!(await renew(rotated.data.token)).ok, 'rotation invalidates grace-period credentials')
  const restart = await exchange(); gate.bind(restart.data.token, accountSession)
  gate = new ClientAdmission(config, keyPath, () => now, () => {}); gate.reload()
  const before = mutations, rejection = unpack((await post('/api/index.php/load', {}, headers(restart.data.token))).rawPayload).data_headers.client_admission
  check(rejection.action === 'handshake' && !rejection.message.includes('群聊') && mutations === before, 'restart requests handshake rather than obsolete APK update')
  const afterRestart = await exchange()
  await post('/player-auth/resume', { token: accountSession }, headers(afterRestart.data.token))
  check((await post('/api/index.php/load', {}, headers(afterRestart.data.token))).json().loaded, 'restart handshake and resume restore access')
  const beforeLogout = mutations
  await post('/player-auth/logout', { token: accountSession }, headers(afterRestart.data.token))
  const loggedOut = unpack((await post('/api/index.php/load', {}, headers(afterRestart.data.token))).rawPayload)
  check(loggedOut.data_headers.result_code === 516 && mutations === beforeLogout, 'live admission ticket never bypasses real account logout')
  policy.builds[1].platform = 'windows'; save(); check(!gate.reload(), 'invalid platform configuration rejected')
  policy.builds[1].platform = 'ios'; save(); gate.reload()
  for (let i = 0; i < 121; i++) gate.challenge({ build: 'android', protocol: 1 }, 'flood')
  const limited = gate.challenge({ build: 'android', protocol: 1 }, 'flood')
  check(limited.action === 'retry' && limited.retry_after_ms === minute && !limited.message.includes('群聊'), 'transient throttle does not claim APK is obsolete')
  console.log(JSON.stringify({ passed: true, checks, simulatedTime: true, fastifyHttp: true, realAccountResume: true, isolatedDatabase: true, platforms: ['android', 'ios'] }))
}
main().catch(e => { console.error(e); process.exitCode = 1 }).finally(async () => {
  await app.close()
  await require('../src/multi/npc/player-party-pool').stopQuestNpcPartyPoolWorker()
  getDb().close()
  setImmediate(() => process.exit(process.exitCode || 0))
})
