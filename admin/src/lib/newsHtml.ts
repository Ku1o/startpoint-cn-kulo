import { NEWS_HTML_TAGS, isNewsHtmlAttribute, isNewsHtmlUrl, safeNewsInlineStyle, safeNewsStylesheet, xmlSafeNewsVoidElements, normalizeNewsImageOnlyParagraphs } from "../../../src/lib/news-html-policy"

const HTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
const DROP_CONTENT = new Set(["script", "style", "iframe", "object", "embed", "template", "svg", "math", "textarea", "xmp", "noscript", "plaintext", "form", "input", "button", "select", "option", "meta", "link", "base"])

function cleanChildren(source: ParentNode, target: Node, document: Document, depth = 0): void {
    if (depth > 64) return
    for (const child of Array.from(source.childNodes)) {
        if (child.nodeType === 3) { target.appendChild(document.createTextNode(child.textContent ?? "")); continue }
        if (child.nodeType !== 1) continue
        const element = child as Element, tag = element.localName.toLowerCase()
        // Drop foreign trees whole: never unwrap SVG/math/foreignObject children.
        if (element.namespaceURI !== HTML_NAMESPACE || DROP_CONTENT.has(tag)) continue
        if (["html", "head", "body", "title"].includes(tag)) {
            if (tag !== "head" && tag !== "title") cleanChildren(element, target, document, depth + 1)
            continue
        }
        if (!NEWS_HTML_TAGS.has(tag)) { cleanChildren(element, target, document, depth + 1); continue }
        const clean = document.createElement(tag)
        for (const attribute of Array.from(element.attributes)) {
            const name = attribute.name.toLowerCase(), value = attribute.value
            if (attribute.namespaceURI || !isNewsHtmlAttribute(tag, name)) continue
            if (["href", "src"].includes(name) && !isNewsHtmlUrl(value, name !== "href")) continue
            if (name === "style") {
                const style = safeNewsInlineStyle(value)
                if (style) clean.setAttribute(name, style)
            } else clean.setAttribute(name, value)
        }
        if (tag === "img" && !clean.hasAttribute("src")) continue
        cleanChildren(element, clean, document, depth + 1)
        target.appendChild(clean)
    }
}

/** Parse into an inert template, then rebuild from safe HTML elements/attributes.
 * Nothing from the untrusted tree is ever attached to the live editing canvas.
 */
export function sanitizeNewsBody(value: string): string {
    const template = document.createElement("template")
    template.innerHTML = value
    const output = document.createElement("template")
    cleanChildren(template.content, output.content, document)
    return output.innerHTML
}

/** Safe head CSS stays in the saved document, never in the live admin DOM. */
export function sanitizeNewsDocument(value: string, bodyOverride?: string): string {
    const template = document.createElement("template")
    template.innerHTML = value
    const styles = Array.from(template.content.querySelectorAll("style"))
        .filter(element => element.namespaceURI === HTML_NAMESPACE && !element.closest("svg, math, form, iframe, object"))
        .map(element => safeNewsStylesheet(element.textContent ?? ""))
        .filter((style): style is string => !!style)
    const body = normalizeNewsImageOnlyParagraphs(xmlSafeNewsVoidElements(sanitizeNewsBody(bodyOverride ?? value)))
    if (!body.trim()) return ""
    const head = styles.length ? `<head><style>${styles.join("\n")}</style></head>` : ""
    return `<html lang="zh">${head}<body>${body}</body></html>`
}
