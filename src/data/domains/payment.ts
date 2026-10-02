import { getDb } from "../db"

export interface PaymentReceipt {
    playerId: number
    paymentKey: string
    productId: string
    paidVmoney: number
    freeVmoney: number
    afterVmoney: number
    afterFreeVmoney: number
    purchaseCount: number
}

interface RawPaymentReceipt {
    player_id: number
    payment_key: string
    product_id: string
    paid_vmoney: number
    free_vmoney: number
    after_vmoney: number
    after_free_vmoney: number
    purchase_count: number
}

function buildReceipt(row: RawPaymentReceipt): PaymentReceipt {
    return {
        playerId: row.player_id,
        paymentKey: row.payment_key,
        productId: row.product_id,
        paidVmoney: row.paid_vmoney,
        freeVmoney: row.free_vmoney,
        afterVmoney: row.after_vmoney,
        afterFreeVmoney: row.after_free_vmoney,
        purchaseCount: row.purchase_count,
    }
}

export function getPaymentReceiptSync(playerId: number, paymentKey: string): PaymentReceipt | null {
    const row = getDb().prepare(`
        SELECT player_id, payment_key, product_id, paid_vmoney, free_vmoney,
               after_vmoney, after_free_vmoney, purchase_count
        FROM player_payment_receipts
        WHERE player_id = ? AND payment_key = ?
    `).get(playerId, paymentKey) as RawPaymentReceipt | undefined
    return row ? buildReceipt(row) : null
}

export function getPaymentProductCountSync(playerId: number, productId: string): number {
    const row = getDb().prepare(`
        SELECT COUNT(*) AS count
        FROM player_payment_receipts
        WHERE player_id = ? AND product_id = ?
    `).get(playerId, productId) as { count: number }
    return Number(row.count) || 0
}

export function insertPaymentReceiptSync(receipt: PaymentReceipt): void {
    getDb().prepare(`
        INSERT INTO player_payment_receipts (
            player_id, payment_key, product_id, paid_vmoney, free_vmoney,
            after_vmoney, after_free_vmoney, purchase_count, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
        receipt.playerId,
        receipt.paymentKey,
        receipt.productId,
        receipt.paidVmoney,
        receipt.freeVmoney,
        receipt.afterVmoney,
        receipt.afterFreeVmoney,
        receipt.purchaseCount,
        Date.now(),
    )
}
