# 深渊续战阵容复用：Android 测试补丁

2026-09-09 验收纠正：本页两份公网/内网测试 APK 均因使用 9 月 6 日旧基线而遗漏 Lens 累计内容，
现已判定不通过，禁止继续交付或作为新输入。内网包点击基诺维的 C7050 与缺少 422 解析分支一致。
当前基线已登记为 [Lens v3](../android-accepted.json)，详情见 [验收记录](../ACCEPTANCE-20260909.md)。
以下内容仅是失败候选的历史记录；构建器的旧输入保护保留，续战改动需基于 Lens v3 重新审计移植。

2026-09-09：用户授权先以安卓 APK 修改尝试。本目录只包含客户端构建方法；
没有修改服务端、CDN、数据库、IPA，也没有提交或更新已验收客户端登记。

## 问题与最终行为

服务端已经通过 `unlock_played_parties=true` 保留深渊楼层记录并清空下发的角色 ID。
普通逐关开战因此能复用阵容，但客户端续战设置额外比较各关预设队伍，
把跨关重复的主位、副位角色标为重复并阻止开始。

修改 `pinball.common.data.quest.singleQuestAutoStart.RushEventAutoStartQuestGroup`
的 `getDuplicatedCharacterIdsForEachQuest`，当前 Android 位置为 **284:24599**。

- `event.id == 700099`：按 `folder.getQuests().length` 返回每关独立的空数组。
  外层长度保留，避免续战列表按楼层索引读取时取得空值。
- 其他活动：进入原有方法的完整指令序列，维持原有角色锁定规则。
- 保留 `shouldSelectPartyForEachQuest()`、逐关选队界面和续战进度逻辑。
- 续战列表标记和开战前检查共用这个方法，因此都得到同一豁免结果。

补丁直接导入一个方法的 P-code，不对整个类重编译后发版。新分支使用寄存器
20–22，原有方法的寄存器与跳转逻辑保持不变。

## 本次公网候选

输入为 `client-patch/android-accepted.json` 登记的已验收公网包，身份检查通过。

| 项目 | 值 |
| --- | --- |
| 输入 APK SHA-256 | `7990f9191ecf41bd35a4d886ced4d13248d13559284639c69bee5837bd682f0e` |
| 输入 SWF SHA-256 | `27bdd055f8ca15f0863f564f5b4d57aba7de18d65d5fb9cdec43e87f96740e64` |
| 输出 APK SHA-256 | `c0823d0e5ad6c8677de7ee7dddf2094e527c498c0972ae6d0b9ede5180754bc7` |
| 输出 SWF SHA-256 | `4bf46774c7fc907b838f5268be9bc79fa37a3597f79623c3f971ffd3f0457d2f` |
| 新 AIR UUID | `43ae285f-892d-4cc3-8b12-54196b70a59a` |
| 服务器地址 | 沿用公网基线 `http://175.178.160.158:8001` |
| 状态 | 本地校验通过，未真机验收 |

成品：`outputs/abyss-autostart-public-test-20260909/StarPoint-CN-1.8.1-abyss-autostart-public-test-20260909.apk`。
同目录附 `verification-report.json` 和 `SHA256.txt`。

反编译和构建证据：`work/abyss-autostart-build-public-20260909-r2/`，
包含源/最终 P-code、最终 AS、方法比较结果和输入/输出 SWF。
初次构建在控制台输出 FFDec 日志时遇到 GBK 编码错误，未签名或交付；
构建器现已将输出设为 UTF-8，成功构建使用上述 r2 目录。

## 已完成的本地验证

- 核验已验收 APK、内嵌 SWF 和 AIR UUID。
- 比较全部 96,397 个方法体，只有 `284:24599` 改变。
  先前 MOD、幻想连战、轮播、排行榜、关注/本人资料和标题方法均未改变。
- 从最终 SWF 重新导出 P-code，与预期指令和方法栈/寄存器元数据一致。
  非深渊分支的原始指令与跳转图不变；目标类其他内容也不变。
- 对实际回读的新增指令做小范围解释执行：深渊 0/1/30/60 关，
  幻想 `700098`、普通 `700007` 和复刻 `700017` 共 7 个用例。
  验证每关空数组、各数组独立、循环结束、非深渊分支干净回到原逻辑。
  这是指令级模拟，不是 AIR 或真机运行。
- 回读已签名 APK，确认 SWF 正确，manifest 仅更新 UUID，
  除签名、manifest、SWF 外的全部 APK 成员保持原字节。
- ZIP 对齐及 v1/v2 签名验证通过，证书 SHA-256 为
  `569D19A3578D4CBA16E3D6E7AD8CCAB4FA667EFC758DEEF6C9BE3ADB99919894`。

## 内网候选（2026-09-09）

用户随后要求提供内网测试包。以登记的已验收内网 APK 为直接输入，运行同一个
`build_apk.py --variant lan`，只改 `284:24599`，地址沿用该内网基线。
内网地址从忽略的 `outputs/android-build-local.json` 校验，不写死在源码或本文中。

- 成品：`outputs/abyss-autostart-lan-test-20260909/StarPoint-CN-1.8.1-abyss-autostart-lan-test-20260909.apk`。
- 输入 APK SHA-256：`8e10df1f2b259fdc5cacf30f9a66ed3bc0556d5d253a22f55a931c22a0e6c9c0`。
- 输出 APK SHA-256：`111a396cd8a80cbb6a64ce27be37639c33a2a876addec41f0832ac78726ebd5d`。
- 输出 SWF SHA-256：`4005af61395da3db9805d40b3f547ad8f0d3e99ec23de6091c7b53d348c44e89`。
- 新 AIR UUID：`1c15c17e-1303-4d75-a210-64d5f2f969c9`。
- 同目录附 `verification-report.json` 和 `SHA256.txt`；反编译及构建证据位于
  `work/abyss-autostart-build-lan-20260909/`。

同样通过全部方法体比较、最终 P-code 回读、7 个指令用例、APK 成员/UUID 检查、
ZIP 对齐、v1/v2 签名及固定证书校验。状态仍为本地验证候选，等待真机测试。

## 真机测试

1. 覆盖安装公网候选，在深渊续战设置中给多关选择同一队，确认没有跨关重复拦截。
2. 连续通过至少 2–3 关，检查队伍、关卡推进、奖励和停止续战后的手动选队。
3. 测试仅部分角色重复、主位/副位交叉复用，以及已有进度时开启续战。
4. 完成第 30 关，核对最终奖励、进度重置和下一轮续战。
5. 检查普通狂热激战的跨关重复限制仍按原样生效。

## 构建方法

`build_apk.py --help` 列出全部参数。示例（在仓库根目录运行）：

```powershell
python client-patch/abyss-autostart/build_apk.py `
  --variant public `
  --out outputs/<新的输出目录>/StarPoint-CN-abyss-autostart-test.apk `
  --work work/<新的工作目录> `
  --java <java.exe> --javac <javac.exe> --ffdec <ffdec.jar> `
  --zipalign <zipalign.exe> --apksigner <apksigner.jar> `
  --keystore F:/StartPointCN/wf_full_patch/launcher.jks `
  --credential F:/codex/.codex/secrets/startpoint-apk-signing.credential.xml
```

构建器拒绝覆盖已有工作/输出目录，并验证输入仍是本补丁检查过的累计 SWF。
使用通用 APK 回封工具及已提交的 Java 方法比较工具，不运行历史补丁构建器。
每次构建分配新 UUID；APK 哈希因此不会与上表历史候选完全相同。
`sign_apk.ps1` 只在独立签名进程中加载 DPAPI 凭据，通过进程环境变量传给签名器，
退出时清空，不保存或输出明文密码。

当前源码基点为 `staging` / `dc440e622db544e9fc9be1f5fd9b05b43515c941`。
本任务仅新增本目录，原有未提交的入场条件资源工作保持原样。
本轮没有提交、推送、同步运行镜像或生成云端覆盖包；用户请求的是 APK 本地修改尝试。
