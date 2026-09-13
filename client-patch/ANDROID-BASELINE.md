# Android APK/SWF：新会话从这里开始

2026-09-13，用户认可商店优化 LAN 版效果，并授权制作公网版、验收及提交。当前身份见
[android-accepted.json](./android-accepted.json)，范围见 [商店优化验收](./ACCEPTANCE-SHOP-FIRST-OPEN-20260913.md)。
登记为 `accepted_offline`：保留用户 LAN 商店反馈，公网派生包未独立真机测试。

## 当前直接基线

| 环境 | APK（相对仓库根目录） | 状态 |
| --- | --- | --- |
| 公网 | `outputs/shop-first-open-public-20260913/StarPoint-CN-1.8.1-shop-first-open-public-20260913.apk` | 用户授权离线验收，从已测试 LAN 转换 |
| 内网 | `outputs/shop-first-open-lan-test-20260913/StarPoint-CN-1.8.1-shop-first-open-lan-test-20260913.apk` | 用户反馈商店卡顿明显减轻；离线身份与累计方法已核验 |

主 ABC 291，共 96543 个方法体。商店新增活动商品成员索引及存在性短路，同时包含觉醒任务响应后
角色、等级与页签即时刷新。保留昵称、入手来源文件夹、缓存、圆角、切队 F1009、登录和全部既有累计功能。
不包含共斗加载改造；服务端觉醒和称号查询修复仍单独待交付，不因安装 APK 生效。

旧昵称注册表按原字节保存在 `accepted-history/android-record-holder-20260912.json`。
历史构建器只复现其精确输入；新功能从当前注册表继续。
iOS 使用独立已验收注册表，商店移植候选须等用户验收后再提交，不能直接套用 Android 原生布局。

在仓库根目录执行只读身份检查：

```powershell
python client-patch/verify_android_baseline.py --variant public
python client-patch/verify_android_baseline.py --variant lan
```

检查器核对明确登记的 APK、内嵌 SWF、DEX、大小及 AIR UUID，不扫描其他 APK 作为替代。
需要验收输入位于其他位置时，可用 `--apk` 指定，但必须匹配原件哈希。签名和 ZIP 对齐另由制作入口核验。

个人内网地址只存在忽略的 `outputs/android-build-local.json`，公开记录使用 `<LAN_HOST>` 与摘要。
不要把具体个人内网 IP 写进源码。Git 保存制作代码与身份，APK/SWF 二进制留在本机 `outputs`；
换电脑必须取得精确成品，不能因为缺失而回退旧版。

## 深渊续战与 Lens 累计内容

9 月 9 日续战步骤仅对活动 `700099` 放开续战队伍的跨关角色复用；每关返回独立空数组，逐关选队、其他活动的重复检查保持。该历史步骤只改 `284:24599`（当前内网为 `286:24599`），方法见 [深渊续战](./abyss-autostart/README.md)。

当前包在下表的资料页和标题修复上加入 724 Fever、422 冲刺参数完整解析/描述/战斗逻辑、
稻穗 PF 连击数、基诺维冲刺、五重决战随机地图与联机房号种子、手动开局后的 Auto 锁、
5900101 禁止铁钢替代觉醒材料。详见 [Lens 方法](./lens0907-0908/README.md)。
两个错误续战测试包遗漏这批内容，已经明确排除；当前成品已从 Lens v3 重新移植，并完成全方法与基诺维解析保护检查。

9 月 10 日内网步骤保留属性通道 21496、详情 71835/78350、Lens 0910 四方法及三个 HUD 状态槽；该历史包主 ABC 为 286，原方法总计 96,422。下面的 284 是历史容器序号，方法体索引不变。

## 9 月 6 日累计修改（继续保留）

| 方法 | 最终行为 |
| --- | --- |
| `PlayerProfileView.refreshFollowRelationButtons`，`284:79085` | 保持服务端四态含义，直接控制 `follow_button` / `remove_button` 可见性；未关注显示关注，已关注显示取消关注。 |
| `OtherProfileLogic.applyButton`，`284:79222` | 对旧取消按钮帧补充按真实关系分派动作：状态 0/3 发起关注，1/2 取消关注。 |
| `RushEventRankingPartyScene.copyPlayedParty`，`284:71120` | 用 `globalLogic.getPlayer().get_viewerId()` 比较行 ID；本人走 `ProfileGetMyProfile`，他人走 `ProfileGetProfile(row.id)`，返回排行榜。 |
| `TitleView.refreshHealth`，`284:82510` | 两种提示状态均隐藏 `CNtips_b`，保留 `CNtips_a` 及底部版本信息。 |
| `DevConfig_gf_android.<constructor>`，`284:92013` | 公网/内网地址切换。每个不同 SWF 同时更换 AIR UUID。 |

细节、各步输入身份和脚本入口见 [TITLE-CNTIPS.md](./rush-leaderboard/TITLE-CNTIPS.md)。服务端真实 ID、资料和关注持久化配套修改已由“修复深渊竞速池角色兑换”接手，并随 `f348ee94` 提交；不要用客户端伪造关系替代服务端数据。

## 以前的累计功能也必须保留

- MOD 五合一：免登录、私服重定向、深渊装备限制、赛瑞斯双形态、逐角色缩放。
- 幻想连战：活动路由、战斗判定、结算返回、队伍和装备图标缓存及生命周期修复。
- [角色编队轮播优化](./character-carousel/README.md)、[通用 Rush 排行榜与资料导航](./rush-leaderboard/README.md)。
- [标题及游戏内数据继承入口](./account-takeover/README.md)、[深渊装备与能力魂副本限制](./abyss-mode-equipment/README.md)。

9 月 6 日标题包、r12b、V51、8 月 6 日包、没有标题隐藏的本人资料 v2、关注诊断包及两份 9 月 9 日错误续战测试包均不是当前直接基线。历史步骤中的精确输入约束保留用于复现，不等于允许丢失其后的修改。

## 后续修改完成时

1. 先确认当前基线身份，从实际 APK 提取 SWF，只修改本次所需方法。
2. 回读最终 SWF，检查变化集合与预期一致，确认上表和历史累计功能仍在。
3. 使用新 UUID 回封，核对 APK 其他成员、包名和版本身份、ZIP 对齐、v1/v2 签名及固定证书。密码只在签名进程内从本地 DPAPI 凭据加载。
4. 用户明确验收或要求执行验收后，按实际证据更新 `android-accepted.json` 的路径、APK/SWF 哈希、UUID 和验收范围，同时维护检查器与本页。离线通过与真机反馈分开登记，历史构建报告保持原样。
5. 不通过整目录同步交付 APK 方法，不改 IPA；提交只包含明确授权的源码和文档。
