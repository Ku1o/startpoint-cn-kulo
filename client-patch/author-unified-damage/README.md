# Android 作者伤害规则统一

此候选从 2026-09-24 已验收的公网 SET 编辑 C8601 APK 出发，完成作者 1043 内容移植后，移除旧通用伤害路径协议。新角色按“原生触发条件 → 瞬时能力 629 → ActionDSL 指定伤害类型”配置，普通攻击节点只走作者分类规则。

## 行为与保留范围

- 删除 `MemberImpl/applyInstantAbility` 的旧上下文装饰、`ActionEvaluator/addImpactToSubject` 的旧分类和 `NormalAttackCalculator/calculate` 的旧结果钩子。输出不含 `GenericDamage`、`spGenericDamage` 或旧 `battle/cnmod/generic_damage/v1/` 前缀。
- 原生 629、作者 423/424、充能来源区分、语音移植以及已验收累计功能保留。相对作者移植阶段，仅三个主 ABC 方法体发生删除；其余 92,564 个主 ABC 方法体、类布局及除旧 helper 外的其他 ABC 保持一致。
- 旧 helper ABC 在原位置替换为 `cn.mod.InahoAbilityVisuals`。三个既有视觉调用继续处理稻穗弹道、命中特效和六项必要预载，不修改伤害类型、攻击归属或计数器。
- 攻击力按脚本原生引用选择。需要队长攻击力时应显式配置，不自动改取队长；需要额外“发动能力攻击”通知时也应按角色机制实现。
- 不新增存档字段、正式角色 ID、数据库结构或资源版本；没有存档迁移要求。APK 沿用准入号 `android-181-independent-party-20260923`，仅连接 `<LAN_HOST>:8001`。

## 角色配置入口

ActionDSL 根节点的作者标记：`101` 技能、`102` 能力、`104` 直击、`131/132/133` 分别为 PF1/PF2/PF3。路径是普通资源路径，不再编码伤害类型。显式脚本分类优先于环境转换；PF 伤害分类不等于发动一次原生强化弹射动作。

已实测的例子：原生触发条件 `20`（自身直击命中），阈值 `1`、CT `300` 帧、瞬时能力 `629`；脚本用 `FindNearSubjects` 选择敌人，`CreateNormalAttack` 引用 `12`，根标记 `131/132/133`。同一套动作从非队长稻穗发动，分别结算三个等级的 PF 伤害。示例临时脚本和能力表只用于设备验证，未成为正式角色内容。

## 验证

扫描 1.4.117 启用链最终覆盖的 6,036 个 common 文件、21,144 个 orderedmap、237,311 个叶子，包含 zlib 与 raw-deflate 脚本解压，未发现旧路径依赖。移除三个钩子后重新插回可逐字节还原原方法。37 项作者机制和语音离线检查通过。

MuMu 实例 2 的单人木桩验证记录了 247 次发动者物理直击：80 次符合 300 帧冷却条件，167 次被冷却阻止；每个符合条件的命中准确调用三个脚本，各产生一笔 PF1/PF2/PF3 伤害，共 240 笔，无额外或递归调用。所有触发帧都等于冷却结束后的首个有效直击帧。

PF 伤害使用发动者攻击力 827，队长攻击力为 744；新鲜统计样本读取 PF 加成 400% 和等级追加 10%/20%/30%，未读入技能、直击、能力伤害加成。物理直击自身保持原分类；测试期间没有实际发动原生 PF。逐次统计来自仅作观察的诊断派生包，交付 APK 不包含诊断模块。

资源验证使用现有 8001 服务、正常 active ZIP 和 manifest。临时 1.4.118 边在验证后移除，manifest 精确恢复 1.4.117，模拟器恢复三张原表并移除三个临时脚本，无还原增量。设备结论仅覆盖 Android 单人场景；未验证 iOS、多人和全部角色组合。

交付 APK 另经实际覆盖安装、登录和原资源木桩回归，稻穗能力伤害、月相状态与战斗特效正常显示，未出现 C8016、验证错误或崩溃。测试后的模拟器恢复测试前实际 APK 和已备份偏好，不把此候选自动登记为已验收基线。

## 构建与产物身份

`build_swf.py` 可接受已复现的作者移植 SWF，或先通过 `--accepted` 与 `--donor` 生成该阶段。所有输入有精确哈希门禁，不接受更早内网包代替已验收公网基线。

```powershell
python -X utf8 -B client-patch/author-unified-damage/build_swf.py --accepted <accepted-public.swf> --donor <reviewed-donor.swf> --source <new-author-port.swf> --output <new-unified-public.swf> --work <helper-work>
$env:STARPOINT_LAN_HOST='<LAN_HOST>'
python -X utf8 -B client-patch/author-unified-damage/package_android.py --swf <new-unified-public.swf> --work <apk-work> --out <delivery-directory>
```

| 载荷 | SHA-256 |
| --- | --- |
| 已验收公网 APK | `f24f469c1be0cb3d2d16520a739ace52b58055ce65621f5243404026beba6066` |
| 作者移植 SWF | `fce5aabaea98ffa84381de91e936a5adfd5991e955ed0c62fb804b7551c5a10c` |
| 统一规则公网端点 SWF | `caea4de3f02591211dfb4359f37281b60696c6433719ef6383fbefb6844e4091` |
| 内网交付 SWF | `2e806d30ad3e2f9b71f63085e03ca3d41886bb81a7b8e01a19133eaea3828ed2` |
| 内网交付 APK | `de89cf79f4d101eae28a95175f490e2ff79040dc61ab374064fb08d60c014b09` |

交付 AIR UUID 为 `eac4a37d-aeaa-4d43-8594-fe504a495a75`；包名 `com.leiting.wf`、版本 1.8.1/1008001 和原签名证书保留。包体回读、DEX 身份、4,172 个其他成员、v1/v2 签名和 ZIP 对齐已核验。accepted registry 不变，本候选等待后续使用验收。
