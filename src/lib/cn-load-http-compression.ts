import {
    brotliCompress,
    constants as zlibConstants,
    gzip,
} from "node:zlib"

export type CnLoadHttpCompressionMode = "off" | "observe" | "gzip" | "br" | "auto"

export interface CnLoadHttpCompressionConfig {
    readonly mode: CnLoadHttpCompressionMode
    readonly minimumBytes: number
    readonly gzipLevel: number
    readonly brotliQuality: number
    readonly log: boolean
    readonly maxConcurrent: number
    readonly maxInputBytes: number
}

export interface CnLoadHttpCompressionResult {
    readonly body: Buffer | string
    readonly encoding: "gzip" | "br" | null
    readonly originalBytes: number
    readonly wireBytes: number
    readonly reason: "compressed" | "disabled" | "below-threshold" | "not-accepted" | "observe" | "capacity"
    readonly statusCode?: 406 | 503
}

const DEFAULT_MAX_CONCURRENT = 4
const DEFAULT_MAX_INPUT_BYTES = 32 * 1024 * 1024
// Production encoding workers return base64 to their parent before compression,
// so every local/worker/fallback response shares this budget. There is no queue.
const compressionStats = { active: 0, inputBytes: 0, rejected: 0, failed: 0,
    maxConcurrent: DEFAULT_MAX_CONCURRENT, maxInputBytes: DEFAULT_MAX_INPUT_BYTES }
export function getCnLoadCompressionStats() { return { ...compressionStats } }

function clampInteger(value: string | undefined, fallback: number, minimum: number, maximum: number): number {
    const parsed = Number.parseInt(value ?? "", 10)
    if (!Number.isFinite(parsed)) return fallback
    return Math.max(minimum, Math.min(maximum, parsed))
}

function parseBoolean(value: string | undefined): boolean {
    return /^(1|true|yes|on)$/i.test(value ?? "")
}

export function getCnLoadHttpCompressionConfig(
    environment: NodeJS.ProcessEnv = process.env,
): CnLoadHttpCompressionConfig {
    const configuredMode = (environment.CN_LOAD_HTTP_COMPRESSION ?? "off").trim().toLowerCase()
    const mode: CnLoadHttpCompressionMode = ["off", "observe", "gzip", "br", "auto"].includes(configuredMode)
        ? configuredMode as CnLoadHttpCompressionMode
        : "off"
    return {
        mode,
        minimumBytes: clampInteger(environment.CN_LOAD_HTTP_COMPRESSION_MIN_BYTES, 4_096, 0, 10_000_000),
        // Level 1 keeps main-login CPU cost low while repeated save keys still compress well.
        gzipLevel: clampInteger(environment.CN_LOAD_HTTP_GZIP_LEVEL, 1, 1, 9),
        brotliQuality: clampInteger(environment.CN_LOAD_HTTP_BROTLI_QUALITY, 3, 0, 11),
        log: parseBoolean(environment.CN_LOAD_HTTP_COMPRESSION_LOG),
        maxConcurrent: clampInteger(environment.CN_LOAD_HTTP_COMPRESSION_MAX_CONCURRENT, DEFAULT_MAX_CONCURRENT, 1, 32),
        maxInputBytes: clampInteger(environment.CN_LOAD_HTTP_COMPRESSION_MAX_INPUT_BYTES, DEFAULT_MAX_INPUT_BYTES, 1, 256 * 1024 * 1024),
    }
}

export function acceptsHttpEncoding(
    header: string | readonly string[] | undefined,
    encoding: "gzip" | "br" | "identity",
): boolean {
    const text = typeof header === "string" ? header : header?.join(",")
    if (!text) return encoding === "identity"
    let wildcardQuality: number | null = null
    for (const token of text.split(",")) {
        const [rawName, ...parameters] = token.trim().toLowerCase().split(";")
        if (!rawName) continue
        let quality = 1
        for (const parameter of parameters) {
            const match = parameter.trim().match(/^q\s*=\s*(0(?:\.\d+)?|1(?:\.0+)?)$/)
            if (match) quality = Number(match[1])
        }
        if (rawName === encoding) return quality > 0
        if (rawName === "*") wildcardQuality = quality
    }
    // RFC 9110 12.5.3: identity is acceptable unless explicitly excluded,
    // including '*;q=0' without a more specific identity entry.
    return encoding === "identity" ? wildcardQuality !== 0 : (wildcardQuality ?? 0) > 0
}

function gzipAsync(body: Buffer | string, level: number): Promise<Buffer> {
    return new Promise((resolve, reject) => gzip(body, { level }, (error, result) => (
        error ? reject(error) : resolve(result)
    )))
}

function brotliAsync(body: Buffer | string, quality: number): Promise<Buffer> {
    return new Promise((resolve, reject) => brotliCompress(body, {
        params: { [zlibConstants.BROTLI_PARAM_QUALITY]: quality },
    }, (error, result) => (
        error ? reject(error) : resolve(result)
    )))
}

export async function compressCnLoadHttpBody(
    body: Buffer | string,
    acceptEncoding: string | readonly string[] | undefined,
    config: CnLoadHttpCompressionConfig,
): Promise<CnLoadHttpCompressionResult> {
    const originalBytes = typeof body === "string" ? Buffer.byteLength(body) : body.length
    const identityAllowed = acceptsHttpEncoding(acceptEncoding, "identity")
    const base = {
        body,
        encoding: null,
        originalBytes,
        wireBytes: originalBytes,
    } as const
    const uncompressed = (reason: CnLoadHttpCompressionResult["reason"], statusCode: 406 | 503 = 406): CnLoadHttpCompressionResult => (
        identityAllowed ? { ...base, reason } : { ...base, body: "", wireBytes: 0, reason, statusCode }
    )
    if (config.mode === "off") return uncompressed("disabled")
    if (originalBytes < config.minimumBytes && identityAllowed) return uncompressed("below-threshold")
    if (config.mode === "observe") return uncompressed("observe")

    const supportsBrotli = acceptsHttpEncoding(acceptEncoding, "br")
    const supportsGzip = acceptsHttpEncoding(acceptEncoding, "gzip")
    const encoding = config.mode === "br"
        ? (supportsBrotli ? "br" : null)
        : config.mode === "gzip"
            ? (supportsGzip ? "gzip" : null)
            : supportsBrotli
                ? "br"
                : supportsGzip
                    ? "gzip"
                    : null
    if (encoding === null) return uncompressed("not-accepted")

    // Older callers may provide a config without the new fields.
    const maxConcurrent = config.maxConcurrent ?? DEFAULT_MAX_CONCURRENT
    const maxInputBytes = config.maxInputBytes ?? DEFAULT_MAX_INPUT_BYTES
    Object.assign(compressionStats, { maxConcurrent, maxInputBytes })
    if (compressionStats.active >= maxConcurrent || originalBytes > maxInputBytes - compressionStats.inputBytes) {
        compressionStats.rejected++
        return uncompressed("capacity", 503)
    }
    compressionStats.active++
    compressionStats.inputBytes += originalBytes
    try {
        // zlib converts strings only after admission; rejected base64 does not
        // allocate another full Buffer. Release only when native work settles.
        const compressed = encoding === "br"
            ? await brotliAsync(body, config.brotliQuality)
            : await gzipAsync(body, config.gzipLevel)
        return { body: compressed, encoding, originalBytes, wireBytes: compressed.length, reason: "compressed" }
    } catch (error) {
        compressionStats.failed++
        throw error
    } finally {
        compressionStats.active--
        compressionStats.inputBytes -= originalBytes
    }
}
