require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const { gunzipSync, brotliDecompressSync } = require("node:zlib")

const moduleRoot = process.env.CN_LOAD_COMPRESSION_COMPILED === "1" ? "../out" : "../src"
const {
    acceptsHttpEncoding,
    compressCnLoadHttpBody,
    getCnLoadHttpCompressionConfig,
} = require(`${moduleRoot}/lib/cn-load-http-compression`)

async function main() {
    assert.equal(acceptsHttpEncoding("gzip, deflate", "gzip"), true)
    assert.equal(acceptsHttpEncoding("gzip;q=0, *;q=1", "gzip"), false)
    assert.equal(acceptsHttpEncoding("br;q=1, gzip;q=0.5", "br"), true)
    assert.equal(acceptsHttpEncoding(undefined, "gzip"), false)

    const body = Buffer.from("repeated-load-payload:".repeat(4_000), "utf8")
    const base = {
        minimumBytes: 4_096,
        gzipLevel: 1,
        brotliQuality: 3,
        log: false,
    }
    const gzipResult = await compressCnLoadHttpBody(body, "gzip, deflate", { ...base, mode: "gzip" })
    assert.equal(gzipResult.encoding, "gzip")
    assert.deepEqual(gunzipSync(gzipResult.body), body)
    assert.ok(gzipResult.wireBytes < gzipResult.originalBytes)

    const brResult = await compressCnLoadHttpBody(body, "br, gzip", { ...base, mode: "br" })
    assert.equal(brResult.encoding, "br")
    assert.deepEqual(brotliDecompressSync(brResult.body), body)

    const noSupport = await compressCnLoadHttpBody(body, "identity", { ...base, mode: "gzip" })
    assert.equal(noSupport.encoding, null)
    assert.equal(noSupport.reason, "not-accepted")
    assert.deepEqual(noSupport.body, body)

    const observed = await compressCnLoadHttpBody(body, "gzip", { ...base, mode: "observe" })
    assert.equal(observed.encoding, null)
    assert.equal(observed.reason, "observe")

    const parsed = getCnLoadHttpCompressionConfig({
        CN_LOAD_HTTP_COMPRESSION: "auto",
        CN_LOAD_HTTP_COMPRESSION_MIN_BYTES: "8192",
        CN_LOAD_HTTP_GZIP_LEVEL: "99",
        CN_LOAD_HTTP_BROTLI_QUALITY: "-1",
        CN_LOAD_HTTP_COMPRESSION_LOG: "true",
    })
    assert.deepEqual(parsed, {
        mode: "auto",
        minimumBytes: 8_192,
        gzipLevel: 9,
        brotliQuality: 0,
        log: true,
    })
    console.log("CN /load HTTP compression tests passed")
}

main().catch(error => {
    console.error(error)
    process.exitCode = 1
})
