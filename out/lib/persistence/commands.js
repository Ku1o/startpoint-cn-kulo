"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const command_registry_1 = require("./command-registry");
const command_names_1 = require("./command-names");
const settlement_1 = require("../mission/settlement");
/**
 * Domain command implementations.
 *
 * This module is the single place that binds stable command names to domain
 * code. It must be imported by every process that executes commands: the main
 * process (in-process fallback and rollback mode) and the writer worker. The
 * import is intentionally side-effect only.
 *
 * Adding a domain here means the identical function is used by both execution
 * paths, which is what makes the `CN_WRITER_THREAD` switch behaviour-neutral.
 */
(0, command_registry_1.registerWriterCommand)(command_names_1.MISSION_SETTLE_CATEGORIES, args => (0, settlement_1.settleMissionCategories)(args.playerId, args.categories, new Date(args.evaluationTimeMs)));
