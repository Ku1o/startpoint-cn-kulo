# iOS 增量 AOT 端口：字段与槽偏移安全

这份记录来自 2026-10-04 救援铃铛 iOS 缓存清理进入副本 F1009 的排查与修复，配合此前 HUD（实例字段）和作者装备（类/实例 trait）批次的经验。只约束 iOS IPA/SWF/ABC/AOT 增量端口；Android 解释执行按名字解析，不适用同样的固定槽约束。

## 硬性规则

- **不要给既有类新增字段（slot trait）。** AIR arm64 按类型排布槽位：32 位标量（`Boolean`/`int`/`uint`，以及数值）排在引用字段之前。给既有类追加一个 `Boolean` 就会整体移动该类的引用槽。类对象静态槽（`public/private static var/const`）和实例字段同样受此影响。
- 槽偏移在 AOT 编译期就烘焙进已链接的原生代码。只追加新方法不会重编译既有方法，因此既有访问器仍按旧偏移读写：偏移处为 0 时抛 `TypeError #1009`，指向其它字段时静默读错数据。
- 新增运行状态的默认做法是放进**新类**（用 `ClassImporter.merge()` 导入类 + 脚本 + ctor/cinit），保持既有类的 class/instance trait 列表逐字节不变。给既有类追加**方法** trait 历史上是安全的（`cn.mod::AuthorState` 曾累计追加 60+ 方法并通过实机验收）。
- 确需给既有类加字段时，必须重编译所有绑定该类槽的既有方法（`method_redirects`）并做偏移门槛；这通常比搬状态到新类更难枚举、更难验证。

## 真实案例（2026-10-04，`cn.mod::AuthorState`）

- 候选把 `periodicStarted:Boolean`、`periodicTimer:Timer` 追加到已有 `gauge`/`damage`/`context` 的 `cn.mod::AuthorState`，用于 10 分钟缓存清理。
- 同一 AIR AOT 编译器 A/B 对照：载体全 ABC 编译出 `getGauge`/`setGauge` 读 `+0x30`、`getDamage`/`setDamage` 读 `+0x38`；10-04 全 ABC 编译出 `0x38`/`0x40`，新 Boolean 占 `0x30`。
- 链接器只追加了 5 个新方法（`method_redirects` 为空），四个既有访问器（101323–101326）仍是载体代码。
- 进入副本时 `MemberAbilityTotalizerImpl/get wfGaugeRules()` → `AuthorState.getGauge()` 从类对象 `+0x30` 取 `gauge` 字典，实际得到 `periodicStarted`（默认 0）→ 空值分支跳运行时 helper（`0x10b74a9f0 → 0x100a2676c`，`mov w1,#0x3f1`）抛 `TypeError #1009`。公网日志 35 条 iOS 记录同一栈顶，同窗口 Android 无此签名。
- 修复：新增 `cn.mod::CacheCleanupState` 承载两个字段与 5 个方法，`cn.mod::AuthorState` 与载体逐字节一致；AOT 方法表 101458 → 101466，仅新增 8 个方法。
- 参考实现：`client-patch/orochi-rescue-bell-ios/{prepare,compile,verify}_port.py`；记录见 `client-patch/IOS-STATIC-SLOT-F1009-20261004.md`。

## 端口管线必备门槛

1. **prepare**：既有 class/instance/body 字节不变、池前缀不变，并单独断言目标旧类与载体快照一致；新方法不得带 activation trait（当前链接器只支持无 activation 的新方法）。
2. **compile**：拒绝本批新方法的 `Verify error`；对绑定旧类槽的既有访问器做偏移门槛——载体内冻结代码与本次重编译结果的槽立即数必须一致（`compile_port.py` 的 `accessor_slot_guard`）。
3. **verify**：独立回读旧类快照一致、新类结构（槽与方法名）、AOT 表项、签名布局与变更成员范围；只用构建报告自身不足以说明问题。
4. 新类的桥接方法号会随导入顺序变化，必须同步写进 `port.json` 的 `native_start_wrapper.bridge_method`。

## 排查手法

- 从崩溃栈顶方法反汇编其 AOT 入口，看它从 `x0`（类对象或实例）读取的固定偏移；再用同一 AOT 编译器分别编译载体 ABC 与候选 ABC，对比同名方法的偏移，即可判定是否为布局位移。
- 错误码可用运行时 helper 交叉确认：`0x100a2676c` 处的 `mov w1,#0x3f1` 即 `Error #1009`；helper 常以 trampoline（`adrp/add/br`）形式出现在新增段里。
- 判据优先级：先确认“既有类 trait 是否变化”和“既有方法是否被重编译”，再看运行值；不要只给报错方法加空值保护，那会掩盖槽位错位。
