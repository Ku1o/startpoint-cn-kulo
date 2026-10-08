# 赞助者称号「特别鸣谢」

用户于 2026-09-09 选定 B 款「锦绣中国结」，并确认以下方案。美术原稿保持原比例居中，正式 PNG 画布为 320×50、8-bit RGBA、透明背景。

| 项目 | 值 |
| --- | --- |
| 称号 ID | `9900012` |
| 内部名称 | `degree_mod_special_thanks` |
| 显示名称 | 特别鸣谢 |
| 获取说明 | 感谢您对 StarPoint CN 的支持与赞助。 |
| 分类 | `8`，其他 |
| 排序值 | `9900011` |
| 持有期限 | 永久 |
| 获得方式 | 管理员确认赞助资格后，通过后台向指定存档发放称号邮件 |

本功能不定义最低赞助金额或自动支付回调；资格由管理员确认。没有自动任务、商店兑换或登录赠送。

## 资源和数据

- 原图：`assets/asset-patch/artwork/sponsor-special-thanks/degree_mod_special_thanks.png`，SHA-256 为 `c2c4d06e1b386abfcf11a15a23ac2c72a01617fbed02c4a1d4cfca88ed0354ff`，与用户选定的 B 成品字节一致。
- 客户端图片：`dynamic/degree/degree_mod_special_thanks.png`。发布时通过 `wf_assets.png_encode` 转成游戏存储文件头，严格解码后与原图完全一致。
- 客户端主表：`master/degree/degree.orderedmap`，仅追加 `9900012`，保留原有 1496 行的顺序及压缩字节。
- 服务端定义：`assets/degree_sponsor.json`，通过 `src/lib/content-master.ts` 合入实际 `degreeDefinitions`，同时供后台 ID 校验和资料统计使用。
- 复用 `dynamic/degree/background` 及已存在于 `item/sprite_sheet` 的 `item/etc/degree` 20×20 图标，无需增加图集帧。
- 两个平台共用 `production/upload` PNG 和主表。本次不修改 APK、IPA、SWF 或平台专用纹理。

## 后台定向发放

在后台邮件页面选择**指定存档**，填写目标存档 ID；不要把游戏显示的 UID 直接当作存档 ID。若先拿到 UID，先在后台查出对应存档。

| 邮件字段 | 值 |
| --- | --- |
| 附件类型 | 称号（`13`） |
| 附件 ID | `9900012` |
| 数量 | `0`（称号协议约定） |
| 邮件标题 | 特别鸣谢 |
| 邮件正文 | 感谢您对 StarPoint CN 的支持与赞助。 |
| 发送对象 | 明确填写指定存档 `playerId` |

后台原有通用接口在未填写目标时会群发，发放此赞助称号时应使用指定存档。当前改动不改变其他邮件的群发功能。

收件人领取后才永久拥有称号，可以自行佩戴；不会强制替换当前称号。重复邮件不会增加重复所有权。未拥有者不能佩戴，其他玩家查看资料时会收到佩戴的同一称号 ID。

## 本地 CDN 版本与暂缓改动

本任务在实际本地尾版 `1.4.104` 后追加 `1.4.105`。补丁为 `assets/asset-patch/active/pinball-1.4.104-1.4.105-1-sponsor-special-thanks-cn.zip`，只含称号主表与 PNG 两个成员。审计目录为 `assets/asset-patch/audit/sponsor-special-thanks-1.4.105/`。

以下直接下载文件已在源工作区生成，字节与 ZIP 成员相同。这些生成路径被 Git 忽略，后续交付应从已提交并校验过的补丁 ZIP 中还原，不可遗漏，也不可从混有其他任务改动的生成目录整体复制：

- `assets/asset-patch/production/upload/03/076857d74f07bb194f6185d4f1c1d6061850ce`：称号图片。
- `assets/asset-patch/production/upload/89/e5c25c791e2a9527422c186084a1793218c2ac`：称号主表。

前一条 `entry-condition-message-1.4.104` 是其他任务的暂缓提交成果。它和所有既有清单条目均保持不变；本任务未授权发布、同步或打包它。将来发布本称号前，必须单独处理该暂缓版本的发布决定与版本依赖，不能直接把整个工作区清单提交或部署。审计中的 `manifest-entry.json` 单独保存本称号条目。

历史构建入口 `tools/fantasy-gauntlet-mod-tools/publish_sponsor_special_thanks.py` 锁定本次清单、主表和 B 图片的前像；不应在未来更新链上直接重跑。任务前像备份位于 `F:/codex/work/sponsor-thanks-title-20260909/before/`。

## 验证与交付边界

资源检查覆盖原有称号行保留、重复 ID 拒绝、普通 PNG 文件头拒绝、ZIP 回读、有效补丁链和单文件下载资源一致性。服务端回归使用临时数据库和 Fastify 注入请求，不启动本地正式服务或发送真实玩家邮件。

2026-09-09 本地验证通过：

- `python -B -m unittest discover -s tools/fantasy-gauntlet-mod-tools -p test_sponsor_special_thanks.py -v`：4 项通过。
- `npm run typecheck` 和 `npm run build`：通过；对应生成文件为 `out/lib/content-master.js`。
- `node --test tests/sponsor-degree.test.js tests/shop-degree-reward.test.js tests/profile-follow-identity.test.js`：16 项通过，包含定向投递、越权领取拒绝、重复领取、佩戴、他人资料及新进程持久化。
- 最终 ZIP 回读、单文件下载资源一致、既有清单条目及暂缓 `.104` ZIP 哈希未变，均通过。

验证时分支为 `staging`，HEAD 为 `2e7ab5a06fbd941fec6d799ebd51e1abd67bf441`，与 `origin/staging` 无提交分歧。本任务改动未暂存、未提交；原有客户端验收、自动开战实验及 `.104` 暂缓改动均保留。

真机称号列表、领取提示、个人资料及他人资料上的美术显示仍需在后续资源发布后验收。当前仅完成本地开发，不含提交、推送、本地运行镜像同步、云端部署或云服整合包。

## 2026-09-10 宽版美术增量：本地测试 1.4.107

用户选定宽版预览后，要求转交“重roll深渊连战塔关卡”任务沿其当前测试链制作增量；本任务随后收到用户明确允许本地脚本处理背景并保留构图的答复。

- 输入：`F:/codex/work/sponsor-thanks-width-preview-20260910/degree_mod_special_thanks_wide_preview.png`，SHA-256 `91af3cc31e0cccdcfc50d3c11f660f5c1700c0aeaf1c2d1520da4beba63bbf29`。它是已选的内置 image_gen 白底构图。再次内置透明化输出仍是 RGB 假透明，已弃用，没有进入正式资源。
- 正式宽版文件：`assets/asset-patch/artwork/sponsor-special-thanks/degree_mod_special_thanks_wide.png`，320×50、8-bit RGBA，SHA-256 `54c217185bb463354c8aed169746023ffa6a2b42a6fd022fc678435da66ed82a`。实际 alpha 区域 `[3,2,317,47]`，314×45；旧图为 `[52,1,267,49]`，215×48。保留旧正式图作为历史复现输入。
- 仅从已选预览去除中性白底、处理轮廓白色混色、裁去空白，并预乘 alpha 等比整理至正式尺寸（整数像素取整）。四字、红金中国结、祥云、飘带构图没有重画；已检查原生尺寸及深灰、浅白、蓝灰、粉色背景，未见棋盘格或明显白晕。
- 基于实际本地 `.106`（苍机兵及同类核心关联修复）追加 `.107`，不使用源仓库同号暂缓清单。增量文件：`assets/asset-patch/inactive/candidates/pinball-1.4.106-1.4.107-1-sponsor-title-wide-test.zip`，34,501 字节，SHA-256 `25598d1475baa39c98f66493b0c224cca73e7f1199c14e57d6633da6cf7e2c8b`，仅含 `production/upload/03/076857d74f07bb194f6185d4f1c1d6061850ce`。
- 称号 ID 9900012、主表、发放机制不变；塔结果、诅咒、ban、血量、第二关及苍机兵修复不变。全部 303 个有效资源核验，仅该 PNG 改变。四项 PNG 存储回归通过；游戏存储头经严格解码与正式 PNG 相等，实际 HTTP ZIP 及直接资源回读一致，称号主表实际 HTTP 哈希不变。
- Android/iOS 共用此 PNG，更新尾版均为 1.4.107；不是新增客户端平台能力，不重建 APK/IPA。实际客户端 UI 效果待用户更新资源后测试。
- 已同步三个明确文件：新 ZIP、该 PNG 的直接资源、独立测试 manifest。备份为 `F:/startpoint-cn-main/.codex-backups/20260910-161724-sponsor-title-wide/`；精确前后哈希见 `assets/asset-patch/audit/sponsor-title-wide-1.4.107-test/local-sync-report.json`。提示词、授权记录、四背景检查图及接口审计也在该审计目录。
- 分支 `staging`、HEAD `8f6252bb31c7f18a8cb61f11fa699282e68ebc4b`，与跟踪的 `origin/staging` 无提交分歧；保持未提交/未推送。没有云服覆盖整合包或云端部署，没有写入 `.cdn`。原暂缓清单及其他用户修改保留。
- 复现工具：`prepare_sponsor_title_wide.py`（需 Pillow、numpy，使用已加载的 workspace Python）与 `publish_sponsor_title_wide_local_test.py`（已发布后不会再次覆写同版）。本地测试说明：`outputs/quest-element-channel-lan-test-20260910/1.4.107称号更新说明.txt`。
