const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const ts = require('typescript');
const Fastify = require('fastify');
const { unpack } = require('msgpackr');
const crashHelpers = require('../out/lib/crash-report');
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'gacha-seed-feedback-'));
process.env.GACHA_SEED_DIR = directory;
fs.writeFileSync(path.join(directory, 'confirmed_seeds.json'), JSON.stringify({ fes: { 100: 0, 103: 0 } }));
const validator = require('../out/lib/seed-validator').default;
const app = Fastify({ logger: false });

// Register the actual CN feedback handlers without starting its unrelated TCP
// listener or schedulers. No copied handler implementation is kept in the test.
const server = fs.readFileSync(path.join(__dirname, '../src/cn-server.ts'), 'utf8');
const start = server.indexOf('async function persistSeedFeedback(');
const end = server.indexOf('fastify.register(cnToolPlugin', start);
assert.ok(start >= 0 && end > start);
const handlers = ts.transpileModule(server.slice(start, end), {
    compilerOptions: { target: ts.ScriptTarget.ES2020 },
}).outputText;
new Function('fastify', 'seedValidator', 'gameVerboseLog', 'console', ...Object.keys(crashHelpers), handlers)(
    app, validator, () => {}, { log: () => {} }, ...Object.values(crashHelpers));
// Also use the production parsers so legacy form crash reports reach the same
// handler used in production rather than Fastify's default JSON-only parser.
const source = ts.createSourceFile('cn-server.ts', server, ts.ScriptTarget.Latest, true);
const parserStatements = source.statements.filter(statement => {
    if (ts.isFunctionDeclaration(statement)) return statement.name?.text === 'jsonParser';
    return ts.isExpressionStatement(statement) && ts.isCallExpression(statement.expression)
        && statement.expression.expression.getText(source) === 'fastify.addContentTypeParser';
});
assert.ok(parserStatements.length >= 3);
const parsers = ts.transpileModule(parserStatements.map(statement => statement.getText(source)).join('\n'), {
    compilerOptions: { target: ts.ScriptTarget.ES2020 },
}).outputText;
new Function('fastify', 'unpack', 'parseCrashReportBody', parsers)(app, unpack, crashHelpers.parseCrashReportBody);
const star = String.fromCharCode(0xe2, 0x98, 0x85);
const correction = seed => `C3032 seed=${seed} movie_id=fes 結果レア度=${star}5 play=1`;
const read = kind => JSON.parse(fs.readFileSync(path.join(directory, `${kind}_seeds.json`), 'utf8'));
test.after(async () => {
    await app.close(); await validator.close();
    assert.equal(path.dirname(fs.realpathSync(directory)), fs.realpathSync(os.tmpdir()));
    fs.rmSync(directory, { recursive: true });
});

test('GET and POST C3032 responses wait for the corrected rarity to reach disk', async () => {
    for (const [method, seed] of [['GET', 100], ['POST', 101]]) {
        const loc = correction(seed);
        const response = await app.inject(method === 'GET'
            ? { method, url: `/debug?loc=${encodeURIComponent(loc)}` }
            : { method, url: '/debug', payload: { loc } });
        assert.equal(response.statusCode, 200);
        assert.equal(response.body, 'OK');
        assert.equal(read('verified').fes[seed], 2);
        assert.equal(validator.isKnownRarityMismatch('fes', seed, 3), true);
    }
});

test('PLAY feedback keeps the sent rarity and persists verification before replying', async () => {
    validator.markSent('fes', 102, 4);
    const response = await app.inject({ method: 'GET', url: `/debug?loc=${encodeURIComponent('PLAY|play=1|seed=102, movie_id=fes')}` });
    assert.equal(response.statusCode, 200);
    assert.equal(read('verified').fes[102], 1);
    assert.equal(validator.getSentR('fes', 102), undefined);
});

test('a disk failure retains the original beacon response contract and retries the correction', async () => {
    const target = path.join(directory, 'confirmed_seeds.json');
    const previous = `${target}.original`;
    fs.renameSync(target, previous);
    fs.mkdirSync(target);
    try {
        const response = await app.inject({ method: 'GET', url: `/debug?loc=${encodeURIComponent(correction(103))}` });
        assert.equal(response.statusCode, 200);
        assert.equal(response.body, 'OK');
        assert.equal(validator.isKnownRarityMismatch('fes', 103, 3), true);
    } finally {
        fs.rmdirSync(target);
        fs.renameSync(previous, target);
    }
    await validator.flushPersistence();
    assert.equal(read('verified').fes[103], 2);
    assert.equal(read('confirmed').fes[103], undefined);
});

test('the legacy crash-report path still records known rarity without inventing a play result', async () => {
    const response = await app.inject({ method: 'POST', url: '/crash', payload: {
        message: 'C3032 seed=104 movie_id=fes 結果レア度=★4',
    } });
    assert.equal(response.statusCode, 200);
    assert.equal(read('confirmed').fes[104], 1);
    assert.equal(read('verified').fes[104], undefined);
});

test('C3032 correction after a long stack survives mislabeled JSON form parsing and reaches disk', async () => {
    const payload = JSON.stringify({ stack: 'at client.LoadingTask\n'.repeat(160),
        message: 'C3032 seed=105 movie_id=fes 結果レア度=★5', viewer_id: 19, resource_version: '1.4.134' });
    assert.ok(payload.indexOf('C3032') > 2000);
    const response = await app.inject({ method: 'POST', url: '/crash',
        headers: { 'content-type': 'application/x-www-form-urlencoded' }, payload });
    assert.equal(response.statusCode, 200);
    assert.equal(response.body, 'OK');
    assert.equal(read('confirmed').fes[105], 2);
    assert.equal(read('verified').fes[105], undefined);
});
