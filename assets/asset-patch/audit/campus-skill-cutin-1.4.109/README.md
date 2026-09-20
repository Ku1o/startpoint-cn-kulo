# 校园三人技能展示图（.109 第 3 分包）

用户确认放技能时显示的图片过大，并要求从原立绘重裁、预览后加入同一个版本的分包。沿用 `1.4.108 → 1.4.109`，使用第 3 分包，避开此前 C2265 修复使用的第 2 分包编号。

## 内容

- 校碧安卡 `119989 / lady_summoner_campus`、校希尔媞 `149989 / wind_spgirl_campus`、校奈芙提姆 `169989 / ruin_girl_campus`。
- 每人进化前后各一张技能展示图，共 6 张。扩大取景范围，保留上半身和主要动作；直接重裁已有原画，没有生成式重绘。
- 原尺寸 `1024×512` 和透明背景保留。6 个 medium PNG、6 个 Android ETC1 ATF、6 个 iOS ETC2 RGBA ATF，共 18 个资源。两端从各自对应的同一张已确认 PNG 独立编码。
- 普通头像、立绘全图、技能连锁头像、角色数值、技能脚本、存档 ID 和格式不变。无服务器源代码或 APK／IPA 变化。
- 既有 `trimmed_image` 的 6 行均为 `0,0,1024,512`，与新图一致，不需要替换主数据表。

## 交付

- 分包：`assets/asset-patch/active/pinball-1.4.108-1.4.109-3-campus-skill-cutin.zip`
- 大小：4,551,141 字节；SHA-256：`2b89ec0ffae5fac59a36d04c1226493a2f420a4dff3b6fe4d31cbe975a5948f2`。
- 同批使用最终 `assets/asset-patch/manifest.json`，保留已有 .109 作者更新第 1 分包。源仓库当前 .109 下载列表为第 1、第 3 分包；本任务没有恢复、替换或合入 C2265 历史测试包。
- 已经上报 `.109` 的客户端不会因为同版本新增分包自动触发下载。本次遵照用户要求保留版本号；后续若要求本地测试，另行安排明确的更新触发方式。

## 验证与状态

- 6 张 PNG 与已确认预览逐字节一致；原生小写 PNG 存储签名、严格解码和透明 RGBA 尺寸通过。
- 6 组平台配对的尺寸和 11 级 mip 一致；Android 槽 2、iOS 槽 3 各自有效，全部 mip 可解码，检查了压缩后可见效果。
- 最终 ZIP 的 18 个安全成员路径、CRC、每个成员摘要、有效客户端链回读通过；所有旧启用 ZIP 字节保持。
- 实际资源路由处理器的 Android／iOS `.108 → .109` 下载列表和总大小通过；当前版本返回无更新也已核对。未启动监听服务或访问玩家数据库。
- 本次仅源仓库本地完成，未创建提交、推送、同步 `F:/startpoint-cn-main`、部署云服或制作云服覆盖整合包。手机战斗显示尚未复测。

`prepared.json` 保留源资源摘要、裁剪参数和双端编码误差；`approved-png/` 保存六张输入；`report.json` 与 `delivery-verification.json` 保存交付核验。

制作工具：`tools/campus-skill-cutin/build_patch.py`；下载路由核验：`node tools/campus-skill-cutin/verify_delivery.cjs`。构建先写稀疏工作区，显式 `--apply` 阶段才写入源仓库 active ZIP 与 manifest；不写入 `.cdn`。
