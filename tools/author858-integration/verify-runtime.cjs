// Exercise the actual public data accessor against candidates without starting a service.
const fs = require('fs'), path = require('path'), assert = require('node:assert/strict'), Module = require('module');
const repo = path.resolve(__dirname, '../..');
const work = path.resolve(process.argv[2]);
const installed = process.argv.includes('--installed');
const read = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const report = read(path.join(work, 'prepared.json'));
const replacements = new Map(report.server_files.map(x => [path.join(repo, x.path), path.join(work, 'prepared-server', x.path)]));
const originalLoader = Module._extensions['.json'];
if (!installed) Module._extensions['.json'] = (mod, filename) => originalLoader(mod, replacements.get(filename) || filename);
const assets = require(path.join(repo, 'out/lib/assets.js'));
const master = require(path.join(repo, 'out/lib/content-master.js'));
const rules = require(path.join(repo, 'out/lib/gacha-rules.js'));
Module._extensions['.json'] = originalLoader;
const builder = require(path.join(repo, 'tools/rebuild_gacha_from_odds.cjs'));
const native = read(path.join(work, 'native-gachas.json'));
const expectedGachas = read(path.join(work, 'prepared-server/assets/gacha.json'));
const expectedCharacters = read(path.join(work, 'prepared-server/assets/character.json'));
const expectedNodes = read(path.join(work, 'prepared-server/assets/mana_node.json'));
const baselineNodes = read(path.join(work, 'before-server/assets/mana_node.json'));
const oldNodes = new Set(Object.values(baselineNodes).flatMap(levels => Object.values(levels).flatMap(nodes => Object.keys(nodes))));
const newNodes = new Set();
for (const cid of report.full_character_ids) {
  assert.deepEqual(assets.getCharacterDataSync(cid), expectedCharacters[cid]);
  assert.equal(assets.getCharacterManaBoardCountSync(cid), 2);
  for (const level of ['1', '2']) {
    const nodes = assets.getCharacterManaNodesSync(cid, level);
    assert.deepEqual(nodes, expectedNodes[cid][level]);
    for (const oldId of Object.keys(baselineNodes[cid]?.[level] || {})) {
      assert(Object.hasOwn(nodes, oldId), `existing saved node removed ${cid}:${level}:${oldId}`);
    }
    if (report.new_character_ids.includes(cid)) {
      assert.equal(Object.keys(nodes).length, level === '1' ? 23 : 18);
      for (const id of Object.keys(nodes)) {
        assert(!oldNodes.has(id) && !newNodes.has(id), `persisted node ID collision ${cid}:${id}`);
        newNodes.add(id);
        assert.deepEqual(assets.getCharacterManaNodeSync(cid, level, id), nodes[id]);
      }
    }
  }
}
const excluded = new Set([10,113001,141003,153001,163001,213001,213013,223001,223007,223013,223019,233001,233007,233013,243001,243007,243013,243019,253001,253007,253013,253019,263001,263002,323001,333001]);
const pools = {};
for (const gid of ['990001', '990002']) {
  const gacha = assets.getGachaSync(gid);
  assert.deepEqual(gacha, expectedGachas[gid]);
  const n = native[gid], row = n.meta_row;
  const exported = {rarity: {[row[11]]: {entries: n.rarity_rows.map(r => ({rarity: +r[0], weight: +r[1]}))}}, character: {}, equipment: {}};
  for (const [bucket, rows] of Object.entries(n.character_rows)) {
    exported.character[row[{1: 16, 2: 15, 3: 14}[bucket]]] = {entries: rows.map(r => ({characterId: +r[0], rarity: +r[1], weight: +r[2], oddsUp: r[3] === 'true', isLimited: r[4] === 'true', isExchangeable: r[5] === 'true', trialReadingForced: r[6] === 'true'}))};
  }
  assert.deepEqual(builder.buildBannerFromRow(gid, row, exported), gacha, 'native/server gacha mismatch');
  const all = Object.values(gacha.pool).flat();
  assert.equal(new Set(all.map(x => x.id)).size, all.length);
  for (const entry of all) {
    assert(!excluded.has(entry.id));
    assert.equal(assets.getCharacterDataSync(entry.id)?.rarity, entry.rank, `unknown/wrong rarity ${entry.id}`);
  }
  const zeroExchange = all.filter(x => x.odds === 0 && rules.getExchangeableGachaItem(gacha, x.id) !== null).map(x => x.id);
  assert.deepEqual(zeroExchange, gid === '990001' ? [179981] : []);
  for (const cid of [179982,179983,179984,179985,179986]) assert.equal(rules.getExchangeableGachaItem(assets.getGachaSync('990002'), cid), null);
  pools[gid] = {rows: all.length, native_parity: true, zero_exchangeable_ids: zeroExchange};
}
assert.equal(newNodes.size, 164);
const result = {status: 'passed', installed, actual_public_accessors: true, native_gacha_parity: true,
  prepared_sha256: require('crypto').createHash('sha256').update(fs.readFileSync(path.join(work, 'prepared.json'))).digest('hex'),
  characters: report.full_character_ids.length, new_saved_character_ids: report.new_character_ids,
  new_saved_node_ids: newNodes.size, saved_id_collisions: 0, pools, service_started: false, player_database_accessed: false};
fs.writeFileSync(path.join(work, installed ? 'installed-runtime-verification.json' : 'candidate-runtime-verification.json'), JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result, null, 2));
