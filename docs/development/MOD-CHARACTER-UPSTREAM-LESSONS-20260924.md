# MOD 角色制作：上游经验与本地适用范围

整理日期：2026-09-24。

来源：[kuronzzhan-droid/startpoint-cn-mod-tools][repo]，本次读取的 `master` 为 [`fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21`][commit]。以下链接固定到该提交，便于区分后续更新。

本次重点阅读角色制作、资源、技能切换和 PF 文档，并抽查编译器、资源收集器、发布合并代码及相关测试；不是全仓逐行审计。上游记载的设备结论保留为“上游案例”，代码和测试的静态阅读不代表已在当前客户端复现。本次只维护经验文档与技能引用，不改游戏数据、存档、客户端或服务端行为，也不新增运行时校验。

本地已经遇到并处理的问题见[中秋稻穗制作复盘](MOD-CHARACTER-PRODUCTION-RETROSPECTIVE-20260922.md)。两份文档互补：本文件记录上游提供的依据、可借鉴方法及限制；本地复盘记录本地实际结果。

## 可直接用于后续制作的方法

### 1. 先区分外观替换、独立换皮角色、全新角色

外观替换可以复用原数据；独立持有的换皮角色仍需要独立身份与数据引用。制作方分配角色 ID、资源代码、能力/技能键及玛纳板节点，不能只复制一行角色主表。主城台词、技能预览、立绘定位、获取演出等外围表也在角色读取链中。

可借鉴上游的模板克隆方式，先保留已知结构，再逐项替换；未修改的官方素材允许复用。ID 编码规则和必需表范围以当前读写代码为准，不把上游某次“16 张表”当成所有客户端的固定全集。参见[资产文档 §6–7][assets-doc]、[生成器说明 S0][generator-doc]。

### 2. 分清服务端数据、工具镜像和客户端主数据

工具页看到的 JSON、服务端发放/培养使用的 JSON、客户端读取的 orderedmap 可能是不同消费层。修正文案、属性或角色身份时，逐项确认谁实际读取它；只改工具镜像不能证明游戏已经更新。

上游早期逆向指南与后续[技能切换文档 §3][switch-doc]存在修正关系。采用后者关于消费层同步的结论，但不直接照搬旧路径、端口或发布器。原生技能切换也有自己的 character 表条件与 `switched_action_skill` 引用，不能只修改技能 DSL 就认定切换条件已成立。

### 3. 数据格式以对应解析器为准

能力表与队长表不能机械复制列号。空串、`(None)`、零、布尔文本按具体字段分别解释；百分比、次数、秒/帧也不能使用一个全局换算。处理带换行的角色简介和台词时，将完整 CSV 文本交给 CSV 解析器，不能先按行拆散。

ActionDSL 的命令名、位置参数、枚举和 AMF3 类型一起构成接口。JSON 中的整数与浮点数也可能对应不同编码类型。采用“参考同类官方命令 → 修改明确参数 → 序列化后读回”的做法，不把结构检查通过等同于行为正确。代码依据：[字段布局与单位][fields]、[`wf_client_legality.py`][legality]、[`wf_dsl.py`][dsl]、[DSL 编译测试][dsl-test]、[完整 CSV 读取][requirements]。

### 4. 显示描述和战斗行为是两条链

同一个效果挪到队长技后，可能改变主位/协力上下文，描述生成器也可能走另一分支。优先找同一张表、同一使用场景的官方条目；没有先例时进一步看解析器与执行器，不能直接断言可用或必崩。

原生主位标记、属性标记和图表化视图由对应显示机制生成，避免在自由文本里再写死一份图标。上游的双主位标记案例有参考价值，但其文档对 `unisonable` 所属表和 `202` 的说明不完全一致；定位时从实际能力行和当前 schema 出发。参见[新角色制作心得][lessons]、[字段手册 ability 布局][fields]；本地文案问题见稻穗复盘。

### 5. UI 派生应由母版、裁切焦点和定位数据共同生成

进化前后母版锁定后，分别生成头像、队伍主位/协力卡片、战斗 UI、立绘设置图集和 cut-in。脸部焦点及构图要按页面处理，不能把同一张完整立绘等比塞进所有尺寸。

同时保留图像与 `character_image`、`full_shot_image_attribute`、`trimmed_image` 等定位信息的对应关系。上游 UI 编译器及测试已经按不同用途和形态处理裁切；其中具体像素坐标属于模板，不能原样套给另一角色。参见[生成器说明 S2–S3][generator-doc]、[UI 编译器][ui-code]、[UI 测试][ui-test]。

### 6. 像素动作的“图”与“时序/定位”一起保留

换色或服饰改绘可以优先继承模板 atlas 的帧名、裁切框、偏移，以及 frame/timeline 的动作标签和时间。新增轮廓超出原格时再重新安排图集，不能仅放大 PNG 而忽略元数据。上游像素编译器中的尺寸、帧数、九组动作是其雷龙模板约束，不是所有角色的标准。

获取演出的特殊动作也不能漏掉：上游有专门的兼容编译器生成 `special_land`、`special_pose`。复用 special 槽制作战斗变身时，需要兼顾原来的获取演出用途。参见[普通像素编译器][pixel-code]、[特殊动作兼容编译器][special-code]。实际领取表现仍按使用该资源的当前客户端确认。

### 7. “基础资源齐全”不等于所有引用都能加载

角色目录外还可能有状态图标、技能/PF 动作、效果 parts/timeline、图集和贴图。上游资源收集器后来补充了这些引用，说明单看固定模板清单会漏项。可借鉴“从实际表/DSL 引用追到资源”的方法，而不是继续堆固定文件名。

当前上游收集器只覆盖列出的引用种类和路径前缀，其 `skill_effect` 分支也采用特定目录命名约定。它不是任意特效的完整依赖解析器；其他结构继续沿实际加载路径查。浏览器帧预览只能证明其已实现的播放部分，复杂 parts 变换和补间不能由帧墙推断。参见[资源引用提取代码][requirements]、[2D 预览的证据边界][preview-doc]。

### 8. 特殊 PF 要先选实现路径

上游区分了两类官方做法：替换 PF 的等级动作，以及在 PF 触发时额外调用技能动作。选哪一种取决于需要改变弹射本体，还是追加攻击/演出。追加调用技能不自动改变其伤害类别，也不能把“造成 PF 类伤害”理解成一次真正的 PF 发动。

飞行、命中、玩家侧伴随效果可以是不同动画；找不到某张“角色 PF 图”时，沿 DSL 的特效路径查配套 parts/timeline 和共享图集。参见[PF 逆向文档 §2、§3.5][pf-doc]。本地当前采用[作者统一伤害规则](../../client-patch/author-unified-damage/README.md)，通过原生 629 调用脚本并由扩展标记分类；[旧通用伤害入口](../../client-patch/generic-damage/README.md) 仅作历史参考。触发方式、攻击力来源、PF 分类与原生 PF 发动的区别见[本地返修经验](MOD-CHARACTER-PRODUCTION-RETROSPECTIVE-20260922.md#author-integration-20260924)。

### 9. 音频按真实引用收集，音效另列

固定命名的战斗语音之外，主城语音可能使用角色专属名称或自定义 `home_N`。上游收集器专门补过后者，否则导出/克隆会遗漏仍在使用的文件。后续以 `character_speech` 的实际引用和战斗调用约定为依据；不能仅按 `_0/_1` 文件名推断所有语音的进化关系。

音频源文件、游戏内存储格式、表中绑定是三件事。上游使用 WAV 转 CBR Layer III MP3，再转换游戏帧头；编码器还处理过“只转换前半段”的问题。`44.1 kHz/单声道/96 kbps` 是已用配置，不代表所有可播放音频只能采用这一组合。声音可解码也不能证明音色、响度、日语语气或台词正确。参见[资源/语音收集与编码][assets-code]、[语音编译实例][voice-code]。

角色喊声和主动技能音效分别记录。上游 flatomo 编译实例输出的 `sounds` 为空，不能因为视觉特效已生成就认为起手、飞行和命中音效也完成了。对应代码：[flatomo 编译器][flatomo-code]；本地遗漏记录见稻穗复盘。

### 10. 可预览文件与游戏可读文件不同

普通 PNG 的头部与游戏存储态不同；MP3 也不能仅凭桌面播放器能播就直接装包。同一个逻辑文件名还要落在读取器选择的资源根下。角色 UI 的 medium/small、普通公共资源、平台 cut-in 分开核对；上游较早文档主要列 Android，不能据此推断已经覆盖 iOS。

依据：[路径与存储说明][paths-doc]、[`wf_assets.py`][assets-code]、[PNG 存储态测试][pack-test]。本地角色图片根目录和 Android/iOS 配对的实际修复见稻穗复盘及现有资源经验。测试只检查特定格式时，也不能代替完整解码和页面表现。

### 11. 整合版本时按最终覆盖结果合并

上游链合并器按实际可下载路径重放旧包，保留每个成员最终生效的内容，并考虑旧版本客户端是否仍能到达目标版本。值得沿用的是这套“保留终态”的思路：不能按文件时间、包名或“测试包”标签选择取舍，也不能从旧模板重新生成共享表而覆盖其他角色改动。

上游脚本使用其自身的 legacy 目录、active 格式、版本桥和文件退役办法；这些操作不直接移植到本地。这里只吸收方法，本地沿现有源码、manifest 和发布流程完成整合。参见[链合并器及验证函数][squash-code]、[多角色包共存/rebase 说明][flow-doc]。

### 12. 排错先看本次日志，错误码只负责缩小范围

结合报错发生页面、堆栈、资源版本和实际读取文件定位问题。上游记录了“界面提示资源损坏，实际上是字符串键缺失”等案例；同一个 F1009、C8105 或“数据不足”可能有多种根因，不能建立一对一结论，更不能未经取证先清存档或改服务端。

上游[制作心得的崩溃案例][lessons]是查找线索，不是当前客户端错误码字典。设备侧检查仅在对应测试任务内进行，静态阅读不算设备验收。

## 明确保留的差异与未复核事项

| 上游表述或做法 | 后续采用方式 |
|---|---|
| PF 文档早段推测 master 同名键可以覆盖 | 同文 §3.5 已更正为 base/download 文件联合时重复键会出 C7051；普通资源的下载优先规则与 master 键合并分开理解。具体表以当前读取器为准。 |
| 旧资料称 `voice/words` 只给剧情 NPC 使用 | 后续技能切换文档已提供可玩角色实例。是否制作该类台词由角色需求决定。 |
| 工作流规定 37 项必需资产，动态语音是建议项 | 这是该版本工具的范围，不是角色完成定义。以本角色用途补齐主城语音、进化形态、音效与额外特效引用。 |
| 生成器说明描述 GPT-SoVITS 默认 provider | 本次读取的 [`wf_voice.py`][voice-interface] 中 `local_http` 仍抛出 `NotImplementedError`，[对应测试][voice-test]也按预留接口检查。文档不能证明该调用链已实现，更不能据此自动替换现有语音流程。 |
| 生成器 v2 不支持新 flatomo 时间线/SFX | 同一提交已有独立 `wf_flatomo_compile.py` 生成特定效果。分别判断某个入口支持什么；该编译器的空 `sounds` 也不代表已经实现 SFX 编辑。 |
| 队长表没有官方先例就必崩；P-code 引用新类必崩 | 仅保留为对应上游版本/实现的事故经验，不能作为普遍定理。本地通用伤害扩展已经有独立类和接入记录。 |
| 含 ACUnique 的 CreateCondition 条件数量限制 | 保留为上游案例，未在本次本地复现；设计类似复合状态时核实当前执行器，不自动限制所有角色。 |
| 固定图集尺寸、32 色、轮廓 IoU 阈值、ZIP 5 MiB 上限 | 多为模板、生成器或上游 CI 策略，不认定为游戏引擎通用上限；按实际资源与项目要求选择。 |
| 上游直写 live/CDN、自动调整已有存档、特殊发布口令 | 不纳入本地角色经验的自动执行步骤。采用源码为准、定向同步的现有工作方式；修改已有玩家数据仍需具体任务依据。 |

## 给角色制作工具的可用输入

作者侧继续填写自然语言：角色资料、进化前后设定、技能/队长技/PF/能力的条件与效果，以及美术、台词、语音、音效参考。制作方负责字段编码、ID、单位、伤害类别、动作和资源绑定。

工具可借鉴上游的模板资产枚举、按页面裁切、只重做被修改的语音/图像、独立工作目录与生成物记录。不能把 37 项、旧文档所称“可发布”或已生成预览直接显示为角色全部完成。已完成的内容、复用项、待提供项和不适用项分别记录；不为借鉴经验新增客户端准入或服务端运行时校验。

具体填写项统一维护在[本地制作复盘](MOD-CHARACTER-PRODUCTION-RETROSPECTIVE-20260922.md)，避免再维护一份不同步的作者表格。此文档本身不表示已升级制作工具。

## 来源索引

以上技术结论为阅读与归纳，原始文档和实现归上游作者。复用源代码时继续遵守仓库许可证及现有来源记录。

[repo]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools
[commit]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/commit/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21
[lessons]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/docs/新角色制作心得.md
[assets-doc]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/docs/角色资产与全角色替换方案.md
[generator-doc]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/docs/角色生成器使用说明.md
[switch-doc]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/docs/技能形态切换与资产包导入结论.md
[fields]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/CN-Mod字段手册.md
[legality]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/wf_client_legality.py
[dsl]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/wf_dsl.py
[dsl-test]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/tests/test_action_skill_compile.py
[ui-code]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/wf_character_ui_compile.py
[ui-test]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/tests/test_character_ui_compile.py
[pixel-code]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/wf_pixelart_compile.py
[special-code]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/wf_pixelart_special_compat_compile.py
[requirements]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/wf_character_requirements.py
[preview-doc]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/docs/2D序列帧只读预览.md
[pf-doc]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/docs/强化弹射与boss连战逆向结论.md
[assets-code]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/wf_assets.py
[voice-code]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/wf_summer_thunder_voice_compile.py
[voice-interface]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/wf_voice.py
[voice-test]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/tests/test_voice.py
[flatomo-code]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/wf_flatomo_compile.py
[paths-doc]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/docs/资源路径与解密逻辑.md
[pack-test]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/tests/test_character_pack.py
[squash-code]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/wf_chain_squash.py
[flow-doc]: https://github.com/kuronzzhan-droid/startpoint-cn-mod-tools/blob/fd433b05bf6f2ac9cb4b7c415b5a0f40f469ef21/docs/角色包工作流.md
