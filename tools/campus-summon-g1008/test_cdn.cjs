// Exercise the existing deployed-route build with source-side .108 assets.
// Fastify.inject is in-process; no service listener or runtime mirror is used.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const root = path.resolve(__dirname, '../..');
const index = process.argv.indexOf('--work');
assert.ok(index >= 0 && process.argv[index + 1], '--work is required');
const work = path.resolve(process.argv[index + 1]);
const pristine = fs.realpathSync(path.join(root, '.cdn'));
assert.ok(!work.toLowerCase().startsWith(pristine.toLowerCase() + path.sep));
fs.mkdirSync(work, { recursive: true });
process.env.DATA_DIR = path.join(work, 'cdn-test-data');
const Fastify = require(path.join(root, 'node_modules/fastify'));
const route = require(path.join(root, 'out/routes/cn/asset')).default;
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'assets/asset-patch/manifest.json')));
const edge = manifest.patches.find(item => item.enabled && item.version === '1.4.108');
assert.ok(edge);
const repair = 'pinball-1.4.107-1.4.108-3-campus-summon-g1008.zip';
assert.ok(edge.chain.includes(repair));
const digest = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');

async function main() {
    const app = Fastify({ logger: false });
    const receipts = [];
    await app.register(route);
    try {
        for (const device of ['Android', 'iOS']) {
            for (const resVersion of ['1.4.107', '1.4.108']) {
                const response = await app.inject({ method: 'POST', url: '/get_path',
                    headers: { device, res_ver: resVersion }, payload: {} });
                assert.equal(response.statusCode, 200);
                const data = response.json().data;
                assert.equal(data.info.target_asset_version, '1.4.108');
                if (resVersion === '1.4.107') {
                    assert.equal(data.diff.length, 1);
                    assert.equal(data.diff[0].original_version, '1.4.107');
                    assert.equal(data.diff[0].version, '1.4.108');
                    const archives = data.diff[0].archive;
                    assert.deepEqual(archives.map(item => path.posix.basename(item.location)), edge.chain);
                    for (const archive of archives) {
                        const name = path.posix.basename(archive.location);
                        const file = path.join(root, 'assets/asset-patch/active', name);
                        const integrity = edge.archive_integrity.find(item => item.name === name);
                        assert.equal(archive.size, fs.statSync(file).size);
                        assert.equal(digest(file), integrity.sha256);
                    }
                    receipts.push({ device, from: resVersion, to: data.info.target_asset_version,
                                    archives: archives.map(item => ({ name: path.posix.basename(item.location), size: item.size })) });
                } else {
                    assert.equal(data.diff, null);
                    assert.equal(data.full, null);
                    receipts.push({ device, from: resVersion, to: resVersion, no_repeat_download: true });
                }
            }
        }
        const report = { passed: true, in_process_route_test: true, runtime_service_or_device_tested: false,
            source_route_sha256: digest(path.join(root, 'src/routes/cn/asset.ts')),
            compiled_route_sha256: digest(path.join(root, 'out/routes/cn/asset.js')),
            receipts };
        fs.writeFileSync(path.join(work, 'cdn-distribution.json'), JSON.stringify(report, null, 2) + '\n');
        console.log(JSON.stringify(report));
    } finally {
        await app.close();
        const db = require(path.join(root, 'out/data/db')).getDb();
        if (db.open) db.close();
    }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
