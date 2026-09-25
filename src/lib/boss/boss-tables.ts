import baseBossBattleQuests from "../../../assets/boss_battle_quest.json"
import cnmodBossBattleQuests from "../../../assets/boss_battle_quest_cnmod.json"
import { RawQuests } from "../types"

/**
 * Server-side boss master data.  New permanent bosses are appended through a
 * cnmod table so the upstream master stays untouched and future bosses can
 * be added without rewriting the existing entries.
 */
export const serverBossBattleQuests: RawQuests = {
    ...(baseBossBattleQuests as RawQuests),
    ...(cnmodBossBattleQuests as RawQuests),
}
