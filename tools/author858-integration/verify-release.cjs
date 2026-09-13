// Execute the actual asset route handlers locally, without a listener or database.
const fs = require('fs'), path = require('path'), assert = require('node:assert/strict'), crypto = require('crypto');
const repo = path.resolve(__dirname, '../..'), work = path.resolve(process.argv[2]);
const read = file => JSON.parse(fs.readFileSync(file, 'utf8'));
const sha = data => crypto.createHash('sha256').update(data).digest('hex');
const report = read(path.join(work, 'apply-report.json'));
const manifest = read(path.join(repo, 'assets/asset-patch/manifest.json'));
const patch = manifest.patches.find(x => x.version === '1.4.107' && x.enabled);
assert.equal(sha(fs.readFileSync(path.join(repo, 'assets/asset-patch/manifest.json'))), report.manifest_after_sha256);
assert.equal(patch.depends_on, '1.4.106'); assert.equal(patch.chain.length, 2);
const expectedBytes = patch.chain.reduce((sum, name) => sum + fs.statSync(path.join(repo, 'assets/asset-patch/active', name)).size, 0);
assert.equal(patch.archive_size, expectedBytes);
for (const archive of patch.archive_integrity) {
  const data = fs.readFileSync(path.join(repo, 'assets/asset-patch/active', archive.name));
  assert.equal(sha(data), archive.sha256); assert.equal(data.length, archive.size);
}
for (const file of report.server_files) assert.equal(sha(fs.readFileSync(path.join(repo, file.path))), file.sha256);
const asset = require(path.join(repo, 'out/routes/cn/asset.js'));
const version = require(path.join(repo, 'out/lib/version.js'));
assert.equal(version.getEffectiveVersion(), '1.4.107');
(async () => {
  const handlers = new Map(); await asset.default({post: (name, handler) => handlers.set(name, handler)});
  async function call(name, device, res_ver) {
    let body, status;
    const reply = {type() {return this}, status(x) {status = x; return this}, send(x) {body = x; return this}};
    await handlers.get(name)({headers: {host: '127.0.0.1:8001', device, res_ver}}, reply);
    assert.equal(status, 200); return body;
  }
  const platforms = {};
  for (const device of ['android', 'ios']) {
    const update = (await call('/get_path', device, '1.4.106')).data;
    assert.equal(update.info.target_asset_version, '1.4.107'); assert.equal(update.diff.length, 1);
    const group = update.diff[0]; assert.equal(group.original_version, '1.4.106'); assert.equal(group.version, '1.4.107');
    assert.deepEqual(group.archive.map(x => path.posix.basename(x.location)), patch.chain);
    assert.equal(group.archive.reduce((sum, x) => sum + x.size, 0), expectedBytes);
    assert.equal(asset.getAssetDownloadSize('1.4.106', device), expectedBytes);
    assert.equal((await call('/version_info', device, '1.4.106')).data.total_size, expectedBytes);
    const current = await call('/get_path', device, '1.4.107');
    assert.equal(current.data.full, null); assert.equal(current.data.diff, null);
    assert.equal(current.data_headers.asset_update, false);
    assert.equal(asset.getAssetDownloadSize('1.4.107', device), 0);
    platforms[device] = {edge: ['1.4.106', '1.4.107'], parts: patch.chain, bytes: expectedBytes,
      already_current_has_no_update: true};
  }
  const result = {status: 'passed', manifest_sha256: report.manifest_after_sha256,
    actual_asset_route_handlers: true, archive_hashes_verified: true, server_file_hashes_verified: true,
    platforms, listener_started: false, runtime_service_contacted: false, runtime_mirror_modified: false,
    player_database_accessed: false, device_tested: false};
  fs.writeFileSync(path.join(work, 'release-verification.json'), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result, null, 2));
})().catch(error => {console.error(error); process.exitCode = 1});
