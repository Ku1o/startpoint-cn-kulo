# SP-CLIENT-002 · 客户端稳定性、方法移植与性能诊断

适用：StarPoint CN 的编队换人锁输入、加载/黑屏回归、方法级 ABC 补丁、Android/iOS AOT 移植、准入轮换及性能采用决策。状态：**已验证**（下列限定静态、受控 AIR、离线封包与历史 MuMu 样本）；手机/GPU、长期/全玩法、公网和 iOS 运行覆盖不能由这些证据推定。

## 输入与当前基线从哪里取

- 当前输入、平台、LAN/public 变体及验收层级从对应 `client-patch/AGENTS.md`、[Android 基线](../../../../client-patch/ANDROID-BASELINE.md)、[android-accepted.json](../../../../client-patch/android-accepted.json)和 iOS accepted registry 取；本专题不重复维护易漂移的版本号、成品摘要或准入号。`accepted_offline`、本地台账、用户批准基线、设备实测、部署是不同状态；某平台没有同功能 LAN 成品时，不拿旧 LAN 当同功能输入。
- 开发先查原始国服 1.8.1 资料（历史本地记录）的 class-index/reference-info，按需读原实现及直接调用者、消费者、生命周期，再对照实际登记 APK/SWF 的对应方法和累计补丁。原始源码没有后加 helper，文件日期不代表当前实现，不覆盖累计修复；原 ZIP/提取副本仅本地私有。
- 盘点后续已采用改动或查累计阅读源码，先由源码阅读入口 CURRENT.json（历史本地记录）定位固定快照，再查分平台采用清单、CLASS-INDEX、来源 manifest 和 iOS 原生映射。原版、当前载荷反编译、已有手写源稿及配方候选分开标记；快照不会随 registry 自动更新，也不替代当前输入选择。iOS full ABC 仍可保留返回桩/旧声明，native-only、追加 hook 与运行时槽位改动不能只靠 AS3 导出覆盖。完整 QName 和方法语境优先于短类名；诊断脚本可帮助定位，但不能据此恢复诊断行为。实际方法表覆盖与原作者工程缺失另记，不把阅读参考当完整可重编工程。方法与限定验证见当前整理说明（历史本地记录）。
- 客户端构建、验包、地址/准入及平台差异按客户端细则（历史本地记录）、任务效率细则（历史本地记录）及[client-release Skill](../client-release-workflow.md)执行。已有证据的输入和验证条件未变时复用；新输入或语义变化补受影响检查，不把“未重验”写成永久豁免。
- 固定 head 已整合不等于当前远端 head 已覆盖；收尾发现新头且本地对象缺失时补取或 compare，不能沿用旧祖先回执。同资源版本不证明内容相同；同版本组件按 manifest 序号路由，已缓存版本不保证自动补取同号新组件。
- 后补批准的基线文件须接回同批发布待办，区分本地台账和可提交登记，不因已是脏文件永久隔离；仍按现有提交/推送权限和明确文件范围处理。历史纠错证据：当前头与登记（历史本地记录）、收尾结果（历史本地记录）。

## 方法级补丁：身份、语义、链接、封包

用已确认输入与最终有效方法差异组织补丁，固定捐赠 APK/提取树身份，拒绝重复套补丁。方法按标签/QName/代码指纹定位；SWF raw tag、DoABC ordinal、method body 编号互不替代，历史 `main_abc_index` 不直接复用。本项目 `compare_clients.View.by_label` 保存的是 body 数组下标，取得 AOT/method_info 方法号须再取 `abc.bodies[body_index][0]`，不能将前者直接写入方法表配方。QName 的 `::` 与 DoABC 标签的点号先规范化；方法比较数与总方法体数分开记录。

静态栈检查和重编译模型通过后，仍须执行实际生产方法及完整 helper ABC 的独立链接：

- AVM2 循环反跳落点需要真实 opcode `0x09`，汇编符号 label 只定义偏移；静态绿仍可能在 ADL 报 VerifyError1021。检查正常 CFG、分支和 switch，以及取消/空结果/多次进入等 active 路径；getter 的初始 null 与实际 keys 赋值靠邻接指令和源 SHA 区分，不取第一个 setlocal。
- `pushstring 0` 曾漏过静态检查而在真实 AVM2 报1032，空串使用有效非零常量。`NEED_ACTIVATION`/`NEED_ARGUMENTS` 随原 MethodInfo 保留；typed Delay 的旧 coerce 与新 RequestTimer 同步更新，覆盖真实取消路径。
- 测试编译显式 `-compiler.float=false` 生成工具支持的 ABC46，不手动降生产 ABC 版本。mxmlc 可能将入口及辅助类合入同一 DoABC，替整 ABC 前检查 traits/类清单，不能删主入口；必要时动态定位并独立插入原 helper。
- FFDec exit0 可能输出 OOM 伪源码，要检查导出内容；已有案例批量 1 GB 失败后定向 3 GB 导出有效。工具受策略阻止未执行时，静态替代不能冒充运行通过。
- `File.applicationDirectory.resolvePath` 可能指向受保护 `app:/` 并报 fileWriteResource；用 `new File(File.applicationDirectory.nativePath).resolvePath(...)` 写任务目录。先用已知正常夹具确认入口，无结果/空 trace 不能直接归因环境或链接。

离线封包比较目标方法、非目标方法内容、类/traits 布局、原成员字节、签名、对齐和 AIR 身份；只换身份时应有精确逆变换证明。工具退出0、签名通过或 APK 生成均不等于游戏、设备/GPU通过。代表证据：换人两方法（历史本地记录）、综合实际方法（历史本地记录）、实际 helper 纠错（历史本地记录）、加载审计（历史本地记录）。

- F1069 先读取实际崩溃栈，不能由错误号直接归因资源或存档。CN crash 记录可能在 report.text 的JSON内再嵌info JSON；只抽取代码与栈，避免输出设备或账号标识。活动类不能从类名推断后统一读id：ScoreAttack/SoloTimeAttack使用eventId，其余族与继承变体可通过原生getEventId返回的EventIdKind取得真实身份。对应测试须使用密封实例、真实槽/继承关系和实际生产方法体，覆盖所有挂接接收者；普通动态object和策略键矩阵不能代替原生对象调用。保留旧生产helper的1069负例，与新包原生getter/base调用链正例及成品哈希绑定。见活动标识修复（历史本地记录）。
- **C8601先区分空加载、缺键和无效查找键。** “资源损坏”是通用提示。教程前常驻组只加载bundled/iosBundled路径，普通表可被创建为空map；因此CDN中有分类9，运行时仍可能缺9。新挂接逻辑不能先读普通分类再决定是否接管教程，应在读表前将真实教程接收者交回原判断。用当前生产helper、原生三条period入口及密封教程对象保留旧代码负例和原时间规则正例；受控空表替身不证明手机当时的具体阶段。方法入口：[C8601补丁与定向验证](../../../../client-patch/startup-equipment-c8601/README.md)。
- **扩展编队枚举要同时检查下游显示消费者。** 独立分类5/6/7除SET标题，还会进入装备占用说明及其排序。旧说明switch只覆盖1–4会把null传给UiString表；只有文本显示值/局部优先级可归一到Rush，真实保存类别、占用保护和未知类别错误须保留。对照当前包真实方法覆盖三个新类别、原有类别和未知值，不能只测已修过的SET入口。入口同上。
- **iOS累计方法与跳表核验以真实范围为准。** 早期追加helper只存在active表，不能机械要求每个目标都有legacy表项；按原始MAIN_METHOD_COUNT推导并独立回读。ARM64的SUB等W寄存器写入同样清零高32位，带独立求和寄存器及无关指令调度的CMP/HI/LDRSW/ADD/BR仍须证明同一u32选择值、边界和表归属，不能跳过检查。实际对象正例与改界限、条件、写宽、求和寄存器和表目标的负例应一起保留。源码路径外部化后重新核对共享页算法的实际源码身份，不沿用迁移前文件哈希。入口同上，iOS配方/独立成品回读不等于真机执行。
- 无限期按真实消费者逐类保留 Option 合同：原生允许 None 时使用其无限分支；要求 Some 的资源预加载或构造器不能直接改 None。数值上界与无限期文案分开，沿实际 ABC 的 getter 引用闭合普通逻辑、公共 dateConfig、独立日期 formatter 和剩余时间标签，不能以公共构造器 sanitizer 覆盖全部独立面板。新旧负/正例应执行 GachaRepository→GachaLogic→资源容器、活动原生构造器及独立日期方法；测试只导入构造器前几条 prologue 时，明确前缀精确且整构造器未执行，不写成完整页面运行。见隔离修复与验证边界（历史本地记录）。

- **已验证：跨动作时间回退。** C2044表示原生TimeRange按秒处理后的结束早于传入开始；先读真实栈，不按错误号猜资源。逐动作接管后，未接管的exchange/browse不能再组合已按enter改写的起点和原截止。最窄修复只替换该原生回退表达式的起点，保留受管动作gate、结束getter虚派发及原坏区间守卫；用真实密封继承接收者覆盖活动族、campaign起点和Ranking领奖终点，保留旧包负例与候选正例。入口为隔离树 `client-patch/content-operations/build_exchange_repair.py` 与原生回归证据（历史本地记录）。
- **已验证：原有日期控件的像素范围。** 原文本框width/height或autoscale检查不证明文字落在背景内。先用真实Flatomo原生goto核对帧索引（1基），再连同pivot/transform、有效背景和最终嵌入字体核实际有alpha字像素；短文案可能不触发宽度缩小而垂直出框。控件限定地居中/收紧原有field，不扩大父容器或全局改其它日期栏；Absent/未知内容保留原生行为。最终helper输出必须接到像素输入并逐适用资源覆盖，区别原生方法导入、参考算法栅格与完整页面/GPU/设备证据；相关夹具与边界见Pass布局复现（历史本地记录）。

## Android、x86 与 iOS AOT 移植

Android 从当前登记基线按差异追加 x86 原生/ANE，保留 ARM、地址/准入和累计逻辑，不能整包重放已撤回 R4。跨平台提取树哈希须固定路径排序；历史工具按路径分段 casefold，避免 WindowsPath/POSIXPath 遍历差异。源码工具连同最小解析依赖闭包、客观来源与可复现私有输入入口交付，清理旧固定路径但保留身份/哈希拒绝条件。

iOS 以 QName、规范化参数名和可选常量映射，保留旧字段、flags、activation，仅追加必要类/closure。旧 full ABC 的 script 可能仅为 return stub：direct replace 需在独立 compiler-only 输入恢复 owner 的 newclass 上下文，用目标符号全覆盖门控；编译 exit0 不证明目标函数已生成，compiler 上下文不得混入 runtime。实际回读原生入口、共享别名、重定位和签名/ldid 边界；方法表/ABI 兼容、离线封包通过不证明已重签、安装或运行。

Android新旧差分只能筛入口，不能证明iOS依赖完整：整方法导入可能带入Android基底已存在、donor未变化、iOS却缺失的callee。按实际receiver类型、完整QName和继承链闭合所导入方法的必需调用；补真实body及AOT，不补空声明或默认恒零。无子类的叶类可以在全旧槽保持条件下尾追加，若既有native仍按运行时属性查找，可保留caller原字节。编译输入使用旧AOT返回桩时，还须核新callee的实际原生调用/参数与返回寄存器，避免把签名或零警告当成真实求值。SDK声明可含versioned Multiname和非零early disp ID，应按真实binding规则及当前ABI解码，不能将新helper的零ID约束扩到旧SDK/应用类；先用实际SDK声明做小预检，再做整IPA回读。固定修复、真实方法负正例及实际sum ABI证据见战斗缺失callee修复（历史本地记录），设备仍另验。

既有类追加实例方法时，旧 trait 前缀不变仍可能移动后代的虚方法槽。按实际完整继承树比较每个旧绑定的槽号、MID 和参数约定，并核实际 native runtime ABC；叶类尾追加只有在全部旧槽不变且无受影响后代时才可保留。需要迁出时，使用独立静态 helper、显式接收对象，并确认后代没有覆盖原绑定；同时重编按旧候选布局生成的累计调用者，不能只修崩溃点或直接引用 helper 的方法。无法可靠收窄调用闭包时，可在证明每个源体均非 AOT 占位后重编当前累计函数集；旧 wrapper 只定向重绑其内部目标。检查器与已验证的 ABC/AOT/实际 IPA 范围见继承派发修复配方（历史本地记录），设备结果另验。

固定历史配方不得读取可变 accepted 作为历史输入；现行开发则按当前登记更新差异计划。参考[Android 源码链](../../../../client-patch/pr43-port/README.md)、[稀疏输入准备](../../../../client-patch/pr43-port/prepare_inputs.py)、[iOS 配方](../../../../client-patch/pr43-ios/README.md)。代表证据：移植离线结果（历史本地记录）、Android 独立发布（历史本地记录）、iOS 复现发布（历史本地记录）。历史本地主线混有未授权 server/CDN 时，独立发布从实际 origin/main 组织客户端明确范围，再接回本地主线；不能因此推整个本地 main。

累计源码恢复的限定方法（**已验证：固定输入的源码、原生字节、静态调用对应及隔离 AIR；不含 iOS 设备运行**）：

- 从当前 Mach-O 的 AOTInfo 取方法表，按 segment 映射 VA/文件偏移，回读当前槽、分支及必要 veneer；历史 helper 字节仍在不表示当前入口仍采用它。固定地址 guard 与后续槽替换需要分别记录；不能由未见直接调用断言所有虚调用不可达。稀疏导出须与实际完整字节区间对应，并拒绝同一导出中重复地址。
- 编译回执同时绑定当前源文件路径、源码摘要、退出状态和产物摘要，避免旧同名产物混过；仅供编译的 API 替身另验且不进入运行载荷。比较只消除明确的 nop/label，并同步重映射分支、switch、异常边界；保留原始指令、flags、activation、堆栈及寄存器差异。局部窗口外一致不升级为整方法一致，可读恢复稿不升级为原作者源稿。 比较namespace(kind,URI)及namespace-set时，实际引用必须无身份歧义或有显式一一映射，不能仅按文字合并private身份。重试使用独立attempt目录保留日志/命令/退出；已覆盖的原始失败日志须明确缺口，不能伪称完整历史记录。
- 对有保留 compiler-only 输入的单函数，核对输入/依赖身份、唯一目标符号、完整函数长度及每处重定位，再比较当前实际函数字节。LIEF 的 section/symbol 等对象依赖 owning Binary 生命周期，循环筛选时连同 Binary 保留；先核 raw 长度与声明长度相等，再解释解析异常。独立函数字节复现仍不证明完整工程或设备行为。工具和实例见累计源码续作（历史本地记录）。
- 实例方法转静态 helper 的局部槽重映射同时处理 generic 与 short `getlocal/setlocal_0..3`、kill 和增减局部指令，并保留原始初始化序言、分支、switch 和异常边界。移至独立类时，static 方法首个局部 scope 先放 helper class，再保留原 receiver 的 scope；相应调整 `getscopeobject`、max scope 与捕获闭包，不能仅搬原 receiver（真实 AIR 负例为 1058）。新类不得遮蔽原词法绑定，闭包可追加克隆并保留原 activation 身份，原 orphan 保留范围及不可达证据单列。短指令变长会移动异常表的字节边界，须按指令映射重定位；不支持的闭包异常表先拒绝，不能直接清空。只映射 generic setlocal 会留下覆盖参数的短写入；按实际方法逐处对照源/目标槽，不只检查局部总数。对当前方法与只改对应 store 的隔离对照分别执行，覆盖空集合和过滤开关；修复候选再由真实 donor 经生产转换器正向生成，并与对照、保存 SWF 回读和冻结的无关结构绑定。当前反例见装备核实（历史本地记录），实际生成器与候选证据见隔离修复（历史本地记录）及上述继承派发修复配方。
- 原生调用桥不能仅修正分支到完整序言：先核 receiver、强类型指针与 Object Atom、MethodEnv 寄存器和所属方法。需要桥接时可在独立 compiler-only 输入保留真实目标的 owner、MethodInfo 和 activation，只替换其桥体并提取唯一完整函数；由编译器装箱参数并获取被调用 helper 自己的环境。原生旧 helper 也须随 ABC 修正重编；仅新增入口不会替换旧 handler。保留旧包装器和它实际调用的原函数，不能把后者改跳回新包装器形成递归。旧报告接口应明确禁用，不能只靠文档提醒。上述仅获固定输入静态/AOT及桌面验证，不证明 GC、异常或设备运行。
- 原生稀疏计划按原对象逐项覆盖全部重定位并独立解码，非重定位字节冻结；远 BL 可用经范围/寄存器检查的本地 ADRP/ADD/BR x16 veneer，GOT_LOAD 的 ADRP/LDR 只在实际 builtin AOTInfo 证据和配对指令守卫齐全时转换为 ADRP/ADD。依赖池不能误绑主池。旧 helper 入口 detour 前查完整原函数边界和 RX B/BL/AOT 指针的内部入口，无法证明则拒绝；槽、被覆盖入口首指令及前像分别保存。尚未分配地址的计划不是 Mach-O 链接，full/runtime ABC、摘要、内存段、展开信息与签名仍另验。方法、工具和独立对象→计划复核见生成器修复批次（历史本地记录）。
- 实际累计链接按当前段表扩展已存在的末端 RX，保留旧 VA、dyld rebase 及不相关原字节，并核新增表/activation 指针与旧 flags。对象符号范围可含尾部 switch 数据，必须用 compact_unwind、ADDEND/PAGE 配对和有界分派证据划分代码与表，不能把完整 symbol 长度一律当指令或展开范围。CMP 与 B.HI 存在不证明有界：分支须绕开表读取，selector/NZCV 不得被中途改写，需相应故障反例。
- 展开信息扩容前先查实际字节，地址上的尾部余量可能已有历史原生代码。EH 已搬到 header 时，旧的相邻 EH 释放方案不再适用。原空间不足可先核完全相同的标准 compressed 页 payload 共享：一级索引分别保留函数基址和 LSDA 范围，仍限每页 1021 项/4096 字节，所有旧边界（含零）、encoding、personality、LSDA、sentinel 和区间语义保持；不能改成超规格大页或删旧记录。限定配方、公开 reader 依据及实际成品读回见上述继承派发修复配方，未执行目标 iOS unwinder。仅对已核实的简单 arm64 zR/PC-relative FDE/无未处理重定位载体，可将 EH 搬入验证过的 header 零区，保留所有 CIE/CFI/FDE 绝对目标并按节地址排序同步合法符号 n_sect；未知 EH、引用或节重定位拒绝。候选独立回读按旧边界/区间验证展开语义、LSDA、函数起点、符号、重定位及全部非声明字节，不以同实现 roundtrip 代替。原生尚未 finalize 时，首份落盘回执即标 pending，封包还须检查明确 finalized 标志；中断不能暂时暴露“可封包”状态。该工具已在本批三个累计端口复用，实际证据见iOS R11 候选（历史本地记录），未外推 iOS 执行或设备验收。
- 分阶段 iOS 功能累计导致载体增长时，可从受保护的功能基底一次链接最终方法集，而非按主 AOTInfo 指针盲删旧数据。多批对象必须逐方法选定唯一原定义，显式处理覆盖方法并保留原符号索引、完整函数边界与 owning Binary；普通对象拼接可能选中后批返回桩。最终池/MethodInfo 保持前缀，运行 body 按各方法来源批次及基底保留规则合成，连同 max_stack 等全部字段核对，不能直接使用最后一批 compiler ABC。构建及 finalizer 使用冻结的同一所有权映射，独立验证器从原批次自行推导，并对实际 IPA 核全量目标重定位、非重定位字节、原代码/表、full/runtime/SWF/flags、展开与签名。新追加区仅一份最终 runtime/flags；体积收益与设备内存、启动和稳定性分开报告。工具与固定输入证据见累计整合候选（历史本地记录）及其独立源码入口；仅获离线回读，未验证 iOS 执行或全局任意数据裁剪。
- **本地源码管理的现行入口：** 统一总入口（历史本地记录） → catalog模块/文件台账 → local-maintenance/source或recovered。新增本地自用稿、恢复与复现工具不写源仓；已提交源码保留原位原内容，依赖副本绑定固定commit/摘要。迁移先固定初始归档和自身修改前像，再核自身明确文件范围；原仓恢复后证明HEAD/index内容和status，不能用移动已有已发布源码换取干净状态。新路径须真实运行并拒绝旧repo/work Python，历史回执不改写；新增src镜像不是完整服务端或可发布包。当前案例/迁移验收见总入口的迁移记录，早期“源码接回main”仅作历史事实。
- 当前源码覆盖按实际平台登记固定输入，手写源、私有恢复稿、阅读稿、字节码/原生映射和配方分别标注。验证可维护性时，在新检出目录真实生成SWC/AOT，绑定源稿、命令/退出、工具链、对象和实际包；运行时导入审计区分仓内代码、明确第三方运行库与基线/SDK数据。旧任务AS/smali作为明确输入时应保留来源并复制到稳定私有参考，旧项目Python改走仓内维护闭包；冻结配方保持原输入/哈希守卫，通过显式adapter调用，导入/接口合同不冒充整条旧制作main通过。相同SWF保留UUID，native-only同full/runtime时可只更新原生；原始工程缺失与仅保留现包另记。RX内嵌ABC仅在完整解析回读、无原生起点/AOT入口证明后排除，真实代码负例仍拒绝；源码时点变化保留精确前像/hash/diff。基础反例见主城模块复现（历史本地记录），扩大与现用维护入口见双端扩大复现（历史本地记录），均仅获离线结论。
- **已验证：固定追加helper集的源码与原生槽复现。** full ABC为返回桩时，只在独立compiler-only输入恢复源体，保留当前MethodInfo、字段、activation、池与最终full/runtime；新AOT须与当前完整函数字节及每处重定位逻辑目标/常量对应。缺旧函数边界时不能放宽detour守卫；仅在唯一槽、无共享别名、ABI/flags已证实且旧函数/直接调用及旧RX前缀全保留的明确slot-only策略下接入新函数，未知闭包/签名/映射拒绝。展开表邻接真实旧代码时禁止扩写；可重排本轮新函数按实际unwind编码分组，仅折叠新冗余同编码边界，保留全部旧边界/EH/LSDA/personality及逐函数起点，并独立解码全部新重定位。历史Java稿编译成功不代表旧合并DEX可整类替换；手写smali新汇编后完整DEX相同只计配方重放。实现、故障注入与排除边界均见上述扩大复现入口，不外推原生执行或其他载体。
- 受控测试直接保留目标方法/闭包体，依赖替身和接线改名另记；每个用例结束时冻结观测对象，避免后续清理改写旧调用数组。发现这种记录污染后保留旧证据并修正夹具、重跑受影响案例，不能手改旧结果。编译源码摘要取写入后的实际字节，Windows 换行规范文本摘要单列；行为对照、词法槽合同和生产类初始化/网络的边界分别报告，见四处源码收尾（历史本地记录）。
- 装备验证将选档、数据/数值、资源登记和真正加载分开；导入方法数不等于实际走到的方法数。原样当前方法与单因子对照一起运行，观察断言通过之外另列设计符合项和偏差，避免把预期错误也统计成原包功能通过。构造/查询替身可对齐完整 MethodInfo 并保留 ID、等级、计算引用，却不代表真实构造器或战斗消费；完整边界与实例见无实机装备核查（历史本地记录）。
- 复用固定客户端输入时，源仓出现并行提交先核对实际变更路径与客户端、解析工具、登记和资源链依赖；无交集且受保护输入及所选成员未变时，记录前后 head 与并行差异并复用证据，不改写旧输入基线或宣称全仓未变化。依赖有交集时重新核对受影响项；此限定不替代提交/推送或新客户端交付检查。

## 旧服资源兼容与准入轮换

协议不变不保证资源兼容。历史旧链1.4.136的材料 master 缺新晶10000320、仍有10000302，O2/O3单按五星满4筛选可让实际 View 空列表并抛 C4205；保留新晶的模型曾漏此组合。已验证修法是两个筛选加 `maxOverLimitStep>4`，缺定义仅回退显示，库存筛选不回退以禁确认。缺 master 与库存0分别建夹具，并跑实际旧 master、完整生产窗口及调用者；不只查协议或抽象模型。Android/iOS 的对应变更与独立封包见旧服兼容结果（历史本地记录），它不代表设备/公网运行。

准入配对轮换在完整私有主记录追加新 ID，按实际授权保留指定旧行/key/enforce，先覆盖 keys 后 policy。用真实服务类的内存 FS 验证新旧 ticket/challenge 隔离，不改运行 config 来代替隔离检查；配置交付、上传部署另记状态。

- Android 同查 ClientAdmission 内折叠的 ID/HMAC-prefix/key 及 BuildConfig，不能只改 BuildConfig；精确池槽回读，并逆变换全部 DoABC。
- iOS 仅当同长 ID/key 在实际 transport/proof 闭包和 cinit 经 `_llGetString` 按既有索引加载、所有副本可确定时采用原位轮换；同时更新 full/runtime/native 常量副本、AOTInfo full SHA1 及 SWF 摘要，以逆变换证明整个 native 代码/ABI/表未变；否则走编译移植。
- “保留上一版”按平台 registry 中真实 `admission_id` 取，不用 artifact build_id 标签或私有旧快照扩大允许列表。不因只有 Android 变化而给未变 iOS 分配新号或重复验 IPA；是否需要检查取决于实际输入是否变化。

代表证据：配对离线验证（历史本地记录）、R4 配对范围纠正（历史本地记录）。敏感配对不放 Git/普通资源或玩家渠道；开服缺策略的条件恢复见[运行上下文](runtime-context.md#客户端准入配置暂时不可用的条件恢复)。

## 编队锁输入、刷新与资源生命周期

### 动画完成与同步通知

历史 PartyCarousel 仅推进当前容器，但 EditOnce 完成谓词检查全部初始化容器，离屏 fall/kachidoki 残留会让输入锁一直等。20帧是动画完成后延迟，不是超时。有效修法只在 Waiting 推进有未完成动画的已初始化离屏容器，每容器每帧至多一次，保留平时 current-only、原谓词和回调；不能用超时伪造动画完成。这可解释条件性锁输入，不能独立解释整个渲染循环停止。

getter 延迟刷新不能调用会同步发 view command 的 applyParty。R2 的 G1002 链是 present→getPartyData→applyParty→sendCommand；改静默数组/revision 更新，保留详情和页面刷新协议，并用实际 present/apply/onPresentCarouselPage 与同步 dispatcher 检查重入深度。没模拟真实通知的对象夹具不足以证明事件生命周期正确。

同次汇总复用仅在 PartyTranslator 首次满血/普通模式与面板原转换满足相同条件时使用，其余分支保留；不是跨帧缓存。Lazy 不能仅按 party 同对象或 visualizationUpdated 跳过旧页 present，缺总 dirty/revision 与完整显示失效契约时可能漏文字、缩略图、滚动和 timeline。opaque Lazy 保持 dirty 走原 apply，不强制 get；离屏裁剪保留动画收尾及 alpha/z 同步，边缘小人修复不等于整页动画恢复。

### 任务、文件与纹理

- MultiTask 在任务启动及 progress 同步回调后再次检查取消/失败，防止取消后继续起任务或发 complete。文件打开占位对同步抛错、异步 IO_ERROR、重复关闭和排队取消一次性归还；排队 openAsync 同步失败走统一失败清理。
- native 运行期只写待清理标记，下次冷启动 AIR 前清限定目录；JVM 覆盖活跃文件不删除。root 纹理统计不等于精确 GPU 内存，不凭它更改淘汰策略。
- 4 ms、每 phase 数量等是协作调度预算，不能抢占单次 PNG 解码、上传或原生操作。正确取消、回调和 bitmap 所有权不等于性能收益；短下载/转换特殊模式未证等价前保留串行入口。

R3 的历史 MuMu Android15 覆盖登录、面板数值、SET/翻页、主副位完成替换、HP 条件、前后台、冷启及一场单人结算返回；它未登记，不证明手机偶发冻结消失、长期内存/耗电、联机/长战或故障恢复。证据见综合结果（历史本地记录）。

## 加载/黑屏：已验证因果与未修隐患

R4 是历史已撤回实现；以下用于故障识别和避免重引，不作为可继续套用的活动基线。

1. **排队 close 丢失。** 实际 FileStreamWithCounter.close 在全局额度满时把 openAsync→writeBytes→close 当取消，文件没写且不发 CLOSE；真实按需小下载写 incoming 后只等 CLOSE，因而可能长期等资源。全局文件上限100与每 MultiTask 30不同，现场 mode2/峰值未测。公共 flush-and-close 与 cancelStream 分离，保留计数回退和 owner 取消；只换旧 close 是因果夹具，不能当完整正式修复。
2. **restore 开始标记延后。** BitmapRestore.restoreHandler 延后 onStart，restoring 暂空；ConcreteTexture 先 clear 并置 dataUploaded 后，背景 RestoreContext 可误合成透明图且不重画。先同步开始标记的最小 helper 在受控 packed 重画对照恢复正确结果；GPU clear/draw/读取受控，生产方法归一和上传链执行也不等于真机 GPU通过。
3. **轻量完成被重预算节流。** 实际 OpenHandler/FileStream、真实小文件/ByteArray 对照显示 R4 对小任务大量分窗等待；decode 也占 heavy 名额再等16ms。加载关键路径宜与 PNG/GPU 重阶段分预算，保留真实耗时上限，不能简单全局加并发或外推手机秒数。

两处旧正常/R4失败/最小修正正常与吞吐证据见回归定位（历史本地记录）、文件三组（历史本地记录）、纹理三组（历史本地记录）、吞吐对照（历史本地记录）。没有证据把旧 PNG 容错、硬30简单依赖或全部网络/UI/data都列为根因。

隔离 r2 测试候选修正常 close FIFO/显式 cancel、restore 同步 start、decode/deliver 轻预算，失败 record close 仍清 wait；实际 helper、方法/成员、签名/对齐和受控恢复检查通过，见候选总核验（历史本地记录）。后续同一 ready-file fixture 三组交错证明 r2 比 R4 快但仍明显慢旧正式：512项旧15/9 ms、R4 1349/1324 ms、r2 192/207 ms；64步/4ms/Timer仍有等待，不能称已恢复旧性能或推定 FPS收益，见三组结果（历史本地记录）。该候选未被采用，不以离线修正覆盖设备待验。

追加公共链路审计有实际 AIR 条件复现的七类隐患：非空坏账号、同步 I/O 异常未 close、坏 PNG 无局部失败、marker I/O 阻断 Activity、Delay 抛错遗留、reset 晚响应覆盖、AdmissionSession 某回调抛错丢其他 waiters；首次启动救援安装晚及 HTTP 账号传输是静态风险。这些不都由 R4 新增，也不是玩家现场已证，未随 r2 全修。触发、最小方案和实际导出见综合审计（历史本地记录）。

其他静态线索：动画池 pop 后删整桶不直接等于泄漏；FileStream 异步打开计数、MultiTask 启动后限额、HTTP 跨请求残余 timeout 需逐条件核查。负帧自定义 timeout 未触发时仍有原生 idleTimeout/成功/错误事件，不能称永久挂起；rank 索引、技能槽三字段、差量 present 的设备因果未测。见只读排序（历史本地记录）。

## 性能判断：先定位，再决定是否采用

### 设计与取样

同一受控工作负载同时比较修改前已验收版本、问题版本和修正版本，执行各自实际方法/helper；不只比已知坏版本。缺正式旧版/候选直接设备 A/B 时，不能把内部 R3→R4 数据换算成正式旧版收益，也不把 R2/R3 新回归算成旧正式包缺陷。

先分独立一览与编队选角，测控制器初始化再决定改什么。历史 537 view 创建仅48 ms，真正热点是徽章 Lazy 创建前 537 次 quest-group 查询约2145 ms；移入原 Lazy并捕获原 player/id/time 后创建约2 ms、列表初始化2308→115 ms。保留其他徽标分支、失败传播/重试，并单列查询时间后移的语义。该受控/历史设备收益不能外推轮播、手机或官方原版动画。

普通 APK 采用同机/专用账号、保留磁盘缓存、冷进程匹配、旧版与候选穿插；保留全部正式慢样本，近邻子集只作补充，不混旧基线/诊断包。主机万次局部快或语义通过不等于 UI 净收益。回归计实际完成替换、横向滚动及最终可操作；98%加载不算返回。C1100 可由启动 rescueLatest 根据残留 active 生成，Activity 负责前后台标记，不直接归为战斗异常。

### 分阶段计时与可见端点

- PNG request→COMPLETE 是异步墙钟，不能称纯解码 CPU；上传 API 返回不等于 GPU完成。分别量排队、读字节、PNG完成、转换/交付、纹理 API、draw/present/translate/store。父子 inclusive 段不相加，嵌套 table.draw 不重复算；后帧 drawCount 不解释此前 gap。
- 内存窗口在缓冲分配前取 arm 时间，冻结后落盘且确认不落后续窗口；partial gap 的窗口外未知、未闭合 span、event/span tail drop、overlap 如实保留，不能归零或称完整8秒。缺 PNG metadata/字段归属时留 unknown；0 ms量化不代表绝对零成本。
- “首 decode”曾实际是 file-readbytes-sync 最早 start，不能标 PNG COMPLETE；跨 phase 最早对象可能不同。同步资源交付提前而全部绑定延后只证明调度交错，不证明总工作减少；先核原 hasAppliedInAdvance，避免优化不存在的重复。
- 计时钩子须验证正常 CFG 与 active 路径。历史 while 条件共享入口错误插 end，使首次跳转 end-before-begin；collector 忽略无效 token不代表 scope正确。修正范围后检查边/switch成对、空 renderer和同次多 kind闭合，见CFG独立审查（历史本地记录）。
- 普通视频按同视频真实可见事件相减，不扣名义 tap 1秒或未知原点；菜单首次淡出后持帧不重置起点。用真实输出 PTS，VFR 的0.15–0.40秒空档保留区间，不伪造成50ms精度。稳定位置至少三个后续不同PTS见证。
- 12/6小人终点逐原尺寸格/面板核脸和身体（含半透明选择态），底座/勾选不算，缺格每轮可能不同；位置稳定、缩略图放大与人齐分别计时。原生2秒窗口保留双输入跨界间隔和慢样本；20Hz结构采样、相同buffer都不等于游戏FPS或严格输入延迟。
- 启动 ADB 失败和 bootstrap 与正式样本分开，保留非0退出的 bounded stdout/stderr，不猜原因或自动重发 tap。只有核心证据冲突才定点回原帧；非关键阈值可留 unknown。决定范围可在首测前缩到最小关键对照，证据足够则停，不机械要求三轮。

阶段诊断与视觉方法代表证据：render 分阶段（历史本地记录）、同步热点与绑定调度（历史本地记录）、Q3关键对照（历史本地记录）。

### 负结果与仍应守住的优化契约

以下均为历史未采用实验，不作为后续输入；必要数值与全部样本留原报告。

| 实验方向 | 保留的方法与采用结论 |
| --- | --- |
| N5已知能力跳未用描述；R5 atlas/PNG并行 | 未知类型沿旧逻辑；语义/生命周期通过仍须普通包对照。并行完成/取消/所有权正确不保证更快，竞争是待证假设；本机候选变慢，未采用。见资源实验（历史本地记录）。 |
| U1 phase上限8→16；U2每draw最多3次首次绑定；U3 mode0的12ms/max3且至少1进度 | 一览和右切、原生p95/max可能反向变化，不能拿单端点改善代替净收益。已bound dirty不限、失败/裁剪不消费、保留 advance，mode1/default不新增timer，受控uint算术不称多日实测。总绑定成本未降，三项未采用。见U2/U3结果（历史本地记录）。 |
| Q1索引查表 | 仅精确原类/构造器/keys别名、primitive整数唯一性才快查，首 matching 构造前永久回原查找，保留同步 keys突变、重复raw key错误与cachehit。减少局部扫描仍可能增加资格检查，不能跨诊断包相减，普通净收益未证，未采用。见Q1（历史本地记录）。 |
| Q2 fresh Template单literal | 完整 parseTokens、原 parse/final错误逻辑，无共享实例/AST/字符串缓存；sealed非final类的constructor可被动态子类伪造，实际用新增List/token读取前的native superclass守卫保留重写及错误顺序。位置更早稳定不等于小人更早齐，未采用。见Q2（历史本地记录）。 |
| Q3纯文字getter | 非空typed String、Boot false、exact EReg/RegExp及non-global；match false直返，true恢复result/lastIndex再原构造，不缓存实例/AST/文字。跨DoABC保留首次script触达顺序，cinit returnvoid不代表可忽略；同QName/kind4 setter只读。局部主机加速与单对画面改进不足以证稳定体感，未采用。见Q3（历史本地记录）。 |

真实 numAbilities getter含描述格式化、learned/disabled过滤、merge/sort，不用 raw trigger数替代；formatter、kindRenderFilter和renderCall可能比 trim/blank更贵，应按同次实测分解。Template有可变实例和共享正则状态，不能未经语义验证按同值复用；0ms包装成本仍有量化边界。Boot.skip在构造实参前复位，双方绿断言不能掩盖null起态；缺Op*依赖、原生RegExp子类独立构造#1107须与真实候选错误分开。

## 设备保护、后台执行与精确恢复

每轮设备操作前备份**实际当前** APK 与非 asset 文件，记录内容、权限、UID/GID、adbd身份和配置；不能沿用上一轮35/37/38等旧清单，或重启旧 pending=false会话。MuMu root设置开启而 su缺失不证明无root；必要时 adb root，结束恢复原 adbd UID、原设置及文件并回读。缓存和新 active/正常结算按本批保留策略处理，测试日志先备份再移除；不能只还原APK而声称整体恢复。最终以当前 device/session-state和restore receipt为准。

本地后台入口为[client-background](../../../../tools/client-background/README.md)：`python -B <repo>/tools/client-background/run_background.py --timeout 180 --cwd <实际源码或worktree目录> -- python -B -u <检查脚本> <参数>`。Codex 发起的本机 Windows AIR/ADL 检查必须包裹完整最外层命令，覆盖离线夹具、临时脚本、worktree 和间接启动 ADL 的构建/测试；启动前核对实际命令，失败或超时禁止裸跑回退。仅隐藏 initialWindow、控制台或重定向输出不能隔离 HARMAN 启动画面。源脚本保留普通 subprocess，不恢复源内私有工具依赖；执行要求从任务效率入口（历史本地记录）读取。已有真实AIR stage/Timer/trace与GUI孙进程私有桌面继承证据；超时只保留已flush输出，外层不能补内部尚未生成日志。它不替代明确要求的可见交互/GPU验收，也不改AIR许可或游戏包。迁出回执（历史本地记录）取代源内旧接线作为当前工具入口。

## 撤回、源码复现与历史实现退出

出现加载回归或异常收益时，可按授权做可审阅的定向撤回：确认实现提交/路径，撤活动代码、组装入口和当前指针，保留公共工具、其他服务/CDN/iOS更新及既有 dirty；不能整仓退回代替范围判断。保留前像、候选实包/原报告及精确撤销证据，按范围回读，未安装设备就不声称设备恢复。

R4 后曾完成源码累计组装：固定旧正式LAN功能输入，按 liveness/refresh/network/data/resource/UI六阶段及方法/helper清单，一次重建SWF/public字节一致；固定累积入口与 accepted接续入口必须分开，避免重复套补丁。发布回执（历史本地记录）仅作历史可复现来源。R4随后已定向撤回，加载r2亦未采用，旧版原有600秒运行期限定AIR缓存策略随旧包恢复，不称新修复。历史“当前/保留R4”、登记号、源码发布或测试包路径不能覆盖现行 registry；旧包有的已按清单清理，路径不保证实物仍在。退出与保留范围见[撤回说明](../../../../client-patch/ANDROID-BASELINE-ROLLBACK-20261017.md)、撤回核验（历史本地记录）、历史清理清单（历史本地记录）。

## 客户端发布相关的 Git 预检与过程产物

含 Token/OAuth/Key 文件名的实际 ABC SHA-256 可触发 generic-api-key；先重算实物摘要、排除私有配对，再按 `.gitleaksignore` 约定仅记录具体 commit/path/rule/line指纹，禁止整目录跳过。同 blob被另一历史提交引入时，旧提交指纹不自动覆盖；比较完整Git blob、逐行摘要及原实物证据，只补实际报告的指纹。普通Windows/Bash文件检查不包含历史密钥扫描，当前树通过不证明待推历史已扫，准确目标SHA的远端检查仍独立取证。

2026-10-20 已撤回后来新增的本机统一预检，v2/lightweight 候选同时弃用，不再安装或调用其工具、薄扫描或缓存流程。仓库恢复原有 LFS、commit-msg 和 post-* 钩子；正常提交审查、独立历史密钥扫描、GitHub 原有 hygiene/Gitleaks 及精确历史例外继续保留。撤回状态及必要恢复信息见撤回记录（历史本地记录）。

历史检查经验仍可按需参考：中文路径枚举须避免把 ls-files 的转义显示误作实际路径；文件检查和 Git 历史密钥扫描分别取证，不能以旧回执代替当前目标检查。原预检及 thin 优化仅属已退役实现的历史证据：原预检回执（历史本地记录）、对象扫描优化（历史本地记录）。不由这些历史结果恢复本机预检，也不放宽现有例外或修改源 CI。

过程产物整理先区分Git跟踪/忽略与内容用途，优先处理误跟踪生成缓存；零文件名引用仅说明静态依赖，不证明搬动有必要。不为目录整齐迁移过程记录，保留正式交付、缺源码缓存、历史构建输入及已忽略work；只有明确收益和完整保留条件才整理。历史12份记录已恢复、可重建缓存外置的范围见恢复回执（历史本地记录），不把阶段结果当当前Git状态。

全部批次、数值、候选采用状态及历史入口保存在历史原文（历史本地记录）。本次仅重组既有知识，未新验包、构建、安装、运行游戏、改登记或部署；后续任务仍按实际对象和授权验证，整理本身不证明复用收益。
