# iOS 深渊续战阵容复用：Lens 累计补丁

2026-09-09，从 [历史 Lens 0907/0908 IPA](../accepted-history/ios-lens-20260909.json) 制作，保留此前累计修改。
用户随后要求“ios和安卓都验收并提交修改内容至github”，本次离线验收通过，更新 [当前 iOS 登记](../ios-accepted.json)。
验收边界见 [双端记录](../ACCEPTANCE-ABYSS-AUTOSTART-20260909.md)：原 IPA 仍未签名，没有安装或真机测试。

## 成品

`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-abyss-autostart-lens-20260909-unsigned.ipa`

| 项目 | SHA-256 |
| --- | --- |
| 输入 Lens IPA | `de28d8134e51d22f3c596869e53e90072866c17f54ec54af99b2a3fcd78dcd02` |
| 输入完整 ABC | `932c5b21f01de3a8aae4529e651b30f3bc42ccd789306c93cb4f151b64c42ef6` |
| 参考安卓续战 Lens 公网 APK | `c868534b575348dde825fcd4c88c156157174fd4444724f1141fd9aa95e32a2d` |
| 参考安卓 SWF | `11c06fd77a0e3811164d196208ecce28cba5ec3a602e3d798f3c67d5d5b17e04` |
| 输出 IPA | `8e6fb8cc4de6fe1c79efaded8e4ab1159c012645bdc3a52a22e19562e0661193` |
| 输出原生主程序 | `7c37c6ad5fd9019a502fb4f01fd5b1af6dfcdf608996240c26319186f0d594ba` |
| 输出主 SWF | `051c240268db2953cedf5571fc641bcac7a139044c17513b83c9b09833eb7e52` |

包身份沿用 `com.kulo.wf`、版本 `1.8.4`、构建 `1.8.46`，服务地址及资源沿用输入。
侧件位于 `F:/codex/ios-artifacts/abyss-autostart-lens-20260909/`，包含使用说明、哈希和构建/验证报告。
本次登记上述原交付 IPA；构建报告保留生成时状态，没有重编译、重签或安装到设备。

## 行为与移植范围

与 [安卓续战补丁](../abyss-autostart/README.md) 一致：深渊活动 `700099` 的续战预设队伍可以跨关复用角色。
返回值仍保留每关一个独立空数组，避免列表按楼层取值时得到空值。
其他活动进入原有重复检查，逐关选队、进度、结算和其他开战条件保持。

只替换 `RushEventAutoStartQuestGroup.getDuplicatedCharacterIdsForEachQuest`：

- iOS 主 ABC body index `24810`，AOT method ID `26363`。
- 新方法与安卓 `284:24599` 的规范化指令完全一致，寄存器从 20 增至 23。
- 类初始化方法 `26365` 仅用于 AIR 编译，不替换它的运行时元数据或原生实现。
- 保持原有 101,071 个方法编号；类、字段、方法声明不变，常量池只追加整数 `700099`。

iOS 的主 SWF 不直接执行该 ABC，因此同时移植一个 2,876 字节 ARM64 函数。
新增 `__ABYAUTO` 只读可执行段，容纳新的 stripped ABC 和该函数，总大小 5,701,632 字节；
原 `__LENS` 代码段完整保留。新段位于 LINKEDIT 之前，既有 TEXT/DATA/LENS 的地址、大小及节编号保持。
LINKEDIT 载荷原样后移，相关加载命令的文件偏移同步更新。

通过当前 AOT 信息指针与实际段映射读取 Lens 的运行时 ABC，不能继续使用历史固定 `MAIN_ABC_OFFSET`。
修改现有方法表中的一个指针，并在原函数入口插入跳转；原 ASLR rebase 条目继续覆盖方法指针和 ABC 指针。
主 SWF 只更新与原生一致的 20 字节 AOT 身份。

## 验证

- 回读全部 3,568 个 IPA 成员及 ZIP CRC，只改变主程序和主 SWF，成员及 ZIP 元数据保持。
- 独立解码核对全部 73 处原生重定位、跳转入口、方法指针、加载段及 dyld rebase。
- 恢复明确改动区间后，所有原有非目标原生字节与输入一致；原 LINKEDIT 和整个 `__LENS` 段逐字节不变。
- 既有常量索引、类/字段/脚本结构、非目标方法信息与闭包布局保持。
- iOS 和安卓续战方法规范化指令一致；iOS 完整 ABC 的基诺维 422 解析不变。
- 保留 Lens 的 724/422、稻穗 PF、五重地图及手动 Auto 锁、5900101 铁钢限制，
  以及此前 MOD、MemberView、排行榜、关注/本人资料和 iOS `CNtips_b` 行为。
- 实际 Lens IPA 的运行时指针回归检查，确认读取的是 Lens 段中的当前 ABC，而非仍留在旧偏移处的历史 ABC。

以上为离线代码和文件检查，没有将其记成真机测试。

## 构建方法

工作目录默认 `F:/codex/work/ios-abyss-autostart-lens-20260909`，通过 `STARPOINT_IOS_ABYSS_WORK` 指定新的空目录。
脚本锁定上表历史 Lens 输入哈希。当前登记已升级为续战成品，默认入口拒绝重复套用；仅复现本步骤时显式传 `--reproduce-lens`，从固定历史登记回读原 Lens IPA。输入缺失或不匹配立即停止；新任务从当前累计 IPA 重新审计，不绕过断言。
复现依赖 [iOS Lens 方法](../ios-lens0907-0908/README.md) 所列本地 AIR SDK、LIEF、
运行库符号映射和原累计 ABC；不执行历史构建入口，不将二进制、编译对象或签名材料提交 Git。

```powershell
$env:STARPOINT_IOS_ABYSS_WORK = 'F:/codex/work/ios-abyss-autostart-rebuild-example'
python -X utf8 client-patch/ios-abyss-autostart/prepare.py --reproduce-lens
python -X utf8 client-patch/ios-abyss-autostart/compile.py
python -X utf8 client-patch/ios-abyss-autostart/build_native.py
python -X utf8 client-patch/ios-abyss-autostart/verify.py
python -X utf8 -m unittest discover -s client-patch/ios-abyss-autostart -p test_runtime_pointer.py -v
```

准备、编译、封装、独立回读逐步执行，任何一步失败即停止。编译子进程有超时及进程树清理，
构建拒绝覆盖已有工作或输出目录。编译产生的其他函数不装入 IPA。

## 使用与交付边界

沿用原方式重签后安装。先检查启动、登录、基诺维详情，再为深渊连续多关选择同一队，
检查启动和推进 2–3 关、停止后手动选队、主副位交叉复用及整轮结算；回归其他活动原有重复限制。

制作时源码基点为 `staging / 2e7ab5a06fbd941fec6d799ebd51e1abd67bf441`。本目录保存移植、复现、独立验证方法及验收身份；IPA 不提交 Git。服务端无需配套修改，本次不涉及运行镜像同步或云服整合包。
