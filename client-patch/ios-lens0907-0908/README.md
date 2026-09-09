# iOS Lens 0907 / 0908 客户端修改方法

2026-09-09 固化本轮方法、构建脚本和独立验证脚本。初次交付配套资源为 1.4.102；
服务端后续已更新到 1.4.103，本次只保存客户端修改方法，不重建 IPA 或调整资源版本。

从 `client-patch/ios-accepted.json` 登记的 2026-09-08 无 DEBUG、已验收的关注/本人资料 IPA 继续构建。
原签名状态为 unsigned；本次仍交付未签名 IPA，保留 `com.kulo.wf`、`1.8.4`、`1.8.46` 和原服务地址。
本次输出尚待用户真机验收，不更新已验收登记。

## 内容

- 724 Fever 满槽比例增减及 422 冲刺参数，包括能力解析、描述、汇总与战斗执行。
- 稻穗特殊 PF 使用弹射前连击数；基诺维使用角色配置的冲刺参数。
- 五重决战随机地图，联机沿用房号参与确定的随机种子。
- 五重联机手动开战后锁定 Auto，暂停菜单也显示锁定状态。
- 死亡使者终式 5900101 不提供五星铁钢觉醒选项。

移植本轮哈希锁定的安卓 v3 的 33 个现有方法。7 个辅助函数通过带参数转换、独立局部变量和分支重定位的字节码展开接入；
保持 iOS 原有 101071 个方法编号与方法表，不借用其他方法编号。三个新增字段追加到无子类的原类中。
724 个匿名方法信息通过相邻具名方法区间及签名匹配，目标方法的闭包布局逐项保持。

## iOS 原生实现

iOS 主 SWF 不携带可直接执行的主 ABC，运行逻辑需要 AIR AOT 原生移植。
完整编译输入由已验收 IPA 对应的完整 ABC 加本次方法生成，原生编译只抽取指定 33 个函数。
既有非目标代码、方法表、原 ABC、历史补丁、UI 与标题 CNtips_b 均保留。

本次新建 9158656 字节的只读可执行 `__LENS` 段，放置新的 stripped ABC、33 个函数及数值常量。
该段插入 `__DATA` 与 `__LINKEDIT` 之间；原 TEXT/DATA 地址、段编号、节编号及现有重定位地址不变。
LINKEDIT 只平移，原载荷完整保留，所有相关加载命令中的文件偏移同步平移。
复用已有 dyld rebase 条目更新 AOT ABC 指针与 33 个函数指针；原函数入口加跳转，兼容既有绑定调用。
SWF 只更新 20 字节 AOT 身份。交付包需要重新签名；原生布局与重签后的安装/运行仍需真机确认。

## 精确输入与成品身份

输入沿用 [已验收 iOS 登记](../ios-accepted.json) 和 [资料页累计修改方法](../ios-profile-follow/README.md)。
这是本步骤的历史输入锁，不代表以后可以回退新的已验收客户端；登记变化时脚本会拒绝继续。

| 文件 | SHA-256 |
| --- | --- |
| 输入 IPA：`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-profile-follow-self-20260908-unsigned.ipa` | `09eca214d1e73559bbc7af98d642f9056b0eeee4a44f3e09dd25f2a1e9091a43` |
| 输入完整 ABC：`F:/codex/ios-profile-follow-port-20260908/profile-full.abc` | `b374e739c7da1541182f0608f6f52c2e597efafc5133f2ecad97da819f842c4c` |
| 安卓公网 v3：仓库 `outputs/lens0907-0908-android-20260908/public-v3-final/StarPoint-CN-1.8.1-lens0907-0908-public-v3-20260908.apk` | `8e5999e2689788159362acc81cd4bcd89182966fce9af7800d085ff89dccb41b` |
| 安卓 v3 主 SWF | `ff96d39ae9dd30b7341958da0dbb19db38f557f5eb37ec9ed5284fd15f238a71` |
| 输出 IPA：`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-lens0907-0908-cdn102-20260908-unsigned.ipa` | `de28d8134e51d22f3c596869e53e90072866c17f54ec54af99b2a3fcd78dcd02` |
| 输出主程序 | `932f2b0da7a229b3c55cb5d762994a1ea28e661e3ddb08643ec11c9ec751aab8` |
| 输出主 SWF | `beef743a7da817181955badceb43fd617cb7e696279751529ed189bdbd238062` |

构建器在工作目录 `output/` 生成同一载荷的 `StarPoint-iOS-1.8.4-lens0907-0908-cdn102-unsigned.ipa`；
交付时仅文件名增加日期。包名中的 `cdn102` 记录初次资源版本，不要求把服务端降回 1.4.102。
IPA、APK、ABC、编译对象及签名材料不进入 Git。

## 构建与验证

工作目录默认 `F:/codex/work/lens-ios-20260908`，可通过 `STARPOINT_IOS_LENS_WORK` 指定新的目录。
使用当前登记 IPA 和哈希锁定的本任务安卓公网 v3；没有回退至作者包或旧版 iOS 成品。
依赖现有 AIR 51.2.1.5、LIEF、仓库 AVM2 解析器，以及此前 iOS 移植中已经验证的运行库地址映射。
完整重编译还需要以下本机材料；只克隆仓库不能直接完成 AOT 构建：

- `F:/codex/ios-rush-leaderboard-port-20260830/`：`build_ios_rush_leaderboard_ipa.py`、
  `stitch_ios_stripped_abc.py`、`runtime-helper-map.json`、`runtime-archive-members/hm-stubs.o`、
  `AIRSDK_51.2.1.5/` 和 `android-baseline/abc/` 中的 284 个依赖 ABC。
- `F:/codex/ios-rush-navigation-port-20260907/build_incremental_ipa.py`：历史功能保护范围和 ZIP 元数据复制工具。
- `F:/codex/tools/ios-re-libs/`：LIEF 等已安装的原生分析依赖。
- 上表锁定的 IPA、完整 ABC 和安卓公网 v3。输入缺失时须恢复对应材料，不能换用旧包或绕过哈希断言。

`STARPOINT_IOS_LENS_WORK` 只改变输出工作目录，其他输入和工具路径见脚本；迁移机器时需要配置这些路径。
复现时先指定全新的工作目录，保留历史报告。下面的 `F:/codex/work/lens-ios-rebuild-example` 是新目录示例，
已存在时应改用另一个空目录；`build_native.py` 会拒绝覆盖已有 IPA。

```powershell
$env:STARPOINT_IOS_LENS_WORK = 'F:/codex/work/lens-ios-rebuild-example'
python -X utf8 client-patch/ios-lens0907-0908/prepare.py
python -X utf8 client-patch/ios-lens0907-0908/compile.py
python -X utf8 client-patch/ios-lens0907-0908/resolve_helper.py
python -X utf8 client-patch/ios-lens0907-0908/build_native.py
python -X utf8 client-patch/ios-lens0907-0908/verify.py
python -X utf8 -m unittest discover -s client-patch/ios-lens0907-0908 -p test_port.py -v
```

运行顺序为输入核对与方法移植、AIR 编译、运行库辅助函数地址确认、原生增量封装、独立验证。
每一步失败后应停止，不继续使用残留的中间文件。`port.json` 保存 iOS/安卓方法编号、匿名方法映射和字段，
`output/build-report.json` 保存函数、钩子、数值常量、加载命令及重定位明细；
`output/verification-report.json` 保存独立回读结果。它们是该次生成的本地记录，不作为真机验收登记。

独立验证回读 3568 个 IPA 成员，仅主程序和主 SWF 改变；解码检查 32258 处原生重定位。
同时检查加载段不重叠、旧 TEXT/DATA 几何、dyld rebase 集合、方法表改动范围、字段和闭包布局、
未修改机器指令、原 LINKEDIT 字节、标题及原资源保持。四项展开器测试覆盖操作数栈、调用处入边、重复调用和不支持的作用域拒绝。
历史 `ios-five-in-one`、`ios-rush-leaderboard`、`ios-profile-follow` 原生差分没有与本次目标原函数范围重叠。

## 服务端配套与后续状态

初次构建配套 1.4.102，11 组 iOS 平台资源由资源增量交付。
解除本轮临时 iOS 平台限制的服务端清单修改已由 `dc3b83ae` 单独提交，
后续 1.4.103 资源与联机更新由 `06fc91ed` 等提交接续；本目录不携带第二份服务端清单。
历史部署若仍显式设置 `CN_LOCAL_CLIENT_PLATFORM=android`，须按该部署的配置流程处理。

2026-09-09 本次归档仅提交这里的六个 Python 文件和本说明，不包含 IPA 成品、验收登记变更、
暂缓的 1.4.104 文案资源、服务端同步或云服覆盖包。提交方法不等于真机验收或重新签名发布。

## 真机回归

先确认自行重签后能覆盖安装、启动、登录并更新至当前部署的资源版本，再测试两位新增角色及四项改版、五重单人/多人地图与转场、
手动 Auto 锁和暂停菜单、新武器觉醒材料。最后回归关注/取关、排行榜本人/他人资料、幻想连战、已有 MOD 和标题。
门票/体力、奖励及整轮每人一次复活由已整合的服务端处理，不在 IPA 中另设第二套规则。
