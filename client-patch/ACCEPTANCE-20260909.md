# Android / iOS Lens 累计成品验收（2026-09-09）

后续状态：本页是原 Lens 成品的历史离线验收。当前开发基线已升级为 [深渊续战累计成品](./ACCEPTANCE-ABYSS-AUTOSTART-20260909.md)；下文“本次”“当前”均指当时。

用户要求：“你先把之前提交的安卓和ios验收了，避免再出现问题”。本次回读此前交付的原成品，
完成离线包体、累计方法和基诺维 C7050 相关能力解析检查，将下列三份登记为当前开发基线。
登记状态为 `accepted_offline`，没有将这句话记成用户已经完成真机测试。

| 当前成品 | SHA-256 |
| --- | --- |
| Android Lens v3 公网 | `8e5999e2689788159362acc81cd4bcd89182966fce9af7800d085ff89dccb41b` |
| Android Lens v3 内网 | `966facaa01de0fc9952fe648f4ffef0fd99a53fad73deac7f652d6cf6f9fbc04` |
| iOS 1.8.4 Lens 0907/0908（未签名 IPA） | `de28d8134e51d22f3c596869e53e90072866c17f54ec54af99b2a3fcd78dcd02` |

路径、APK/IPA/SWF/原生哈希和 Android AIR UUID 以 [Android 当时登记](./accepted-history/android-lens-v3-20260909.json)
及 [iOS 当时登记](./accepted-history/ios-lens-20260909.json) 为准。Android 方法来自 `a7ac300a`，iOS 方法来自 `dc440e62`。
Git 保存方法与成品身份；二进制仍保留在原交付位置。

## 本次重新执行的检查

- Android 公网、内网：实际 APK/SWF 哈希、ZIP CRC、重复成员、包身份、AIR UUID、
  ZIP 对齐、v1/v2 签名和固定证书均通过。与 9 月 6 日父版本相比，APK 普通成员只改变 manifest UUID 和主 SWF。
- FFDec 独立比较全部 96,397 个既有方法体：两版各有预期的 33 处改动和 7 个新增方法。
  公网和内网主 ABC 的方法体仅 `284:92013` 地址配置不同；关注、本人资料、标题等非目标方法保持。
- 基诺维回归：从实际 Android APK 提取的 `AbilityValues.parseAt109` 包含 `422` → `DashParameter`
  构造分支。独立 P-code 回读同时确认 `422` / `724`；Android 与 iOS 完整 ABC 的该方法规范化指令一致，
  iOS 对应 AOT 方法 `42739` 在重新验证的 33 个原生方法之内。
- iOS：交付 IPA 与构建成品哈希一致；重新验证 3,568 个成员，只改变主程序与主 SWF。
  33 个原生函数、32,258 处重定位、方法指针、闭包布局、ASLR 重定位和加载段均通过；
  原有非目标原生代码、LINKEDIT、资源、包身份及 iOS `CNtips_b` 行为保持。
- Android 移植器 5 项测试、iOS 展开器 4 项测试通过。
- 当前三个成品的身份检查通过；旧 Android 公网/内网、两份错误续战测试 APK、旧 iOS 资料页 IPA
  和 iOS DEBUG 诊断 IPA 均由检查器拒绝。

`AbilityValues` 的高级 AS 反编译遇到 FFDec 图重建异常，因此没有将不完整 AS 输出当成验收证据；
使用完整 P-code、独立方法比较和解析器规范化指令完成该项核对。原始日志保留。

## 防止再次选错基线

每次新修改前必须执行对应检查器，输入不存在或哈希不符立即停止，不扫描旧包替代：

```powershell
python client-patch/verify_android_baseline.py --variant public
python client-patch/verify_android_baseline.py --variant lan
python client-patch/verify_ios_baseline.py
```

9 月 6 日 Android 标题包及 9 月 8 日 iOS 资料页包的原验收记录，完整归档于
[Android 历史登记](./accepted-history/android-20260906.json) 和
[iOS 历史登记](./accepted-history/ios-20260908.json)。它们仅用于追溯，不再用于新修改。
历史构建器的精确输入保护继续保留；登记升级后不能通过绕过断言来运行旧步骤。

两份 `abyss-autostart-*-test-20260909.apk` 因基线回退漏掉 Lens 内容而判定不通过，
准确哈希见 Android 登记的 `excluded_artifacts`。禁止继续交付或作为输入。
深渊续战补丁需要在上述 Lens v3 上重新移植和验证；本次验收未重新制作续战包。

## 证据边界

本次没有重新编译、重签、安装客户端或进行真机战斗。离线检查不能替代覆盖安装、
角色详情、实战、五重联机、续战与 UI 的真机回归；iOS 原成品仍为 unsigned。
原构建与交付报告保留其生成时 `candidate` / `pending` 状态，后续真机反馈另行登记。

本次本机审计脚本、P-code、比较日志及回执在 `F:/codex/work/client-acceptance-20260909/`，
总回执为 `acceptance-receipt.json`。没有修改服务端、运行镜像或 CDN，没有生成云服覆盖包。
