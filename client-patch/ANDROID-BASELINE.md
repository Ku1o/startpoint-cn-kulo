# Android APK/SWF：新会话从这里开始

2026-09-06，用户明确确认本会话的最终公网、内网 APK **全部验收通过**，包括关注按钮、本人资料跳转和标题 `CNtips_b` 隐藏。当前成品身份统一登记在 [android-accepted.json](./android-accepted.json)，不再依据历史 README 中的“最新”字样挑选 APK。

## 当前直接基线

| 环境 | 已验收 APK（相对仓库根目录） | 地址 |
| --- | --- | --- |
| 公网 | `outputs/rush-leaderboard-self-profile-title-public-20260906/StarPoint-CN-1.8.1-self-profile-title-public-20260906.apk` | `http://175.178.160.158:8001` |
| 内网 | `outputs/rush-leaderboard-self-profile-title-lan-20260906/StarPoint-CN-1.8.1-self-profile-title-lan-20260906.apk` | `http://<LAN_HOST>` |

在仓库根目录运行只读检查：

```powershell
python client-patch/verify_android_baseline.py --variant public
python client-patch/verify_android_baseline.py --variant lan
```

检查器读取 JSON 中的明确路径，核对 APK SHA-256、内嵌 SWF SHA-256、manifest UUID 及验收状态；不会扫描其他 APK 作为替代。成品放在其他位置时，可以显式传 `--apk`，仍须匹配同一份成品哈希。这里的身份检查不替代新包交付前的签名和对齐检查。

仓库禁止硬编码个人内网 IP，`<LAN_HOST>` 表示包含端口的内网地址。已在本机忽略目录
`outputs/android-build-local.json` 保存 `lan_host`，新会话直接读取即可；公开记录保存地址摘要以核对一致性。
涉及地址切换的三个脚本按 `--lan-host` → `STARPOINT_LAN_HOST` 环境变量 → 本机配置的顺序取值。
换电脑时一并携带这份本机配置；不要把它提交 Git，也不要把现有 APK 的内网地址当作通用默认值写回脚本。

Git 保存修改方法和验收身份；APK 二进制仍保存在本机 `outputs`。换电脑时须另行取得这份精确已验收包。只克隆源码无法凭空得到 APK，找不到时不能回退到旧版。

## 本会话保留的修改

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

r12b、V51、8 月 6 日包、没有标题隐藏的本人资料 v2、关注诊断包均不是当前直接基线。历史步骤中的精确输入约束保留用于复现，不等于允许丢失其后的修改。

## 后续修改完成时

1. 先确认当前基线身份，从实际 APK 提取 SWF，只修改本次所需方法。
2. 回读最终 SWF，检查变化集合与预期一致，确认上表和历史累计功能仍在。
3. 使用新 UUID 回封，核对 APK 其他成员、包名和版本身份、ZIP 对齐、v1/v2 签名及固定证书。密码只在签名进程内从本地 DPAPI 凭据加载。
4. 用户验收后更新 `android-accepted.json` 的路径、APK/SWF 哈希、UUID 和验收依据，同时维护脚本与本页。这一步让下一个会话接上最新进度。
5. 不通过整目录同步交付 APK 方法，不改 IPA；提交只包含明确授权的源码和文档。
