import { getContentSnapshot } from "../content/runtime/content-snapshot"
import { QuestCategory } from "./types"

type StoryJoinRow = readonly [string, string, string, string, string, string, string, string]

/** Native quest-join rows only. Town joins have a separate character endpoint. */
export function getQuestJoinCharacterIds(category: number, questId: number): number[] {
    const table = getContentSnapshot().repository.table<Record<string, StoryJoinRow[]>>("story_join_character.json")
    const result: number[] = []
    for (const [characterIdText, rows] of Object.entries(table)) {
        if (!Array.isArray(rows) || rows.length !== 1 || !Array.isArray(rows[0]) || rows[0].length !== 8) {
            throw new Error(`Invalid story join row for character ${characterIdText}.`)
        }
        const [referenceKind, chapter, section, episode, encodedQuestId, , joinType, temporary] = rows[0]
        if (joinType !== "quest") continue
        if (referenceKind !== "0" || temporary !== "false") {
            throw new Error(`Unsupported quest story join for character ${characterIdText}.`)
        }
        const characterId = Number(characterIdText)
        const components = [chapter, section, episode, encodedQuestId].map(Number)
        if (!Number.isSafeInteger(characterId) || characterId <= 0
            || components.some(value => !Number.isSafeInteger(value) || value < 0)
            || components[0] * 1_000_000 + components[1] * 1_000 + components[2] !== components[3]) {
            throw new Error(`Invalid story join quest identity for character ${characterIdText}.`)
        }
        if (category === QuestCategory.MAIN && questId === components[3]) result.push(characterId)
    }
    return result
}
