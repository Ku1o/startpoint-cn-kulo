# 深渊续战阵容复用：Android Lens 累计成品

2026-09-09，从 Lens v3 公网和内网原成品制作，两版均已签名。用户随后要求“ios和安卓都验收并提交修改内容至github”，本次完成离线验收并更新 [当前基线登记](../android-accepted.json)。
验收范围见 [双端记录](../ACCEPTANCE-ABYSS-AUTOSTART-20260909.md)，没有将该指令记为已完成真机测试。
此前旧标题包候选见 [失败记录](./HISTORY-REJECTED-20260909.md)，禁止继续交付或作为输入。

## 当前离线验收成品

| 环境 | APK（相对仓库根目录） | SHA-256 |
| --- | --- | --- |
| 内网 | `outputs/abyss-autostart-lens-lan-test-20260909/StarPoint-CN-1.8.1-abyss-autostart-lens-lan-test-20260909.apk` | `3dd568ff64c3c099cf60d99985d706f1704a1c5666f945f8b548d8eaefa3d588` |
| 公网 | `outputs/abyss-autostart-lens-public-test-20260909/StarPoint-CN-1.8.1-abyss-autostart-lens-public-test-20260909.apk` | `c868534b575348dde825fcd4c88c156157174fd4444724f1141fd9aa95e32a2d` |

每份成品目录附 `verification-report.json`、`SHA256.txt` 和 `使用说明.md`。
签名证书 SHA-256 为 `569D19A3578D4CBA16E3D6E7AD8CCAB4FA667EFC758DEEF6C9BE3ADB99919894`；
包名、应用版本及对应服务地址沿用 Lens v3，两个 SWF 各分配全新 AIR UUID。
公网输入 APK SHA-256 `8e5999e2689788159362acc81cd4bcd89182966fce9af7800d085ff89dccb41b`；
内网输入 APK SHA-256 `966facaa01de0fc9952fe648f4ffef0fd99a53fad73deac7f652d6cf6f9fbc04`。

## 修改行为

服务端已有 `unlock_played_parties=true`，普通深渊逐关战斗可复用阵容。
续战设置另有预设队伍重复检查；本次只修改
`RushEventAutoStartQuestGroup.getDuplicatedCharacterIdsForEachQuest`（`284:24599`）：

- `event.id == 700099`：返回长度为 `folder.getQuests().length` 的数组，每关各有独立空数组，解除跨关重复拦截。
- 其他活动：进入原方法的完整指令与跳转图。
- 保留逐关选队界面、续战进度及其他开战条件。

方法体直接导入 P-code，不对完整类重编译。新增分支用寄存器 20–22，原方法使用的寄存器不变。
复核证明该目标方法在 Lens v3 中与旧父版本一致；重做的是基线选择及累计内容保护。

## 防回退及验证

构建器保留精确 Lens v3 输入保护。当前登记已升级为续战成品，默认入口会拒绝重复套用；仅复现本步骤时通过 `--reproduce-lens-v3` 读取 [历史 Lens v3 登记](../accepted-history/android-lens-v3-20260909.json)，仍核对实际 APK 与 SWF 哈希。新任务从当前累计成品重新审计目标，不绕过断言。
其后检查目标方法原始指令哈希、92,561 个主 ABC 方法体及基诺维 422 解析方法哈希。
真实旧包回归用例已证明，两份发生基线回退的续战 APK 会被拒绝。

两版均完成：

- FFDec 比较全部 96,404 个方法体，只有 `284:24599` 改变；包括 7 个 Lens 新增方法在内的其他方法保持。
- 独立 ABC 解析器核对既有常量池前缀、类/脚本/方法元数据、非目标异常表和 activation 元数据、非主 ABC 标签。
- `AbilityValues.parseAt109` 保持 Lens v3 的 `422` / `DashParameter` 解析，代码 SHA-256 为
  `4a035a6b48b89a8a1b3f60eb371c49dfcf8095b1fe129e7bff46730e3a81b065`。
  724、稻穗 PF、五重地图/手动 Auto 锁、5900101 铁钢限制，以及关注/本人资料/标题等非目标方法保持。
- 最终 P-code 与预期一致，非深渊原分支及目标类其他内容不变；AS 回读完整。
- 对回读指令执行 7 个用例：深渊 0/1/30/60 关，以及幻想 700098、普通 700007、复刻 700017。
  检查数组长度、每关数组独立、循环退出和原逻辑回退；这不是 AIR/真机测试。
- 签名后 APK 内嵌 SWF、全新 AIR UUID、其他成员、manifest 包身份、ZIP 对齐、v1/v2 签名及固定证书。

真实成品基线回归：

```powershell
python -X utf8 -m unittest discover -s client-patch/abyss-autostart -p test_lineage.py -v
```

此测试需要登记中的本地当前/失败 APK；输入不存在会报错，不静默跳过。
三项测试覆盖历史 Lens v3、当前续战累计版与失败版，各含公网/内网共六份实际成品；确认历史输入可以显式复现、当前成品不会重复打补丁、失败输入被拒绝。

## 构建入口

`build_apk.py --help` 列出参数。示例（在仓库根目录运行）：

```powershell
python client-patch/abyss-autostart/build_apk.py `
  --variant lan --reproduce-lens-v3 `
  --out outputs/<全新目录>/StarPoint-CN-abyss-autostart-lens-test.apk `
  --work work/<全新工作目录> `
  --java <java.exe> --javac <javac.exe> --ffdec <ffdec.jar> `
  --zipalign <zipalign.exe> --apksigner <apksigner.jar> `
  --keystore F:/StartPointCN/wf_full_patch/launcher.jks `
  --credential F:/codex/.codex/secrets/startpoint-apk-signing.credential.xml
```

公网用 `--variant public`，内网地址从忽略的本机配置核对，不写死在源码。
构建器拒绝复用已有输出/工作目录，每次生成新 UUID，因此重建后的 APK 哈希会变化。
签名只在独立进程内从 DPAPI 凭据导入密码，经进程环境传入签名器，finally 清空。

本次工作证据位于 `work/abyss-autostart-lens-rebase-20260909/`、
`work/abyss-autostart-lens-build-lan-20260909/` 和 `work/abyss-autostart-lens-build-public-20260909/`。
没有遗留 FFDec/Java 子进程。源码基点为 `staging / 2e7ab5a06fbd941fec6d799ebd51e1abd67bf441`。
本目录只归档客户端方法、基线保护与验收身份；二进制保留原交付路径。服务端无需配套修改，本次不涉及运行镜像同步或云服整合包。

## 真机回归

先点击基诺维角色详情，再为深渊连续多关设置同一队，检查续战启动、推进 2–3 关及停止后手动选队。
继续测试主副位交叉复用、已有进度时启动、整轮结算与新一轮，以及普通狂热激战重复限制。
