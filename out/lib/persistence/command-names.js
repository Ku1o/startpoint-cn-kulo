"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.MISSION_SETTLE_CATEGORIES = void 0;
/**
 * Stable command names and their argument shapes.
 *
 * Commands are named here instead of inside the domain modules so callers, the
 * registry and the writer worker can share one literal without importing each
 * other. The domain type import is type-only, so this module stays free of
 * runtime dependencies and cannot create an import cycle.
 */
exports.MISSION_SETTLE_CATEGORIES = "mission.settle_categories";
