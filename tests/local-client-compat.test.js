const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Fastify = require('fastify');
const { installLocalClientCompat } = require(path.join(process.env.TEST_OUT_DIR || '../out', 'lib/local-client-compat.js'));

test('legacy Android-only settings no longer block iOS and preserve other clients', async () => {
    const app = Fastify();
    installLocalClientCompat(app, 'android');
    app.get('/*', async () => ({ available: true }));
    try {
        for (const headers of [
            { device: 'ios' }, { device: '1' },
            { 'user-agent': 'iPhone' }, { 'user-agent': 'iPad' }, { 'user-agent': 'iPod' },
            { device: '2' }, { device: 'android' }, {},
        ]) {
            const result = await app.inject({ url: '/api/index.php/asset/get_path', headers });
            assert.equal(result.statusCode, 200);
            assert.deepEqual(result.json(), { available: true });
        }
        assert.equal((await app.inject('/shijtswy/version/client_release_ios.dis')).statusCode, 200);
        assert.equal((await app.inject('/shijtswy/version/client_release_ios.dis?version=1')).statusCode, 200);
    } finally { await app.close(); }
});

test('inherited Android-only environment does not block iOS or bypass route authorization', async () => {
    const previous = process.env.CN_LOCAL_CLIENT_PLATFORM;
    process.env.CN_LOCAL_CLIENT_PLATFORM = 'android';
    const app = Fastify();
    installLocalClientCompat(app);
    app.get('/', async () => 'ok');
    app.get('/protected', async (_request, reply) => reply.code(401).send('unauthorized'));
    try {
        assert.equal((await app.inject({ url: '/', headers: { device: '1' } })).statusCode, 200);
        assert.equal((await app.inject({ url: '/protected', headers: { device: '1' } })).statusCode, 401);
    } finally {
        await app.close();
        if (previous === undefined) delete process.env.CN_LOCAL_CLIENT_PLATFORM;
        else process.env.CN_LOCAL_CLIENT_PLATFORM = previous;
    }
});

test('normal mode keeps existing iOS behavior', async () => {
    const app = Fastify();
    installLocalClientCompat(app, '');
    app.get('/', async () => 'ok');
    try { assert.equal((await app.inject({ url: '/', headers: { device: 'ios' } })).statusCode, 200); }
    finally { await app.close(); }
});
