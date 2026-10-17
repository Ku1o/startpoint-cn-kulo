# Android R4 基线撤回与旧正式基线恢复（2026-10-17）

2026-10-17 撤回 Android R4 作为后续开发基线，恢复 2026-10-02 内网与由其直接转换的 2026-10-04 公网成品。R4 存在已确认的加载回归：排队文件流取消/关闭未保留原完成语义、Context3D 恢复标记延后导致合成背景漏重试、轻量解码受重阶段数量预算限制。基线回退采用此前正式输入，不继续以 R4 或其局部修复候选接续开发。

本次选择登记在 [android-accepted.json](android-accepted.json) 的 `baseline_selection`；原 `accepted_on`、每变体验收层级和历史记录保持。选择日期不是重新进行设备验收的日期。本记录不改变 iOS 当前登记和成品。

## 当前精确输入

| 项目 | 内网 | 公网 |
| --- | --- | --- |
| 原验收日期 | 2026-10-02 | 2026-10-04 |
| 原验收层级 | `user_accepted` | `accepted_offline` |
| APK SHA-256 | `4f62b899a89b0648f79d0dbaf20d8aab9b64ad91959d91706dc71af02cb6c335` | `cd840c201cf6436e38b2e92ebe0dad4d66b9bce8eff04a2418e123648b77c508` |
| SWF SHA-256 | `9418137820c007b52a11ad0d7955c102795d8dd903213670577bf3407ed709f7` | `59802822cd25336e8478ca82a57c3c9d4c225f7f026f0ba805fa39db8a20376d` |
| AIR UUID | `4728fb03-7242-4fcc-9bc4-e8b4fc073a43` | `92f713a5-7de2-44b3-8357-56082e4f8a04` |
| 地址表示 | `http://<LAN_HOST>:8001` | `http://124.222.203.221:8001` |

回退同时恢复旧版每 600 秒在运行期清理限定 AIR 缓存的原有策略；R4 的“仅标记、下次冷启动清理”逻辑随 R4 实现一并撤销。本次不另改旧缓存策略。

两份原 APK 路径、DEX 身份、包名版本、原准入 ID 和签名证书约束从登记 `variants` 读取；不重新生成包或分配缓存身份。两变体沿用实际准入 ID `android-181-author-1047-public-20261001`。内网的原设备确认与公网的原离线转换身份分别保留，不新增手机性能、偶发冻结率、长战或公网设备验收结论。

登记结构与成品身份恢复自 `6c6a3930^` 中的 `client-patch/android-accepted.json`，另加本次选择和撤回记录；没有整份恢复过时的早期 Android 文档。累计内容仍以 [当前基线说明](ANDROID-BASELINE.md)、[10-02 内网验收](ACCEPTANCE-OROCHI-RESCUE-BELL-C8016-CACHE-20261002.md) 与 [10-04 公网验收](ACCEPTANCE-OROCHI-RESCUE-BELL-PUBLIC-20261004.md) 为依据。

## ABC 索引口径

实际读取两份旧 SWF，均为 300 个 DoABC，`boot_ffc6` 的零基 DoABC ordinal 为 `299`，零基原始 SWF tag index 为 `362`，没有 R4 新增的 5 个 helper ABC。登记使用 `main_abc_index=299`、`main_abc_index_kind=zero_based_DoABC_ordinal` 与 `main_abc_raw_tag_index=362`。历史 `main_abc_index=361` 保留为历史值说明，不用它定位方法；它既不是 DoABC ordinal，也不等于当前解析器的原始 tag 索引。

96706 是旧基线原方法体比较数。DoABC ordinal、SWF 原始 tag index 和方法体编号分别记录，不混用。

## 已撤回与未采用输入

- R4 内网 APK `b42f52a6552cf989f9998b62f23fd291a23913901a1961e7d6b88570a1e66398`、公网 APK `2d4a9254548cf80effbce87a45d5bd28accb7f2e784ee68e31340bf92d365024` 已撤回，不再作为开发基线。旧实包和 [10-14 历史验收正文](ACCEPTANCE-CLIENT-R4-20261014.md) 保留用于复现，禁止默认选入；原日期和当时离线记录不删除、不解释为当前认可。
- 2026-10-16 R4 加载修复测试候选 r2 未采用。其 APK SHA-256 为 `ac341aeb15df4961eeadd03b92cb47891d0e16539a410c75609fa7a0a255875d`，SWF SHA-256 为 `1682117a9d64d0b248b959f25e62270f36462018eb961677254594eaac7e02c5`；已有受控 AIR 与离线检查不等于手机验收，不把它写入当前 `variants`。这里的“加载修复 r2”与 10-14 历史准入配置 r2 是不同对象。
- R4 的历史构建与 expected 清单按历史提交 `6c6a3930` 定位，不作为当前构建入口；Q1/Q2/Q3 和其他未采用优化也不作为后续输入。

## 源码撤销范围

撤销 `46095b26`、`8e92d698`、`a0a19d94`、`a4f822ea`、`66aac625`、`0bc7e804` 六个实现提交引入的 R4 活动实现与构建入口。`545d71b2` 的 quiet 公共工具、旧 `startup-cache` 实现以及其他服务端、CDN、iOS 内容保留；本次不以删除历史成品或历史验收正文代替撤销活动实现。

## 后续入口

实际选择或修改 Android 输入时，按 [client-patch 工作入口](AGENTS.md) 读取当前 `variants` 并运行对应的既有基线检查器。本次记录只恢复当前指针并保留历史；未检查当前云服准入名单或进行本轮云端 HTTP 验证。旧 `acceptance.public_admission_http_verified=true` 仅保留 2026-10-04 的历史验收记录。云服允许名单、设备安装版本和部署状态需要各自的实际记录证明，不能从历史包已生成或本次 Git 变更推断。
