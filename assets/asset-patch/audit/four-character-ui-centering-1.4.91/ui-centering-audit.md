# `1.4.90 → 1.4.91` 四角色 UI 定位修复审计

本次修复建立在已部署的 `1.4.90` 之上，使用独立的新版本增量，不修改或替换旧版 `1.4.89 → 1.4.90` 归档。

- 增量包只包含两个成员：共享 `trimmed_image` 与巴萨拉卡 `illustration_setting_sprite_sheet`。
- 将 `139997`、希耶提、西蒙与巴萨拉卡基础形态 `skill_cutin_0` 的固定画布纹理帧改为 `0,0,1024,512`。
- 四张觉醒形态 `skill_cutin_1` 定位行及 `trimmed_image` 其余记录保持不变。
- 巴萨拉卡图集按未修改的既有 atlas 修正为上方觉醒 `_1`、下方初始 `_0`，新画布 `363×754` 与 atlas 实际占用范围一致。
- 两个 ZIP 成员均为唯一、安全的相对路径，载荷与校正后的有效快照逐字节一致。

视觉复核图：

- `qa-skill-cutin-frame-before-after.png`
- `qa-vaseraga-illustration-order-before-after.png`

最终显示效果仍需游戏内复测确认。
