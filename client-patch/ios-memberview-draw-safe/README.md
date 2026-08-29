# iOS MemberView.draw 稳定入口与已验证类型/布局保护

该补丁用于修复 iOS 战斗刷怪阶段的原生空函数指针崩溃。两份 IPS 均定位到
`MemberView` 构造函数中的 `draw()` 动态分发：返回地址为 `0x2B9C088`，最终执行地址为
零。

第三版不升级 AIR，也不删除现有 MOD 逻辑。它不再只检查 AIR 解析前的函数指针，而是
在首次创建 `MemberView` 时修复该方法的运行时实现槽：

1. 构造函数仍按原逻辑取得 `MemberView.draw` 的 `MethodEnv`；
2. 调用点不再进入可能失败的 AIR 延迟解析器，而是进入 16 字节槽位修复器；
3. 修复器把现有赛瑞斯 wrapper 写入该方法的 `MethodInfo + 0x50` 实现槽，并立即执行；
4. 后续每帧的通用 `Drawable.draw()` 会读取同一个已修复槽位，因此也不再依赖首次
   解析；
5. wrapper 完成 MOD 逻辑后仍跳到原版 `MemberView.draw` 主体。

因此赛瑞斯双形态、逐角色 render-scale、幻想魂珠异步贴图及其他五合一功能均保留。

第四版继续保留第三版的入口修复。第三版真机 IPS 已证明程序成功进入赛瑞斯 wrapper，
但 wrapper 内 `0x3D69318` 的另一层 AIR 动态调用仍从 `MethodInfo + 0x50` 读到零并执行
`BLR X8`。第四版将 wrapper 内五个未保护的同类调用统一改走共享跳板：

- `X8` 非零时以 `BR X8` 执行原实现，返回地址仍是原 wrapper 调用点的下一条指令；
- `X8` 为零时进入 wrapper 已有的公共清理路径，再跳到官方 `MemberView.draw`；
- 已经校验具体实现地址的 `0x3D69360` 调用保持不变；
- 不修改 AOT 方法表，不删除 wrapper，也不覆盖五合一 `PixelArtCharacterView` 跳板。

对第四版 IPS 的最初判断是 `characterTags.indexOf` ABI 不相容；官方代码审计随后确认
`Array.indexOf` 的寄存器 ABI 本身正确，真正原因是旧 wrapper 从错误的 `source+0x100`
取得了非 Array 对象，因而按错误对象的虚表进入了不相容实现。

第五版曾尝试用原生角色 ID 做身份门控，但新 IPS 已证明这条路径错误，测试包现已作废。
第五版把 `SquadMemberSource+0x48` 当成 metadata 指针；官方 AS3/P-code 与 iOS AOT
共同证明该字段实际是 `atk`。崩溃时 `atk=1624 (0x658)`，随后读取所谓
`metadata+0x78`，恰好得到日志中的故障地址 `0x6D0`。

第六版从第四版重新构建，完全移除第五版错误身份门控，同时保留第三版稳定入口、第四版
空实现保护和现有 MOD wrapper。新增保护只使用已经由官方 APK 与当前 iOS AOT 双重验证
的数据路径：

1. 在读取 `MemberImpl+0x120` 前，复用官方 `MemberView` 的
   `MemberPeek.getCharacterAnimation` 接口解析序列；
2. 从 `PoolObject+0x198` 的描述符表读取 `+0x804B8` 槽，并调用官方接口解析器
   `0x100A268C0`；
3. 解析出的实现必须精确等于 `MemberImpl.getCharacterAnimation`
   `0x102B69AF8`，否则清理后回官方 `MemberView.draw`；
4. 通过具体类型证明后，才读取 `MemberImpl.source+0x120`；
5. `characterTags` 改为已验证的 `source+0xC8`，保留官方 `Array.indexOf` ABI 和
   `ModDualForm` 标签门控；
6. 特殊像素动画路径使用已验证的 `mainCharacterStringId+0xB0`；普通路径继续使用已
   验证的 `pixelArtAnimationPath+0xA0`。

因此第六版没有删除赛瑞斯双形态适配，也没有把功能缩成硬编码角色 ID。只有对象无法证明
为目标 `MemberImpl` 具体布局时，本帧才安全回退到官方绘制。

第一版只在调用解析器前判断 `X8` 是否为空。新的 IPS 证明解析器入口可能非空、但解析
过程仍会落到零地址，所以第一版仅保留作问题演进记录。

第二版实现了运行时槽位修复，但错误地让 16 字节修复器与五合一
`PixelArtCharacterView` 绘制跳板在 `0x3D694D0` 重叠，导致点击幻想魂珠时执行
`BR X10` 并跳到地址 `1`。第二版测试包已经作废。第三版从原始最终 IPA 重新构建，
完整保留 `0x3D694D0` 开始的五合一跳板，并把修复器迁移到幻想魂珠补丁自身已牺牲的
debug sound-test cave 未使用尾部 `0x30199C0`。

## 构建已验收 IPA

输入必须是当前哈希锁定的最终未签名 IPA：

- 文件：`iOS-1.8.4-kulo-private-final-fantasy-soul-unsigned.ipa`
- SHA-256：`FCBA08D30702BB941D412CA1D650D0573481873489C4F94A38682D46E279EC88`

```powershell
python client-patch/ios-memberview-draw-safe/patch_ios_memberview_draw_verified_layout_v6.py `
  --ipa F:\codex\ios-artifacts\iOS-1.8.4-kulo-private-final-fantasy-soul-unsigned.ipa `
  --out F:\codex\ios-artifacts\iOS-1.8.4-kulo-private-final-fantasy-soul-memberview-verified-layout-v6-test-unsigned.ipa
```

脚本会从哈希锁定的原最终 IPA 重建并复验第四版全部输入、布局和调用保护契约，再应用
第六版类型门控与两个字段偏移修正。它会验证官方解析器 `BL`、所有 `CBZ`/条件失败
分支、精确 AOT 实现比较、wrapper 回调目标以及两个 `LDR` 的寄存器和偏移。输出仍是
未签名 IPA，必须使用原有方式合法签名后安装。虽然沿用的成品文件名包含 `test`，该
精确负载已经完成用户确认的 iOS 真机验收。

构建器会验证类型门控不得与现有幻想魂珠 wrapper、第三版槽位修复器、第四版共享跳板、
五合一绘制跳板、官方 `draw` 或 AOT 表重叠。相对第四版，wrapper 本体只允许修改类型
门控调用、`characterTags` 字段和 `mainCharacterStringId` 字段三条指令。

第六版验收包的 `CFBundleVersion` 为 `1.8.46`，Mach-O UUID 为
`064f8e49-fdd9-532f-8445-439ab9f71e6c`，未签名 IPA SHA-256 为
`C3E22D1E5DB5C45B6864D4125A86EA194134FF3032AF1A060F3B40F711F5848A`。这三个标记共同
锁定已验收负载；此前 IPS 中的构建号 `1.8.4` 和 UUID `4c4c…` 属于旧基线，不能视为
第六版实际运行。如果再次闪退，新 IPS 必须先核对构建号和 UUID。

## 回归重点

- 使用原闪退用户的相同队伍进入幻想连战第 13 层；
- 使用此前在幻想连战第 1 关加载时闪退的队伍复测；
- 冷启动直进及连续游玩 45～60 分钟后进入都要测试；
- 普通主线、赛瑞斯双形态、基诺维显示比例和幻想魂珠界面都要回归；
- 如果仍然闪退，保留新的 IPS、`info.json` 和 `replay.log`，先核对构建号和 UUID，
  再核对是否进入类型门控、赛瑞斯专用后半段或新的独立崩溃链。

该补丁只处理已定位的 `MemberView.draw` 分发链、错误对象布局访问和 wrapper 内已确认
的空实现调用，不掩盖其他地址的崩溃。第六版已完成用户确认的 iOS 真机验收；构建器
只能证明重新生成的字节、具体类型/字段数据路径和控制流与该验收负载一致。任何代码或
成品哈希变化都必须重新回归，不能自动继承本次验收结论。回滚时重新安装原最终 IPA 即可。
