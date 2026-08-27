export function countNewAbilitySoulEquipments(
    previousIds: readonly (number | null | undefined)[],
    currentIds: readonly (number | null | undefined)[],
): number {
    let count = 0
    for (let slot = 0; slot < currentIds.length; slot++) {
        const nextId = currentIds[slot]
        if (Number.isSafeInteger(nextId)
            && Number(nextId) > 0
            && nextId !== previousIds[slot]) {
            count++
        }
    }
    return count
}
