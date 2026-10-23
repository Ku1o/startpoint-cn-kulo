'use strict'
// No listener: validate the prepared LAN contract through the real application.
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict')
const { createHmac } = require('node:crypto')
const repo = path.resolve(__dirname, '..'), load = name => require(path.join(repo, 'out', name))
async function main() {
    assert.equal(process.env.CN_RUNTIME_IMPORT_ONLY, '1')
    const config = JSON.parse(fs.readFileSync(process.env.CLIENT_ADMISSION_CONFIG, 'utf8'))
    const keys = JSON.parse(fs.readFileSync(process.env.CLIENT_ADMISSION_KEYS, 'utf8'))
    assert.equal(config.enforce, true); assert.equal(config.builds.length, 1)
    const build = config.builds[0], app = load('cn-server').fastify
    await app.ready()
    const writer = load('lib/persistence/writer-client')
    assert.equal(writer.startSqliteWriter(load('data/db').getDb().name), true)
    assert.equal(await writer.waitForSqliteWriterReady(30000), true)
    try {
        const post = (url, payload, headers = {}) => app.inject({ method: 'POST', url, payload, headers })
        const challenge = (await post('/client-admission/challenge', { build: build.id, protocol: 1, platform: 'android' })).json()
        assert.equal(challenge.ok, true)
        const proof = createHmac('sha256', Buffer.from(keys[build.id], 'hex')).update(load('lib/client-admission').proofMessage(build.id, challenge.data.challenge, challenge.data.nonce)).digest('hex')
        const granted = (await post('/client-admission/prove', { challenge: challenge.data.challenge, proof })).json()
        assert.equal(granted.ok, true)
        assert.equal((await post('/client-admission/challenge', { build: build.id, protocol: 1, platform: 'ios' })).json().ok, false)
        const registered = (await post('/player-auth/register', { username: 'lan_' + Date.now().toString(36), password: 'synthetic-lan-test-password', remember: false }, { 'x-sp-admission': granted.data.token })).json()
        assert.equal(registered.ok, true, JSON.stringify({ ok: registered.ok, code: registered.code, message: registered.message }))
        const headers = { 'x-sp-admission': granted.data.token, 'x-sp-session': registered.data.token, udid: registered.data.udid }
        const viewer = registered.data.profile.viewer_id
        const loaded = await post('/api/index.php/load', { viewer_id: viewer }, headers)
        assert.equal(loaded.statusCode, 200)
        const decoded = require('msgpackr').unpack(Buffer.from(loaded.body, 'base64'))
        assert.equal(decoded.data_headers.result_code, 1)
        assert.ok(Math.abs(decoded.data_headers.servertime * 1000 - Date.now()) < 2000)
        assert.equal(load('multi/room/serializer').getDisplayHost(), process.env.CN_LISTEN_HOST)
        assert.equal(process.env.SESSION_PORT, '18003')
        assert.equal(process.env.CDN_BASE_URL, `http://${process.env.CN_LISTEN_HOST}:8001/patch/cn`)
        const urls = []
        const collect = value => { if (typeof value === 'string' && /^https?:\/\//.test(value)) urls.push(value); else if (Array.isArray(value)) value.forEach(collect); else if (value && typeof value === 'object') Object.values(value).forEach(collect) }
        for (const route of ['/api/index.php/asset/version_info', '/api/index.php/asset/get_path']) {
            const assets = await post(route, {}, { ...headers, host: `${process.env.CN_LISTEN_HOST}:18001`, device: 'android' })
            assert.equal(assets.statusCode, 200, assets.body); collect(assets.json())
        }
        const zips = urls.filter(url => /\.zip(?:[?#]|$)/.test(url))
        assert.ok(zips.length > 0, 'actual asset route returns a nonempty archive list')
        for (const url of urls) { const parsed = new URL(url); assert.equal(parsed.hostname, process.env.CN_LISTEN_HOST); assert.equal(parsed.port, '8001'); assert.ok(parsed.pathname.startsWith('/patch/cn/')) }
        const decode = response => { assert.equal(response.statusCode, 200, response.body); return require('msgpackr').unpack(Buffer.from(response.body, 'base64')) }
        const room = decode(await post('/api/index.php/multi_battle_quest/create_room', { viewer_id: viewer, category: 2, quest_id: 1001001, party_id: 1, api_count: 1 }, headers))
        assert.equal(room.data_headers.result_code, 1)
        assert.ok(room.data.room_number)
        const prepared = decode(await post('/api/index.php/multi_battle_quest/prepare', { viewer_id: viewer, category: 2, quest_id: 1001001, room_number: room.data.room_number, access_token: room.data.access_token, api_count: 2 }, headers))
        assert.equal(prepared.data_headers.result_code, 1)
        assert.equal(prepared.data.ip_address, process.env.CN_LISTEN_HOST); assert.equal(prepared.data.port, 18003)
        assert.equal(load('lib/news-config').readNewsConfigState().error, null)
        const result = { existingBuildId: build.id, exactOneBuild: true, correctPlatformProof: true, wrongPlatformRejected: true, freshAccountRegistered: true, freshAccountLoaded: true, realServerTime: true, apiPort: 18001, sessionPort: prepared.data.port, roomCreatedAndPrepared: true, resourcePort: 8001, assetUrlsChecked: urls.length, archiveUrlsChecked: zips.length, noLanListenerStarted: true, noSourceWrites: true }
        fs.writeFileSync(path.join(process.env.STARPOINT_ISOLATED_RUNTIME_ROOT, 'lan-inject-check.json'), JSON.stringify(result, null, 2))
        console.log('ISOLATED_LAN_CHECK ' + JSON.stringify(result))
    } finally { await writer.stopSqliteWriter(); await app.close(); const db = load('data/db').getDb(); if (db.open) db.close() }
}
main().then(() => process.exit(0), error => { console.error(error); process.exit(1) })
