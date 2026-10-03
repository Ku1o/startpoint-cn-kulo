import { registerWriterCommand } from "./command-registry"
import { MISSION_SETTLE_CATEGORIES, type MissionSettleCategoriesArgs } from "./command-names"
import { settleMissionCategories, type MissionSettlementResult } from "../mission/settlement"

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

registerWriterCommand<MissionSettleCategoriesArgs, MissionSettlementResult>(
    MISSION_SETTLE_CATEGORIES,
    args => settleMissionCategories(
        args.playerId,
        args.categories,
        new Date(args.evaluationTimeMs),
    ),
)
