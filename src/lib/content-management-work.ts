import { FastifyReply, FastifyRequest } from "fastify";

// Administrative reads share the game event loop. Keep only a small amount of
// pending work, and yield between batches so player traffic can run as well.
const MAX_WAITING = 3;
type Entry = { start: () => void; cancel: () => void };
const waiting: Entry[] = [];
let running = false;

export class ContentReadError extends Error {
    constructor(public statusCode: number, public code: string, message: string) { super(message); }
}

const nextTurn = () => new Promise<void>(resolve => setImmediate(resolve));

function pump(): void {
    if (running) return;
    const entry = waiting.shift();
    if (entry) { running = true; entry.start(); }
}

export function contentManagementReadStatus(): { running: number; waiting: number; capacity: number } {
    return { running: running ? 1 : 0, waiting: waiting.length, capacity: MAX_WAITING };
}

/** Shared reads own their cancellation signal, independently of any one browser. */
export function queueContentManagementRead<T>(
    signal: AbortSignal,
    work: (checkpoint: () => Promise<void>) => Promise<T> | T,
    onBusy: () => void = () => {},
): Promise<T> {
    if (running && waiting.length >= MAX_WAITING) {
        onBusy();
        return Promise.reject(new ContentReadError(429, "CONTENT_READ_BUSY", "后台查询较多，请稍后重试。"));
    }
    return new Promise<T>((resolve, reject) => {
        let started = false;
        let cancelled = false;
        let settled = false;
        const cancellation = () => new ContentReadError(499, "CONTENT_READ_CANCELLED", "该查询已取消。");
        const cleanup = () => signal.removeEventListener("abort", abort);
        const abort = () => {
            if (settled) return;
            cancelled = true;
            if (!started) {
                const index = waiting.indexOf(entry);
                if (index >= 0) waiting.splice(index, 1);
                settled = true;
                cleanup();
                reject(cancellation());
            }
        };
        const checkpoint = async () => {
            if (cancelled || signal.aborted) throw cancellation();
            await nextTurn();
            if (cancelled || signal.aborted) throw cancellation();
        };
        const entry: Entry = {
            cancel: abort,
            start: () => {
                started = true;
                void (async () => {
                    try {
                        await checkpoint();
                        const value = await work(checkpoint);
                        if (cancelled || signal.aborted) throw cancellation();
                        resolve(value);
                    } catch (error) { reject(error); }
                    finally {
                        settled = true;
                        cleanup();
                        running = false;
                        pump();
                    }
                })();
            },
        };
        signal.addEventListener("abort", abort, { once: true });
        if (signal.aborted) { abort(); return; }
        waiting.push(entry);
        pump();
    });
}

export function runContentManagementRead<T>(
    request: FastifyRequest,
    reply: FastifyReply,
    work: (checkpoint: () => Promise<void>) => Promise<T> | T,
): Promise<T> {
    const controller = new AbortController();
    const abort = () => controller.abort();
    const closed = () => { if (!reply.raw.writableEnded) abort(); };
    request.raw.on("aborted", abort);
    reply.raw.on("close", closed);
    if (request.raw.aborted || (reply.raw.destroyed && !reply.raw.writableEnded)) abort();
    return queueContentManagementRead(controller.signal, work, () => reply.header("Retry-After", "1"))
        .finally(() => {
            request.raw.removeListener("aborted", abort);
            reply.raw.removeListener("close", closed);
        });
}
