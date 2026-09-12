# 死亡使者魂珠与深渊觉醒核预览修正

2026-09-12 用户要求使用已有魂珠转换工具生成新图，并明确把内容加入 `.106` 的后续分包。已生成、同步本地；未提交、未推送、未部署云服，尚无手机实机验收。

## 分包与修改

- 新增 `assets/asset-patch/active/pinball-1.4.105-1.4.106-2-deathbringer-core-icons.zip`，970,506 字节，SHA-256 `eeb310b65106cf8a3a827cd8bc5bc434ff95e91d939e1a01557f610cdae343b4`。
- 原 `.106-1-mech-item-sources.zip` 保留原字节，SHA-256 `f25bccc0027d54b980462d78b792d86d015efabb568a76c207e6ba7debd3d9b2`。manifest 的 `.106` chain 依次包含两个包，总大小 1,327,670 字节，资源版本仍为 `1.4.106`。
- 死亡使者·终式魂珠 `5900101`：从当前有效装备图 `item/equipment/mod/five_boss/deathbringer_final_lv0.png` 取图，通过 `tools/soul-icon-converter/dist/魂珠图标一键转换工具.exe --convert` 生成 20×20 魂珠配色，替换旧 41×41 魂珠；逐像素 Alpha 保持不变。
- `master/generated/trimmed_image.orderedmap` 增加该魂珠路径的 `0,0,20,20` 完整子纹理记录，遵循原生 ItemThumbnail 的 6× 显示规则。其他行原始字节保持不变。
- `master/shop/event_item_shop.orderedmap` 仅修改商品 `9700199` 的第 13 列（零基）：机兵材料图改为 `item/materials/mod/abyss/abyss_core`。对应真实奖励为深渊觉醒核 `2370100`。兑换币 `2370099`、价格 500、限购 5、每次奖励 1 及其他字段均保持原值。
- 觉醒核已有独立图片及 `item/sprite_sheet` 预加载图块，逐像素核对一致，不需要另造图片或修改图集。

三个成员全部为 common/upload 资源，安卓与 iOS 共用，不涉及平台纹理、APK/IPA、服务端构建或数据库。纯图片与路径修改不影响存档 ID、格式、导入导出或入手来源，不需要重建入手索引。深渊换塔时间标记保持 `b7f64b4be9d492d56419293d911d06c3bfef6d2d917275c9d01735fd086340f3`，本次不触发成绩重置。

## 验证与本地同步

- 生成器：`tools/lens-integration/fix_deathbringer_core_icons.py`。工作目录 `F:/codex/work/deathbringer-core-icons-20260912` 保存有效链取图来源、修改前后稀疏资源与清单，未写入 `.cdn`。
- 原转换工具退出码 0，重复转换输出字节一致；严格 PNG 编解码、20×20 尺寸和透明度校验通过。`converter-preview.png` 是工具自带五星图标格预览，非手机截图。
- ZIP CRC 和回读校验通过；商店表仅目标商品一个字段变化，trim 表只新增目标行；有效链重新读取三个资源均与目标字节相同。
- 本地实际 HTTP `/api/index.php/asset/get_path`：安卓及 iOS 的 `.105` 请求均返回两个 `.106` 包；`.106` 请求仍返回无更新。下载实际服务的第二包与源文件哈希一致，证据见 `live-verification.json`。
- 换塔标记门禁 `python tools/fantasy-gauntlet-mod-tools/wf_quest_time_revision.py` 通过，当前关卡版本 `.104` 与 `.106` 计时标记匹配。
- 本地仅同步 manifest、新 ZIP 和三个直读资源，共五个路径。精确路径、前后哈希见 `report.json` 的 `delivery`；备份为 `F:/startpoint-cn-main/.codex-backups/20260912-205050-deathbringer-core-icons`。资源服务保持运行，无需重启，无存档操作。

## 更新与回滚

已下载旧 `.106` 的客户端不会因为同版本新增分包而自动更新；测试时需通过客户端提供的资源重新下载入口重新获取资源。本次没有修改客户端版本，也没有清除任何用户设备数据。尚未更新到 `.106` 的客户端正常升级即可取得两个包。

回滚时按 `report.json` 的精确文件集恢复来源备份和本地备份；原先不存在的分包及散资源按回滚授权移除，最后恢复 manifest。保留 `.106-1` 与此前所有功能。不对项目根做镜像覆盖，不删除基础 CDN 或玩家数据。

云服待合并记录已更新到 `docs/development/PENDING-CLOUD-OVERLAY.md`。未来整合包须原样包含新增 active ZIP 与最终 manifest；外层排除 production 散资源，内层 ZIP 的 production 成员完整保留。本次没有制作或部署云服整合包。
