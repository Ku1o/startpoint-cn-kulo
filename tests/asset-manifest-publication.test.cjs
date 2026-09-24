const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const Fastify = require('fastify');

const current = 'pinball-1.4.116-1.4.117-1-consolidated.zip';
const superseded = 'pinball-1.4.116-1.4.117-1-superseded.zip';
const disabled = 'pinball-1.4.116-1.4.117-2-held.zip';
const second = 'pinball-1.4.116-1.4.117-3-extra.zip';
const files = [current, superseded, disabled, second].map((filename, i) => ({filename, size: (i + 1) * 100}));

function loadRoutes(patches) {
    const filename = process.env.STARPOINT_ASSET_ROUTE_FILE || path.resolve(__dirname, '../out/routes/cn/asset.js');
    const output = {exports: {}};
    const localRequire = name => {
        if (name.endsWith('/file-exists')) return {existsSync: () => false};
        if (name.endsWith('/utils')) return {generateDataHeaders: value => value || {}};
        if (name.endsWith('/zip-summary-cache')) return {
            getZipArchiveMetadata: directory => directory.replaceAll('\\', '/').endsWith('/asset-patch/active') ? files : [],
            invalidateZipCache() {},
        };
        if (name.endsWith('/version')) return {
            getPatchManifest: () => ({cdn_version: '1.4.117', patches}),
            computeAssetTarget: version => ({targetVersion: version === '1.4.117' ? version : '1.4.117', isFirstTime: !version, fullVersion: '1.4.0'}),
        };
        return require(name);
    };
    vm.runInNewContext(fs.readFileSync(filename, 'utf8'), {
        module: output, exports: output.exports, require: localRequire,
        __dirname: path.dirname(filename), process: {env: {}}, console, URL,
    }, {filename});
    return output.exports.default;
}

async function inspect(patches, expected) {
    const app = Fastify({logger: false});
    await app.register(loadRoutes(patches));
    try {
        for (const device of ['Android', 'iOS']) {
            const headers = {device, res_ver: '1.4.116'};
            const response = await app.inject({method: 'POST', url: '/get_path', headers, payload: {}});
            assert.equal(response.statusCode, 200);
            const archives = response.json().data.diff.flatMap(group => group.archive);
            assert.deepEqual(archives.map(a => path.basename(a.location)).sort(), [...expected].sort());
            const size = await app.inject({method: 'POST', url: '/version_info', headers, payload: {}});
            assert.equal(size.json().data.total_size, files.filter(f => expected.includes(f.filename)).reduce((sum, f) => sum + f.size, 0));
            const upToDate = await app.inject({method: 'POST', url: '/get_path', headers: {device, res_ver: '1.4.117'}, payload: {}});
            assert.equal(upToDate.json().data.diff, null);
        }
    } finally { await app.close(); }
}

test('both platforms exclude superseded and disabled archives retained on disk', async () => {
    await inspect([
        {type: 'patch', enabled: true, archive: current},
        {type: 'patch', enabled: false, archive: disabled},
        {type: 'mod', enabled: true, archive: superseded},
    ], [current]);
});

test('enabled multi-archive chains publish each listed archive and ignore unregistered files', async () => {
    await inspect([{type: 'patch', enabled: true, archive: superseded, chain: [current, second]}], [current, second]);
});
