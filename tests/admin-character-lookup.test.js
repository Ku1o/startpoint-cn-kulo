const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")

const root = path.resolve(__dirname, "..")
const { buildCharacterLookup } = require("../out/routes/web_api/lookup")

const expected = {
    149995: { name: "希耶提", title: "十天众之首", rarity: "5★", element: "风" },
    169996: { name: "西蒙", title: "愿望的牧羊人", rarity: "5★", element: "暗" },
    169997: { name: "巴萨拉卡", title: "不死大镰", rarity: "5★", element: "暗" },
}

test("integrated trio is present in the generated admin character lookup", () => {
    const rows = require("../docs/generated/character_table.json")
    const byId = Object.fromEntries(rows.map((row) => [row.id, row]))
    for (const [characterId, fields] of Object.entries(expected)) {
        assert.deepEqual(
            {
                name: byId[characterId]?.name,
                title: byId[characterId]?.title,
                rarity: byId[characterId]?.rarity,
                element: byId[characterId]?.element,
            },
            fields,
        )
    }
})

test("generated CSV carries the same integrated trio IDs", () => {
    const csv = fs.readFileSync(path.join(root, "docs/generated/character_table.csv"), "utf8")
    const ids = new Set(csv.split(/\r?\n/).slice(1).filter(Boolean).map((line) => line.split(",", 1)[0]))
    for (const characterId of Object.keys(expected)) assert.equal(ids.has(characterId), true)
})

test("server-only characters remain selectable through the admin fallback", () => {
    const lookup = buildCharacterLookup(
        [{ id: 1, name: "静态角色", title: "静态称号", rarity: "4★", element: "火" }],
        {
            1: { name: "不得覆盖", rarity: 5, element: 5 },
            900001: { name: "兜底角色", rarity: 5, element: 3 },
        },
    )
    assert.deepEqual(lookup[1], {
        name: "静态角色",
        title: "静态称号",
        rarity: "4★",
        element: "火",
    })
    assert.deepEqual(lookup[900001], {
        name: "兜底角色",
        title: "",
        rarity: "5★",
        element: "风",
    })
})
