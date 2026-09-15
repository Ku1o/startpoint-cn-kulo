# iOS 正式公网准入版（2026-09-15）

用户通过“整合、提交、云服包”任务要求补做 IPA：从 iOS 已验收版本出发，只加入当前准入功能，不移植 Android R8/R9/R10 性能、队伍缓存及相关加载优化，不加入诊断或日志导出。

## 输入与成品

- 唯一直接 IPA 输入为 `ios-accepted.json` 登记的商店优化累计版：`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-shop-first-open-public-20260913-unsigned.ipa`，SHA-256 `544ec90332845ff6c6b06e98aad691c0d9f10c725470eceeb4237c8bdbd65361`。已运行 iOS 基线验证器。
- 保持 `com.kulo.wf`、1.8.4 / 1.8.46、公网初始地址 `http://175.178.160.158`（端口 80），沿用已接受的 TrollStore unsigned 交付方式。
- 成品：`F:/codex/startpoint-cn-private-clean/outputs/ios-admission-public-20260915/StarPoint-iOS-1.8.4-admission-public-20260915-unsigned.ipa`。
- SHA-256：`764a7c5183a8605f58364e786a08a59f65333403bded9918dd3b544a85112f09`。
- 原生程序 SHA-256：`ad35c8894e5c883798e9d2ff305ada8562fdc26361d550e2affb5f5456ccf211`；SWF SHA-256：`addf3ee62d783fff828c1811ee4b6461cb1323146871d78ee2107bff8e439c2e`。
- 完整 AOT ABC：`F:/codex/work/ios-admission-public-20260915/admission-full.abc`，SHA-256 `86e787a8d169cabfee94e8420d56ff1bf8ed928afdb04e367d9967cf91844ae3`，共 101,283 方法。保留该文件供后续累计构建使用，不能替换成 stripped ABC。

本批 iOS 新号 `ios-184-admission-20260915`，真实平台为 `ios`。Android 继续使用 `android-181-r10-20260915` 和原 APK 哈希 `afca9f44d1bea9edea7b573fa96dddd32bc304afd0bbaa4d3df6fb21d41c2a90`。本目录及 `r10-public-release/release.json` 记录同批对应关系，未因为补做 IPA 再推进 Android 号。

## 实现范围

复用 `r10-public-release/src/cn/admission/` 的完整生命周期源码，只在生成的 iOS `ClientAdmission.as` 中把平台字面量由 `android` 改成 `ios`；构建号、密钥与端口 80 通过本轮 BuildConfig 写入实际 AOT 常量。请求等候共享握手、账号绑定、相对计时续期、过期/服务重启恢复、有限退避和取消保护均保留。

| iOS 方法 ID | 准入接入位置 |
| --- | --- |
| 32403 | RemoteUtil.requestCompleteHandler：把明确准入拒绝交回队列恢复 |
| 32429 | RequestQueue.startRequest：等候有效凭证并带请求头 |
| 32433 | RequestQueue.requestSuccessHandler：仅处理业务执行前的准入拒绝 |
| 32435 | RequestQueue.clearQueue：使等待中的回调失效 |
| 34260 | SockletConnection.socket_connected：握手携带准入凭证 |
| 34262 | SockletConnection.socketConnect：连接前恢复准入和账号绑定 |
| 34276 | SockletConnection.close：取消等待中的重连 |
| 101122 | PlayerLogin.request：登录/注册/恢复等请求先完成准入 |
| 101128 | PlayerLogin.cancelNetwork：超时或取消后旧回调不再发送请求 |

仅新增 `ClientAdmission`、`AdmissionSession`、`BuildConfig` 三个类、69 个方法。七个通用网络方法的 P-code 参考已验收、无诊断 Android 商店版；这不是 IPA 基线。PlayerLogin 编译上下文来自固定哈希的 iOS 缓存累计 ABC。编译上下文和旧类初始化只用于生成原生代码，链接时保留它们的原机器码和运行元数据，仅替换表内九个方法。

新增 RX `__CNADMIT` 与 RW `__CNADTAB`，旧字段、方法签名、activation 布局及已有数据池索引不变。原生程序保留其余 101,205 个旧方法与全部既有累计功能，包含原 iOS 商店、觉醒页、登录、HUD、Lens、深渊、五重、切队及 CNtips_b 行为。没有引入 `cn.loading.PartyDerivedCache` 或诊断类。

唯一新增运行库调用 `do_loadenv_number` 用 SDK 对象与已验收程序的唯一匹配定位：84 字节函数中 80 字节不含重定位并逐字节匹配。完整证明随成品保存，不猜测 native helper 地址。

## 配套及验证

`config/client-admission.json` 已在原 Android 条目上追加 iOS，保留 Android 原字段和 `enforce:false`。独立受控私有文件 `outputs/ios-admission-release-private-20260915/config/client-admission.keys.json` 完整包含本批两端材料，Android 密钥与此前完全一致。不得用只有 iOS 的名单覆盖 Android。

服务器接口未变化。成品 `server-files/` 提供两端允许配置及原六份 HTTP/TCP 准入源码/out；六份代码哈希与 Android 任务执行完整 `npm run build` 的结果一致，因此没有为单纯新增配置重复改造或重编译服务器。

- 3568 个 IPA 成员逐项核验，仅主原生程序和主 SWF 改变；实际 AOT 平台、构建号、密钥、公网前置及游戏地址检查通过。
- 九个接入方法与已验证准入行为的规范化指令一致；69 个 iOS helper 方法逐一对应生成源，78 个链接函数的非重定位字节与编译对象一致。
- 2175 个重定位、61 个跳转桥接、92810 个新增 rebase、旧原生字节边界、三种 ldid 签名替换模型通过。
- 56 项 AIR 生命周期断言、37 项实际双端正式配对/真实账号 HTTP 协议断言通过；停用/重新启用、错平台/错密钥、续期宽限和重启恢复均覆盖。
- 5 项历史签名截断、rebase 0xF0、错误初始公网地址及 HUD 字段错位回归通过。

以上是离线与隔离协议验证，**未真机测试**。AIR harness 不是 iOS 真机；HTTP 测试用真实账号路由与隔离数据库，游戏业务是桩处理器，使用模拟时间，没有手机长时间联机验收。没有占用 MuMu 或改 Android 安装。

无存档 ID、玩家表/列、账号归属或 V1/V2 存档格式变化，无资源/CDN 分包变化；无需迁移。未提升 accepted registry，未提交、推送、同步运行镜像、部署/重启云服或改变严格模式，统一云服包仍由整合任务按后续授权处理。

## 复现

在源仓库选择新的独立工作目录，保留固定基线及受控配对文件，依次执行：

```powershell
$env:STARPOINT_IOS_ADMISSION_WORK = 'F:/codex/work/ios-admission-reproduce-unique'
python -B -X utf8 client-patch/ios-admission-release/prepare.py
python -B -X utf8 client-patch/ios-admission-release/compile.py
python -B -X utf8 client-patch/ios-admission-release/build.py
python -B -X utf8 client-patch/ios-admission-release/verify.py
python -B -X utf8 client-patch/ios-admission-release/tests/run-session.py
```

工具沿用仓库既有 AIR 51.2.1.5、AOT 编译依赖和经过地址证明的原生链接工具。输入不匹配或输出已存在时停止，不绕过断言。构建成品、完整 ABC、工作目录、配对秘密不进入 Git；源码和验证脚本按授权单独提交。
