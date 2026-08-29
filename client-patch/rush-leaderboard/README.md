# Rush 连战排行榜客户端补丁

本补丁只允许以下列已经验收的角色轮播优化 APK 为基线：

- APK：`outputs/StarPoint-CN-LAN-1.8.1-character-carousel-optimized-final-20260829.apk`
- APK SHA-256：`FA45B7727B638ACCFDEB133E7E47EB3612B54AF614D6C8DA2001FDB60B603CCF`
- 内嵌 SWF SHA-256：`E3E6CDC8D9A5D93A297912C571BEF58239EFB50F7B77132CF1768AD5A4260475`
- 原 `uniqueappversionid`：`808339e8-8e32-42f5-9a1a-d66cc876d4bb`

不要改用旧 LAN APK、分享 APK 或 AB 诊断包；否则会丢失已经过实机验收的
`PartyCarousel.update` 优化。

## 客户端协议与界面

客户端复用官方 Rush 排行榜页面、按钮和列表素材，通过独立的
`/event/rush/leaderboard` 读取同一套服务端驱动协议：

- `enabled/name`：活动是否已经登记排行榜，以及排行榜/报酬正文使用的活动名称；

- `rows`：最多显示前 500 名，每页 100 人；
- `item/page/row/index`：供“我的排名”定位，500 名外时追加一条只给本人看的行；
- `time/total`：显示更新时间和真实参赛人数；
- `reward`：在客户端生成“报酬一览”，不借用全局服务条款页面。

所有 Rush 活动共用这套客户端逻辑。服务端已登记的活动返回 `enabled=true` 和实际数据；尚未登记的
活动也返回 HTTP 200、`enabled=false`、空榜及“排行榜暂未开放”，不再使用 H404。以后给幻想连战
开放排行榜时，只需在服务端登记活动范围、显示名称、赛季和奖励配置，不再修改 SWF。

专用请求复用官方 `EventRushRewardRealRemote`：正常正数 `eventId` 仍访问原生
`event/rush/reward`；排行榜场景内部传负数作为私有标记，remote 在发出请求前恢复正数并改走
`event/rush/leaderboard`。这样无需新增参数、方法或字段，也不影响普通 Rush 报酬领取。

## 二进制构建约束

`patch.py` 对基线新导出的 9 个类做 SHA-256 校验，修改 7 个类的 15 个既有方法。
`TermsOfServiceLoadingTask` 与 `ToolAgreementRealRemote` 保持逐字节不变。

`build_apk.py` 的完整类替换结果只作为临时 carrier：

1. 从 carrier 导出目标类 P-code；
2. 切出 `METHOD_PATCHES` 声明的 15 个既有方法；
3. 在干净基线中重新定位 ABC/方法体索引；
4. 逐个使用 FFDec `-replace <pcode> <methodBodyIndex>` 移植方法体；
5. 用 `CompareMethodBodies` 要求最终变化集合与这 15 个索引完全相等。

当前服务端驱动修复以前一版深渊专用候选 SWF 为中间参照，只移植取消客户端活动硬编码、读取
`enabled/name` 和动态奖励标题实际涉及的 5 个方法。最终 APK 仍回封到批准基线，并同时要求
“相对参照只变 5 个方法、相对批准基线仍只变上述 15 个方法”。

绝不能把 carrier SWF 直接回封。当前权威基线的已验证变化集合是：

```text
changed_count=15
changed=284:48482,284:48484,284:71113,284:71115,284:71120,284:71122,284:71123,284:71132,284:71143,284:71162,284:71163,284:71167,284:71189,284:71203,284:71207
```

基线与成品中的 `PartyCarousel.update` 均为 `abc=284`、`body=66481`，不在变化集合中。

## APK 回封与签名

构建器会调用 `client-patch/character-carousel/repack_apk_with_unique.py`，为每个不同 SWF
生成全新的 `uniqueappversionid`。它还会回读 SWF/UUID、校验 ZIP 成员保持、执行
`zipalign -c -p 4`，并验证 v1/v2 签名和固定证书指纹。

签名密码只能由仓库规定的 DPAPI 凭据在构建进程内注入环境变量；不要把密码写入参数、日志、
文件或仓库。构建器不会安装 APK，设备覆盖安装和真机验证由用户执行。

2026-08-29 已完成真机验收的通用 Rush 成品（文件名保留构建时的 `final-candidate`，身份以下列哈希为准）：

- APK：`outputs/rush-leaderboard-character-carousel-generic-rush-final-candidate-20260829/StarPoint-CN-LAN-1.8.1-character-carousel-rush-leaderboard-generic-rush-final-candidate-20260829.apk`
- APK SHA-256：`07C316413E4E3F99DFF83C52A5000F03ECBD466E76D5BC9F29FCD0884072DE09`
- 内嵌 SWF SHA-256：`A354037C593F77773B3A0A18841FE4501CF55C1128BB1F89B0E47AD799DCFBA60`
- `uniqueappversionid`：`690fdca8-a0cf-4bf8-9241-733bcc7ed124`
- 签名证书 SHA-256：`569D19A3578D4CBA16E3D6E7AD8CCAB4FA667EFC758DEEF6C9BE3ADB99919894`
- 验证报告：`outputs/rush-leaderboard-character-carousel-generic-rush-final-candidate-20260829/verification-report.json`

旧候选 `7010325E...F25CEF` 在排行榜按钮中错误地把 `ChangeSceneNextKind`
传给只接受 `LoadingTaskKind` 的 `changeSceneWithLoading`，实机触发 `TypeError #1034`，不得继续使用。
类型修复候选 `A5ED7A...9DBEE` 已能进入排行榜，但“报酬一览”缺少官方富文本要求的
`html/body` 外壳，实机触发 `C7606`，同样不得继续使用。当前候选保留类型修复，并为奖励正文
补齐外壳并把富文本页标题键改为实际显示“报酬一览”的 `quest_detail_reward`。此前将入口硬编码为
深渊连战事件 `700099` 的候选也已被本通用候选取代。相对该候选只改变 5 个方法体：
`284:71120,284:71122,284:71189,284:71203,284:71207`，客户端不再保存活动 ID 白名单，
并使用新的 `uniqueappversionid` 防止 AIR 复用旧 SWF。

用户真机已确认：排行榜可进入并显示成绩，队伍头像不再为黑块，“报酬一览”可打开，深渊连战
通关与结算正常，奖励已调整为第1名/第2～3名/第4～15名分别发放10/5/2张 `999016`，第16名起
发放1张 `999015`。在当时，该 APK 是下一次 Android SWF 修改的唯一直接基线；后继不得回到角色
轮播 APK 重复构建排行榜，也不得从上述失败候选继续。

该“下一次基线”规则已在 2026-08-30 完成一次合法后继：当前最新权威基线是
[`../account-takeover/README.md`](../account-takeover/README.md) 登记并通过真机验收的公网继承版，
APK SHA-256 为 `0C7BBA3D8E2EF07B8AC9E98B11AAF257008A0B373950FD98332047C727064857`，SWF SHA-256 为
`7EEA1972F568E31CE5B708E057EB7FEF306E2B25BA5CF7C6A198557914623CA7`。今后新增 Android SWF
修改必须直接从该公网成品开始；本页的通用 Rush APK只作为累计重建的精确前序基线。

## 后续修改与提交顺序

1. 从上面已验收 APK 提取实际 SWF，并回读 APK、SWF、UUID 与签名证书哈希；
2. 重新定位目标 ABC/方法体，只通过临时 carrier 导出 P-code，再移植到干净的直接基线；
3. 每个不同 SWF 使用全新 `uniqueappversionid`，绝不复用
   `690fdca8-a0cf-4bf8-9241-733bcc7ed124`；
4. 回封后验证实际载荷、变化方法集合、ZIP 成员、zipalign、v1/v2 签名与固定证书；
5. 只生成本地测试候选，不擅自安装；由用户覆盖安装并完成相关页面、战斗和返回路径测试；
6. 用户明确验收后，才把该候选登记为新的权威基线并提交文档与可复现构建器。失败候选仅保留在
   本地排查材料中，不提交、不作为后继基线。
