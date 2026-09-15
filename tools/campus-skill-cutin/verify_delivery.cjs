// Exercise actual resource route handlers without starting a server or database.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '../..');
const audit = path.join(root, 'assets/asset-patch/audit/campus-skill-cutin-1.4.109');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const manifestBytes = fs.readFileSync(path.join(root, 'assets/asset-patch/manifest.json'));
const manifest = JSON.parse(manifestBytes);
const report = JSON.parse(fs.readFileSync(path.join(audit, 'report.json')));
const patch = manifest.patches.find(x => x.enabled && x.version === '1.4.109');
assert.equal(sha(manifestBytes), report.manifest_after_sha256);
assert.equal(manifest.cdn_version, '1.4.109');
assert.equal(patch.depends_on, '1.4.108');
assert.deepEqual(patch.chain, [
  'pinball-1.4.108-1.4.109-1-author-update-fusion.zip',
  'pinball-1.4.108-1.4.109-3-campus-skill-cutin.zip',
]);
let total = 0;
for (const receipt of patch.archive_integrity) {
  const bytes = fs.readFileSync(path.join(root, 'assets/asset-patch/active', receipt.name));
  assert.equal(bytes.length, receipt.size);
  assert.equal(sha(bytes), receipt.sha256);
  total += bytes.length;
}
assert.equal(total, patch.archive_size);
const asset = require(path.join(root, 'out/routes/cn/asset.js'));
const version = require(path.join(root, 'out/lib/version.js'));
assert.equal(version.getEffectiveVersion(), '1.4.109');
(async () => {
  const handlers = new Map();
  await asset.default({post: (name, handler) => handlers.set(name, handler)});
  async function call(name, device, res_ver) {
    let status, body;
    const reply = {type() { return this; }, status(n) { status = n; return this; }, send(x) { body = x; return this; }};
    await handlers.get(name)({headers: {host: '127.0.0.1:8001', device, res_ver}}, reply);
    assert.equal(status, 200);
    return body;
  }
  const platforms = {};
  for (const device of ['android', 'ios']) {
    const update = (await call('/get_path', device, '1.4.108')).data;
    assert.equal(update.info.target_asset_version, '1.4.109');
    assert.equal(update.diff.length, 1);
    const group = update.diff[0];
    assert.equal(group.original_version, '1.4.108');
    assert.equal(group.version, '1.4.109');
    assert.deepEqual(group.archive.map(a => path.posix.basename(a.location)), patch.chain);
    assert.equal(group.archive.reduce((n, a) => n + a.size, 0), total);
    assert.equal(asset.getAssetDownloadSize('1.4.108', device), total);
    assert.equal((await call('/version_info', device, '1.4.108')).data.total_size, total);
    const current = await call('/get_path', device, '1.4.109');
    assert.equal(current.data.diff, null);
    assert.equal(current.data.full, null);
    assert.equal(current.data_headers.asset_update, false);
    platforms[device] = {from: '1.4.108', to: '1.4.109', archives: patch.chain, bytes: total,
      already_current_has_no_update: true};
  }
  const result = {status: 'passed', actual_asset_handlers: true, archive_integrity_verified: true,
    manifest_sha256: sha(manifestBytes), platforms, listener_started: false,
    runtime_synced: false, player_database_accessed: false, device_tested: false};
  fs.writeFileSync(path.join(audit, 'delivery-verification.json'), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
