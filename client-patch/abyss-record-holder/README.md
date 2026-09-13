# 深渊全服纪录保持者昵称（2026-09-12 本地试用）

后续状态：用户已验收本页 LAN 原件并恢复发布。当前基准和公网派生件见 `../ACCEPTANCE-RECORD-HOLDER-20260912.md`；iOS 对应候选见 `../ios-record-holder/README.md`。下文保留本次试用交付时记录。

在关卡详情现有“本期全服最快”用时下增加“纪录保持者：昵称”。本次基于用户已验收的入手来源文件夹修正 APK，保留其全部累计修改；只替换 `cn.ui.AbyssRecordDetails.responseText`（288:1）的方法体。

## 行为与边界

- 服务端 `/abyss-records/:questId` 的成功响应增加 `holder_name`。通过纪录原有 viewer ID 对应的账户公开资料解析当前默认玩家昵称，与公开个人资料身份规则一致；不使用全局当前选中的存档，也不返回账户、玩家或 viewer ID。
- 已有纪录可以直接显示昵称，无需重刷。改名后返回当前公开昵称；同分保持原纪录；身份不存在时保留用时并显示“未知玩家”。客户端缓存仍为 10 秒。
- 客户端将昵称中的控制字符换为空格并转义 HTML，空纪录、旧客户端版本提示和接口失败提示维持原行为。旧服务端没有昵称字段时显示“未知玩家”。
- 本次没有数据库结构、存档格式、结算及换塔重置规则变更，不需要新 CDN 增量，也没有改动 `.106` 分包或 manifest。

## 试用产物

- APK：`outputs/abyss-record-holder-lan-test-20260912/StarPoint-CN-1.8.1-abyss-record-holder-lan-test-20260912.apk`
- APK SHA-256：`e04b9e4f367be0ee447f1cfc8f45ff314fafc4a2df7efcef03db120347278f32`
- SWF SHA-256：`c5fcc853a10db415fc898d24ac940dc59a2ee1c886e7cff9544fd6a0ba661559`
- 新 AIR UUID：`eeb1d3e6-eb89-47d6-887a-419ad6d063e3`
- 父 APK SHA-256：`e79f6abcde6ce9286023689a876173a8bb9d8ed2583aee06a11a6b128e91674e`
- 构建目录：`F:/codex/work/abyss-record-holder-20260912/apk-build`。

## 验证和本地同步

`npm run build`、5 项服务端纪录测试、4 项昵称格式化测试通过。格式化测试执行从 AS 源码提取的函数，不代替 AVM2 或手机界面验收。独立方法比对确认 96,535 个方法体中仅 288:1 变化；原生代码、AIR 身份、签名证书、ZIP 对齐及 APK 成员回读验证通过。

已备份并同步以下四个文件到 `F:/startpoint-cn-main`，逐一核对字节：

- `src/data/domains/abyss-records.ts`
- `src/routes/cn/abyssRecords.ts`
- `out/data/domains/abyss-records.js`
- `out/routes/cn/abyssRecords.js`

备份：`F:/startpoint-cn-main/.codex-backups/20260912-213415-abyss-record-holder`。重启后服务 PID 为 19164、端口 8001（交付时状态）。实际 HTTP 返回深渊第 1 关已有纪录 22,185 毫秒及非空昵称，未返回身份私有字段，旧资源版本仍被拒绝。没有插入演示纪录或修改真实玩家存档。输出目录保存 `verification.json`、`local-sync.json`、`live-verification.json` 和 `SHA256.txt`。

## 验收与发布状态

昵称版尚待用户手机验收，未晋升 accepted 注册表。用户要求先验收本次效果，再继续之前的提交、公网 APK、云服整合包和 iOS 工作；这些发布步骤保持暂停。之前已生成的 `item-source-records-public-20260912` 公网 APK 不含昵称功能，后续发布必须基于最终验收的累计版本重新生成，不可直接作为昵称版交付。
