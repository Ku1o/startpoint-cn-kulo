const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
const unzipper = require('unzipper');

const gacha = require('../assets/gacha.json');
const {getGachaSync} = require('../out/lib/assets');
const manifest = require('../assets/asset-patch/manifest.json');

const SALT = 'K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy';
const archiveName = 'pinball-1.4.124-1.4.125-1-cursed-weapon-pool-20261001.zip';
const archivePath = path.join(__dirname, '..', 'assets', 'asset-patch', 'active', archiveName);

function orderedMapRows(raw) {
    const compressedIndexLength = raw.readUInt32LE(0);
    const index = zlib.inflateSync(raw.subarray(4, 4 + compressedIndexLength));
    const count = index.readUInt32LE(0);
    const pairs = [];
    let cursor = 4;
    for (let i = 0; i < count; i += 1) {
        pairs.push({
            keyEnd: index.readUInt32LE(cursor),
            rowEnd: index.readUInt32LE(cursor + 4),
        });
        cursor += 8;
    }
    const keyBlob = index.subarray(cursor);
    const rowBlob = raw.subarray(4 + compressedIndexLength);
    const keys = [];
    const rows = [];
    let previousKeyEnd = 0;
    let previousRowEnd = 0;
    for (const pair of pairs) {
        keys.push(keyBlob.subarray(previousKeyEnd, pair.keyEnd).toString('utf8'));
        rows.push(rowBlob.subarray(previousRowEnd, pair.rowEnd));
        previousKeyEnd = pair.keyEnd;
        previousRowEnd = pair.rowEnd;
    }
    return {keys, rows};
}

async function readClientRows(directory, logical) {
    const digest = crypto.createHash('sha1').update(`${logical}${SALT}`).digest('hex');
    const member = `production/upload/${digest.slice(0, 2)}/${digest.slice(2)}`;
    const entry = directory.files.find(file => file.path === member);
    assert.ok(entry, `missing CDN member for ${logical}`);
    const outer = orderedMapRows(await entry.buffer());
    assert.equal(outer.keys.length, 1);
    const inner = orderedMapRows(outer.rows[0]);
    return inner.rows.map(row => zlib.inflateSync(row).toString('utf8').trim().split(','));
}

function ids(rows) {
    return rows.map(row => Number(row.id));
}

test('990004 keeps special cursed weapons and only official weapon-pool entries', async () => {
    const target = gacha['990004'];
    const official = gacha['25043'];
    const specialFive = new Set([5900101, ...Array.from({length: 29}, (_, index) => 5910101 + index), 5920001]);
    const expectedCounts = {1: 47, 2: 24, 3: 30};
    const expectedWeights = {1: 13872, 2: 24, 3: 30};

    assert.deepEqual(getGachaSync(990004).pool, target.pool);
    const directory = await unzipper.Open.file(archivePath);
    const clientRanks = {5: '1', 4: '2', 3: '3'};

    for (const [rank, rarity] of Object.entries(clientRanks)) {
        const rows = target.pool[rarity];
        const officialIds = new Set(official.pool[rarity].filter(row => row.odds > 0).map(row => row.id));
        const allowed = rarity === '1' ? new Set([...officialIds, ...specialFive]) : officialIds;
        assert.equal(rows.length, expectedCounts[rarity]);
        assert.equal(new Set(ids(rows)).size, rows.length);
        assert.ok(rows.every(row => allowed.has(row.id)), `non-pool weapon in rarity ${rarity}`);
        assert.equal(rows.reduce((sum, row) => sum + row.odds, 0), expectedWeights[rarity]);

        const clientRows = await readClientRows(directory, `master/gacha_odds/cnmod_weapon_gacha_${rank}.orderedmap`);
        assert.deepEqual(clientRows.map(row => Number(row[0])), ids(rows));
        for (const [index, serverRow] of rows.entries()) {
            const clientRow = clientRows[index];
            assert.deepEqual(clientRow.slice(0, 3), [String(serverRow.id), String(serverRow.rank), String(serverRow.odds)]);
            if (specialFive.has(serverRow.id)) {
                assert.equal(clientRow[3], serverRow.id === 5900101 || serverRow.id >= 5910101 && serverRow.id <= 5910129 ? 'true' : 'false');
            } else {
                assert.deepEqual(clientRow.slice(3), [
                    String(serverRow.isRateUp),
                    String(serverRow.isLimited),
                    String(serverRow.isExchangeable),
                ]);
            }
        }
    }

    assert.equal(target.pool['1'].find(row => row.id === 5900101).odds, 152);
    assert.ok(target.pool['1'].filter(row => row.id >= 5910101 && row.id <= 5910129).every(row => row.odds === 456));
    assert.equal(target.pool['1'].find(row => row.id === 5920001).odds, 0);

    const patch = manifest.patches.find(item => item.id === 'cursed-weapon-pool-20261001');
    assert.ok(patch.enabled);
    assert.equal(patch.version, '1.4.125');
    assert.equal(patch.depends_on, '1.4.124');
    assert.equal(patch.archive, archiveName);

    // Later resource fixes may extend the chain while this pool stays effective.
    let version = patch.version;
    const visited = new Set();
    while (version !== manifest.cdn_version) {
        assert.ok(!visited.has(version), `cycle after cursed weapon patch at ${version}`);
        visited.add(version);
        const nextVersions = [...new Set(manifest.patches
            .filter(item => item.enabled && item.depends_on === version)
            .map(item => item.version))];
        assert.equal(nextVersions.length, 1, `missing or ambiguous successor for ${version}`);
        version = nextVersions[0];
    }
});
