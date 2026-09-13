"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.isCharacterDegreeEligible = exports.isCharacterDegreeActivation = exports.CHARACTER_DEGREE_MAX_OVER_LIMIT = exports.CHARACTER_DEGREE_LEVEL_100_EXP = exports.CHARACTER_DEGREE_CATALOG = exports.CHARACTER_DEGREE_CHARACTER_IDS = void 0;
/** Reborn 24-character nameplates, excluding bosses and minibosses. */
exports.CHARACTER_DEGREE_CHARACTER_IDS = Object.freeze([
    119989, 119996, 119997, 129952, 129992, 129997, 129999, 139995,
    139997, 139998, 139999, 149988, 149989, 149990, 149995, 149996,
    149997, 149999, 169989, 169996, 169997, 169998, 169999, 179999,
]);
exports.CHARACTER_DEGREE_CATALOG = Object.freeze(exports.CHARACTER_DEGREE_CHARACTER_IDS.map((characterId, index) => Object.freeze({
    character_id: characterId,
    degree_ids: Object.freeze([9910001 + 2 * index, 9910002 + 2 * index]),
})));
exports.CHARACTER_DEGREE_LEVEL_100_EXP = 379988;
exports.CHARACTER_DEGREE_MAX_OVER_LIMIT = 4;
/** The activation switch cannot redirect rewards or expand the reviewed roster. */
function isCharacterDegreeActivation(value) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const config = value;
    if (Object.keys(config).sort().join(",") !== "characters,enabled,schema_version"
        || config.schema_version !== 1 || typeof config.enabled !== "boolean"
        || !Array.isArray(config.characters)
        || config.characters.length !== exports.CHARACTER_DEGREE_CATALOG.length)
        return false;
    return config.characters.every((raw, index) => {
        if (!raw || typeof raw !== "object" || Array.isArray(raw))
            return false;
        const entry = raw;
        const expected = exports.CHARACTER_DEGREE_CATALOG[index];
        return Object.keys(entry).sort().join(",") === "character_id,degree_ids"
            && entry.character_id === expected.character_id
            && Array.isArray(entry.degree_ids) && entry.degree_ids.length === 2
            && entry.degree_ids.every((id, variant) => id === expected.degree_ids[variant]);
    });
}
exports.isCharacterDegreeActivation = isCharacterDegreeActivation;
function isCharacterDegreeEligible(character) {
    return Number.isSafeInteger(character.exp)
        && character.exp >= exports.CHARACTER_DEGREE_LEVEL_100_EXP
        && character.over_limit_step === exports.CHARACTER_DEGREE_MAX_OVER_LIMIT;
}
exports.isCharacterDegreeEligible = isCharacterDegreeEligible;
