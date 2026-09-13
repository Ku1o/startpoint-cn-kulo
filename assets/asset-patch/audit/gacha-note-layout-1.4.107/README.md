# 两池注意事项叠字修复

2026-09-13 用户报告深渊池与竞速池说明重叠，并明确要求 CDN 增量放在同一版本的分包中；客户端重新获取资源由用户自行处理。

原因是 .107 第二分包生成说明时，将原有段落改成了直接挂在 `body` 下的裸文本。当前已登记 APK 的内置 `rich_text/style_bundled.css` 中，`body` 使用 `font-size:32px; line-height:1.4`。游戏的 `RichTextLength` 按绝对长度读取无单位数值，裸文本继承该样式后行距约为 1.4 像素。原生 `p` 样式使用 `1em`，因此恢复段落结构即可解决多行叠字。

修复保留两池全部文字、概率、排序和兑换规则，分别恢复 10、9 个原生段落。生成器 `tools/author858-integration/prepare.py` 也已改用 `gacha_notice.py`，避免再次生成裸文本。

## 资源与本地交付

- 版本保持 **1.4.107**，追加第 3 分包 `pinball-1.4.106-1.4.107-3-gacha-note-layout.zip`。
- 第 3 包为 **2,148 字节**，只含两份共通 HTML deflate 资源，Android/iOS 共用。
- 第 3 包 SHA-256：`2967f361d5c5b957f40e1613c00031c8534594ee4c3200a2687000c7dd2ffd28`。
- 前两包逐字节保留；三个分包合计 **61,484,779 字节**。
- 已同步 `F:/startpoint-cn-main/assets/asset-patch/active/pinball-1.4.106-1.4.107-3-gacha-note-layout.zip` 和 `F:/startpoint-cn-main/assets/asset-patch/manifest.json`。
- 旧 manifest 备份：`F:/startpoint-cn-main/.codex-backups/20260913-113539-gacha-note-layout/assets/asset-patch/manifest.json`。
- 服务端沿用 PID 26440，manifest 自动重读，本次未重启。

## 校验与范围

已核验最终 ZIP CRC、唯一且精确的两项成员、deflate 回读、全部段落原文不变、前两包哈希、源码/运行镜像 gacha 数据不变，以及两平台实际 HTTP 更新列表和第 3 包下载哈希。`.106` 请求仍升级到 `.107`，按顺序返回三个分包。

已从登记的累计 LAN APK（SHA-256 `c158139f7c25fe9faaf39f24323fd329f7d9671e21495377a786d98971bce9e9`）检查原生行距解析及文本节点继承方法。桌面 AIR 探针超时退出，未作为通过依据；没有宣称手机 UI 验收。客户端获取资源和实际显示由用户复测。

这次是文本标记修改，不改变存档 ID、进度、表结构、账号数据或导入导出合同，因此不运行无关存档迁移测试，也不需要服务端构建或 APK/IPA 重打包。

当前 `staging@0691fef4208bb56263984fcfbc2a4dae846cc188`，与 `origin/staging` 无分歧。本轮保持未提交，未推送、未合并 main；用户原有未提交内容继续保留。没有制作云服覆盖整合包或部署云服。下次云服包需包含第 3 包与最新 manifest。

完整本地证据位于 `F:/codex/work/gacha-note-layout-20260913`，包括同步回执、下载校验、前后说明和生成器前像。
