const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'asset-empty-update-'));
process.env.DATA_DIR = path.join(temp, 'db');
process.env.CDN_DIR = path.join(temp, 'cdn');
// Real tiny archive tasks must not be mistaken for an empty update (UI rounds sizes to MB).
for (const platform of ['common', 'medium', 'android', 'ios']) {
    const dir = path.join(process.env.CDN_DIR, 'cn', `archive-${platform}-full`);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, 'fixture.zip'), Buffer.alloc(22));
    fs.mkdirSync(path.join(process.env.CDN_DIR, 'cn', `archive-${platform}-diff`), { recursive: true });
}
const Fastify = require('fastify');
const routes = require('../out/routes/cn/asset').default;
const { getEffectiveVersion } = require('../out/lib/version');

test.after(() => {
    const db = require('../out/data/db').getDb();
    if (db.open) db.close();
    assert.equal(path.dirname(temp), os.tmpdir());
    fs.rmSync(temp, { recursive: true, force: true });
});

test('current/higher version uses None, genuine initial and incremental tasks remain downloadable', async () => {
    const app = Fastify({ logger: false });
    await app.register(routes);
    try {
        for (const device of ['Android', 'iOS']) {
            for (const version of [getEffectiveVersion(), '1.4.999']) {
                for (const asset_size of ['fulfill', 'shortened', 'delayed']) {
                    const headers = { device, res_ver: version, asset_size };
                    const response = await app.inject({ method: 'POST', url: '/get_path', headers, payload: {} });
                    assert.equal(response.statusCode, 200);
                    const { data, data_headers } = response.json();
                    assert.equal(data.full, null);
                    assert.equal(data.diff, null);
                    assert.equal(data_headers.asset_update, false);
                    assert.equal(data.info.target_asset_version, version);
                    const size = await app.inject({ method: 'POST', url: '/version_info', headers, payload: {} });
                    assert.equal(size.json().data.total_size, 0);
                }
            }
            const first = (await app.inject({ method: 'POST', url: '/get_path', headers: { device }, payload: {} })).json();
            assert.equal(first.data.info.is_initial, true);
            assert.equal(first.data_headers.asset_update, true);
            assert.equal(first.data.full.archive.length, 3);
            assert.equal(first.data.full.archive.reduce((n, x) => n + x.size, 0), 66);
            const upgrade = (await app.inject({ method: 'POST', url: '/get_path',
                headers: { device, res_ver: '1.4.103' }, payload: {} })).json();
            assert.equal(upgrade.data_headers.asset_update, true);
            assert.ok(upgrade.data.diff.some(group => group.archive.length > 0));
        }
    } finally { await app.close(); }
});
