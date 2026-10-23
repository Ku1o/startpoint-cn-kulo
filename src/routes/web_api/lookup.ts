import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { createHash } from "crypto";
import characterTable from "../../../docs/generated/character_table.json";
import { degreeDefinitions, serverCharacters as serverCharacterData } from "../../lib/content-master";
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

export function buildDegreeLookup(rows: Readonly<Record<string, { name: string; string_id: string }>>): Record<string, { name: string; image: string }> {
    return Object.fromEntries(Object.entries(rows).map(([id, degree]) => [id, {
        name: degree.name,
        image: `dynamic/degree/${degree.string_id}.png`,
    }]))
}

function cachedLookup(value: unknown) {
    const body = JSON.stringify(value)
    return { body, etag: `"${createHash("sha256").update(body).digest("hex")}"` }
}

const lookups = {
    characters: cachedLookup(charMap),
    items: cachedLookup(mergedItemLookup),
    equipment: cachedLookup(equipmentLookup),
    quests: cachedLookup(questLookup),
    degrees: cachedLookup(buildDegreeLookup(degreeDefinitions)),
}

const routes = async (fastify: FastifyInstance) => {
    for (const [kind, value] of Object.entries(lookups)) {
        fastify.get(`/${kind}`, async (request: FastifyRequest, reply: FastifyReply) => {
            // These URLs are stable across releases: revalidate, never mark them immutable.
            reply.header("Cache-Control", "private, no-cache").header("ETag", value.etag)
            const condition = request.headers["if-none-match"]
            if (typeof condition === "string" && condition.split(",").some(tag => {
                const normalized = tag.trim().replace(/^W\//, "")
                return normalized === "*" || normalized === value.etag
            })) return reply.status(304).send()
            return reply.type("application/json").send(value.body)
        })
    }
}

export default routes;
