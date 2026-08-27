import { getConfigSync } from "./assets"

export const OFFICIAL_MAX_MANA = 999999999

export interface ManaBalances {
    freeMana: number
    paidMana: number
}

export interface FreeManaGrantResult {
    freeMana: number
    creditedMana: number
}

export function getMaxManaSync(): number {
    const configuredMaxMana = getConfigSync().max_mana
    return Number.isSafeInteger(configuredMaxMana) && configuredMaxMana > 0
        ? configuredMaxMana
        : OFFICIAL_MAX_MANA
}

export function getTotalMana(balances: ManaBalances): number {
    return balances.freeMana + balances.paidMana
}

export function canReceiveMana(
    balances: ManaBalances,
    amount: number,
    maxMana: number = getMaxManaSync(),
): boolean {
    return Number.isFinite(amount)
        && amount >= 0
        && getTotalMana(balances) + amount <= maxMana
}

/**
 * Applies the CN client rule for free-Mana rewards: free and paid Mana share
 * one cap, and only the portion that still fits is credited.
 */
export function calculateFreeManaGrant(
    balances: ManaBalances,
    amount: number,
    maxMana: number = getMaxManaSync(),
): FreeManaGrantResult {
    if (!Number.isFinite(amount) || amount <= 0) {
        return { freeMana: balances.freeMana, creditedMana: 0 }
    }

    const availableMana = Math.max(0, maxMana - getTotalMana(balances))
    const creditedMana = Math.min(amount, availableMana)
    return {
        freeMana: balances.freeMana + creditedMana,
        creditedMana,
    }
}
