import type { PersistenceDomain } from "../persistence-coordinator"

/**
 * Registry of write commands that can run either inside the writer thread or,
 * as a rollback path, in the main process.
 *
 * A command owns a complete read-modify-write section: it may read through the
 * normal domain APIs, mutate through them, and return a plain result. Running
 * the whole section in one place keeps nested savepoint semantics identical to
 * the in-process coordinator and avoids splitting "read here, write there".
 *
 * Contract for command implementations:
 * - Arguments and results must be structured-clone safe (plain objects, arrays,
 *   strings, numbers, booleans, null). The writer worker verifies this before
 *   COMMIT so a non-cloneable result rolls back instead of committing silently.
 * - Nested `runPersistenceTransactionSync` calls stay inside the same
 *   transaction through better-sqlite3 savepoints.
 * - Non-durable side effects (in-memory caches, seed bookkeeping) must be
 *   registered through `context.afterCommit` so a rolled-back command cannot
 *   leak them.
 *
 * This module intentionally imports no domain code. It is loaded by the main
 * process, by the writer worker and by tests, so keeping it dependency-free
 * avoids import cycles with the persistence coordinator.
 */

export interface WriterCommandMeta {
    domain: PersistenceDomain
    operation: string
    playerId?: number
}

export interface WriterCommandContext {
    meta: WriterCommandMeta
    /**
     * Register a side effect that only runs after the surrounding SQLite
     * COMMIT succeeds. Effects of rolled-back commands are discarded.
     */
    afterCommit(effect: () => void): void
}

export type WriterCommandHandler<Args = any, Result = any> = (
    args: Args,
    context: WriterCommandContext,
) => Result

const commands = new Map<string, WriterCommandHandler>()

export function registerWriterCommand<Args, Result>(
    name: string,
    handler: WriterCommandHandler<Args, Result>,
): void {
    if (!name.trim()) throw new Error("Writer command name must not be empty.")
    commands.set(name, handler as WriterCommandHandler)
}

export function getWriterCommand(name: string): WriterCommandHandler | undefined {
    return commands.get(name)
}

export function listWriterCommands(): string[] {
    return [...commands.keys()].sort()
}

/** Test helper: drop every registration so a suite can start from a clean registry. */
export function clearWriterCommands(): void {
    commands.clear()
}

export function createWriterCommandContext(meta: WriterCommandMeta, afterCommit: (effect: () => void) => void): WriterCommandContext {
    return { meta, afterCommit }
}
