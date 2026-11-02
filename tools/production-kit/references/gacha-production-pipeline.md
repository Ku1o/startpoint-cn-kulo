# 扭蛋池制作管线

本入口把已采用的原生模板、美术合成、资源编译、检查、便携预览和采用记录连接起来。它是现有 MOD Skill 的扭蛋分支；不是另一个重复 Skill，也不自动发布资源或改数据库。美术判断和原生细节仍查 [gacha-art-workflow.md](gacha-art-workflow.md)。

## 已采用模板与能力

从 CURRENT.acceptedProduction（历史本地记录） 找当前采用记录与项目配置。首例是万圣惊奇池：一个四人双阶段封面、四张双形态单人 Movie、官方字样横幅、透明原生底栏、专券十连 UI。最终名牌支点修订的采用记录与运行版本分别登记，目录编号不表示已发布版本。

可自动执行的步骤：

1. 校验每份输入文件、SHA256、尺寸、模板与页面关系。
2. 按显式图层配方合成立绘/字图/横幅；保持等比缩放和透明度，文字支持绑定字体、字号与描边。
3. 复用原生 Movie，替换声明的纹理、重定逻辑资源路径，必要时修正独立动画分支的静态外层布局及真实图内支点。
4. 严格读回 Movie/timeline/atlas/stored-PNG，检查内外序列、分域实例池、图集与逐帧命令，生成最终编译物的预览模型。
5. 将页面、底栏、横幅、像素人物和按钮等嵌入单 HTML，输出资源交接目录及构建回执。
6. 将明确的人工采用结果绑定到具体预览 SHA；采用动作不激活资源。

**能力边界：**目前实际模板族是四人封面与单人双形态 Movie。减少预览页数不等于封面已改成对应人数；不同人数/全新动画拓扑须先做一个样板，再登记模板。图层工具不自动设计构图，文字尺寸、人物遮脸、小横幅可读性、完整入场仍要看预览。网页只展示 Movie 美术页；实际九页轮播中的四个 kind2 技能战斗另走原生接线及设备检查。不能把四人模板复制成功说成任意人数或第二个新池已经验收。

## 一个入口

主工具：[scripts/gacha_pipeline.py](../scripts/gacha_pipeline.py)。Python 使用当前项目已有解释器和 Pillow；Node 与只读原生工具根在配置 `toolchain` 指定。`supportRoot` 指包含 `tools/fantasy-gauntlet-mod-tools` 的仓库根。不要安装新全局环境，也不要盲跑历史总装脚本。

```powershell
$py = '<local-tool-path>'
$pipe = '<repo>/tools/production-kit/scripts/gacha_pipeline.py'
# 现有采用工程；新任务按CURRENT查找，避免复制过期字节指针。
$template = '<workspace>/work/halloween-five-gacha-20261027/native-integration-20261028/official-parity-20261028/pipeline-freeze-20261028/accepted-project.json'
& $py -X utf8 -B $pipe init --template $template --output '<workspace>/work/new-gacha-project' --name '新主题扭蛋' --key 'cnmod_new_theme'
# 完成素材、槽位、角色、UI、支付和技能引用配置后：
& $py -X utf8 -B $pipe validate '<workspace>/work/new-gacha-project/project.json'
& $py -X utf8 -B $pipe build '<workspace>/work/new-gacha-project/project.json' --run 'candidate-01'
& $py -X utf8 -B $pipe verify '<workspace>/work/new-gacha-project/builds/candidate-01/BUILD.json'
```

`init` 创建**未适配草稿**：保留模板人物/字图以便继续编辑，清空旧业务行与技能输入，重新命名输出 Movie 路径，不声称完成新主题。页面会标注草稿状态。字符数量、封面人数、下方小人、姓名/属性/称号/双形态原画、券与按钮必须同时核对。`validate` 只证明已绑定输入有效，不代表美术、业务或设备验收。

工程选页试验也要同步维护关联：例如只留 `cover` 和一个单人页时，`nativePages`、`preview.pageOrder`、`characters[].posterPage`、`preview.footerOrder`须相符；不能把其他角色的posterPage冒名指向保留页。封面内仍是模板原有人数，必须明示。支付为 unconfigured 时自动显示“模板券（支付待配置）”；ticket-ten 的券名/ID/数量从payment统一传入，冲突的preview覆盖会拒绝。生成横幅必须显式绑定到预览与候选资源，编译后核两者RGBA一致。

每次 `build --run` 使用新的子目录，拒绝覆盖已有构建、输入、源仓库和 `.cdn`。失败留 `FAILURE.json` 定位原因；修正后换一个 run，不覆盖已审阅预览。输出 `review.html`、`native/<page>/`、`handoff/resources.json`、`BUILD.json`。资源交接目录是明确候选闭包，**不是可直接启用的版本边**；预览里的设备截图为本地非公开参考。

## 项目配置

以真实采用配置为示例，不另复制静态大资源到 Skill。`schemaVersion:1` 的主要字段：

| 字段 | 含义 |
| --- | --- |
| `project` | `key/name/poolId/purpose`；purpose 为 production、accepted-replay 或 engineering-variation |
| `toolchain`、`protectedRoots` | 只读原生工具仓库、Node 路径、不可输出的目录 |
| `characters` | 有序 `id/name/posterPage`，与当前角色数据和素材绑定核对 |
| `nativePages` | 每页 key/label/native；四资源模板逐条绑定 logical/file/sha256/bytes |
| `art` | `schema_version:1`、artifacts 列表；每张图 key/size/background/layers |
| `artResources` | 将生成图按 key/logical/encoding=`stored-png` 严格编码为原生资源 |
| `preview` | SHA绑定的采用 HTML 播放器模板、pageOrder、footerOrder、overrides |
| `payment` | 当前实现 ticket-ten：itemId/name、cost1/pulls10/buttons=[ten]；未配置使用 unconfigured |
| `featureOrder` | 实际 Movie(kind0) 与技能(kind2)顺序；skillKey须从真实表行读取 |
| `businessInputs/skillInputs` | 业务和技能证据引用，**不自动复制到发布资源** |
| `extraResources` | 经声明的附加候选资源；禁止整份搬旧 assembly 以免回退新业务 |
| `stageStatus` | 美术、业务、技能、设备分别记录；不得用总“成功”掩盖缺口 |

所有外部 `{file:...}` 输入都需要 `sha256`，资源输入还要 `bytes`。相对文件路径按项目文件目录解析；工具链用已验证的绝对路径。输入变化后重新绑定，不能改检查器放行。禁止在配置里塞任意命令或自动服务动作。

### 美术到原生纹理

[gacha_art.py](../scripts/gacha_art.py) 的图片层用 file/sha256、position、单值 scale 或等比 fit 的 size；crop 是 `[x,y,w,h]`，可用同尺寸 mask、opacity、rotation。文本层用 text、font 的 file/sha256、font_size、position、fill、stroke_fill、stroke_width、anchor。字号与输出画布一起按2×采样，再在原生叶上均匀缩放；不得单向拉宽姓名。

原生纹理配置在 `nativePages[].native.textures`，例如：

```json
{"slot":33,"asset":{"generated":"serio_nameplate"}}
```

这会把同一轮生成图片绑定到声明槽位。图像画布必须与模板槽相符，不自动缩图硬塞；布局变动需重新审查实际矩阵。横幅可以同时从 `artResources` 输出原生 stored-PNG，并通过 `preview.overrides.banner:{"generated":"banner"}` 进入预览，避免预览与候选使用两份图。

[gacha_native.py](../scripts/gacha_native.py) 的 `inspect_template` 提供模板清单；`build_native` 支持 `logical_prefix/textures/anchors/anchor_checks/repack`。纹理、支点约束和模板拓扑先读其 API/检查错误，不按另一个模板的 slot 数字猜位置。支点必须来自**当前字图的来源及实际尖角**，外层布局与原生缩放/摆动分离，稳帧与未改图层逐帧保全。轻摆保留原曲线，不能把底板与文字强制绑成一组；本次被替代的268文字跟板方案不是采用模板。

### 预览与验收

[gacha_preview.cjs](../scripts/gacha_preview.cjs) 从编译模型读取数据，不执行输入 HTML 的脚本来取数据。模型 `source` 可是单页或pages字典；assetBindings逐张绑定本地图片。支付显示、名称、UI/人物数据通过结构化覆盖进入；模板播放器时钟、控件和墨迹基线保留。

先检查资源/模型全帧结果，再看正常速度完整入场、稳定帧、换页与暂停/继续；底部文字按实际字形墨迹与券图标对齐。比较同一尺寸/同一帧的官方画面，不能拿不同裁切估算字号。浏览器或设备未实际执行，就如实记未执行；当前工具访问被策略拒绝时不换端口、协议、浏览器绕过。

人工确认后才记录采用：

```powershell
& $py -X utf8 -B $pipe accept '<构建目录>/BUILD.json' --review-sha256 '<已审阅HTML的SHA256>' --scope '已确认的美术和动画范围'
```

`ACCEPTANCE.json` 不宣称设备验证、不修改原构建、不启动服务。历史已采用原产物可以保留单独采用回执；工具重建的 HTML 若内容改变，不自动继承新的审美验收。

`verify`检查构建产物、输入、原生回执和预览图片的字节绑定；来源或模型在原路径被覆盖也会拒绝。工具版本SHA保留为历史生产者记录，安装工具升级不会单独判定旧成品损坏。后续修改构建行为时运行受影响案例，不以元数据验证代替实际重建。

## 原生接入与后续制作

新池业务沿 [扭蛋美术流程](gacha-art-workflow.md) 的 kind2、专用券和运营身份步骤；角色技能效果修改另读 [active-skill-workflow.md](active-skill-workflow.md)。正式制作可连续完成素材准备、编排、构建和离线检查，但发布、版本边、共享表合并、身份切换与设备验收仍按当前任务授权执行，管线没有隐式执行入口。

专券 profile 的真实含义是1券十连、只有十连按钮、pageKind4；零券隐藏由原生规则决定，预览余额只是示意。新券登记不自动授权发券、兑换或获取来源。新池复用时需新建/核对 ID、原生feature/skill key、表行白名单与服务端扣券测试，不把旧池行换名后直接发布。

本隔离服已采用轻量身份流程：不再做存档备份、临时整库副本或全表存档指纹；用最新运营状态捕获、raw-CAS、原子重绑和原启动校验。仅限 269续作约定（历史本地记录） 的这套隔离运行；不能推广到正式服，也不删除历史备份。

每次新池先做一个样板，采用后扩全批；自然任务才证明真实跨池复用。工程变体测试可以证明配置替换与检查器有效，不能替代第二个新主题的美术、技能和设备验收。
