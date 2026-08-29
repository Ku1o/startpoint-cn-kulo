import {
    degreeDefinitions as degrees,
    serverCharacters as characters,
    serverManaNodes as manaNodes,
} from "./content-master"
import { getPlayerCharactersSync } from "../data/domains/character"
import { getPlayerDegreeIdsSync } from "../data/domains/degree"
import { PlayerCharacter } from "../data/types"

export interface PlayerProfileStats {
    maxOpenedManaBoardSecondCount: number
    maxOwnedCharacterCount: number
    maxOwnedDegreeCount: number
    openedManaBoardSecondCount: number
    ownedCharacterCount: number
    ownedDegreeCount: number
}

const MAX_OWNED_CHARACTER_COUNT = Object.keys(characters).length
const MAX_OWNED_DEGREE_COUNT = Object.keys(degrees).length
const MAX_OPENED_MANA_BOARD_SECOND_COUNT = Object.values(
    manaNodes as Record<string, Record<string, unknown>>,
).filter(boards => Object.prototype.hasOwnProperty.call(boards, "2")).length

export function getPlayerProfileStatsSync(
    playerId: number,
    characters: Record<string, PlayerCharacter> = getPlayerCharactersSync(playerId),
): PlayerProfileStats {
    const ownedCharacters = Object.values(characters)
    return {
        maxOpenedManaBoardSecondCount: MAX_OPENED_MANA_BOARD_SECOND_COUNT,
        maxOwnedCharacterCount: MAX_OWNED_CHARACTER_COUNT,
        maxOwnedDegreeCount: MAX_OWNED_DEGREE_COUNT,
        openedManaBoardSecondCount: ownedCharacters.filter(character => (
            character.bondTokenList.some(token => token.manaBoardIndex === 2 && token.status >= 1)
        )).length,
        ownedCharacterCount: ownedCharacters.length,
        ownedDegreeCount: getPlayerDegreeIdsSync(playerId).length,
    }
}
