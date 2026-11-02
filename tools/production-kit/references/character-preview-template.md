# 角色离线预览模板 V1

适用于 StarPoint CN 新角色与换皮制作的分阶段审阅。入口是[整角色流程](character-production-workflow.md)，实现是 [character_preview.py](../scripts/character_preview.py) 和 固定前端（历史本地记录）。保持现有五栏目：概览、动作、技能、数值、验收。角色参数全部来自清单，不复制示例中的角色名称、形态数量、6 倍缩放或技能时点。

## 新角色的执行路线

1. 收到“制作/新建一个 MOD 角色”且已有制作授权时，即使没有提到离线预览，也读取整角色流程并在仓外新任务目录运行 `character_production.py init`。它自动建立阶段台账、音频计划、`preview-spec.json` 与 `preview-start/index.html`；空清单显示缺项，不代表已完成。
2. 先按设计和同用途官方资料建立本角色资源清单；随着立绘、UI、动作、声音、数值产出，填写预览数据并生成新的版本目录。立绘选稿、待机母版、完整动作/技能、整角色离线版是自然审阅点，不必等全部完成。
3. 继续旧工程先读 CURRENT/配方，不重新初始化或替换采用稿。旧网页可保留；适配器从实际候选读回，生成数据后用通用模板展示。
4. 审阅时提供实际 HTML 链接并说明缺项。离线完整、用户审美确认、声音认可、游戏/设备验证分别记录。预览生成与源码写入、资源接入和发布相互独立。

## 命令

以下从技能 `scripts` 目录运行；Python 标准库即可。新目录须放在 `<workspace>/work` 或 `<workspace>/outputs` 内，台账初始化仍只允许 `work`。绝不覆盖已有审阅版本。

```powershell
python -B character_production.py init --out <workspace>/work/<角色任务> --character-code <角色代码>
# 填写该任务的 preview-spec.json，再构建一个新的审阅版本。
python -B character_preview.py check --spec <workspace>/work/<角色任务>/preview-spec.json
python -B character_preview.py build --spec <workspace>/work/<角色任务>/preview-spec.json --out <workspace>/outputs/characters/<角色>/preview-v1
python -B character_preview.py verify --bundle <workspace>/outputs/characters/<角色>/preview-v1
```

`init` 也可独立运行：`character_preview.py init --out <新清单.json> --character-code <代码> --name <名称>`。`check/build/verify` 可传 `--report <新报告.json>` 保存结构回执。命令成功表示结构/身份检查执行成功；**pending 缺项可以合法构建，退出码 0 不等于角色做完**。修改清单后按受影响阶段更新台账输入 SHA，不直接抹掉旧验收证据。

## 清单合同（schemaVersion 1）

顶层必须有 `character` 和下表全部数组，暂未制作时保留空数组。所有 id 为 1–128 位 ASCII 字母/数字/`_.-`；资产 id 独立，形态/UI/动作/media 的展示 id 全局唯一。正文按普通文本显示，不接受 HTML 注入。

| 字段 | 内容与约束 |
| --- | --- |
| `character` | `code/name/subtitle`；不从上一角色继承。 |
| `assets` | `{id,kind,path,sha256}`；kind 为 image/audio/video，真实本地文件及当前 SHA256，缺文件不伪造资产。构建复制到内容寻址的相对路径并校验复制结果。 |
| `forms` | `{id,label,illustration}`；illustration 为 image id 或 null，任意形态数量。null 显示缺项。 |
| `ui` | `{id,label,asset,form,variant,resourceKeys,status,note}`；form 可 null，variant 如 medium/small。`resourceKeys` 对应实际原生槽；ready 不允许空键列表脱离清单。status 为 ready/pending/not_applicable。不适用必须说明原因。 |
| `motions` | `{id,label,displayScale,fps,frames,note,viewport?}`；frames 是 `{asset,ticks}` 数组，ticks 为正整数，fps 为每秒源 tick。viewport 可为固定 `{x,y,width,height}`；保持原点，不能逐帧自动裁边。同样适用于纯人物对照或组合审阅，但说明其是否原生序列。 |
| `media` | `{id,label,kind,asset,section,caption,status,note?}`；kind 为 audio/video，section 为 overview/actions/skill。技能 V1 默认完整视频，角色专用交互播放器保留独立案例；不能用视频证明原生可运行。 |
| `mechanics` / `extras` | `{title,text}`；玩法数值/特殊说明独立于前端。 |
| `checks` | `{id,label,state,note}`；state 为 pending/offline_checked/approved/deferred_to_game/not_applicable，必须说明覆盖范围。工具不判定游戏已通过。 |
| `inventory` | `{key,category,entry,status,note}`；category 为 ui/motion/audio/illustration/skill。entry 为对应展示 id 或 null；ready 必须有真实就绪展示，UI 反向 resourceKeys 也要匹配。立绘映射 form id。 |
| `inventoryScope` | 文本说明清单来自哪些原生集合，哪些未知/不适用。完整性的分母不能只由网页已有卡片反推。 |
| `sourceBindings`（可选，仅制作端） | `[{path,sha256}]`，绑定 CURRENT/配方/最终资源清单等来源；构建前检查新鲜度，不随分享页导出绝对路径。 |

适配器负责枚举实际资源、解码 stored PNG、重建原生帧、保留真实视口/ticks、声画增益和语音引用关系。模板不做原生解包，不从一张 PNG 或已有录音数量推定动作/语音槽完整。平台纹理在网页无法直接播放时可用配对 PNG 辅助观察，但不能计作平台纹理本体已展示/验证。重复剧情槽可共用媒体，关系和是否独立表情仍须列出。

## 构建与检查边界

生成内容是 `index.html/style.css/player.js/preview-data.js/media/bundle.json`，不用 fetch、网络资源或服务。分享整个目录即可；只发 HTML 会缺少媒体。白名单导出字段隔离 sourceBindings 和任意制作私有字段，但正文/标签仍是分享内容，发给别人前照常检查。

构建检查 schema、引用、源文件 SHA、实际复制 SHA、清单到展示映射、遗漏/不适用理由和便携资源闭包；`verify` 再按清单独立读回全部叶文件及派生缺项。它不认证清单自身完整、原生语义、审美、音量或浏览器播放。静态/VM、浏览器实播、游戏和设备验收分别报告，工具限制不得绕过。

改模板时至少验证当前采用角色、一个参数不同且有明确缺项的 fixture，以及一次不带历史设计答案的入口任务。使用合成 fixture 只能证明参数化和缺项行为，不能宣称第二个真实角色制作/审美已经成功。测试与适配实例见 V1 工程（历史本地记录）。后续自然任务仍需确认实际遵循路线及展示质量。
