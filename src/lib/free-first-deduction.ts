export interface FreeFirstDeduction {
    freeBalance: number
    paidBalance: number
    freeSpent: number
    paidSpent: number
}

/**
 * Computes a free-currency-first deduction without performing any I/O.
 * Returns null when the balances or cost are invalid, or the combined balance
 * cannot cover the cost.
 */
export function computeFreeFirstDeduction(
    freeBalance: number,
    paidBalance: number,
    cost: number,
): FreeFirstDeduction | null {
    if (
        !Number.isSafeInteger(freeBalance)
        || !Number.isSafeInteger(paidBalance)
        || !Number.isSafeInteger(cost)
        || freeBalance < 0
        || paidBalance < 0
        || cost < 0
    ) return null

    const freeSpent = Math.min(freeBalance, cost)
    const paidSpent = cost - freeSpent
    if (paidSpent > paidBalance) return null

    return {
        freeBalance: freeBalance - freeSpent,
        paidBalance: paidBalance - paidSpent,
        freeSpent,
        paidSpent,
    }
}
