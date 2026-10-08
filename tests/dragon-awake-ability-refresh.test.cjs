const assert = require("node:assert/strict")
const crypto = require("node:crypto")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const test = require("node:test")
const vm = require("node:vm")
const Fastify = require("fastify")
const unzipper = require("unzipper")

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "dragon-awake-refresh-"))
process.env.CDN_DIR = path.join(temporary, "cdn")
for (const platform of ["common", "medium", "android", "ios"]) {
    for (const kind of ["full", "diff"]) {
        fs.mkdirSync(
            path.join(process.env.CDN_DIR, "cn", `archive-${platform}-${kind}`),
            { recursive: true },
        )
    }
}

const root = path.resolve(__dirname, "..")
const manifest = require("../assets/asset-patch/manifest.json")
const patch = manifest.patches.find(
    entry => entry.id === "dragon-awake-ability-refresh-1.4.135",
)
const assetRoutes = require("../out/routes/cn/asset").default
const sha256 = raw => crypto.createHash("sha256").update(raw).digest("hex")

test.after(() => fs.rmSync(temporary, { recursive: true, force: true }))

test("the .135 refresh archive contains only the current terminal ability table", async () => {
    assert.ok(patch)
    assert.equal(manifest.cdn_version, "1.4.135")
    assert.equal(patch.depends_on, "1.4.134")
    assert.equal(patch.version, "1.4.135")
    assert.equal(patch.enabled, true)
    assert.deepEqual(patch.chain, [patch.archive])
    assert.equal(patch.files.length, 1)

    const archivePath = path.join(root, "assets/asset-patch/active", patch.archive)
    const archiveRaw = fs.readFileSync(archivePath)
    assert.equal(archiveRaw.length, patch.archive_size)
    assert.equal(sha256(archiveRaw), patch.archive_integrity[0].sha256)
    assert.equal(patch.archive_integrity[0].members, 1)
    const archive = await unzipper.Open.buffer(archiveRaw)
    assert.deepEqual(archive.files.map(file => file.path), patch.files)
    const payload = await archive.files[0].buffer()
    const report = require(
        "../assets/asset-patch/audit/dragon-awake-ability-refresh-1.4.135/report.json"
    )
    assert.equal(payload.length, report.resource.payload_bytes)
    assert.equal(sha256(payload), report.resource.payload_sha256)
    assert.equal(report.verification.balance_values_changed, false)
})

for (const device of ["Android", "iOS"]) {
    test(`${device}: .134 downloads the .135 ability refresh and .135 is current`, async t => {
        const app = Fastify({ logger: false })
        await app.register(assetRoutes, { prefix: "/asset" })
        await app.register(require("@fastify/static"), {
            root: path.join(root, "assets/asset-patch/active"),
            prefix: "/patch/cn/asset-patch/active/",
        })
        await app.ready()
        t.after(() => app.close())

        const headers = {
            host: "127.0.0.1:8001",
            device,
            res_ver: "1.4.134",
            asset_size: "fulfill",
        }
        const response = await app.inject({
            method: "POST",
            url: "/asset/get_path",
            headers,
            payload: {},
        })
        assert.equal(response.statusCode, 200)
        const update = response.json()
        assert.equal(update.data_headers.asset_update, true)
        assert.equal(update.data.info.target_asset_version, "1.4.135")
        const edge = update.data.diff.find(group => group.version === "1.4.135")
        assert.ok(edge)
        assert.equal(edge.original_version, "1.4.134")
        assert.deepEqual(
            edge.archive.map(file => path.posix.basename(file.location)),
            [patch.archive],
        )
        const download = await app.inject({
            method: "GET",
            url: new URL(edge.archive[0].location).pathname,
        })
        assert.equal(download.statusCode, 200)
        assert.equal(download.rawPayload.length, patch.archive_size)
        assert.equal(sha256(download.rawPayload), patch.archive_integrity[0].sha256)

        const size = await app.inject({
            method: "POST",
            url: "/asset/version_info",
            headers,
            payload: {},
        })
        assert.equal(size.statusCode, 200)
        assert.equal(size.json().data.total_size, patch.archive_size)

        const current = await app.inject({
            method: "POST",
            url: "/asset/get_path",
            headers: { ...headers, res_ver: "1.4.135" },
            payload: {},
        })
        assert.equal(current.statusCode, 200)
        assert.equal(current.json().data_headers.asset_update, false)
        assert.equal(current.json().data.diff, null)
    })
}

test("the asset route publishes no unregistered .135 archive", async () => {
    const source = fs.readFileSync(path.join(root, "out/routes/cn/asset.js"), "utf8")
    const output = { exports: {} }
    const files = [
        { filename: patch.archive, size: patch.archive_size },
        { filename: "pinball-1.4.134-1.4.135-2-held.zip", size: 1 },
    ]
    const localRequire = name => {
        if (name.endsWith("/file-exists")) return { existsSync: () => false }
        if (name.endsWith("/utils")) return { generateDataHeaders: values => values ?? {} }
        if (name.endsWith("/zip-summary-cache")) return {
            getZipArchiveMetadata: directory => directory.replaceAll("\\", "/")
                .endsWith("/asset-patch/active") ? files : [],
            invalidateZipCache() {},
        }
        if (name.endsWith("/version")) return {
            getPatchManifest: () => manifest,
            computeAssetTarget: () => ({
                targetVersion: "1.4.135",
                isFirstTime: false,
                fullVersion: "1.4.134",
            }),
        }
        return require(name)
    }
    vm.runInNewContext(source, {
        module: output,
        exports: output.exports,
        require: localRequire,
        __dirname: path.join(root, "out/routes/cn"),
        process: { env: {} },
        console,
        URL,
    })
    const app = Fastify({ logger: false })
    await app.register(output.exports.default)
    try {
        const response = await app.inject({
            method: "POST",
            url: "/get_path",
            headers: { device: "Android", res_ver: "1.4.134" },
            payload: {},
        })
        assert.equal(response.statusCode, 200)
        const archives = response.json().data.diff.flatMap(group => group.archive)
        assert.deepEqual(
            archives.map(file => path.posix.basename(file.location)),
            [patch.archive],
        )
    } finally {
        await app.close()
    }
})
