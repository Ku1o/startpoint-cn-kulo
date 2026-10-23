/** Shared by the admin's inert DOM sanitizer and the server's save boundary.
 * Keep the client's containers, text formatting, scene links and image attributes;
 * never admit browser execution, foreign namespaces or resource-bearing CSS.
 */
export const NEWS_HTML_TAGS = new Set([
    "html", "head", "body", "title", "style", "div", "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "br", "hr", "img", "a", "ul", "ol", "li", "table", "thead", "tbody", "tfoot", "tr", "td", "th",
    "b", "strong", "i", "em", "u", "s", "strike", "span", "font", "small", "big", "sub", "sup", "blockquote", "pre", "code",
])
const GLOBAL_ATTRIBUTES = new Set(["class", "title", "lang", "dir", "align", "style"])
const TAG_ATTRIBUTES: Record<string, readonly string[]> = {
    img: ["src", "alt", "width", "height", "button"], a: ["href", "scene"],
    font: ["color", "face", "size"], table: ["width", "height", "border", "cellpadding", "cellspacing", "bgcolor"],
    td: ["width", "height", "colspan", "rowspan", "valign", "bgcolor"],
    th: ["width", "height", "colspan", "rowspan", "valign", "bgcolor"], ol: ["start", "type"], li: ["value"],
}
const STYLE_PROPERTIES = new Set([
    "color", "background-color", "font", "font-family", "font-size", "font-weight", "font-style", "text-align", "text-decoration",
    "vertical-align", "line-height", "letter-spacing", "white-space", "word-break", "overflow-wrap", "width", "height", "max-width", "max-height",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left", "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "border", "border-top", "border-right", "border-bottom", "border-left", "border-color", "border-style", "border-width", "border-collapse", "border-spacing",
])

export function isNewsHtmlAttribute(tag: string, name: string): boolean {
    return GLOBAL_ATTRIBUTES.has(name) || (TAG_ATTRIBUTES[tag] ?? []).includes(name)
}

export function isNewsHtmlUrl(value: string, image = false): boolean {
    if (!value || /[\u0000-\u0020\u007f<>"`]/.test(value)) return false
    if (!image && value.startsWith("#")) return true
    try {
        const protocol = new URL(value).protocol.toLowerCase()
        return (image ? ["https:", "file:"] : ["https:", "http:", "file:", "mailto:"]).includes(protocol)
    } catch { return false }
}

/** Quoted attribute values may legally contain >; only the real tag end counts. */
export function xmlSafeNewsVoidElements(value: string): string {
    return value.replace(/<(img|br|hr)\b((?:"[^"]*"|'[^']*'|[^'">])*)>/gi, (_full, tag: string, attributes: string) =>
        attributes.trimEnd().endsWith("/") ? `<${tag}${attributes}>` : `<${tag}${attributes} />`)
}

export function normalizeNewsImageOnlyParagraphs(value: string): string {
    return value.replace(/<p>\s*(<img\b(?:"[^"]*"|'[^']*'|[^'">])*\/>)\s*<\/p>/gi, '<div class="center">$1</div>')
}

/** Return null for CSS outside the deliberately small presentation-only grammar. */
export function safeNewsInlineStyle(value: string): string | null {
    if (/[\\@{}<>\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]|\/\*/.test(value)) return null
    const declarations: string[] = []
    for (const part of value.split(";")) {
        if (!part.trim()) continue
        const match = /^\s*([a-z-]+)\s*:\s*([^:;]+)\s*$/i.exec(part)
        if (!match || !STYLE_PROPERTIES.has(match[1].toLowerCase())) return null
        const cssValue = match[2].trim()
        if (!/^[a-z0-9#\s.,%()'"+\/-]+$/i.test(cssValue)) return null
        // No url(), expression(), var(), image-set(), browser bindings or escapes.
        if ([...cssValue.matchAll(/([a-z-]+)\s*\(/gi)].some(call => !["rgb", "rgba", "hsl", "hsla"].includes(call[1].toLowerCase()))) return null
        declarations.push(`${match[1].toLowerCase()}: ${cssValue}`)
    }
    return declarations.join("; ")
}

export function safeNewsStylesheet(value: string): string | null {
    const rules: string[] = []
    let rest = value.trim()
    while (rest) {
        const rule = /^([a-z0-9_.,#\s>+-]+)\{([^{}]*)\}/i.exec(rest)
        if (!rule) return null
        const declaration = safeNewsInlineStyle(rule[2])
        if (declaration === null) return null
        rules.push(`${rule[1].trim()} { ${declaration} }`)
        rest = rest.slice(rule[0].length).trim()
    }
    return rules.join("\n")
}

function decodeAttribute(value: string): string {
    return value.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, (entity, code: string) => {
        if (code[0] !== "#") return ({ amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" } as Record<string, string>)[code.toLowerCase()] ?? entity
        const point = code[1].toLowerCase() === "x" ? Number.parseInt(code.slice(2), 16) : Number.parseInt(code.slice(1), 10)
        return point > 0 && point <= 0x10ffff ? String.fromCodePoint(point) : "\u0000"
    })
}

/** Validate markup without a browser DOM or a regex-based attempt at sanitizing it.
 * Reject unknown syntax/tags/attributes rather than repairing active HTML on save.
 */
export function validateSafeNewsHtml(html: string): void {
    let offset = 0
    while (offset < html.length) {
        const start = html.indexOf("<", offset)
        if (start < 0) break
        if (html.startsWith("<!--", start)) {
            const end = html.indexOf("-->", start + 4)
            if (end < 0) throw new Error("HTML 注释未结束")
            const comment = html.slice(start + 4, end)
            if (/^>|^->|--/.test(comment)) throw new Error("HTML 注释格式无效")
            offset = end + 3; continue
        }
        const declaration = /^(?:<!doctype\s+html\s*>|<\?xml\s+version=["']1\.0["'](?:\s+encoding=["'][a-z0-9-]+["'])?\s*\?>)/i.exec(html.slice(start))
        if (declaration) { offset = start + declaration[0].length; continue }
        let quote = "", end = start + 1
        for (; end < html.length; end++) {
            const character = html[end]
            if (quote) { if (character === quote) quote = "" }
            else if (character === '"' || character === "'") quote = character
            else if (character === ">") break
        }
        if (end >= html.length) throw new Error("HTML 标签或属性未结束")
        const token = html.slice(start + 1, end)
        const tagMatch = /^(\/?)([a-z][a-z0-9]*)(?=\s|\/|$)/i.exec(token)
        if (!tagMatch) throw new Error("HTML 包含不支持的标记")
        const tag = tagMatch[2].toLowerCase()
        if (!NEWS_HTML_TAGS.has(tag)) throw new Error(`HTML 不允许 ${tag} 标签`)
        let attributes = token.slice(tagMatch[0].length)
        if (tagMatch[1]) {
            if (attributes.trim()) throw new Error("HTML 结束标签不能包含属性")
        } else {
            attributes = attributes.replace(/\/\s*$/, "")
            const names = new Set<string>()
            while (attributes.trim()) {
                const attribute = /^\s+([a-z][a-z0-9_-]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'`=<>]+))/i.exec(attributes)
                if (!attribute) throw new Error("HTML 属性格式无效；请使用明确的属性值")
                const name = attribute[1].toLowerCase()
                if (names.has(name) || !isNewsHtmlAttribute(tag, name)) throw new Error(`HTML 不允许或重复属性 ${name}`)
                names.add(name)
                const value = decodeAttribute(attribute[2] ?? attribute[3] ?? attribute[4])
                if (name === "src") {
                    if (value.length > 2048) throw new Error("HTML 图片 URL 过长")
                    if (!isNewsHtmlUrl(value, true)) throw new Error("HTML 图片必须使用 HTTPS URL 或 file: 本地资源")
                }
                if (name === "href" && !isNewsHtmlUrl(value)) throw new Error("HTML 的 href URL 无效或不安全")
                if (name === "style" && safeNewsInlineStyle(value) === null) throw new Error("HTML 包含不安全或不支持的样式")
                attributes = attributes.slice(attribute[0].length)
            }
            if (tag === "img" && !names.has("src")) throw new Error("HTML 图片缺少 src")
            if (tag === "style") {
                const closing = /<\/style\s*>/gi
                closing.lastIndex = end + 1
                const match = closing.exec(html)
                if (!match || safeNewsStylesheet(html.slice(end + 1, match.index)) === null) throw new Error("HTML 样式表无效或不安全")
                offset = match.index + match[0].length; continue
            }
        }
        offset = end + 1
    }
}
