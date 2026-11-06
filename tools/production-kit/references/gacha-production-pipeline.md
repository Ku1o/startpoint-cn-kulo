# 扭蛋池制作管线

`scripts/gacha_pipeline.py` 连接图层美术、原生Movie编译、原生技能录制、完整UI审查、单文件HTML及离线交付。它不发布CDN、不改数据库、不发券、不启动游戏服务。原生客户端适配器目前为固定身份的 `c8601-air-v1`，新客户端须另行适配；模板复用不自动证明新构图或设备效果。

## 环境与输入

使用已有Python 3.13和Pillow、仓库要求的Node，以及同仓 `tools/fantasy-gauntlet-mod-tools`。技能录制还需自行提供匹配身份的客户端、资源归档、Java/编译器/AIR SDK、FFmpeg/FFprobe和Chromium。客户端、原画、录制帧、SDK和个人配置不随工具入库。

```powershell
$py = 'python'
$pipe = './tools/production-kit/scripts/gacha_pipeline.py'
$env:STARPOINT_WORK_ROOT = 'D:/starpoint-work'
# 可选；未设置则使用 STARPOINT_WORK_ROOT/gacha-resource-runs
$env:STARPOINT_GACHA_RECEIPTS = 'D:/starpoint-work/gacha-resource-runs'
$template = 'D:/starpoint-work/templates/project.json'
```

模板必须是已核验、文件可读、摘要匹配且完成 `toolchain.supportRoot/node` 路径配置的真实项目；`<repo>` 等文字占位不能执行。先按任务的CURRENT或交付清单确认最终版本，禁止盲跑历史硬编码总装。纯美术任务只决定展示素材；正式名单、UP、券、概率和时间由维护者配置。约定保留已有池规则时先冻结有效业务数据。

## 默认流程与恢复

```powershell
& $py -X utf8 -B $pipe init --template $template --output 'D:/starpoint-work/new-pool' --name '新主题扭蛋' --key 'cnmod_new_theme' --with-skills
# 配置真实角色、图片、原生槽、预览支付和技能输入后：
& $py -X utf8 -B $pipe validate 'D:/starpoint-work/new-pool/project.json'
& $py -X utf8 -B $pipe build 'D:/starpoint-work/new-pool/project.json' --run candidate-01
# 到 needs_visual_review 后，实际审阅每名角色的全UI图像和连续演出：
& $py -X utf8 -B $pipe review-skills '<build>/BUILD.json' --review '<task>/visual-review.json'
& $py -X utf8 -B $pipe resume '<build>/BUILD.json'
& $py -X utf8 -B $pipe verify '<build>/BUILD.json'
# 最终产物上的独立美术审查：
& $py -X utf8 -B $pipe review-art '<build>/BUILD.json' --template-output '<task>/art-review.json'
& $py -X utf8 -B $pipe review-art '<build>/BUILD.json' --review '<task>/art-review.json'
```

`init` 生成未适配草稿及 `ART-SETUP.json`；`--with-skills` 额外生成 `SKILLS-SETUP.json`，清空旧技能录制/业务输入，不继承旧视觉批准。模板人物仍可见，必须明确为草稿。完整演出默认包含技能，只有明确不包含主动演示的静态/Movie工作才省略该选项。只做美术并不意味着可以漏掉约定的技能展示。

每次 `build --run` 使用新目录，拒绝覆盖已有构建和输入。技能准备失败可 `resume`：输入及回执一致的角色复用，失败角色新建尝试目录；媒体失败重组而不重录有效角色。已完成稿仅修播放器时可 `resume --reassemble`，先核旧稿、按摘要归档旧BUILD再生成新组装。素材/场地/UI改变须新构建及重新审阅，不用reassemble偷换批准输入。

## 项目合同

| 字段 | 内容 |
| --- | --- |
| `schemaVersion/project` | schemaVersion 1；主题key/name，必要的离线poolId，production/accepted-replay/engineering-variation目的 |
| `toolchain/protectedRoots` | 只读工具仓库、Node及禁止输出的根目录 |
| `characters` | 真实id/name与posterPage关联，页键可以不是数字 |
| `nativePages` | key/label及native配置；模板Movie、timeline、atlas、图像逐份绑定 |
| `art` | schema_version 1、图层配方；图片file/sha256、position、等比scale/fit、crop/mask/alpha/rotation；文字绑定字体、字号和描边 |
| `artResources` | 生成图key、logical、stored-png编码；横幅同时进入原生资源和预览 |
| `preview` | SHA绑定播放器模板、pageOrder/footerOrder及结构化overrides |
| `payment` | unconfigured或ticket-ten；后者为一券十连且只有十连按钮；预览余额不代表业务登记 |
| `featureOrder` | Movie(kind0)和技能(kind2)的真实页序，skillKey明确声明 |
| `businessInputs/skillInputs/extraResources` | 精确证据或附加候选，不自动发布；不整包搬运旧业务 |
| `skillPreview` | 原生角色配置、可验证reuseRun、媒体预算和关键帧；见[技能分支](gacha-skill-pipeline.md) |
| `stageStatus/artReviewPolicy` | 美术、业务、技能、设备分开；新工程official-art-v1要求采用前逐页美术审查 |

外部文件输入绑定 `{file,sha256}`，资源另含bytes；相对路径按项目文件解析。改变输入必须重绑，不放宽检查器。图层画布应匹配原生槽，不能单轴拉伸文字；横幅原生解码RGBA与预览必须相同。选页试验同步调整nativePages、pageOrder、characters.posterPage和footerOrder，减少页数不等于改造封面人数。未知命令和原生动画语义保留。

## 资源预算

Windows主CLI、原生录制CLI和原生编译CLI自动使用同目录 `gacha_guard.py`：轻检查默认512 MiB，build/resume/capture及原生编译上限2048 MiB；共用单处理槽。启动时须有预算之外至少4 GiB物理内存余量。命名Job在恢复挂起进程前设置并回读限制，覆盖其子进程树的提交内存；超时、失败、低余量或日志超额时停止任务树。GPU、共享内存和其他应用不属于此上限。

继承保护须验证真实Job成员和限制，不只信任环境标记。返回75表示没有启动工作进程；等待条件改变，不密集重试或无保护重跑。回执保存限制、退出、耗时及清理后的活动进程数；Job峰值可能含被拒绝的分配，不能冒充采样RSS。当前非Windows主入口拒绝处理，直至实现等效保护；帮助与纯单元测试可读取。

独立Python API、Node、FFmpeg、FFDec和图片工具需显式走同一guard；不能因为导入模块就声称已受保护。AIR继续使用同仓 `tools/client-background/run_background.py`，放在外层guard之内。

```powershell
& $py -X utf8 -B './tools/production-kit/scripts/gacha_guard.py' --memory-mib 512 --timeout 120 --cwd 'D:/starpoint-work/task' --receipt 'D:/starpoint-work/task/check.json' -- '<program>' '<arguments>'
```

日志写盘并有界读取；大JSON先核大小，摘要流式计算。Movie逐帧严格比较，只报首差位置，不生成整棵对象的Myers差异。Node heap不是进程树内存限制。先做一张代表样板；改字只重建相关纹理/审图，复用输入未变且证据有效的原生录制，避免反复整池重录与编码。

## 预览与美术审查

先按[美术专项方法](gacha-art-workflow.md)审查样板，再扩全池。最终 `review-art --template-output` 产生pending草稿，实际看图后填写每页checks的pass和具体observations，绑定官方参考及两种phase（transition/settled）的完整UI图片。每份evidence声明实际frame、displayWidth、view=full-ui以及image的file/sha256/bytes；build/finalPreview/resourceManifest直接保留草稿绑定。

工具拦截漏页、缺名牌/限定牌检查、pending、缺相位证据及过期图片/HTML；不识字、不自动评分，也不能判断观察是否真实。官方页面确无某限定标识时填写依据，不能省略字段。保存当前ART-REVIEW与按摘要归档的旧回执；这是制作方检查，不是用户采用。最终重组改变HTML或资源后重审受影响部分并更新绑定，旧工程不追改历史合同。

从最终编译资源生成完整单文件播放器，包含所有Movie和技能页、暂停/重播/逐帧/速度控制。检查离线无外部请求、次级入口及完整页序。压缩保留所有帧、原速率与等比视口；原始资源留作交付，紧凑WebP不代替原生PNG。应用内实际渲染、仅请求打开、源码视图与普通浏览器通过分别登记；不能凭一次源码视图断言预览功能取消。应用版本变化重新核体积门槛，不绕过工具策略拒绝。

明确采用后才执行 `accept <BUILD> --review-sha256 <final HTML SHA> --scope <已确认范围>`。新工程缺当前美术审查会拒绝。ACCEPTANCE只记录离线采用，不改资源激活状态。verify检查实际输入和产物字节；工具SHA为历史生产者信息，安装工具更新不单独判旧成品损坏。

## 最终交付与作者接入

冻结最后修字/补背景后的HTML、原生资源逻辑名/大小/摘要、角色录制及完整窗口、场景修改和表行来源；明确覆盖清单，不以过期project或BUILD冒充最后成片。交付包含必要的replay、terrain、背景族及五表连接片段，改动供体独立命名，检查内部图片及field/fieldData/zone引用。占位ID须在目标链核冲突后由维护者分配。

PR按目录隔离池子，仅含可复用源码、原生候选及必要重建/检查说明；不附聊天、私有路径、客户端SWF、SDK、录制大帧目录或个人流水。核实际Git index字节、换行、LFS属性和目标仓大小规则；例外限定精确文件，不放宽整目录。执行相关完整性、卫生、密钥检查并核远端HEAD/CI。上传源码、离线通过、正式业务接入、资源激活和设备验收分别报告。
