import { getDb } from "../db"

export type NewsReceiptKind = "list" | "popup"

interface NewsReceiptRow {
    news_id: number
}

export function getAccountNewsReceiptIdsSync(
    accountId: number,
    kind: NewsReceiptKind,
): Set<number> {
    const rows = getDb().prepare(`
        SELECT news_id
        FROM account_news_receipts
        WHERE account_id = ? AND receipt_kind = ?
    `).all(accountId, kind) as NewsReceiptRow[]
    return new Set(rows.map(row => row.news_id))
}

export function hasAccountNewsReceiptSync(
    accountId: number,
    newsId: number,
    kind: NewsReceiptKind,
): boolean {
    return getDb().prepare(`
        SELECT 1
        FROM account_news_receipts
        WHERE account_id = ? AND news_id = ? AND receipt_kind = ?
        LIMIT 1
    `).get(accountId, newsId, kind) !== undefined
}

export function markAccountNewsReceiptSync(
    accountId: number,
    newsId: number,
    kind: NewsReceiptKind,
): void {
    getDb().prepare(`
        INSERT INTO account_news_receipts (account_id, news_id, receipt_kind, seen_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(account_id, news_id, receipt_kind) DO UPDATE SET
            seen_at = excluded.seen_at
    `).run(accountId, newsId, kind, Date.now())
}

export function markAccountNewsReceiptsSync(
    accountId: number,
    newsIds: readonly number[],
    kind: NewsReceiptKind,
): void {
    if (newsIds.length === 0) return
    const insert = getDb().prepare(`
        INSERT INTO account_news_receipts (account_id, news_id, receipt_kind, seen_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(account_id, news_id, receipt_kind) DO UPDATE SET
            seen_at = excluded.seen_at
    `)
    const now = Date.now()
    getDb().transaction(() => {
        for (const newsId of newsIds) insert.run(accountId, newsId, kind, now)
    })()
}

export function deleteNewsReceiptsSync(newsId: number, kind?: NewsReceiptKind): number {
    if (kind === undefined) {
        return getDb().prepare(`
            DELETE FROM account_news_receipts WHERE news_id = ?
        `).run(newsId).changes
    }
    return getDb().prepare(`
        DELETE FROM account_news_receipts
        WHERE news_id = ? AND receipt_kind = ?
    `).run(newsId, kind).changes
}

export function deleteAllPopupNewsReceiptsSync(): number {
    return getDb().prepare(`
        DELETE FROM account_news_receipts WHERE receipt_kind = 'popup'
    `).run().changes
}
