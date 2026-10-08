# 新角色发布门禁（四道边界）使用说明

2026-10-06 凉月（159992）制作复盘产出的发布门禁。四道门禁的纯逻辑在
`tools/fantasy-gauntlet-mod-tools/wf_character_gates.py`（无 store、无写盘），
CLI 与既有专项门禁在 `tools/lens-integration/`。

| 门禁 | 工具 | 覆盖事故 |
| --- | --- | --- |
| ① 仓库边界：输出路径断言（禁 `.cdn`；`active` + manifest + `audit/`；禁止 `production/production`） | `check_character_edge.py` `repo_boundary` + `wf_character_flow` 写前断言 | 发布路径违规（覆盖层写入 `production/production`；默认写 `.cdn`） |
| ② 链边界：外层 key union（有效链既有 key 不得减少）+ 声明行合并审计 | `check_character_edge.py` `chain_boundary` + `wf_character_flow` 发布前门禁 | C8601 整表覆盖（596 键只发 1 键） |
| ③ 结构契约：timeline/atlas/frame/parts 对官方 donor 逐键对齐 + 锚点逐帧回归 | `check_character_edge.py` `structural_contract`（`--frame-swap`） | timeline 缺 `sounds`（F1009）；1.4.143 像素偏移（补偿符号做反） |
| ④ 解析器契约：声明行 Bool/枚举/数值/`(None)` 强类型 + 官方先例统计 | `check_character_edge.py` `parser_contract`（`--declared`） | C7101（col72/70）、C7050（col75/73）、F1009（flip_limit 族）、+0 显示（col74） |

## 用法

源码路径均相对本仓库根目录，命令也从该根目录运行。`<EDGE_VERSION>` 必须取自当前 manifest 的 enabled patch，`<CHAIN_TAIL>` 为当前有效链尾；历史案例版本不能直接用作当前验收输入。`<DECLARED_JSON>`、`<FRAME_SWAP_JSON>` 为本批实际声明文件，`<TASK_DIR>` 为仓库外或已忽略的任务目录；先替换占位符，再执行命令。多行反斜杠是 POSIX shell 续行写法，PowerShell 中应合并为单行或使用其续行语法。

```text
# 单边四道门禁（fail-closed，退出码 1 = 有阻断问题）
python tools/lens-integration/check_character_edge.py \
  --edge-version <EDGE_VERSION> --expect-tail <CHAIN_TAIL> \
  --declared <DECLARED_JSON> --frame-swap <FRAME_SWAP_JSON> \
  --receipt <TASK_DIR>/character-edge.json

# 专项门禁（可独立复跑）
python tools/lens-integration/check_timeline_sounds.py \
  --expect-tail <CHAIN_TAIL> --edge-version <EDGE_VERSION> --expect-edge \
  --require-logical character/liangyue_onmyoji/pixelart/pixelart.timeline.amf3.deflate \
  --receipt <TASK_DIR>/timeline-sounds.json
python tools/lens-integration/check_ability_strong_fields.py \
  --expect-tail <CHAIN_TAIL> --edge-version <EDGE_VERSION> --expect-edge \
  --check-declared-cells --receipt <TASK_DIR>/ability-strong-fields.json

# 自测
python -m unittest tools.lens-integration.test_check_timeline_sounds
#（或在该目录内）python -m unittest test_check_timeline_sounds test_check_ability_strong_fields
python -m unittest tools.fantasy-gauntlet-mod-tools.tests.test_character_gates
```

## 参数

- `check_character_edge.py`
  - `--edge-version`（必填）：manifest 中 enabled patch 的 `version`。
  - `--expect-tail`：断言有效链尾部版本。
  - `--declared FILE`：声明行 JSON，`{"<逻辑表路径>": {"<key>": true|[行号...]}}`。
  - `--frame-swap FILE`：帧素材替换声明，`[{"member"|"logical", "dx", "dy",
    "keep":[帧号...]}]`。`dx/dy` = 旧帧内素材内容偏移；`keep` 中的帧不做
    替换、期望位移 (0,0)。`fx/fy` 语义见 `Texture.as:339-357`：
    区域左上角画在 `(-fx,-fy)`，客户端 1.4.143 偏移事故即补偿符号做反
    （声明 +12，实况 -12，逐帧偏差 -24）。
  - `--donor-code`（默认 `ekaki_girl`）：官方 pixelart donor 角色代码。
  - `--allow-spec-only`：官方参照不可得时把 donor 缺失降级为不阻断（慎用）。
- `check_timeline_sounds.py`：`--edge-version/--expect-tail/--require-logical/
  --expect-edge/--pathlist/--no-chain-payload-scan`。
- `check_ability_strong_fields.py`：`--edge-version/--expect-tail/--require-key/
  --expect-edge/--check-declared-cells`。

## 回执格式

三个脚本统一输出 JSON 回执（`--receipt` 写出、stdout 打印摘要）：

```jsonc
{
  "gate": "character-edge | timeline-sounds | ability-strong-fields",
  "generated_at": "2026-10-06T...+08:00",
  "edge": {"id": "...", "version": "<EDGE_VERSION>", "archives": ["...zip"]},
  "chain_tail": "<CHAIN_TAIL>",
  "sections": {
    "repo_boundary":  {"archives": [{"name": "...", "sha256": "...", "members": 2}],
                       "audit": {"directory": "...", "files": ["report.json", "..."]}},
    "chain_boundary": {"tables": [{"logical": "...", "before_keys": 3525,
                       "after_keys": 3525, "added": [], "removed": [], "changed": [...]}]},
    "structural_contract": {"members": [{"role": "pixelart-atlas", "donor": "...",
                       "problems": [], "anchor_regression": [{"checked": 123,
                       "max_deviation": 0, "deviations": []}]}]},
    "parser_contract": {"tables": [{"logical": "...", "problems": [],
                       "warnings": [...], "declared": [...]}]}
  },
  "problems": [{"gate": "repo|chain|structural|parser", "reason": "...", "detail": "..."}],
  "warnings": [],
  "status": "passed | failed"
}
```

`problems` 非空即 `status=failed`、退出码 1；`warnings` 只记录
“合法但可疑/需作者补声明”的条目（不阻断）。`check_timeline_sounds.py`
缺 `sounds`、`check_ability_strong_fields.py` 非法 Bool/枚举/Option 单元
都直接失败关闭。

## 历史落地实证（2026-10-06）

以下是当时的验证摘要，不是对当前 manifest 的重跑结果。中间边及原始过程回执已退出当前发布清单；当前验收须重新选择 enabled patch，不能直接照搬下列历史版本号。

- `1.4.145`（基础帧 v2）四道门禁通过；`--frame-swap` 声明
  `dx=dy=12, keep=[19 个技能帧]` 时 123/123 帧锚点偏差为 0。
- 同一个门禁对已发布的事故边 `1.4.143` 复现失败：104 帧锚点位移
  `(-12,-12)` 与声明 `(12,12)` 不符（即玩家看到的 (-24,-24) 偏移），
  证明该门禁能拦截本次事故。
- `1.4.136`（能力表 Option/描述修复）四道门禁通过：两表 outer key
  3525/588 不变，声明行 0 阻断问题。

历史原始回执批次标识：`character-studio-hardening-20261006/receipts/`（仅本地旁证，不随仓库提供，不是仓库内目录或当前验收附件）。

随仓库保留的凉月最终合并边回执示例位于 `assets/asset-patch/audit/liangyue-character-final-merge-1.4.131/`：`gate-character-edge.json`、`gate-timeline-sounds.json`、`gate-ability-strong-fields.json`。这些文件保留原始验证时间与覆盖范围，引用的本地外部旁证不作为入库附件。
