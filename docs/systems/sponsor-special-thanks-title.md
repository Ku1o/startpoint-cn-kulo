# 赞助者称号「特别鸣谢」

称号由管理员确认赞助资格后，通过后台向指定存档发放称号邮件。领取后永久拥有，可以自行佩戴；重复领取不会增加重复所有权。

| 项目 | 值 |
| --- | --- |
| 称号 ID | `9900012` |
| 内部名称 | `degree_mod_special_thanks` |
| 显示名称 | 特别鸣谢 |
| 获取说明 | 感谢您对 StarPoint CN 的支持与赞助。 |
| 分类 | `8`，其他 |
| 排序值 | `9900011` |
| 持有期限 | 永久 |

## 当前资源和数据

- 图片逻辑路径：`dynamic/degree/degree_mod_special_thanks.png`。Android 与 iOS 共用游戏存储格式的 PNG。
- 当前宽版图片为 320×50、8-bit RGBA、透明背景；普通 PNG SHA-256 为 `54c217185bb463354c8aed169746023ffa6a2b42a6fd022fc678435da66ed82a`。
- 宽版原图已包含在受版本管理的 `assets/asset-patch/active/pinball-1.4.103-1.4.104-1-abyss-lens0910-entry-message-consolidated.zip` 中。`tools/lens-integration/artwork_sources.py` 的 `read_artwork("sponsor-special-thanks/degree_mod_special_thanks_wide.png")` 可在内存中还原并校验，无需保留另一份原图。
- 包内图片成员为 `production/upload/03/076857d74f07bb194f6185d4f1c1d6061850ce`。客户端主表为 `master/degree/degree.orderedmap`，称号行使用同一图片逻辑路径。
- 服务端定义为 `assets/degree_sponsor.json`，通过 `src/lib/content-master.ts` 合入 `degreeDefinitions`，供后台校验和资料统计使用。
- 复用 `dynamic/degree/background` 和 `item/sprite_sheet` 中的 `item/etc/degree` 图标。

当前生效结果按启用 manifest 的完整资源链解析。修改称号图片时应读取当时的有效资源、核对尺寸和存储格式，再生成新的增量；不能重跑旧版本的首次发布配方。

## 后台定向发放

在后台邮件页面选择**指定存档**，填写目标 `playerId`。游戏显示的 UID 与存档 ID 不同，应先查询对应存档。

| 邮件字段 | 值 |
| --- | --- |
| 附件类型 | 称号（`13`） |
| 附件 ID | `9900012` |
| 数量 | `0`（称号协议约定） |
| 邮件标题 | 特别鸣谢 |
| 邮件正文 | 感谢您对 StarPoint CN 的支持与赞助。 |
| 发送对象 | 明确填写指定存档 `playerId` |

未填写目标时，后台通用接口会群发。此称号使用定向邮件，不定义最低赞助金额、自动支付回调、商店兑换或登录赠送。

## 已退役的首次发布流程

旧窄版原图及其未启用候选包已淘汰，不再作为当前制作输入，也不保留额外恢复副本。以下入口停止发布操作：

- `publish_sponsor_special_thanks.py`：保留称号定义、行合并和 PNG/ZIP 校验函数，供其他资源工具及测试复用。
- `publish_sponsor_title_wide_local_test.py`：保留被其他工具导入的 JSON、哈希和文件辅助函数。
- `build_abyss_sponsor_laite_candidate.py`：旧候选配方退役。

历史审计中的称号定义和客户端字段仍由回归测试使用，继续保留；其中的旧图片路径、旧候选包和旧镜像同步记录不构成当前运行或恢复依赖。

## 回归入口

- `test_sponsor_special_thanks.py`：称号行保留、重复 ID 拒绝、PNG 存储格式和 ZIP 回读；图片输入取自当前维护的宽版资源包。
- `tests/sponsor-degree.test.js`：服务端主数据、定向领取、佩戴和持久化。
- `test_artwork_sources.py`：按固定包和成员读取原图的完整性及显式输入覆盖。

离线资源校验与实际设备显示、云端部署是不同的验收范围。
