# Lens 0910 与深渊详情累计客户端

2026-09-10，用户明确要求接着截图中的“关卡详情”内网 APK 融合作者更新。用户选择：杰拉尔采用作者新版人物文案；夏白保留作者配置，不调整能力 6 中的队长条件效果。

本次为 Android 本地测试，未提升验收登记，未改 IPA。桌面 AIR 未运行。注册表中的 Sep 9 包仅用于核对祖先血统，不能替代用户选定的本次输入。

## 精确输入与输出

- 输入：`outputs/abyss-detail-ui-lan-test-20260910/StarPoint-CN-1.8.1-abyss-details-lan-test-20260910.apk`
- 输入 APK SHA-256：`eb1edaaae48027362970fb94b3a71da8fa3282ec47f6196a49490b56d9a4c61c`
- 输入 SWF：`355d4b5e1ff41f874c7f32f9ec45542a7cce8469c740497949c1dc0b3c6faa55`
- 输入 AIR UUID：`2bf1476e-2fe3-43b0-bba3-b199415c0128`
- 作者 V16 灰服 SWF SHA-256：`256ba66767653e9490377486a6115f1dd9ec435007221cae05adfcdd58b95f37`
- 输出：`outputs/lens0910-abyss-details-lan-test-20260910/StarPoint-CN-1.8.1-lens0910-abyss-details-lan-test.apk`
- 输出 APK SHA-256：`fd42a417dc7231c8dbc421e4839ceeefcfb027f8c83d8bc418baa427dd0b969d`
- 输出 SWF：`7e3f40fc17ac6fbbec52a0775c6a6357edd258874ed62d13d4ceb287d56d97d3`
- 新 AIR UUID：`2c7e1eae-872e-4da6-8c8a-42cbdb2360fe`
- 原始测试资源为 `1.4.112`，本会话提交时按用户要求合并为 `1.4.103 -> 1.4.104`；600 项资源与原测试终态一致，APK 不变，见 [会话存档](../../docs/development/SESSION-CHECKPOINT-20260910.md)。包名、应用版本、内网地址、原生 AIR 及固定签名保持输入身份。

## 移植范围

只插入四个原生方法的新增片段，主 ABC 索引仍为 286：

| 方法 | 方法体编号 | 内容 |
| --- | --- | --- |
| ConditionSlot.getOneSideTotalAbilityDamageResistance | 56844 | 敌人非敌对侧、可见条件槽按晒伤 1499901 减能力抗性，每层 15000，最多三层，沿用原生下限与其他伤害通道 |
| SquadManagerImpl.invokeActionSkill | 59846 | 夏白按真实 Fever 状态选择常态或 Fever 技能语音，保持原来的技能切换状态 |
| HudMemberStatus.update | 58882 | 夏白两组准备语音独立轮换；杰拉尔四条准备语音轮换，缺失资源保留回退 |
| BattleCharacterLogic.resolveFollowingPathCollection | 92450 | 在原主位、音效与准备音条件分支内预载五条额外语音 |

HUD 只追加三个 int 槽：`wtsReadyNormalNext`、`wtsReadyFeverNext`、`geraldReadyNext`。

作者的完整方法含有额外 Seris 语音选择及重编译差异。移植器仅复制已核对的片段，重定位常量与分支，不能整方法替换。这保留了我方接口命名空间、转换指令、全部旧分支与闭包布局。深渊详情、属性封锁独立 ABC 逐字节保持；续战复用、武器铁钢限制、关注按钮、本人资料路由、称号提示隐藏及既有 Lens 内容均保持。

## 验证与复现

`build_swf.py` 固定输入和作者身份，只追加常量。每个插入均可逆恢复完整旧指令和分支。`package_apk.py` 用独立 FFDec 比较全部 96422 个原方法体，只有上表四个不同，并仅导出四个目标类回查。最终 APK 回读验证 SWF、新 UUID、其余成员、ZIP 对齐、v1/v2 签名及固定证书。

`test_bytecode.py` 在小型解释器中执行最终 SWF 的真实插入字节码，以替身覆盖 624 种晒伤、语音路由、轮换与缺失资源情况。它没有启动 AIR，不能替代真机战斗、场景生命周期、声音播放或 GPU 验证。

```powershell
python -X utf8 -B client-patch/lens0910/build_swf.py --donor <审查确认的donor.swf> --work <新工作目录>
python -X utf8 -B client-patch/lens0910/test_bytecode.py --work <工作目录>
python -X utf8 -B client-patch/lens0910/package_apk.py --work <工作目录> --out <新输出目录>
```

本轮工作目录：`F:/codex/work/lens0910-merge-20260910/client`。签名沿用已有 DPAPI 流程，无明文凭据文件。最终生成前后均未启动或安装游戏。

配套资源、冲突处理、同步及回滚见 `tools/lens-integration/LENS0910-20260910.md`。
