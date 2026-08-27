# 三角色 UI 精准替换审计

- 版本边：`1.4.89 → 1.4.90`
- 补丁：`pinball-1.4.89-1.4.90-1-0827-trio-ui-refresh.zip`
- 补丁 SHA-256：`29f32e2dae8f5145fc01b0964289ca992db7ee0eb15af0830b6cbb1508891d57`
- 发布范围：75 张 UI PNG、6 个 Android ETC1 Cut-in、6 个 iOS ETC2 Cut-in、3 张立绘定位表。
- 所有固定槽位 PNG 尺寸均符合输入契约；6 张新立绘的尺寸变化已同步到三张客户端表。
- 另有 3 张 illustration_setting_sprite_sheet 尺寸变化；该逻辑路径在当前 trimmed_image 中无记录，无需同步裁剪表。
- 三张表只改三角色的 6 个形态记录，所有非目标键及压缩行字节保持不变。
- 主动排除残余文件：17 个。
- 本构建只生成隔离候选，不修改运行时镜像。

## 角色与排除项

### 西蒙（169996 / `simoun_dark`）

- 选入：25 张现行生产 UI PNG。
- 排除：5 个制作残余。
  - `[原图]初始.PNG`：source_or_reference_art，未写入客户端补丁。
  - `[原图]觉醒.png`：source_or_reference_art，未写入客户端补丁。
  - `episode_banner_0.png`：story_asset_not_registered，未写入客户端补丁。
  - `full_shot_1440_1920_0_resized.png`：resized_preview，未写入客户端补丁。
  - `full_shot_1440_1920_1_resized.png`：resized_preview，未写入客户端补丁。

### 巴萨拉卡（169997 / `vaseraga_dark`）

- 选入：25 张现行生产 UI PNG。
- 排除：6 个制作残余。
  - `episode_banner_0.png`：story_asset_not_registered，未写入客户端补丁。
  - `full_shot_1440_1920_0_resized.png`：resized_preview，未写入客户端补丁。
  - `full_shot_1440_1920_1_resized.png`：resized_preview，未写入客户端补丁。
  - `巴萨拉卡初始立绘.png`：source_or_reference_art，未写入客户端补丁。
  - `最终解放巴萨拉卡.png`：source_or_reference_art，未写入客户端补丁。
  - `觉醒巴萨拉卡.png`：source_or_reference_art，未写入客户端补丁。

### 希耶提（149995 / `seofon_wind`）

- 选入：25 张现行生产 UI PNG。
- 排除：6 个制作残余。
  - `episode_banner_0.png`：story_asset_not_registered，未写入客户端补丁。
  - `full_shot_1440_1920_0_resized.png`：resized_preview，未写入客户端补丁。
  - `full_shot_1440_1920_1_resized.png`：resized_preview，未写入客户端补丁。
  - `老7.png`：source_or_reference_art，未写入客户端补丁。
  - `觉醒希耶提.png`：source_or_reference_art，未写入客户端补丁。
  - `觉醒希耶提.psd`：layered_source，未写入客户端补丁。

