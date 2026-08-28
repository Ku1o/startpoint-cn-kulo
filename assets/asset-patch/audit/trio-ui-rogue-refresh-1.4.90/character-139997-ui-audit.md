# 139997 角色 UI 精准替换审计

- 版本边：`1.4.89 → 1.4.90`（沿用现有单一增量包）。
- 输入：`F:\雷皇女ui.zip`，SHA-256 `a52ae1c45b3e22e9cea81df2192e253edf7e614aea7dc2828b8d8ea32d486169`。
- 选入：25 张现行生产 UI PNG；同步重建 Android/iOS 各 2 个 Cut-in。
- 插画设置图集：来稿为上方初始、下方觉醒，已按现有 atlas 重排为上方觉醒 `_1`、下方初始 `_0`，并规范为 `364×788`；atlas 本体未改。
- 定位：两张立绘尺寸变化已同步 `character_image`、`full_shot_image_attribute`、`trimmed_image` 的 6 行。
- 排除：`episode_banner_0.png`、2 张 resized 预览、2 张中文原稿，共 5 个非生产残余。
- 合包：126 个唯一成员，SHA-256 `827d8550fe14400df26c5ff4fc2f3309b8a9cea15d6203d35b153dfb64529cba`。
- 相对上一候选包只改变 `illustration_setting_sprite_sheet.png` 对应的 1 个成员，其余 125 个成员载荷逐字节不变。
- 旧包 97 个成员均保留；只新增 29 个 139997 专属成员，并覆盖 3 张共享定位表。
- 未修改运行镜像。
