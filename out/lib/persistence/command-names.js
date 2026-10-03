"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.MULTI_RECORD_BATTLE_FACTS = exports.MULTI_CLEANUP_ACTIVE_QUEST = exports.SINGLE_REFRESH_QUEST_PROGRESS = exports.MISSION_SETTLE_CATEGORIES = void 0;
/**
 * Stable command names and their argument shapes.
 *
 * Commands are named here instead of inside the domain modules so callers, the
 * registry and the writer worker can share one literal without importing each
 * other. The domain type import is type-only, so this module stays free of
 * runtime dependencies and cannot create an import cycle.
 */
exports.MISSION_SETTLE_CATEGORIES = "mission.settle_categories";
/**
 * 单人副本结算前的关卡进度刷新。原实现用 runPersistenceTransaction 包裹，
 * 因为深渊最好成绩的刷新是"读+写"；把整段搬进写线程后主线程不再承担它。
 */
exports.SINGLE_REFRESH_QUEST_PROGRESS = "single.refresh_quest_progress";
/** 多人结算后清理本场战斗的进行中关卡记录（单条 DELETE）。 */
exports.MULTI_CLEANUP_ACTIVE_QUEST = "multi.cleanup_active_quest";
/**
 * 多人结算的"战斗事实"事务：任务战斗事实、推荐队伍、蒸气机器人挑战与角色经验。
 * finishCtx 全部由请求体与数据库行组成，是普通数据，可安全跨线程传递。
 */
exports.MULTI_RECORD_BATTLE_FACTS = "multi.record_battle_facts";
