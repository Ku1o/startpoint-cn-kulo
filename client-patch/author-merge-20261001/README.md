# 作者装备七层客户端合并

这组补丁把装备描述、强化外观、队伍缩略图、觉醒材料、装备排序和品质框，以及装备规则层重新接到已验收的 Android 公网 1047 基线，再由同一份 SWF 转换为内网地址。补丁源和逐层验证器位于本目录；APK、SWF、签名材料和临时构建目录保留在 `F:/codex/outputs/author-merge-lan-20261001-public1047/`，不进入 Git。

## 已登记成品

- Android 内网 APK：`F:/codex/outputs/author-merge-lan-20261001-public1047/StarPoint-CN-1.8.1-author-merge-lan-public1047-20261001-dd83f336.apk`
- APK SHA-256：`a0a9f4e9c2fe88a413c7047d90206da70cadfabea9e7ad0d10f7471d18bac413`
- 内嵌 SWF SHA-256：`44585d8ff12cb83e4bf718d7765b00f0f29f21bbd039c23b8e047d1b320b4eb1`
- AIR `uniqueappversionid`：`dd83f336-3595-4fe9-a0e5-80cbd9ebc28f`
- 内网地址：`http://<LAN_HOST>:8001`
- 准入 ID：`android-181-author-1047-20260925`，与基线配对保持一致

静态检查确认 14 个既有方法体改动、6 个辅助方法新增、无方法删除；APK 的 v1/v2 签名、ZIP 对齐、固定签名证书及非目标成员保留通过。用户已确认客户端结果；本地 Codex 记录仍单独标注未由 Codex 设备实测、未执行运行镜像重启。

## 重建顺序

1. 从已登记的公网 1047 APK 提取 `assets/worldflipper_android_release.swf`，先用 `build_l1.py` 生成 `public-l1.swf`。
2. 对同一个工作目录运行 `build_stack.py --work-dir <目录>`，生成 L2–L7 层和各层报告。
3. 对 `l7.swf` 运行 `audit_stack.py --work-dir <目录>`，确认方法差分与语义矩阵。
4. 使用仓库现有的 APK 封包、重签和身份检查流程制作内网包；每次 SWF 载荷变化都必须使用新的 AIR UUID。不要把 APK、SWF、keystore 或准入密钥放入仓库。

本目录中的 `abcasm`、`battle-rules` 和各装备专题目录是本次合并实际使用的源模块；`equipment-rules` 是第一层，随后按描述、外观、队伍框、觉醒、排序、品质框顺序叠加。
