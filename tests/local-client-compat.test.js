const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Fastify = require('fastify');
const { installLocalClientCompat } = require(path.join(process.env.TEST_OUT_DIR || '../out', 'lib/local-client-compat.js'));

test('local Android mode blocks iOS before content handlers and preserves Android/web', async () => {
    const app = Fastify();
    installLocalClientCompat(app, 'android');
    app.get('/*', async () => ({ available: true }));
    try {
        for (const headers of [{ device: 'ios' }, { device: '1' }, { 'user-agent': 'iPhone' }]) {
            const result = await app.inject({ url: '/api/index.php/asset/get_path', headers });
            assert.equal(result.statusCode, 409);
            assert.equal(result.json().code, 'LOCAL_ANDROID_TEST_ONLY');
        }
        assert.equal((await app.inject('/shijtswy/version/client_release_ios.dis')).statusCode, 409);
        for (const headers of [{ device: '2' }, { device: 'android' }, {}]) {
            assert.equal((await app.inject({ url: '/admin/', headers })).statusCode, 200);
        }
    } finally { await app.close(); }
});

test('normal mode keeps existing iOS behavior', async () => {
    const app = Fastify();
    installLocalClientCompat(app, '');
    app.get('/', async () => 'ok');
    try { assert.equal((await app.inject({ url: '/', headers: { device: 'ios' } })).statusCode, 200); }
    finally { await app.close(); }
});
