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
}

export interface CnLoadHttpCompressionResult {
    readonly body: Buffer
    readonly encoding: "gzip" | "br" | null
    readonly originalBytes: number
    readonly wireBytes: number
    readonly reason: "compressed" | "disabled" | "below-threshold" | "not-accepted" | "observe"
}

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
    }
}

export function acceptsHttpEncoding(
    header: string | readonly string[] | undefined,
    encoding: "gzip" | "br",
): boolean {
    const text = typeof header === "string" ? header : header?.join(",")
    if (!text) return false
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
    return (wildcardQuality ?? 0) > 0
}

function gzipAsync(body: Buffer, level: number): Promise<Buffer> {
    return new Promise((resolve, reject) => gzip(body, { level }, (error, result) => (
        error ? reject(error) : resolve(result)
    )))
}

function brotliAsync(body: Buffer, quality: number): Promise<Buffer> {
    return new Promise((resolve, reject) => brotliCompress(body, {
        params: { [zlibConstants.BROTLI_PARAM_QUALITY]: quality },
    }, (error, result) => (
        error ? reject(error) : resolve(result)
    )))
}

export async function compressCnLoadHttpBody(
    body: Buffer,
    acceptEncoding: string | readonly string[] | undefined,
    config: CnLoadHttpCompressionConfig,
): Promise<CnLoadHttpCompressionResult> {
    const base = {
        body,
        encoding: null,
        originalBytes: body.length,
        wireBytes: body.length,
    } as const
    if (config.mode === "off") return { ...base, reason: "disabled" }
    if (body.length < config.minimumBytes) return { ...base, reason: "below-threshold" }
    if (config.mode === "observe") return { ...base, reason: "observe" }

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
    if (encoding === null) return { ...base, reason: "not-accepted" }

    const compressed = encoding === "br"
        ? await brotliAsync(body, config.brotliQuality)
        : await gzipAsync(body, config.gzipLevel)
    return {
        body: compressed,
        encoding,
        originalBytes: body.length,
        wireBytes: compressed.length,
        reason: "compressed",
    }
}
