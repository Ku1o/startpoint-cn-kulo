# Android APK/SWF 工作入口

最新 Android 登记（2026-09-13）：用户认可商店优化 LAN 效果并授权公网转换、离线验收与提交；见 `client-patch/ACCEPTANCE-SHOP-FIRST-OPEN-20260913.md` 和 `android-accepted.json`（客户端目录内为同名文件）。当前状态 `accepted_offline`，主 ABC 291、96543 方法体，包含商店索引/存在性短路和觉醒页刷新。公网未独立真机测试；下述昵称/缓存/圆角/切队包均为历史累计来源，不再作为新 Android 输入。iOS 仍使用独立已验收注册表，商店候选等待用户验收后提交。


- 开始 Android APK/SWF 任务前，先读本目录 `ANDROID-BASELINE.md` 和 `android-accepted.json`，再读具体补丁文档。JSON 中登记的已验收公网/内网成品是当前直接基线；其他文档中的旧哈希只代表历史步骤。
- 在修改前运行 `python client-patch/verify_android_baseline.py --variant public` 或 `--variant lan`，回读实际 APK、内嵌 SWF 和 AIR UUID。输入缺失或不匹配时不得按日期、文件名或旧报告另选 APK，也不得跳过哈希保护。
- 当前公网/内网直接基线均为 2026-09-12 用户验收的缓存/圆角 + 切队 F1009 累计包，主 ABC 288、96520 方法体，见 `ACCEPTANCE-CACHE-PARTY-20260912.md`。保留玩家登录、Lens 0910、属性通道、深渊详情、旧服空更新兼容、覆盖安装首次启动缓存清理、圆角按钮与切队初始化/触摸保护，以及此前全部 MOD、幻想连战、排行榜、关注/本人资料路由、CNtips_b 隐藏、422/724、五重决战及 700099 续战队伍复用。9 月 9/10 日登记是归档复现输入，不再作为新任务基线。
- 旧步骤构建器锁定各自的历史输入，用于解释或复现该步骤；不能把任一中间产物直接当成最新成品。不同 UUID 会改变 APK 哈希，串联重建时不得为通过旧步骤的哈希检查而复用 UUID。
- 改动 SWF 时分配新 `uniqueappversionid`，保持包名、版本身份和签名证书；回读最终载荷、方法差异、UUID、ZIP 对齐和签名。完整类重编译产物只能用于提取 P-code，不能直接发版。
- 构建报告只记录本地校验；用户明确验收或明确要求执行验收后，按实际证据更新 `android-accepted.json`、方法文档和检查器，再按用户授权提交。离线验收记为 `accepted_offline`，不得记成用户已真机验收。APK、SWF 成品、临时产物和签名凭据不提交 Git；IPA 必须单独授权。

# iOS IPA 工作入口

- 开始 iOS IPA/SWF/AOT 工作前，先读 `ios-accepted.json` 和其中指定的方法文档，运行 `python client-patch/verify_ios_baseline.py` 回读实际 IPA、主可执行文件、主 SWF 的 SHA-256 和包身份。输入缺失或不匹配时不得改用旧包、诊断包或按文件名推测最新包。
- 当前 iOS 基线为用户于 2026-09-12 验收的公网缓存/圆角累计 IPA，见 `ACCEPTANCE-CACHE-PARTY-20260912.md`；保留本次空更新、安装变化后一次 NSURLCache 清理、圆角按钮及 R4 的登录、深渊、属性伤害通道、Lens 0910、TrollStore 布局、公网初始地址和 HUD 字段修复，以及旧方法 26363 和全部 Lens/资料页行为。iOS 不加入 Android 切队修复。登记原 unsigned 成品与 101191 方法的完整 ABC，用户确认与离线检查分开记录。R4 和更早包仅作历史精确复现，不以 stripped ABC 替代完整 ABC，不绕过历史哈希保护。
- 保留此前累计功能及 iOS 标题 `CNtips_b` 原有行为；本次 iOS 明确不移植 Android 的标题隐藏。诊断包不作为当前成品，不将 DEBUG 标记带入后续发布。
- 原构建、交付及诊断报告保留生成时状态，后续用户验收单独登记。验收不等于授权提交 Git、重签、部署或清理其他 IPA。
- 新增 iOS AOT 数据或 dyld 重定位流时，所有加载器使用的 LINKEDIT 数据必须位于 `LC_CODE_SIGNATURE.dataoff` 之前，签名区域应为文件最后一段。禁止把新增重定位流附在旧签名尾部之后；重签可能移除或覆盖它，导致游戏代码执行前在 dyld 内闪退。交付前同时检查偏移、段边界、签名尾部，并模拟替换不同大小的签名块，确认 rebase/bind/导出及符号数据仍完整。参考 `ios-cumulative-login/test_signing_layout.py`；未签名 IPA 的静态解析成功不代表重签后可启动。
- 用户确认使用 TrollStore 安装 IPA。还必须满足其 `ldid` 的裁剪边界：它会将 `LC_SYMTAB.stroff + strsize` 向上对齐 16 字节作为签名起点，优先于原 `LC_CODE_SIGNATURE.dataoff`。新增 rebase 等数据应放在符号字符串表之前，字符串表作为最后的加载元数据，签名紧随其后。仅把数据移到签名之前仍可能被 ldid 覆盖；必须按实际 ldid 分配/裁剪规则验证，并用历史错误包证明检查可以捕获 `unknown rebase opcode 0xF0`，不能只模拟从原签名偏移替换尾部。
- iOS 登录面板等标题前置联网功能必须核对版本查询完成前的实际地址，不能只凭包内出现公网 IP 或沿用原包配置就判定为公网。原生 `DevConfig_gf_ios` 的初始官网地址会在异步版本查询后才替换；提前缓存它会让登录面板及重试继续访问旧地址。核对原生构造器实际加载的协议/主机常量与当前 AOT 字符串池，并保持初始地址和云服版本配置的规范写法一致，避免记住账号的 origin 与请求头匹配在查询后变化。回归必须能识别历史 R2 的错误初始地址；参见 `ios-cumulative-login/public_endpoint.py` 和 `verify_public_endpoint.py`。
- iOS AOT 给既有类追加实例字段时，必须核对实际内存偏移；trait 列表只追加并不保证原生 ABI 不变。AIR arm64 将 32 位标量放在引用字段之前，追加 `int/uint/Boolean` 可能移动全部既有引用字段，使保留的构造器、初始化、访问器和其他调用者读写错误位置。R3 的三个 HUD 语音计数字段导致引用偏移整体增加 8 字节，在 `HudMemberStatus.run` 初始化时触发 F1009。R4 使用尾部 Number 存储、零默认值和显式整数读取，保留轮换语义与原引用偏移。后续必须从实际运行 ABC 和原生加载指令共同核验，并用 R3 错误包作负例；参见 `ios-cumulative-login/hud_state_layout.py`、`verify_hud_state.py`。不得通过仅给报错方法加空值保护或仅重编译一个访问者来掩盖字段错位。
