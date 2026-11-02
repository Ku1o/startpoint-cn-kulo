# 扭蛋池美术：官方构图、游戏 UI 与原生动效

涉及扭蛋主视觉、选池横幅或池子动效时读取。本参考补充美术判断；CDN 编码、发布与权限边界仍沿用相关规则。

新建或续作优先从[可执行制作管线](gacha-production-pipeline.md)进入：独立项目配置→美术图层→原生资源→检查→单文件预览→采用回执。`CURRENT.acceptedProduction` 保存本次最终采用输入；运行版本另看 `nativeIntegration`。不要重跑旧目录中硬编码总装，或把“减少预览页数”当成已经生成了新人数的封面。

## 已有工程与证据

- 中秋国庆池：`<repo>/tools/midautumn-2026/README.md`、`build_content.py`、`reflow_layout.py`、`layout-v2.json`。最终 1.4.118 已通过手机裁切、动画、抽取和兑换验收。该池曾因轮播遮脸返工，最终四角色面部下移、标题宽度 1000→820 并下移；同一检查拒绝初稿，241 个循环帧通过。
- 深渊 / 竞速后续实例：`<workspace>/outputs/gacha-art-review-20261007/final-project/README.md`。V17 主视觉与 V16 横幅、分层、实机截图校准和离线重建入口集中在该可编辑工程；旧 revision-v17 仅留迁移说明。采用实际截图校准视口、保留已确认的横幅，从同版图层生成静态与原生动效候选；原生候选仍待客户端验收。
- 定向读取工程入口和相近主题的官方参考，不全树遍历、全链解包或重新猜测已证明的加载契约。核对当前版本和验收状态，历史脚本不能直接当发布脚本运行。
- 正式多角色候选从 `<workspace>/work/halloween-five-gacha-20261027/CURRENT.json` 进入；目录历史名称不代表当前名单。原包、现行 CDN、最新原画、像素/底座、作者 scene、原生 Movie 与业务规则分项绑定。当前官方模板复用从 `CURRENT.nativeIntegration.officialParity` 进入；通用原生配方仍见 `CURRENT.nativeIntegration.visualRecipe`，旧布局/节奏证据见 `CURRENT.nativeIntegration.uiRefinement`；`previousOfflineReview` 保留旧V3早期离线演出诊断，不能作为当前视觉配方。`nativeIntegration` 同时指向首批隔离原生总装：已核技能接线、角色事件保全、表行类型、资源读回、抽取兑换和存档；隔离开服状态另读runtime回执，真实collector和设备仍待验，不是已打通的通用实机管线。

## 按游戏界面设计

- 保留官方原立绘、人物体量、群像聚合、前后层次、字体轮廓和原生横幅边框。参考多张官方成品；不要为消除所有 alpha 相交而缩小、分散人物。
- 主视觉与列表横幅各自构图。当前原生列表画布为 510×180；已读官方联动1534/1574的白框主区约在 y20..160，上下透明留白也属于构图。CSS 容器及子项显式使用 `box-sizing:border-box`，导出后读回 PNG 尺寸与 alpha 边界，避免 content-box 加边框后成为514×184、全幅铺满并被轮播裁底。GachaBannerImage 的 focus 只改变 y±5 和明暗，没有选中 scale 放大；不能凭中心项看起来更高就缩放整个 PNG。主视觉上还有顶部轮播，单看1440×1789原图无法发现遮脸。
- 横幅先输出实际游戏缩略尺寸，与少量相近官方横幅并列检查主字、活动飘带和人物五官；大工作稿不能代替小尺寸可读性。多人物可在两侧前后/高低错层，给主字留出明确区域。若四脸与长标题分别挤进半幅后不可读，需重排主次；放大字时同时核人物嘴和下巴，避免把文字清楚当成整体可读。采用官方字样时，优先从对应Movie/atlas取原生透明logo、字图及背景纹理，保留RGBA与等比采样；组合吊牌等多块字标还要核trim和原生相对偏移，不从已合成横幅中裁入残留人物或重新描字。可从官方字样横幅实例（历史本地记录）的来源回执和同尺寸对照复用此路径；具体人物排布仍按本轮目标判断。
- 确定实际裁切、缩放和容器原点，沿真实 parent→child guide 组合位置，叠上顶部轮播、左侧概率 / 兑换、切换箭头、原生小人/资料层和底部抽取区域。walking 的占位取完整动画各帧 alpha/atlas bounds 经矩阵后的最小Y，含阴影、FX及缩放；单张截图或usual/dummy框不能证明全帧安全。标注脸部与必要文字，预留运动余量。横向初始化若反编译丢失对象名，应保留两种模型与不确定项，不能把截图拟合补偿当原生guide。
- 中秋原生工程采用 1080 宽视口、wrapper 原点 `(-180,60)`；历史静态图在 1560 高 featureArea 内居中产生 `-114.5` 图内偏移。它们是项目先例，须结合当前加载器或截图核对，不能按手机宽度直接把全图缩放。V17 截图校准接近 `screen=(art-[180,54.5])*screenWidth/1080`。
- 人物下移后重看层间遮挡：前景道具、头发、环形特效可能新盖住后排脸。建筑补齐等附属层随所属角色一起移动。看完整 UI 合成与原尺寸字形；当前配准、parent/child矩阵及单角信息盒证据从 `CURRENT.nativeIntegration.uiRefinement` 报告的 `references.layout` 进入，读 `RESULT.json`、`character-info-bounds.json` 与 `pixel-widget-anchor.json`。截图变换和安全边缘是对应输入的测量，合成预览只证明所建模界面，不代替客户端实测。

## 原生动效交付

- 先区分 Image `kind=1`、Movie `kind=0` 与 SkillPreview `kind=2`；角色释放真实技能属于第三类。PNG、GIF 预览、旧稿动画候选都不能证明游戏已播放动效；需要动效的交付不能止于四张静态图。
- 复用原生 Movie / atlas / sprite_sheet，根据实际消费者提供必要 timeline。实际播放读取嵌入 `.movie.l`；GachaFeatureDisplayLogic 在 advance 后进入名为 `end` 的序列即切页，不等待最后graphics帧或onComplete，因此必须同步嵌入.l和外置timeline。核两者一致、图像引用闭合、实例容量和严格PNG存储解码，不能只数总帧。atlas按路径/n匹配而非列表顺序，保留r旋转与fx/fy裁切；root和每个MovieClip各自校验image/clip池，kind1只计所属clip实例，不将所有展开叶子错误累计进根池。
- 页序先核真实feature表；已读1552/1534/1574联动均为 cover→skill→poster。原版单人海报从frame1经过159次update进入end（60Hz名义约2.65s），并用 `info_appear` / `info_disappear` 驱动原生角色信息淡入/淡出；本例为start1..4、info_appear5..150、info_disappear151..159、end160..161。只挂Character链接却用idle代替标记会令信息层透明。压缩时间线时，graphics入场也要同步压缩；这些原版参数不自动成为所有角色/版本的全局模板。依据与限制从 `CURRENT.nativeIntegration.uiRefinement` 报告的 `references.timing` 进入，读 `REPORT.md`，加载耗时及省电模式跳过技能页另计。
- 静态与动画从同版图层生成，记录源版本 / 哈希。原画只做正常变换；背光呼吸、分相位星芒、轻微刚性浮动服从官方气质。文字保持稳定并保留原尺寸字形纹理，避免合并图集时无必要地降采样变糊。
- 根据运动范围检查头部与 UI 的关系，包含入场和循环边界；预览从编译后的资源解码渲染。区分离线通过、feature 引用已接入和手机实际播放。
- 接入只改声明的池子 / 页面，完整保留其他 feature 表键和无关行字节；概率、券、兑换数据若未涉及则保持现有值。按当前授权追加资源边，不覆盖已下载的历史包。
- 卡池注意事项由RichTextLayoutParser调用Flash Xml.parse，不按浏览器HTML容错：meta、link、br必须自闭合。完整html文档本身是官方先例；原样保留实际官方note的DOCTYPE/head/body/style_id/container封套，只替换已XML转义的p文本，不能自造浏览器DOCTYPE。C7613 / Error1085实例和六个静态负例门禁见上述nativeIntegration对应packing/validate_note_contract.py；以最终ZIP解压字节校验，静态通过仍需设备回归。提取官方文件用write_bytes保存原字节，冻结输入后再交并行总装，避免write_text的Windows换行转换造成输入漂移。

### 官方联动双形态模板复用

- 先将实机完整周期与所指官方资源族对应，再认定封面阶段和单人槽位。`new_character_pickup_66`的蓝底与宣传群像是同一个top的两阶段；单人start虽为4帧，人物曲线仍收束到frame60。优先完整保留官方g/m/l/t/c/a/o，只重定图片路径、替换声明纹理槽，并给两个人物叶追加局部矩阵；还原声明变化后必须恢复供体完整AST。四人封面新增分支时声明新增image/graphics/矩阵/父segment并独立核池，不用静态群像替代所有运动。
- 保留作者base/evolved与原alpha，用实际图片像素贡献核层叠和遮脸；透明RGB非零或alpha最大254都不等于应重新抠图。姓名、称号、属性从当前数据及真实同属性资源取；不编造CV。先做一位完整样板，在实际UI和正常播放成立后再扩全批。文字字效烘焙在旧字图时，明确新字体差异，不能把旧字残影作为装饰复用。
- 单角info和封面不能共用一张假资料板：按页面标记决定是否出现，资料文字逐角色对照实机。截图裁片若含半透明板背后的旧海报，不再用于候选透明层合成；从实际UI引用的atlas提取RGBA，沿原生slice网格与guide布局叠到当前Movie上，并用两个不同底色核对alpha合成。只裁取不透明按钮/导航；slice越界先与真实texture frame求交，guide取运行代码实际读取的属性。原生中间板可能宽于单格间距，不擅自缩窄。离线kind1嵌套时钟、加色近似与设备原生播放分别记录，保留实际候选截图对照。
- 文字显得压扁时同时核对栅格生成尺寸、atlas旋转/trim、叶矩阵与祖先累计矩阵，不只检查最终scale。原字框不能单向拉宽后再声称等比；保留原逻辑比例，在更高采样分辨率绘制字形后均匀缩放，长名字按实际可用宽度等比适配。新艺术字先看真实UI尺寸及连续入场，再冻结；脸部、原生timeline和非文字纹理须保全。列表横幅的白三角、白框和飘带若原本属于PNG，应作为图片构图保留并检查未被立绘覆盖。
- 整组宣传文字偏小时，在相同stage/frame下逐行比较官方与候选的累计矩阵和alpha可见宽高，区分字图留白、局部fit限制与排版本身；不同裁切截图不能直接估倍数，多行官方logo的总高度也不能作为单行标题的拉伸目标。按实际游戏视口同时检查限定提示、主标题、保底与脚注，调整各行等比大小和间距，再以全帧文字边界核对既有walking安全区。可复用266文字体量对照（历史本地记录）的方法，具体坐标不作为其他构图的固定值。
- 当前可执行制作入口为 `CURRENT.acceptedProduction` 与[参数化管线](gacha-production-pipeline.md)；旧配方（历史本地记录）保留模板出处和历史诊断。通用原生检查器已包含四资源闭包与分域容量检查，旧`batch-audit`保留为历史证据。纯视觉manifest变化仍可能牵动运营身份，发布时复用相应身份流程；本隔离服按其最新约定免存档备份/整库副本/全表指纹，不能套用旧配方重复备份，也不把此例外推广到正式服。原始采用、整批重建、设备性能、iOS及云端结论分别登记。

- 文字放大或吊牌重定位后，先以明确正确的前版确认运动意图：装饰底板可以独立摆动，文字可在入场后静止；画面重叠不表示需要联动。不能只在一个稳定帧反解叶矩阵，旋转节点内的叶平移会改变图像相对支点的位置。需保留新版布局时，优先对前版完整底板运动施加固定外层布局变换，逐帧核对前版轨迹经同一变换后的结果，并证明文字、其他图层和时序未变。268的文字随板方案虽通过相对矩阵检查，但运动目标错误，已被否定，不能作为已采用修法；269预览修正工程（历史本地记录）以265底板行为和266放大文字为基线。候选预览、确认采用和实机验收分别记录；要求先预览时不得同步激活资源。
- 原生文本框移植到Canvas预览时，框顶/行高不是实际字形顶边。核字体、字号、x位置及actualBoundingBoxAscent/Descent，按实际墨迹对齐券图标或底条；用导出像素的上下边界复核，不能仅断言textBaseline属性。先区分原生UI正常而预览错误，预览基线修复不改原生资源。已采用像素回归见268预览对齐（历史本地记录）。
- 姓名牌轻摆支点按当前纹理的真实来源确定，不能根据目标槽号套用另一张官方牌的尖角。用均匀采样比例还原图内尖点，在独立静态叶与恒定外层布局之间重分配平移，保留原版缩放/旋转曲线及稳帧。`gacha_native`的anchors执行修正，anchor_checks锁定已人工确认的实际点并逐帧核验；工具不自动识别尖角。270采用实例仅更改塞里奥尔slot33的14帧平移，其余图层、矩阵线性部分、字体、timeline、atlas、PNG均保持；具体坐标留在该项目，不写成所有姓名牌的固定值。

## 卡池技能演示页（kind=2）

- 客户端原生在轮播区创建 SkillPreviewBattle，加载角色、关卡和自动回放日志。来源列为 Character 时读取角色详情预览的 log/clip；只有详情关卡但 log/clip 为 None 的角色不能直接沿用此路线，会触发 C2285/C2286。另可用 Gacha 来源指定独立键，读取 `master/gacha/gacha_skill_preview.orderedmap` 的关卡、日志路径、裁切 top/left 和能力/PF 开关。
- 正式日志逻辑名为配置 log 加 `.battle.amf3.deflate`，解码得到 config 与 log_parts。复用匹配的官方关卡/日志，保持未知序列化命令原字节；新角色需单独验证施放位置、实际目标、裁切及完整收尾。不能只凭数字猜枚举，也不把某个角色的原版时长固定成全局模板。
- 原生卡池预览默认关闭战斗音效与技能立绘切入，减负模式会跳过 kind=2。更改这些固定行为属于客户端工作，不包含在普通 CDN 展示接入中。
- 仓外离线试作可把已采用立绘、动态海报、独立横幅与原生素材矩阵回放组合成便携页面；绑定 CURRENT 指针和真实候选叶文件，按实际 UI 遮挡检查两形态。网页自绘战场与未接入的原生关卡/日志候选必须明确区分。CSS/SVG 海报、Canvas 素材回放、原生 Movie 编译、feature 接入和双端设备运行分别记录。
- 单文件便携性需把最终 HTML 单独复制到无配套目录的位置，点击原生海报等次级入口后核无文件/网络依赖，不能只测首页加载。内嵌查看器打开/关闭应保留主页面原有播放状态，并检查窄屏；可复用四人候选的 `audit-20261028/check-portable.cjs`。
- 预览暂停保留 CSS 动画对象与 currentTime，不用 `animation:none` 代替冻结。若重播使用 WAAPI play，播放/暂停也统一显式 play/pause；恢复时跳过已经结束的有限入场动画，避免 play 将其重启。回归包含重播→暂停→继续、暂停时换角色/形态、空池名回退；已核浏览器证据留同案 `audit-20261028/ui/`。
- 可复用案例：`<workspace>/work/gacha-halloween-inaho-20261027/TASK.json` 及同目录构建/检查脚本；成品 `<workspace>/outputs/gacha-halloween-inaho-20261027/revision-v1/`。已核原画及当前技能资源身份、原生日志与行结构、file URL 离线加载和控件；原生关卡候选与客户端执行尚未验收。单文件版嵌入全部图片/脚本，检查无外部请求；不要沿用旧浏览器 file 协议故障替代当前检查，也不要绕过当前实际策略拒绝。
- `.wfchar` 的作者 scene 不会自动替换现行 ActionDSL；先区分角色已有原生技能、作者技能美术和入手表演。`special_land` 不作为施法的替身；新演出若需用于 kind=2，必须另做原生效果、坐标、出招/命中/恢复与回放接线。原包旧缺项摘要不能覆盖实际 portrait/scene 绑定，也不能因包无 nativeGameplay 推断当前 CDN 没有该角色技能。
- 收到技能展示任务，先逐轨核对默认 scene：只含 `special_land/special_pose` 是入手编排，只含 effect 而无 actor 不是完整施放场景。原稿保真导出只能作为原稿检视，不能作为默认技能演示交付。最新人物与选定特效须按施放、目标关系、收尾重新装配；新特效时长与旧 DSL TTL 不同要显式记录候选寿命，不静默截断。原生 Some(scale) 覆盖 parts.s，Studio frameScale 也不等于游戏调用倍率；外层投影和图层变化必须在候选中声明。

## 隔离原生总装与运营身份

- 可复用原生总装、独立读回及服务端回归见上述 CURRENT 的 `nativeIntegration`，不要把目录中的早期禁抽候选当最终支付方案。官方 quest128/Rem日志是该批的匹配先例，不是任意技能的固定模板；新角色分别注册Gacha preview键，保留未知命令，仅按完整演出延长结束帧，网页假人和移动轨迹不进入原生日志。
- 只改表现的DSL须列出允许节点与字段，独立逆向撤销后完整AST等于基线；原有全DSL校验缺口与新增节点合法性分别报告。全局像素替换保留非视觉事件；原始立绘尺寸变化时同步核character_image、trimmed_image、pivot/scale/face，原图字节保真并不证明布局正确。
- 新增serverGachas导入会改变共享loader哈希及全局资源身份。先冻结manifest/新业务行，再用真实capture逐项证明旧依赖、定义和serverSources不变，受控刷新旧证据loader元数据，重建派生身份；不能放宽运行时匹配，也不能因刷新而把既有mismatch变为开放。任务/商店规则、箱子关联、展示索引和缩略图的源身份一起闭合。
- 单资源热修也不能假设无需运营身份校准：现行nativeQuestIdentity/nativeShopIdentity纳入全manifest SHA，即使catalog/业务/loader不变仍会改变对应内容摘要。复用已有效的精确证明，仅更新必要来源元数据/投影并在停服备份后对受影响控制做reviewed rebind；只有catalogDigest及contentDigest均未变化的状态才可原字节保持。资源已下载则追加新版本边，禁止覆盖旧ZIP。
- 支付定义等业务变化若改变全局catalogDigest，重绑集合须同时覆盖内容摘要变化和目录身份戳失配，不能只比较contentDigest。区分业务改动、manifest派生和catalog-stamp-only三类；最后一类必须逐项证明原contentDigest、开关、逐动作证据、范围、发布和实例保持，仅更新必要身份戳、revision及审计。用原offline路径保护、固定revision与raw CAS，不放宽currentIdentity、不重放初始化。共享catalog历史资源锚若仍表示旧取证来源应保留，当前新增资源另建闭包；不要刷新共享锚制造全部旧池业务变化。独立库重绑后的验证应包含原启动门禁，避免把局部保全通过当作可开服。
- 身份索引通过仍不证明开服门禁通过：在独立库上执行启动器同样的time-content-deployment verify，核content-deployment、box补核及部署marker是否绑定旧目录/父项。追加池应保全原计划、旧初始化和旧控制，仅用精确审阅扩展认可新身份与可选父项；禁止跳过verify或重新初始化旧内容。该批startup复现从nativeIntegration对应operations-identity/STARTUP-REPRODUCE.md进入，9个窄用例覆盖扩展损坏、额外父项/状态、缺旧控制、坏marker和未审核新池。
- 先在真实库只读快照验证reviewed rebind，核旧开关、逐动作证据、结束/范围/发布/实例、旧审计和非运营表全行指纹；工具可能补空顶层诊断evidence，应与审批证据分开记录。新池默认关闭后再明确核查、发布；消耗、券、概率、兑换、幂等、回滚和当前支持的存档HTTP路径另测。隔离检查不授权切换服务或真实库。
- 静态预载按原生collector语义计PF、Fever、召唤、装饰和共享cache：PF不执行、visible=false不表示不收集。已知矩形需几何装箱，不能只看总面积；未知动态目标保留null，不能写整场通过。开服入口规则与客户端实际端口冲突时，候选完成后明确说明所需例外，不增设隐藏代理或第二资源链。

### 专用券与十连按钮

- 在已核原生客户端中，pageKind=4（TenTimesTicketOnly）对应单个宽版十连按钮，每次使用1张tenTicketItemId券；持券为0时GachaLogic会隐藏卡池。新增券、配置入手来源、实际发券是不同动作，不在未授权时给账号或活动加券。服务端同时核pageKind、tenTicketItemId及禁用通用券，拒绝星导石、单抽和错误券；沿用原事务扣除、十连保底、计数、兑换及存档路径。
- 列号以实际GachaValues解析器为准：已核47列表的角色通用券是20，26是装备通用券，27/28是单抽/十连专券；不能因名称相近写错字段。新道具先核当前有效客户端表与服务器全部ID登记，保留旧行原字节，复用已有十连券类型和图标闭包；必要支付说明沿官方XML封套更新。预览须按原生frame4与cost layer显示“券×1”，示例持有量不等于已发券。
- 切换支付前先保留旧业务文件和旧编译输出，完成最新停服库备份及旧状态捕获后才应用业务候选；只重定向manifest读取的旧工厂仍可能读取新业务JSON。已有目录身份迁移按上节同时检查catalogDigest与contentDigest。实施、资源和隔离验证依据见专券工程（历史本地记录）；设备结果另看当前回执。

## 像素小人与原生底座

- 展示页的 Character 链接字段决定原生角色信息层；Image/Movie 页也可挂小人，群像页未链接单角时不虚构多个角色信息层。GachaFeaturePageHolder 换页播放普通 `walk_front`，不是 NewEntry 的 special。保留源裁片位置和 hold，卡池原生速度 0.5 只应用一次；工坊 runtimeSpeed 另记，不盲目再乘。
- PixelArtCharacterView 将解析后的动画根 scale 重置 1，再由 characterLayer 放大 6；不能将 frame.scale=6 再叠成 36 倍。离线渲染按实际 atlas/frame 公式还原，最近邻采样，不逐帧居中。
- 完整底座优先 CharacterValues.pedestal_image，None 时按元素/星级选择。逻辑图可能在 `character_pedestal/sprite_sheet` 图集中，不是缺少独立 PNG。先取当前有效图集，再按需从已核验客户端 bundle 取共享 `character_on_pedestal`/rarity UI、阴影和矩阵；不要复制旧 bundle 整图覆盖新 CDN。完整底座、角色、阴影、星级分别按共享 UI 的 usual 矩阵绘制，不能自画圆盘代替。
- 最新作者小人转成全局角色资源前，检查旧 timeline 的 sounds/points/circles；工坊空模板不能抹掉血条锚点或身体碰撞圈。新动作时长变了，应按槽名和槽内偏移保留非视觉语义，不能照抄旧绝对帧；新增槽不隐式继承上一槽空圈。只做卡池离线副本时，明确其不是可直接安装的全局角色替换。
- 名单变动同时过滤封面/横幅/单角、原画、小人、作者 scene 的真实图片闭包、业务概率与兑换、原生 payload 和编译后预览数据，不只隐藏按钮。旧稿保留为 superseded，CURRENT 只指向新名单；静态文本/ID扫描与实际图像目检都要做。

## 按问题选证据

带 UI 的静态对照和原生动效预览能直接暴露美术错误。普通修订无需重复 HTTP 下载、服务重启、全链核验或新 APK。把图层版本、真实发布状态、预览入口和剩余验收写进任务记录，避免旧交接中的“先做静态”阶段目标变成最终完成标准。

演出核查必须看最终浏览器画面与连续播放：人物是否实际可辨、主效果是否被界面挡住、目标关系、结束后是否恢复、循环是否跳位。命令数、几何不越界、原包相等、trace.visible=true、无 pageerror 都不能单独证明这些结论；人物被前景光束完全覆盖时，仍可能全部通过。四人早期离线修复历史保留在 `revision-v3/check-performance.cjs`（实际Canvas有/无人物像素差）与 `performance-repair-20261028/ui/v3-final/`（全UI、正常/半速）；当前视觉与节奏继续入口必须读取 `CURRENT.nativeIntegration.visualRecipe` / `uiRefinement`，不能复用旧V3作为当前版。上述历史和当前离线模型均不代替游戏验收。参数只适用该批候选，不自动推广成通用技能模拟器。
