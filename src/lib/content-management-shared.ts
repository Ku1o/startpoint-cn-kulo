import type { FastifyReply, FastifyRequest } from "fastify"
import { Buffer } from "node:buffer"
import { ContentReadError, queueContentManagementRead } from "./content-management-work"

type Flight = { controller: AbortController; promise: Promise<string>; subscribers: number; bytes: number }
const MAX_SUBSCRIBERS_PER_READ = 16, MAX_SUBSCRIBERS = 64
const MAX_SHARED_JSON_BYTES = 2 * 1024 * 1024
export class ContentSharedReadOversized extends Error {}
const stats = { flights: 0, subscribers: 0, jsonBytes: 0, peakFlights: 0, peakSubscribers: 0, peakJsonBytes: 0,
    builds: 0, sharedJoins: 0, completed: 0, cancelled: 0, cancelledBuilds: 0, busy: 0, oversized: 0, failed: 0 }
/** Process diagnostics only; not exposed as a management endpoint. */
export function contentManagementSharedReadStatus() { return { ...stats } }

/** Only in-flight JSON is shared. Completed or cancelled reads are never cached.
 * This avoids retaining large control graphs or reusing time-dependent status.
 * Instances belong to one route registration, so separate apps cannot share data.
 */
export class ContentManagementSharedReads {
    private readonly flights = new Map<string, Flight>()
    private subscribers = 0

    status() { return { flights: this.flights.size, subscribers: this.subscribers } }

    read(request: FastifyRequest, reply: FastifyReply, key: string,
        work: (checkpoint: () => Promise<void>) => Promise<string>): Promise<string> {
        const cancelled = () => new ContentReadError(499, "CONTENT_READ_CANCELLED", "该查询已取消。")
        const disconnected = () => request.raw.aborted || (reply.raw.destroyed && !reply.raw.writableEnded)
        if (disconnected()) return Promise.reject(cancelled())
        let flight = this.flights.get(key)
        if (this.subscribers >= MAX_SUBSCRIBERS || flight && flight.subscribers >= MAX_SUBSCRIBERS_PER_READ) {
            reply.header("Retry-After", "1")
            return Promise.reject(new ContentReadError(429, "CONTENT_READ_BUSY", "后台查询较多，请稍后重试。"))
        }
        if (!flight) {
            const controller = new AbortController()
            const entry: Flight = { controller, promise: undefined!, subscribers: 0, bytes: 0 }
            // The shared task joins the same bounded queue as ordinary reads.
            // Defer admission until this browser has installed its own listeners.
            entry.promise = Promise.resolve().then(() => queueContentManagementRead(controller.signal, async checkpoint => {
                stats.builds++
                const body = await work(checkpoint)
                // A very large legitimate response retains the original bounded
                // independent-query path instead of becoming a shared object.
                const bytes = Buffer.byteLength(body)
                if (bytes > MAX_SHARED_JSON_BYTES) { stats.oversized++; throw new ContentSharedReadOversized() }
                entry.bytes = bytes; stats.jsonBytes += bytes
                stats.peakJsonBytes = Math.max(stats.peakJsonBytes, stats.jsonBytes)
                stats.completed++
                return body
            }))
                .catch(error => {
                    if (error instanceof ContentReadError && error.statusCode === 429) stats.busy++
                    else if (error instanceof ContentReadError && error.statusCode === 499) stats.cancelledBuilds++
                    else if (!(error instanceof ContentSharedReadOversized)) stats.failed++
                    throw error
                })
                .finally(() => {
                    if (this.flights.get(key) === entry) this.flights.delete(key)
                    stats.flights--; stats.jsonBytes -= entry.bytes
                })
            flight = entry
            this.flights.set(key, entry)
            stats.flights++; stats.peakFlights = Math.max(stats.peakFlights, stats.flights)
        } else stats.sharedJoins++
        const shared = flight
        shared.subscribers++; this.subscribers++
        stats.subscribers++; stats.peakSubscribers = Math.max(stats.peakSubscribers, stats.subscribers)
        return new Promise<string>((resolve, reject) => {
            let settled = false
            const cleanup = () => {
                request.raw.removeListener("aborted", abort)
                reply.raw.removeListener("close", close)
                shared.subscribers--; this.subscribers--
                stats.subscribers--
                if (shared.subscribers === 0) {
                    if (this.flights.get(key) === shared) this.flights.delete(key)
                    shared.controller.abort()
                }
            }
            const finish = (error: unknown, value?: string) => {
                if (settled) return
                settled = true; cleanup()
                if (error) {
                    if (error instanceof ContentReadError && error.statusCode === 429) reply.header("Retry-After", "1")
                    reject(error)
                } else resolve(value!)
            }
            const abort = () => { if (!settled) stats.cancelled++; finish(cancelled()) }
            const close = () => { if (!reply.raw.writableEnded) abort() }
            request.raw.on("aborted", abort)
            reply.raw.on("close", close)
            shared.promise.then(value => finish(disconnected() ? cancelled() : null, value), error => finish(error))
            if (disconnected()) abort()
        })
    }
}
