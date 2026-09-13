const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'gacha-seed-persistence-'));
process.env.GACHA_SEED_DIR = path.join(root, 'singleton');
fs.mkdirSync(process.env.GACHA_SEED_DIR);
const { SeedValidator, default: singleton } = require('../out/lib/seed-validator');
let sequence = 0;

function create(t, count = 0) {
    const directory = path.join(root, String(++sequence));
    fs.mkdirSync(directory);
    const confirmed = { normal: { 100: 0, 200: null }, normal_pend: {}, fes: {}, fes_guarantee: {} };
    for (let i = 0; i < count; i++) confirmed.normal[700000000 + i] = i % 3;
    fs.writeFileSync(path.join(directory, 'confirmed_seeds.json'), JSON.stringify(confirmed));
    fs.writeFileSync(path.join(directory, 'purified_seeds.json'), JSON.stringify({ normal: {
        300: { r: 0, tag: '普通躲避球', play: true },
    } }));
    fs.writeFileSync(path.join(directory, 'verified_seeds.json'), JSON.stringify({ normal: { 400: 2 } }));
    const validator = new SeedValidator(directory);
    t.after(() => validator.close());
    return { validator, directory, read: kind => JSON.parse(fs.readFileSync(path.join(directory, `${kind}_seeds.json`), 'utf8')) };
}

test.after(async () => {
    await singleton.close();
    assert.equal(path.dirname(fs.realpathSync(root)), fs.realpathSync(os.tmpdir()));
    fs.rmSync(root, { recursive: true });
});

test('unchanged confirmed seeds clear sent state without rewriting the file', async t => {
    const { validator: v, directory } = create(t);
    const file = path.join(directory, 'confirmed_seeds.json');
    const before = fs.readFileSync(file);
    for (let i = 0; i < 100; i++) { v.markSent('normal', 100, 3); v.flushAll(); }
    await v.flushPersistence();
    assert.equal(v.getSentR('normal', 100), undefined);
    assert.deepEqual(fs.readFileSync(file), before);
    assert.equal(fs.existsSync(`${file}.bak`), false);
});

test('large seed pools persist off the request thread and retain a valid backup', async t => {
    const { validator: v, directory, read } = create(t, 81033);
    const originalWrite = fs.writeFileSync;
    try {
        fs.writeFileSync = () => { throw new Error('synchronous write on request thread'); };
        for (let i = 0; i < 100; i++) { v.markSent('normal', 900 + i, 4); v.flushAll(); }
        await v.flushPersistence();
    } finally { fs.writeFileSync = originalWrite; }
    assert.equal(Object.keys(read('confirmed').normal).length, 81135);
    assert.equal(read('confirmed').normal[999], 1);
    const backup = JSON.parse(fs.readFileSync(path.join(directory, 'confirmed_seeds.json.bak')));
    assert.equal(Object.keys(backup.normal).length, 81035);
});

test('play callbacks, verified rarity corrections and cross-pool cleanup survive restart', async t => {
    const { validator: v, directory, read } = create(t);
    v.confirm('normal', 200, 1);
    v.markSent('fes', 901, 5);
    v.recordPlay('fes', 901, true);
    v.flushAll();
    v.confirm('fes_guarantee', 902, 0);
    v.moveToVerified('fes', 902, 2);
    assert.equal(v.isKnownRarityMismatch('fes', 902, 3), true);
    assert.equal(v.isKnownRarityMismatch('fes', 902, 5), false);
    assert.equal(v.getSentR('fes', 901), undefined);
    await v.flushPersistence();
    assert.equal(read('confirmed').normal[200], 1);
    assert.equal(read('confirmed').fes_guarantee[902], undefined);
    assert.equal(read('verified').fes[901], 2);
    assert.equal(read('verified').fes[902], 2);
    const reload = new SeedValidator(directory);
    t.after(() => reload.close());
    assert.equal(reload.isKnownRarityMismatch('fes', 902, 3), true);
    assert.deepEqual(reload.getVerifiedList('fes'), v.getVerifiedList('fes'));
});

test('newer changes made during an in-flight write cannot be overwritten by its acknowledgement', async t => {
    const { validator: v, read } = create(t);
    v.confirm('normal', 901, 0);
    const first = v.flushPersistence();
    v.confirm('normal', 901, 2);
    v.addPlay('normal', 903, 1, true);
    v.setTag('normal', 903, '热血躲避球');
    await Promise.all([first, v.flushPersistence()]);
    assert.equal(read('confirmed').normal[901], 2);
    assert.equal(read('purified').normal[903].tag, '热血躲避球');
    assert.equal(read('confirmed').normal[903], undefined);
});

test('failed writes reject the durability barrier and retry the latest retained state', async t => {
    const { validator: v, directory, read } = create(t);
    const target = path.join(directory, 'confirmed_seeds.json');
    const previous = `${target}.original`;
    fs.renameSync(target, previous);
    fs.mkdirSync(target);
    v.confirm('normal', 901, 0);
    await assert.rejects(v.flushPersistence(), /EPERM|EISDIR|EEXIST|ENOTEMPTY|access|directory/i);
    fs.rmdirSync(target);
    fs.renameSync(previous, target);
    v.confirm('normal', 901, 2);
    await v.flushPersistence();
    assert.equal(read('confirmed').normal[901], 2);
    assert.equal(read('confirmed').normal[100], 0);
});

test('worker recovery persists current state even when its fresh snapshot already contains the update', async t => {
    const { validator: v, read } = create(t);
    await v.persistence.worker.terminate();
    v.confirm('normal', 902, 2);
    await v.flushPersistence();
    assert.equal(read('confirmed').normal[902], 2);
    assert.equal(read('verified').normal[400], 2);
});

test('admin options and play-mode selection retain their existing behavior', async t => {
    const { validator: v, directory } = create(t);
    v.setMode('play');
    assert.equal(v.getSeed('normal', 3, [100, 200, 300], 211002, 0), 300);
    v.setTestSeed('normal', 5, 987654321);
    v.setSelectedMovieId('normal');
    assert.equal(v.getSeed('normal', 5, [400], 211002, 0), 987654321);
    const reload = new SeedValidator(directory);
    t.after(() => reload.close());
    assert.equal(reload.getMode(), 'natural');
    assert.equal(reload.getSelectedMovieId(), 'normal');
    assert.equal(reload.getTestSeed(5), 987654321);
    reload.clearTestSeed(5);
    assert.equal(reload.getTestSeed(5), null);
});
