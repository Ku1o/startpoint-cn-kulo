import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import characterTable from "../../../docs/generated/character_table.json";
import serverCharacterData from "../../../assets/character.json";
import itemLookup from "../../../assets/item_lookup.json";
import cnmodItemLookup from "../../../assets/item_lookup_cnmod.json";
import equipmentLookup from "../../../assets/equipment_lookup.json";
import questLookup from "../../../assets/quest_lookup.json";

interface CharEntry { id: number; name: string; title: string; rarity: string; element: string }
interface ServerCharEntry { name?: string; rarity?: number; element?: number }
interface CharacterLookupEntry { name: string; title: string; rarity: string; element: string }

const ELEMENT_NAMES: Record<number, string> = {
    0: "火",
    1: "水",
    2: "雷",
    3: "风",
    4: "光",
    5: "暗",
}

/**
 * Build the admin/mail lookup from the descriptive generated table, then fill
 * any newly-added server characters that the static table has not caught up
 * with yet.  The fallback deliberately leaves the title empty instead of
 * inventing metadata; the character remains selectable and identifiable.
 */
export function buildCharacterLookup(
    generatedRows: readonly CharEntry[],
    serverRows: Readonly<Record<string, ServerCharEntry>>,
): Record<number, CharacterLookupEntry> {
    const result: Record<number, CharacterLookupEntry> = {}
    for (const character of generatedRows) {
        result[character.id] = {
            name: character.name,
            title: character.title,
            rarity: character.rarity,
            element: character.element,
        }
    }
    for (const [characterIdText, character] of Object.entries(serverRows)) {
        const characterId = Number.parseInt(characterIdText, 10)
        if (!Number.isSafeInteger(characterId) || result[characterId] !== undefined) continue
        result[characterId] = {
            name: character.name?.trim() || characterIdText,
            title: "",
            rarity: Number.isFinite(character.rarity) ? `${character.rarity}★` : "",
            element: ELEMENT_NAMES[Number(character.element)] ?? "",
        }
    }
    return result
}

const charMap = buildCharacterLookup(
    characterTable as CharEntry[],
    serverCharacterData as Record<string, ServerCharEntry>,
)
const mergedItemLookup = {
    ...(itemLookup as Record<string, string>),
    ...(cnmodItemLookup as Record<string, string>),
}
const routes = async (fastify: FastifyInstance) => {
    fastify.get("/characters", async (_request: FastifyRequest, reply: FastifyReply) => {
        return reply.send(charMap)
    })

    fastify.get("/items", async (_request: FastifyRequest, reply: FastifyReply) => {
        return reply.send(mergedItemLookup)
    })

    fastify.get("/equipment", async (_request: FastifyRequest, reply: FastifyReply) => {
        return reply.send(equipmentLookup)
    })

    fastify.get("/quests", async (_request: FastifyRequest, reply: FastifyReply) => {
        return reply.send(questLookup)
    })
}

export default routes;
