const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { randomUUID } = require('node:crypto')

exports.fixture = function fixture(prefix) {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), `${prefix}-`))
    Object.assign(process.env, { DATA_DIR: directory, CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off',
        GACHA_SEED_DIR: path.join(directory, 'seeds') })
    fs.mkdirSync(process.env.GACHA_SEED_DIR)
    const out = process.env.STARPOINT_TEST_OUT_DIR || path.resolve(__dirname, '../../out')
    const load = name => require(path.join(out, name))
    const db = load('data/db').getDb()
    function create() {
        const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: prefix, idpId: randomUUID(), status: 'normal' })
        const player = load('data/domains/player').insertDefaultPlayerSync(account.id)
        load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
        const viewer = 880000000 + player.id
        db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, '2099-01-01T00:00:00Z')
        return { ...player, accountId: account.id, viewer }
    }
    async function close() {
        await load('lib/seed-validator').default.close()
        db.close()
        fs.rmSync(directory, { recursive: true })
    }
    return { directory, out, load, db, create, close }
}
