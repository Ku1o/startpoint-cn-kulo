# 可复用角色与扭蛋制作工具

本目录保存角色阶段台账、便携预览、扭蛋美术合成、原生 Movie 编译和主动技能三组视觉资源的工具。工具不会自动发布 CDN、改玩家数据库、发券或启动服务。美术、音频、机制与设备验收仍需分别完成。

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
| caster/field/hit 主动视觉框架 | `scripts/active_skill_pipeline.py`；[主动技能方法](references/active-skill-workflow.md) |

扭蛋项目通过 `toolchain.supportRoot` 指定此仓库，`toolchain.node` 指定实际 Node 可执行文件；每个文件输入绑定完整 SHA-256。大型样板资料独立于 Git 源码保存，不能用空素材或改摘要绕过缺失输入。

## 验证边界

现有单元测试保存在 `scripts/tests`。真实原生样板测试显式使用 `GACHA_NATIVE_SUPPORT_ROOT`、`GACHA_NATIVE_CASE_ROOT` 和 `GACHA_NATIVE_TEST_OUTPUT`；缺少样板时的 skip 不算真实样板通过。美术样板重放另需 `GACHA_TEST_FONT`。预览测试使用 `GACHA_PREVIEW_TEST_INPUT` 指定输入清单。

制作工具可复用不代表四人模板能够自动适配任意人数，也不代表网页技能演示执行了游戏内 kind2 战斗。新主题仍须实际配置人物、图层、原生槽位、支付和技能引用，并审阅完整动画。

主动技能入口默认提供 `native-three-group-toolkit` 空框架；它固定三个编译工具和同仓依赖摘要，不包含角色美术或设备验收。以 `prepare --case native-three-group-toolkit --character-code <code> --out <仓外路径>` 新建工程后，需要自行提供三组美术与运动数据。历史案例可通过 `STARPOINT_ACTIVE_CASES` 指定另外下载的资料清单；历史方法文中的本机案例路径不作为默认可用输入。
