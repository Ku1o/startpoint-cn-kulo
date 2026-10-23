const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const test = require("node:test")
const ts = require("typescript")

// Compile only the source modules in memory: no out/, database or news writes.
require.extensions[".ts"] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true },
}).outputText, filename)
const policy = require("../src/lib/news-html-policy.ts")
const { normalizeNewsConfig } = require("../src/lib/news-config.ts")
const configFor = html => ({ version: 1, news: [{ id: 1, title: "Synthetic safety fixture", date: "2026-10-22 12:00:00", html, published: false }] })

test("client containers, rich formatting, scene/button metadata, safe CSS and XML void tags survive", () => {
    const html = '<?xml version="1.0"?><html lang="zh"><head><style>.notice { color: #ff8800; font-weight: bold }</style></head><body><h1 class="notice">Title</h1><p style="text-align: center; font-size: 18px"><b>Bold</b><font color="#ffaa00" size="18">Text</font><br /></p><ul><li><p>List</p></li></ul><table><tr><th>Header</th><td colspan="2">Value</td></tr></table><a scene="QuestScene"><img src="file:///resources/banner.png" button="native_banner_button" width="100%" height="360" /></a></body></html>'
    assert.doesNotThrow(() => policy.validateSafeNewsHtml(html))
    const normalized = normalizeNewsConfig(configFor(html)).news[0].html
    for (const piece of ['scene="QuestScene"', 'button="native_banner_button"', '<style>', '<font ', 'colspan="2"', 'file:///resources/banner.png']) assert.ok(normalized.includes(piece), piece)
})

test("greater-than inside quoted image attributes neither truncates XML normalization nor source validation", () => {
    const fragment = '<p><img alt="A > B and src=not-an-attribute" src="https://example.invalid/a.png" width="100%"></p><br><hr>'
    const normalized = normalizeNewsConfig(configFor(fragment)).news[0].html
    assert.match(normalized, /<div class="center"><img alt="A > B and src=not-an-attribute" src="https:\/\/example\.invalid\/a\.png" width="100%" \/><\/div>/)
    assert.match(normalized, /<br \/><hr \/>/)
    assert.equal(normalizeNewsConfig(configFor(normalized)).news[0].html, normalized)
})

test("active elements, foreign trees, handler attributes, browser resource attributes and CSS are rejected", () => {
    const rejected = [
        '<script>globalThis.__NEWS_MARKER__=1</script>', '<p onclick="globalThis.__NEWS_MARKER__=1">Text</p>',
        '<img src="https://example.invalid/a.png" onerror="globalThis.__NEWS_MARKER__=1">',
        '<svg><foreignObject><p onmouseover="globalThis.__NEWS_MARKER__=1">x</p></foreignObject></svg>',
        '<math><mtext><img src="https://example.invalid/a.png" onerror="globalThis.__NEWS_MARKER__=1"></mtext></math>',
        '<iframe srcdoc="<script>globalThis.__NEWS_MARKER__=1</script>"></iframe>', '<object data="data:text/html,marker"></object>',
        '<embed src="https://example.invalid/marker">', '<meta http-equiv="refresh" content="0;url=https://example.invalid">',
        '<base href="https://example.invalid">', '<link rel="stylesheet" href="https://example.invalid/a.css">',
        '<template><img src="https://example.invalid/a.png" onerror="marker()"></template>',
        '<form action="https://example.invalid"><input name="marker"></form>',
        '<p id="__NEWS_MARKER__">x</p>', '<p xmlns="http://www.w3.org/2000/svg">x</p>',
        '<p style="background-image: url(https://example.invalid/marker)">x</p>', '<p style="width: expression(marker())">x</p>',
        '<p style="color: var(--marker)">x</p>', '<p style="color: r\\65 d">x</p>',
        '<style>@import "https://example.invalid/a.css";</style>', '<style>p { color: red; background: url(x) }</style>',
        '<p style="position: fixed; z-index: 9999">x</p>', '<img/src="https://example.invalid/a.png">',
        '<img src="https://example.invalid/a.png" src="file:///duplicate.png">',
        '<!--><img src="https://example.invalid/a.png" onerror="marker()"><!-- -->',
        '<!-- --!><img src="https://example.invalid/a.png" onerror="marker()"> -->',
        '<!DOCTYPE html [<!ENTITY marker "x">]><p>Text</p>',
    ]
    for (const html of rejected) assert.throws(() => normalizeNewsConfig(configFor(html)), undefined, html)
})

test("URL entities, control whitespace and script protocols fail closed; ordinary HTTPS/file and XML entities remain", () => {
    const rejected = [
        '<a href="javascript:marker()">x</a>', '<a href="java&#x73;cript:marker()">x</a>', '<a href="java&#9;script:marker()">x</a>',
        '<a href="javascript&colon;marker()">x</a>', '<a href="data:text/html,marker">x</a>', '<a href="https:&#10;//example.invalid">x</a>',
        '<img src="http://example.invalid/a.png">', '<img src="data:image/svg+xml,marker">', '<img src="">', '<img alt="no source">',
        '<img src="https://example.invalid/\u0000a.png">', '<img src="https://example.invalid/a.png" style="color: red&#59; behavior: url(x)">',
    ]
    for (const html of rejected) assert.throws(() => normalizeNewsConfig(configFor(html)), undefined, html)
    assert.doesNotThrow(() => normalizeNewsConfig(configFor('<a href="https://example.invalid/?a=1&amp;b=2">Link</a><img src="file:///a.png"><img src="https://example.invalid/a.png">')))
    assert.throws(() => normalizeNewsConfig(configFor('<img src="http://example.invalid/a.png">')), /必须使用 HTTPS URL/)
})

test("safe comments and presentation styles have deterministic boundaries", () => {
    assert.doesNotThrow(() => policy.validateSafeNewsHtml('<!-- safe comment --><p style="color: rgba(0, 0, 0, 0.5); margin: 4px 8px">x</p>'))
    assert.equal(policy.safeNewsInlineStyle("font-weight: bold; text-align: center"), "font-weight: bold; text-align: center")
    assert.equal(policy.safeNewsStylesheet(".notice { color: red } p { font-size: 18px }"), ".notice { color: red }\np { font-size: 18px }")
})

test("existing checked-in announcement sample remains valid offline", () => {
    const sample = JSON.parse(fs.readFileSync(path.join(__dirname, "../assets/news.json"), "utf8"))
    assert.doesNotThrow(() => normalizeNewsConfig(sample))
})
