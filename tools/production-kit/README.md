# 可复用角色与扭蛋制作工具

本目录保存角色阶段台账、便携预览、扭蛋美术合成、原生 Movie 编译、原生卡池技能录制及主动技能三组视觉资源的工具。扭蛋分支包含完整 UI 审查、单文件演出、失败续作与资源预算保护。工具不会自动发布 CDN、改玩家数据库、发券或启动服务。美术、音频、机制与设备验收仍需分别完成。

## 环境与输入

使用项目已有 Python 3.13 环境及 Pillow，Node 版本遵循仓库 `package.json`。原生资源工具位于同仓 `tools/fantasy-gauntlet-mod-tools`。不要将 SDK、虚拟环境或基础模型复制进源码目录。

在 PowerShell 中显式设置仓外输出边界：

```powershell
$env:STARPOINT_WORK_ROOT = 'D:/starpoint-work'
$env:STARPOINT_PREVIEW_ROOTS = 'D:/starpoint-work;D:/starpoint-deliveries'
$env:STARPOINT_SUPPORT_ROOT = 'D:/starpoint-source'
```

路径可替换为其他实际目录。输出必须严格位于允许根目录内；原件、源码根和只读 CDN 不作为输出位置。

## 制作入口

| 任务 | 工具与说明 |
| --- | --- |
| 建立角色阶段、声音要求与缺项预览 | `scripts/character_production.py`；[角色制作流程](references/character-production-workflow.md) |
| 根据角色清单生成便携预览 | `scripts/character_preview.py`；[预览模板](references/character-preview-template.md) |
| 扭蛋制作、校验、编译和交接 | `scripts/gacha_pipeline.py`；[管线合同](references/gacha-production-pipeline.md) |
| 美术图层合成 | `scripts/gacha_art.py` |
| 原生 Movie 模板与逐帧回读 | `scripts/gacha_native.py` |
| 单 HTML 扭蛋预览 | `scripts/gacha_preview.cjs` |
| 原生技能、全 UI 审查及完整演出 | `scripts/gacha_capture.py`、`gacha_skills.py`、`gacha_skill_ui.py`、`gacha_skill_media.cjs`；[技能管线](references/gacha-skill-pipeline.md) |
| 逐页美术检查与采用绑定 | 主命令 `review-art`，初始化生成 `ART-SETUP.json` |
| Windows 处理任务的内存与串行保护 | `scripts/gacha_guard.py`；主 CLI 自动调用，独立处理工具显式包裹 |
| caster/field/hit 主动视觉框架 | `scripts/active_skill_pipeline.py`；[主动技能方法](references/active-skill-workflow.md) |

扭蛋项目通过 `toolchain.supportRoot` 指定此仓库，`toolchain.node` 指定实际 Node 可执行文件；每个文件输入绑定完整 SHA-256。大型样板资料独立于 Git 源码保存，不能用空素材或改摘要绕过缺失输入。

## 验证边界

Windows 上可使用仅依赖 Python 标准库和 Git 的提交卫生检查：

```powershell
python tools/production-kit/scripts/check_hygiene_windows.py --repo .
```

它读取 Git 已跟踪文件的工作区内容，按 `scripts/check-hygiene.sh --all` 的规则报告个人地址、路径、邮箱、`.env` 和不应入库的大文件；支持中文及空格文件名，不修改、暂存、提交或上传文件。未跟踪文件不在检查范围内，准备提交时应先按明确文件清单暂存，再检查最终内容。它不检查历史提交，也不能替代独立 Gitleaks 扫描或远端 CI。两种检查器都只对检查器自身的精确路径排除内置规则示例；其他文件仍受检查。

标准库回归入口为 `python -B tools/production-kit/scripts/tests/test_hygiene_windows.py`。若还需对照 Bash 检查器，设置 `HYGIENE_TEST_BASH` 为已有 Git Bash 的实际可执行文件路径；不要为此安装另一套环境。

现有单元测试保存在 `scripts/tests`。真实原生样板测试显式使用 `GACHA_NATIVE_SUPPORT_ROOT`、`GACHA_NATIVE_CASE_ROOT` 和 `GACHA_NATIVE_TEST_OUTPUT`；缺少样板时的 skip 不算真实样板通过。美术样板重放另需 `GACHA_TEST_FONT`。预览测试使用 `GACHA_PREVIEW_TEST_INPUT` 指定输入清单。

制作工具可复用不代表四人模板能够自动适配任意人数；Movie页面也不能替代kind2原生技能执行证据。新主题仍须实际配置人物、图层、原生槽位、支付和技能引用，并审阅完整动画。

完整扭蛋池使用 `init --with-skills`，配置真实原生输入，`build` 后审阅完整UI并 `review-skills`，`resume` 装配完整演出；最终 `review-art` 检查标题、姓名牌、人物文字、限定牌、配色和底部界面。支持的原生适配器固定为C8601，匹配客户端、原画、资源归档、AIR/编译工具与媒体工具需要另行提供；它们不包含在Git源码内。新客户端须适配，离线播放不冒充手机验收。

主CLI目前要求Windows及明确的 `STARPOINT_WORK_ROOT`（或 `STARPOINT_GACHA_RECEIPTS`），回执目录必须在源码之外。默认轻检查512 MiB，构建/录制上限2048 MiB，预留至少4 GiB物理内存并共用串行槽。该限制覆盖处理进程树，无法约束GPU或其他应用。独立Node/图片/媒体调用也应走guard，详见主管线。

可运行的轻量回归：`python -B -m unittest discover -s tools/production-kit/scripts/tests -p test_gacha_skills.py`、对应的 `test_gacha_art_review.py`、`test_gacha_guard_output.py` 和 `test_gacha_guard_paths.py`；原生配置检查为 `python -B tools/production-kit/scripts/gacha_capture/test_validation.py`。这些测试不启动AIR。Windows资源保护自测为 `python -B tools/production-kit/scripts/tests/test_gacha_guard.py <已存在仓外证据目录>`：控制器在共享槽外，测试子进程自行进入受限Job，不要外套另一个占用同槽的guard。其他处理测试按主管线通过guard运行。

主动技能入口默认提供 `native-three-group-toolkit` 空框架；它固定三个编译工具和同仓依赖摘要，不包含角色美术或设备验收。以 `prepare --case native-three-group-toolkit --character-code <code> --out <仓外路径>` 新建工程后，需要自行提供三组美术与运动数据。历史案例可通过 `STARPOINT_ACTIVE_CASES` 指定另外下载的资料清单；历史方法文中的本机案例路径不作为默认可用输入。
