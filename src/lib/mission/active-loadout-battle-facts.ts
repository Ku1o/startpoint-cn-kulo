import type { ReadonlyContentRepository } from "../../content/runtime/content-snapshot"
import { getContentSnapshot } from "../../content/runtime/content-snapshot"
import { incrementActiveMissionBattleFactSync } from "../../data/domains/active_mission_battle_facts"
import characterTextJson from "../../../assets/cdndata/character_text.json"
import { getEquipmentElement } from "../assets"
import type { FinishContext } from "../quest/finish/types"
import { getActiveMissionMasterDefinitions, type ActiveMissionMasterDefinition } from "./active-master-data"
import { matchesActiveMissionQuestRange } from "./active-reconciliation"

const ELEMENT_LOADOUT_PATTERN = 89
const CHARACTER_CAPABILITY_PATTERN = 90
const ELEMENT_RESISTANCE_DOWN_CATEGORY = "ACToleranceOfElement_Down"
const LOADOUT_PATTERNS = new Set([ELEMENT_LOADOUT_PATTERN, CHARACTER_CAPABILITY_PATTERN])
const ELEMENT_RESISTANCE_DOWN_TEXT = /属性(?:抗性|耐性)(?:降低|下降)/
const OWN_SIDE_RESISTANCE_DOWN_TEXT = /(?:自身|队伍全体)[^。；]{0,80}全?属性(?:抗性|耐性)(?:降低|下降)/

function flattenText(value: unknown, output: string[] = []): string[] {
    if (typeof value === "string") output.push(value)
    else if (Array.isArray(value)) {
        for (const item of value) flattenText(item, output)
    } else if (value && typeof value === "object") {
        for (const item of Object.values(value)) flattenText(item, output)
    }
    return output
}

export function hasEnemyElementResistanceDownCapability(value: unknown): boolean {
    return flattenText(value).some(text => ELEMENT_RESISTANCE_DOWN_TEXT.test(text)
        && (!OWN_SIDE_RESISTANCE_DOWN_TEXT.test(text) || /(?:敌人|敌方)/.test(text)))
}

const ELEMENT_RESISTANCE_DOWN_CHARACTER_IDS = new Set(
    Object.entries(characterTextJson as Record<string, unknown>)
        .filter(([, value]) => hasEnemyElementResistanceDownCapability(value))
        .map(([characterId]) => Number(characterId))
        .filter(characterId => Number.isSafeInteger(characterId) && characterId > 0),
)

export interface LoadoutBattleCharacterState {
    readonly element?: number
    readonly abilityCategories?: ReadonlySet<string>
}

export interface LoadoutBattleContext {
    readonly questAccomplished: boolean
    readonly isMulti: boolean
    readonly questCategory: number
    readonly questId: number
    readonly partyCharacterIds: readonly number[]
    readonly equipmentElements?: readonly number[]
}

export interface LoadoutBattleFact {
    readonly missionId: number
}

export function collectBattleEquipmentElements(
    equipments: readonly ({ readonly id?: number | null } | null)[] | undefined,
): number[] {
    if (!equipments) return []
    const elements = new Set<number>()
    for (const equipment of equipments) {
        const equipmentId = Number(equipment?.id)
        if (!Number.isSafeInteger(equipmentId) || equipmentId <= 0) continue
        const element = getEquipmentElement(equipmentId)
        if (Number.isSafeInteger(element) && element >= 0 && element <= 5) elements.add(element)
    }
    return [...elements]
}

function matchesBattleKind(battleKind: number, isMulti: boolean): boolean {
    return battleKind === 3 || battleKind === 2 && isMulti || battleKind === 1 && !isMulti
}

function parseTargetElement(value: unknown): number | null {
    const target = Number(value)
    return Number.isSafeInteger(target) && target >= 1 && target <= 6 ? target : null
}

function matchesCharacterElement(
    targetElement: number | null,
    partyCharacterIds: ReadonlySet<number>,
    characters: Readonly<Record<string, LoadoutBattleCharacterState>>,
): boolean {
    if (targetElement === null) return false
    for (const characterId of partyCharacterIds) {
        const character = characters[String(characterId)]
        if (character && typeof character.element === "number" && character.element + 1 === targetElement) return true
    }
    return false
}

function matchesEquipmentElement(
    rawTargetElement: unknown,
    equipmentElements: readonly number[] | undefined,
): boolean {
    if (rawTargetElement === undefined || rawTargetElement === null || rawTargetElement === "(None)") return true
    const targetElement = parseTargetElement(rawTargetElement)
    if (targetElement === null || equipmentElements === undefined) return false
    // The finish request contains ElementKind (0-based); the mission master uses ElementTargetKind (1-based).
    return equipmentElements.some(element => Number(element) + 1 === targetElement)
}

function parseAbilityCategories(value: unknown): string[] {
    if (typeof value !== "string") return []
    return value.split(",")
        .map(category => category.trim())
        .filter(category => category.length > 0 && category !== "(None)")
}

function matchesCharacterAbilityCategory(
    rawCategories: unknown,
    partyCharacterIds: ReadonlySet<number>,
    characters: Readonly<Record<string, LoadoutBattleCharacterState>>,
): boolean {
    const requiredCategories = parseAbilityCategories(rawCategories)
    if (requiredCategories.length === 0) return false
    return [...partyCharacterIds].some(characterId => {
        const categories = characters[String(characterId)]?.abilityCategories
        return categories !== undefined && requiredCategories.some(category => categories.has(category))
    })
}

export function collectActiveMissionLoadoutBattleFacts(
    definitions: readonly ActiveMissionMasterDefinition[],
    context: LoadoutBattleContext,
    characters: Readonly<Record<string, LoadoutBattleCharacterState>>,
): LoadoutBattleFact[] {
    if (!context.questAccomplished) return []
    const partyCharacterIds = new Set(context.partyCharacterIds)
    const matched: LoadoutBattleFact[] = []
    for (const definition of definitions) {
        try {
            const pattern = Number(definition.row[29])
            const battleKind = Number(definition.row[32])
            if (!LOADOUT_PATTERNS.has(pattern)
                || !Number.isSafeInteger(battleKind)
                || !matchesBattleKind(battleKind, context.isMulti)
                || !matchesActiveMissionQuestRange(definition.row, context.questCategory, context.questId)) continue
            if (pattern === ELEMENT_LOADOUT_PATTERN && (
                !matchesCharacterElement(parseTargetElement(definition.row[69]), partyCharacterIds, characters)
                || !matchesEquipmentElement(definition.row[70], context.equipmentElements)
            )) continue
            if (pattern === CHARACTER_CAPABILITY_PATTERN
                && !matchesCharacterAbilityCategory(definition.row[71], partyCharacterIds, characters)) continue
            matched.push({ missionId: definition.missionId })
        } catch {
            continue
        }
    }
    return matched.sort((left, right) => left.missionId - right.missionId)
}

function resolveRepository(): ReadonlyContentRepository | undefined {
    try {
        return getContentSnapshot().repository
    } catch {
        return undefined
    }
}

function resolveDefinitions(
    repository?: ReadonlyContentRepository,
): readonly ActiveMissionMasterDefinition[] {
    if (!repository) return getActiveMissionMasterDefinitions()
    try {
        return getActiveMissionMasterDefinitions(repository)
    } catch {
        return getActiveMissionMasterDefinitions()
    }
}

export function recordActiveMissionLoadoutBattleFactsSync(context: FinishContext): void {
    if (!context.questAccomplished) return
    const repository = resolveRepository()
    const definitions = resolveDefinitions(repository)
    const partyCharacterIds = [...context.party.characters, ...context.party.unison_characters]
        .flatMap(character => character?.id ? [character.id] : [])
    const targetCharacterIds = new Set(definitions.flatMap(definition => {
        const pattern = Number(definition.row[29])
        const targetElement = parseTargetElement(definition.row[69])
        const requiredCategories = parseAbilityCategories(definition.row[71])
        return pattern === ELEMENT_LOADOUT_PATTERN && targetElement !== null
            || pattern === CHARACTER_CAPABILITY_PATTERN
                && requiredCategories.includes(ELEMENT_RESISTANCE_DOWN_CATEGORY)
            ? partyCharacterIds
            : []
    }))
    let characterTable: Record<string, { readonly element?: number }> = {}
    if (repository) {
        try {
            characterTable = repository.table<Record<string, { readonly element?: number }>>("character.json")
        } catch {
            characterTable = {}
        }
    }
    const characters: Record<string, LoadoutBattleCharacterState> = {}
    for (const characterId of targetCharacterIds) {
        const element = characterTable?.[String(characterId)]?.element
        const abilityCategories = new Set<string>()
        if (ELEMENT_RESISTANCE_DOWN_CHARACTER_IDS.has(characterId)) {
            abilityCategories.add(ELEMENT_RESISTANCE_DOWN_CATEGORY)
        }
        if (Number.isSafeInteger(element) || abilityCategories.size > 0) {
            characters[String(characterId)] = {
                element: Number.isSafeInteger(element) ? element as number : undefined,
                abilityCategories,
            }
        }
    }
    const equipmentElements = context.equipmentElements
        ?? collectBattleEquipmentElements(context.party.equipments)
    const facts = collectActiveMissionLoadoutBattleFacts(definitions, {
        questAccomplished: context.questAccomplished,
        isMulti: context.isMulti === true,
        questCategory: context.questCategory,
        questId: context.questId,
        partyCharacterIds,
        equipmentElements,
    }, characters)
    for (const fact of facts) {
        incrementActiveMissionBattleFactSync(context.playerId, fact.missionId)
    }
}
