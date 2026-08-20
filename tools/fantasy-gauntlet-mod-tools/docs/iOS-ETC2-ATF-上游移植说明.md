# iOS ETC2 cut-in 自动生成：上游移植说明

> 面向 `startpoint-cn-mod-tools` 上游维护者。实现于 2026-08-20，并已通过真实 iOS
> 设备的史黛拉 cut-in 下载与加载验证。

## 问题

工具原先只在 `android_upload` 生成角色 `skill_cutin_{0,1}.atf.deflate`。iOS 客户端会按
相同逻辑路径和哈希转向 `ios_upload`，因此 Android-only 的 active 增量包在 Android
正常，却会让 iOS 在接触该角色资源时进入资源不足/恢复流程并退出。

把 Android 文件原样复制到 `ios_upload` 不是可靠修复。两端使用同一个逻辑路径哈希，
但 ATF 平台槽和纹理布局不同：

| 平台 | store | ATF 槽 | 纹理布局 |
|---|---|---:|---|
| Android | `android_upload` | 2 | ETC1 颜色流 + ETC1 灰度 alpha 流 |
| iOS | `ios_upload` | 3 | ETC2 RGBA；每个 4×4 块为 EAC alpha 8B + ETC1-compatible color 8B |

## 实现原则

1. `skill_cutin_*.png` 是唯一源文件。
2. Android ETC1 与 iOS ETC2 必须从 PNG 分别编码，禁止一端复制另一端。
3. 两端使用相同的 `sha1(逻辑路径 + 盐)` 相对路径，只写入不同 store。
4. active 仍是一个 ZIP，ZIP 内同时携带 `production/android_upload/...` 和
   `production/ios_upload/...`。
5. `manifest.json` 保持既有 patch 结构，不新增 `platforms`、`archive_integrity` 等
   私有字段；`files` 记录 ZIP 内完整 `production/...` 成员路径。
6. 找不到源 PNG、无法由哈希反查逻辑路径、平台槽错误、两端尺寸/mip 不一致或两端
   字节相同时全部 fail closed。

## 代码落点

- `wf_atf.py`
  - 新增 EAC alpha 编解码验证工具；
  - 新增 iOS ETC2 RGBA ATF(slot 3)构建；
  - 新增 Android/iOS 平台对校验和一源双端生成入口；
  - `parse_atf` 增加边界、槽位一致性和尾部数据检查。
- `wf_assets.py`
  - 资产根增加 `ios_upload`。
- `wf_gui.py`
  - 上传 cut-in PNG 时同时生成并登记 Android/iOS ATF；
  - Android 模拟器同步会跳过 iOS 文件，并保留整套待发布清单，避免发布时丢失配对。
- `wf_publish.py`
  - pending 支持 `ios:`；
  - Android cut-in 进入待发集合后，从 medium/upload 中查找源 PNG，在内存生成 iOS；
  - 同一 active ZIP 写入两端同哈希成员；
  - 回读 ZIP，拒绝目录项、重复成员、成员/字节不一致和 CRC 错误；
  - manifest 自动更新 `files`、`archive_size`，并保持旧格式。
- `wf_kyle_canary.py`、`wf_final_state_guard.py`、`wf_publish_guard.py`
  - 把 iOS 根纳入事务快照、最终态识别和 pending 过滤。
- `tests/test_atf.py`、`tests/test_ios_publish.py`
  - 覆盖编码质量、槽位、平台对、禁止 Android copy、缺 PNG 失败、同包成员、ZIP
    结构、manifest 旧格式和模拟器同步保留 pending。

## 发布流程

```text
用户上传 skill_cutin PNG
  ├─ PNG 混淆后写 medium/upload
  ├─ 从 PNG 编码 Android ETC1 ATF → android_upload/<same-hash>
  └─ 从 PNG 编码 iOS ETC2 ATF     → ios_upload/<same-hash>
             ↓
pending: medium:/android:/ios:
             ↓
wf_publish 发布前重新从 PNG 生成并校验 iOS
             ↓
一个 active ZIP + 旧格式 manifest.files 完整路径
```

发布器再次生成 iOS 是有意设计：GUI 负责即时产物，发布器负责最后一道 fail-closed
保证。即使 pending 来自旧角色包或脚本，只要 Android cut-in 与源 PNG 存在，最终 ZIP
也会自动补齐正确的 iOS 文件。

## 兼容性与移植建议

- 不需要修改服务端下载 API，也不需要按平台拆成两个 ZIP；客户端自己根据设备平台选择
  ZIP 内的 `android_upload` 或 `ios_upload` 成员。
- 旧 pending 的 common/medium/android 写法保持兼容；`ios:` 只是新增内部定位前缀。
- 官方基础数据的 `wf_store_materialize.py` 仍可保持三根不可变快照契约；`ios_upload`
  由 cut-in 编辑流程按需创建，或直接由 active 增量下发，不要求新增
  `archive-ios-full` 基线目录。
- 现有角色包 schema 可以不立即增加 iOS root：发布器会从包落下的 Android ATF 与 PNG
  自动派生 iOS。若未来希望角色包本身长期保存预生成 iOS，再单独升级 schema。
- 不建议静默跳过无法识别的 Android cut-in。宁可停止发布并要求补源 PNG，也不要生成一份
  Android 正常、iOS 进游戏退出的包。

## 验证结果

- 单元测试验证 Android slot 2、iOS slot 3、EAC alpha、同尺寸/mip 和不同字节。
- 史黛拉实包验证两个 cut-in 哈希在同一个 ZIP 中均存在 Android/iOS 成员，ZIP 无目录项。
- 真实 iOS 设备已成功下载并加载该 active 增量资源，原资源不足退出路径不再出现。

上游合入时建议以 `wf_atf.py` 和 `tests/test_atf.py` 为第一组提交，再合 GUI/发布器与
`tests/test_ios_publish.py`，便于分别审核编码格式和发布策略。
