// Manual CDN checks. The default command is offline and never starts a server.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { performance } = require('node:perf_hooks');
const { unpack } = require('msgpackr');

function requireValue(ok, message) { if (!ok) throw new Error(message); }
function versionKey(value) {
    requireValue(typeof value === 'string' && /^\d+\.\d+\.\d+$/.test(value), 'Invalid version');
    return value.split('.').map(Number);
}
function compareVersions(a, b) {
    const left = versionKey(a), right = versionKey(b);
    return left[0] - right[0] || left[1] - right[1] || left[2] - right[2];
}
function enabledPatches(manifest) {
    const patches = (manifest.patches || []).filter(p => p.type === 'patch' && p.enabled === true);
    requireValue(patches.length > 0, 'No enabled incremental edge');
    for (const patch of patches) versionKey(patch.version);
    return patches;
}
function planRange(manifest, fromVersion, toVersion) {
    const patches = enabledPatches(manifest);
    const latest = patches.map(p => p.version).sort(compareVersions).at(-1);
    const to = toVersion || latest;
    versionKey(fromVersion); versionKey(to);
    requireValue(compareVersions(fromVersion, to) < 0, 'The range must advance the version');
    requireValue(compareVersions(to, latest) <= 0, 'Target exceeds the enabled manifest tail');
    const selected = patches.filter(p => compareVersions(p.version, fromVersion) > 0 && compareVersions(p.version, to) <= 0);
    const groups = new Map();
    for (const patch of selected) {
        versionKey(patch.depends_on);
        const previous = groups.get(patch.version);
        requireValue(!previous || previous.from === patch.depends_on, 'Conflicting edge predecessors');
        if (!previous) groups.set(patch.version, { from: patch.depends_on, to: patch.version, archives: new Map() });
        const group = groups.get(patch.version);
        const names = Array.isArray(patch.chain) ? patch.chain : [patch.archive];
        requireValue(names.length > 0 && Array.isArray(patch.archive_integrity), 'Missing archive integrity metadata');
        for (const name of names) {
            const match = typeof name === 'string' && name.match(/^pinball-(\d+\.\d+\.\d+)-(\d+\.\d+\.\d+)-\d+-.+\.zip$/);
            requireValue(match && !/[\\/]/.test(name), 'Invalid incremental archive name');
            requireValue(match[1] === group.from && match[2] === group.to, 'Archive does not belong to its declared edge');
            const entries = patch.archive_integrity.filter(item => item.name === name);
            requireValue(entries.length === 1, 'Missing or duplicate archive integrity metadata');
            const item = entries[0];
            requireValue(Number.isSafeInteger(item.size) && item.size > 0 && /^[a-f0-9]{64}$/.test(item.sha256), 'Invalid archive size or hash');
            const archive = { name, size: item.size, sha256: item.sha256 };
            const old = group.archives.get(name);
            requireValue(!old || JSON.stringify(old) === JSON.stringify(archive), 'Conflicting archive integrity metadata');
            group.archives.set(name, archive);
        }
    }
    const edges = [...groups.values()].sort((a, b) => compareVersions(a.to, b.to));
    let cursor = fromVersion;
    for (const edge of edges) {
        requireValue(edge.from === cursor, 'Requested manifest range is not contiguous');
        cursor = edge.to;
    }
    requireValue(edges.length > 0 && cursor === to, 'Requested target is not an enabled incremental edge');
    const serializeEdge = edge => ({ from: edge.from, to: edge.to, archives: [...edge.archives.values()].sort((a, b) => a.name.localeCompare(b.name)) });
    const serialized = edges.map(serializeEdge);
    return { from: fromVersion, to, archives: serialized.flatMap(edge => edge.archives),
        patchIds: selected.map(p => p.id), edges: serialized };
}
function planLatestEdge(manifest) {
    const patches = enabledPatches(manifest);
    const latest = patches.map(p => p.version).sort(compareVersions).at(-1);
    const selected = patches.filter(p => p.version === latest);
    const predecessors = new Set(selected.map(p => p.depends_on));
    requireValue(predecessors.size === 1, 'Conflicting latest edge predecessors');
    return planRange(manifest, selected[0].depends_on, latest);
}
function decodeApiResponse(raw) {
    const text = Buffer.from(raw).toString('utf8').trim();
    if (text.startsWith('{') || text.startsWith('[')) return JSON.parse(text);
    requireValue(text.length > 0 && /^[A-Za-z0-9+/=\s]+$/.test(text), 'Invalid API response encoding');
    return unpack(Buffer.from(text, 'base64'));
}
function readJson(file) {
    try { return JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '')); }
    catch { throw new Error(`Cannot read ${path.basename(file)} as JSON`); }
}
function localOrigin(value) {
    const url = new URL(value);
    requireValue(url.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)
        && !url.username && !url.password && url.pathname === '/' && !url.search && !url.hash, 'Use the local server origin');
    return url.origin;
}

async function runProbe({ repoRoot, manifest, baseUrl, timeoutMs = 10000, admissionToken, download = false, fromVersion, toVersion }) {
    const started = performance.now();
    const plan = fromVersion ? planRange(manifest, fromVersion, toVersion) : planLatestEdge(manifest);
    const origin = localOrigin(baseUrl);
    requireValue(Number.isSafeInteger(timeoutMs) && timeoutMs > 0, 'Invalid timeout');
    let apiRequests = 0, handshakeRequests = 0;
    async function request(endpoint, options = {}) {
        const remaining = Math.ceil(timeoutMs - (performance.now() - started));
        requireValue(remaining > 0, 'HTTP check exceeded its time budget');
        let response;
        try { response = await fetch(origin + endpoint, { ...options, redirect: 'error', signal: AbortSignal.timeout(remaining) }); }
        catch { throw new Error('Local HTTP service unavailable or request timed out'); }
        requireValue(response.status === 200, `HTTP endpoint returned ${response.status}`);
        return response;
    }
    async function post(endpoint, body, headers = {}) {
        const response = await request(endpoint, { method: 'POST',
            headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
        const declared = response.headers.get('content-length');
        requireValue(!declared || Number(declared) <= 2 * 1024 * 1024, 'API response exceeds size limit');
        const chunks = []; let size = 0;
        for await (const chunk of response.body) {
            size += chunk.length;
            requireValue(size <= 2 * 1024 * 1024, 'API response exceeds size limit'); chunks.push(Buffer.from(chunk));
        }
        return decodeApiResponse(Buffer.concat(chunks));
    }
    let policy, keys;
    async function getToken(device) {
        if (admissionToken) return admissionToken;
        policy ||= readJson(path.resolve(repoRoot, process.env.CLIENT_ADMISSION_CONFIG || 'config/client-admission.json'));
        if (!policy.enforce) return undefined;
        keys ||= readJson(path.resolve(repoRoot, process.env.CLIENT_ADMISSION_KEYS || 'config/client-admission.keys.json'));
        const builds = policy.builds.filter(b => b.enabled && (b.platform || 'android') === device
            && (b.allowUntil === null || Date.parse(b.allowUntil) > Date.now()));
        builds.sort((a, b) => Number(!a.id.toLowerCase().includes('lan')) - Number(!b.id.toLowerCase().includes('lan')) || a.id.localeCompare(b.id));
        requireValue(builds.length > 0, `No enabled ${device} admission build`);
        const build = builds[0];
        requireValue(typeof keys[build.id] === 'string' && /^[a-f0-9]{64}$/.test(keys[build.id]), 'Admission credential unavailable');
        const challenge = await post('/client-admission/challenge', { protocol: 1, build: build.id, platform: device }); handshakeRequests++;
        requireValue(challenge.ok === true && typeof challenge.data?.challenge === 'string' && typeof challenge.data?.nonce === 'string', 'Admission challenge failed');
        const message = `SP-ADMISSION-1\n${build.id}\n${challenge.data.challenge}\n${challenge.data.nonce}`;
        const proof = crypto.createHmac('sha256', Buffer.from(keys[build.id], 'hex')).update(message).digest('hex');
        const grant = await post('/client-admission/prove', { challenge: challenge.data.challenge, proof }); handshakeRequests++;
        requireValue(grant.ok === true && typeof grant.data?.token === 'string', 'Admission proof failed');
        return grant.data.token;
    }
    const expectedByName = new Map(plan.archives.map(a => [a.name, a]));
    const expectedPaths = new Map(plan.archives.map(a => [`/patch/cn/asset-patch/active/${a.name}`, a]));
    const downloadsByPath = new Map();
    const platforms = {};
    for (const device of ['android', 'ios']) {
        const token = await getToken(device);
        const payload = await post('/api/index.php/asset/get_path', {}, { DEVICE: device, RES_VER: plan.from,
            ...(token ? { 'X-SP-Admission': token } : {}) }); apiRequests++;
        const data = payload.data;
        requireValue(data?.info?.target_asset_version === plan.to, 'Running service target differs from the requested target');
        requireValue(data.info.client_asset_version === plan.from, 'Running service did not acknowledge the requested baseline');
        requireValue(Array.isArray(data.full?.archive) && data.full.archive.length === 0, 'Unexpected full download');
        requireValue(Array.isArray(data.diff) && data.diff.length === plan.edges.length, 'Unexpected historical or missing incremental edge');
        const seen = new Set();
        data.diff.forEach((edge, i) => {
            const expectedEdge = plan.edges[i];
            requireValue(edge.original_version === expectedEdge.from && edge.version === expectedEdge.to
                && Array.isArray(edge.archive) && edge.archive.length === expectedEdge.archives.length, 'Unexpected incremental edge or archive count');
            const edgeNames = new Set(expectedEdge.archives.map(a => a.name));
            for (const archive of edge.archive) {
                requireValue(typeof archive.location === 'string', 'Missing archive location');
                const advertised = new URL(archive.location, origin);
                const pathname = decodeURIComponent(advertised.pathname);
                const expected = expectedPaths.get(pathname);
                requireValue(expected && edgeNames.has(expected.name) && expectedByName.has(expected.name)
                    && !advertised.search && !advertised.hash && !advertised.username && !advertised.password, 'Unexpected archive path');
                requireValue(!seen.has(expected.name) && archive.size === expected.size, 'Duplicate archive or advertised size mismatch');
                seen.add(expected.name); downloadsByPath.set(pathname, expected);
            }
        });
        requireValue(seen.size === plan.archives.length, 'Incomplete advertised archives');
        platforms[device] = { target: plan.to, archives: seen.size };
    }
    const downloads = [];
    if (download) {
        for (const [pathname, expected] of downloadsByPath) {
            const response = await request(pathname);
            const hash = crypto.createHash('sha256'); let size = 0;
            for await (const chunk of response.body) {
                size += chunk.length;
                requireValue(size <= expected.size, 'Archive download exceeds declared size'); hash.update(chunk);
            }
            const sha256 = hash.digest('hex');
            requireValue(size === expected.size && sha256 === expected.sha256, 'Archive download size or hash mismatch');
            downloads.push({ name: expected.name, size, sha256 });
        }
    }
    return { schema: 'cdn-http-probe/v1', status: 'passed', mode: download ? 'download' : 'metadata',
        from: plan.from, to: plan.to, patchIds: plan.patchIds, platforms,
        downloads, archiveDownloads: downloads.length, apiRequests, handshakeRequests,
        elapsedMs: Math.round(performance.now() - started), gameRuntimeAcceptance: 'pending' };
}

async function main(args = process.argv.slice(2)) {
    const options = { check: false, download: false };
    for (let i = 0; i < args.length; i++) {
        const arg = args[i];
        if (arg === '--help') {
            console.log('node tools/cdn-http-probe.cjs [--check | --download] [--from VERSION] [--output FILE] [--timeout-ms MS]\nDefault: print the latest enabled edge offline. --from selects only baseline-to-latest. No service start/restart; --check downloads no ZIP.'); return;
        }
        if (arg === '--check') { options.check = true; continue; }
        if (arg === '--download') { options.check = true; options.download = true; continue; }
        requireValue(['--from', '--output', '--timeout-ms'].includes(arg) && args[i + 1], 'Unknown option or missing argument');
        options[arg.slice(2)] = args[++i];
    }
    const repoRoot = path.resolve(__dirname, '..');
    const manifest = readJson(path.join(repoRoot, 'assets/asset-patch/manifest.json'));
    const plan = options.from ? planRange(manifest, options.from) : planLatestEdge(manifest);
    let result;
    if (!options.check) result = { schema: 'cdn-http-probe/v1', status: 'planned', mode: 'offline', ...plan, httpRequests: 0, archiveDownloads: 0 };
    else {
        const envFile = path.join(repoRoot, '.env');
        if (fs.existsSync(envFile)) process.loadEnvFile(envFile);
        const port = Number(process.env.CN_LISTEN_PORT || 8001);
        requireValue(port === 8001, 'The local resource test service must use port 8001');
        result = await runProbe({ repoRoot, manifest, baseUrl: `http://127.0.0.1:${port}`,
            fromVersion: options.from, download: options.download,
            timeoutMs: options['timeout-ms'] ? Number(options['timeout-ms']) : 10000 });
    }
    if (options.output) {
        const output = path.resolve(options.output);
        requireValue(!output.split(path.sep).some(part => part.toLowerCase() === '.cdn'), 'Cannot write into the pristine CDN');
        let ancestor = output;
        const suffix = [];
        while (!fs.existsSync(ancestor)) { suffix.unshift(path.basename(ancestor)); ancestor = path.dirname(ancestor); }
        const resolvedOutput = path.resolve(fs.realpathSync(ancestor), ...suffix);
        const pristine = fs.realpathSync(path.join(repoRoot, '.cdn'));
        const relative = path.relative(pristine, resolvedOutput);
        requireValue(relative && (relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative)), 'Cannot write into the pristine CDN');
        fs.mkdirSync(path.dirname(output), { recursive: true });
        fs.writeFileSync(output, JSON.stringify(result, null, 2) + '\n');
    }
    console.log(JSON.stringify(result, null, 2));
    return result;
}
module.exports = { planLatestEdge, planRange, decodeApiResponse, runProbe, main };
if (require.main === module) main().catch(error => { console.error(`CDN probe failed: ${error.message}`); process.exitCode = 1; });
