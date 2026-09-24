import { pack } from "msgpackr"
import { performance } from "node:perf_hooks"
import { compressCnLoadHttpBody, type CnLoadHttpCompressionConfig } from "./cn-load-http-compression"

/** AIR cannot read uint32 correctly. Copy only when a uint32 tag needs fixing. */
export function fixUint32Tags(input: Buffer): Buffer {
    let output: Buffer | undefined
    let copiedThrough = 0
    let written = 0
    const end = input.length
    function walk(offset: number): number {
        if (offset >= end) throw new Error("Truncated MessagePack response")
        const tag = input[offset]
        let next = offset + 1
        let children = 0
        if (tag <= 0x7f || tag >= 0xe0 || tag === 0xc0 || tag === 0xc2 || tag === 0xc3) return next
        if (tag >= 0xa0 && tag <= 0xbf) return next + (tag & 0x1f)
        if (tag >= 0x90 && tag <= 0x9f) children = tag & 0x0f
        else if (tag >= 0x80 && tag <= 0x8f) children = (tag & 0x0f) * 2
        else switch (tag) {
            case 0xcc: case 0xd0: return next + 1
            case 0xcd: case 0xd1: return next + 2
            case 0xd2: case 0xca: return next + 4
            case 0xcf: case 0xd3: case 0xcb: return next + 8
            case 0xce: {
                const value = input.readUInt32BE(next)
                output ??= Buffer.allocUnsafe(end * 2)
                written += input.copy(output, written, copiedThrough, offset)
                if (value < 0x80000000) {
                    output[written++] = 0xd2
                    output.writeInt32BE(value, written)
                    written += 4
                } else {
                    output[written++] = 0xcb
                    output.writeDoubleBE(value, written)
                    written += 8
                }
                copiedThrough = next + 4
                return copiedThrough
            }
            case 0xd9: case 0xc4: return next + 1 + input.readUInt8(next)
            case 0xda: case 0xc5: return next + 2 + input.readUInt16BE(next)
            case 0xdb: case 0xc6: return next + 4 + input.readUInt32BE(next)
            case 0xc7: return next + 2 + input.readUInt8(next)
            case 0xc8: return next + 3 + input.readUInt16BE(next)
            case 0xc9: return next + 5 + input.readUInt32BE(next)
            // The extension's type byte precedes its payload.
            case 0xd4: return next + 2
            case 0xd5: return next + 3
            case 0xd6: return next + 5
            case 0xd7: return next + 9
            case 0xd8: return next + 17
            case 0xdc: children = input.readUInt16BE(next); next += 2; break
            case 0xdd: children = input.readUInt32BE(next); next += 4; break
            case 0xde: children = input.readUInt16BE(next) * 2; next += 2; break
            case 0xdf: children = input.readUInt32BE(next) * 2; next += 4; break
            default: throw new Error(`Unsupported MessagePack tag ${tag}`)
        }
        for (let i = 0; i < children; i++) next = walk(next)
        return next
    }
    let position = 0
    while (position < end) position = walk(position)
    if (position !== end) throw new Error("Truncated MessagePack response")
    if (!output) return input
    written += input.copy(output, written, copiedThrough)
    return output.subarray(0, written)
}

export interface ResponseEncodingInput {
    readonly payload: unknown
    /** Internal immutable MessagePack snapshot; never supplied by an HTTP client. */
    readonly packedPayload?: Uint8Array
    readonly compression?: {
        readonly config: CnLoadHttpCompressionConfig
        readonly acceptEncoding: string | readonly string[] | undefined
    }
}

export async function encodeCnResponse(input: ResponseEncodingInput) {
    let start = performance.now()
    const packed = input.packedPayload
        ? Buffer.isBuffer(input.packedPayload) ? input.packedPayload : Buffer.from(input.packedPayload)
        : pack(input.payload)
    const packMs = performance.now() - start
    start = performance.now()
    const fixed = fixUint32Tags(packed)
    const fixMs = performance.now() - start
    start = performance.now()
    const base64 = fixed.toString("base64")
    const base64Ms = performance.now() - start
    let compressionError = false
    let compressionResult: Awaited<ReturnType<typeof compressCnLoadHttpBody>> | undefined
    start = performance.now()
    if (input.compression) {
        try {
            compressionResult = await compressCnLoadHttpBody(
                Buffer.from(base64, "ascii"), input.compression.acceptEncoding, input.compression.config,
            )
        } catch { compressionError = true }
    }
    const compression = compressionResult ? {
        encoding: compressionResult.encoding,
        originalBytes: compressionResult.originalBytes,
        wireBytes: compressionResult.wireBytes,
        reason: compressionResult.reason,
    } : undefined
    return {
        body: compressionResult?.encoding ? compressionResult.body : base64,
        compression,
        compressionError,
        timings: { packMs, fixMs, base64Ms, compressWaitMs: input.compression ? performance.now() - start : 0 },
    }
}

export type ResponseEncodingResult = Awaited<ReturnType<typeof encodeCnResponse>>
