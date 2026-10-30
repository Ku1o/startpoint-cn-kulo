const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require('../' + (compiled ? 'out/' : 'src/') + name)
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'water-gerald-board-'))
process.env.DATA_DIR = directory
process.env.GAME_ROUTINE_LOGS = 'off'
Object.assign(process.env, { CN_WRITER_THREAD: '0', MULTI_REALTIME_PROCESS: '0',
    MULTI_REALTIME_OWNER_CHILD: '0', GACHA_SEED_DIR: path.join(directory, 'seeds') })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const Fastify = require('fastify')
const { pack, unpack } = require('msgpackr')
const routes = load('routes/api/character/bond').default
const { getDb } = load('data/db')
const { insertAccountSync } = load('data/domains/account')
const { insertDefaultPlayerSync } = load('data/domains/player')
const characters = load('data/domains/character')
const { getCharacterExpCap } = load('lib/character-overlimit')
const db = getDb(), app = Fastify()
app.addHook('onSend', (_request, reply, payload, done) =>
    done(null, reply.getHeader('content-type') === 'application/x-msgpack' ? pack(payload).toString('base64') : payload))
test.before(async () => { await app.register(routes); await app.ready() })
test.after(async () => {
    await app.close(); await load('lib/seed-validator').default.close()
    db.close(); fs.rmSync(directory, { recursive: true })
})
let sequence = 0
function player(characterId = 129989, exp = getCharacterExpCap(129989, 5, 8) - 1) {
    const account = insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'test',
        idpId: 'water-board-' + ++sequence, status: 'normal' })
    const id = insertDefaultPlayerSync(account.id).id, viewer = 871000000 + id
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES (?,?,?,2)')
        .run(String(viewer), account.id, '2099-01-01T00:00:00.000Z')
    characters.insertDefaultPlayerCharacterSync(id, characterId)
    characters.updatePlayerCharacterSync(id, characterId, { overLimitStep: characterId === 129989 ? 8 : 4, exp })
    characters.updatePlayerCharacterBondTokenSync(id, characterId, { manaBoardIndex: 1, status: 1 })
    return { id, viewer, characterId }
}
const open = (p, index) => app.inject({ method: 'POST', url: '/open_mana_board',
    payload: { viewer_id: p.viewer, character_id: p.characterId, mana_board_index: index, api_count: 1 } })

test('water Gerald level 119 cannot open board two and the failed request changes no progress', async () => {
    const p = player(), before = characters.getPlayerCharacterSync(p.id, p.characterId)
    const response = await open(p, 2)
    assert.equal(response.statusCode, 400)
    assert.match(response.json().message, /level is too low/)
    assert.deepEqual(characters.getPlayerCharacterSync(p.id, p.characterId), before)
})

test('water Gerald level 120 can open board two at the exact cumulative EXP threshold', async () => {
    const threshold = getCharacterExpCap(129989, 5, 8)
    assert.equal(threshold, 679988)
    const p = player(129989, threshold)
    const response = await open(p, 2)
    assert.equal(response.statusCode, 200)
    assert.equal(unpack(Buffer.from(response.body, 'base64')).data.character_list[0].mana_board_index, 2)
    const character = characters.getPlayerCharacterSync(p.id, p.characterId)
    assert.equal(character.manaBoardIndex, 2)
    assert.equal(character.exp, threshold)
    assert.equal(character.overLimitStep, 8)
})

test('first board and other characters keep their existing level requirements', async () => {
    const first = player()
    assert.equal((await open(first, 1)).statusCode, 200)
    const ordinary = player(111183)
    assert.equal((await open(ordinary, 2)).statusCode, 200)
})

test('level 120 still needs the existing previous-board completion proof', async () => {
    const p = player(129989, getCharacterExpCap(129989, 5, 8))
    characters.updatePlayerCharacterBondTokenSync(p.id, p.characterId, { manaBoardIndex: 1, status: 0 })
    const response = await open(p, 2)
    assert.equal(response.statusCode, 400)
    assert.match(response.json().message, /previous mana board/)
})
