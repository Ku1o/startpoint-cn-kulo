import type { FastifyInstance } from "fastify";

/**
 * Retired platform gate. Deferring an IPA build must not block iOS requests.
 * Keep the callable export for deployed entrypoints, but ignore legacy settings.
 */
export function installLocalClientCompat(
    _app: FastifyInstance,
    _platform?: string,
): void {}
