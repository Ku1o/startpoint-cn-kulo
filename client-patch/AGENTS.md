# Android APK/SWF 工作入口

- 开始 Android APK/SWF 任务前，先读本目录 `ANDROID-BASELINE.md` 和 `android-accepted.json`，再读具体补丁文档。JSON 中登记的已验收公网/内网成品是当前直接基线；其他文档中的旧哈希只代表历史步骤。
- 在修改前运行 `python client-patch/verify_android_baseline.py --variant public` 或 `--variant lan`，回读实际 APK、内嵌 SWF 和 AIR UUID。输入缺失或不匹配时不得按日期、文件名或旧报告另选 APK，也不得跳过哈希保护。
- 当前内网直接基线为 2026-09-10 验收的 Lens 0910 + 属性通道 + 深渊详情累计包，见 `ACCEPTANCE-LENS0910-20260910.md`；公网仍为 9 月 9 日登记包。内网主 ABC 序号 286、方法总计 96422。每次改动从对应登记包继续，保留内网三个新增步骤；保留历史 MOD、幻想连战、轮播、排行榜、继承入口、深渊装备限制、关注按钮、原生本人资料路由和 `CNtips_b` 隐藏，以及 Lens 724/422、稻穗 PF、基诺维冲刺、五重地图/手动 Auto 锁和 5900101 铁钢限制。同时保留深渊 700099 续战跨关复用阵容（284:24599）；具体验收依据见 `ACCEPTANCE-ABYSS-AUTOSTART-20260909.md`。Lens v3 已归档为该步骤历史输入，不再作为新任务直接基线。9 月 6 日标题包和两份错误续战测试 APK 禁止作为新输入。
- 旧步骤构建器锁定各自的历史输入，用于解释或复现该步骤；不能把任一中间产物直接当成最新成品。不同 UUID 会改变 APK 哈希，串联重建时不得为通过旧步骤的哈希检查而复用 UUID。
- 改动 SWF 时分配新 `uniqueappversionid`，保持包名、版本身份和签名证书；回读最终载荷、方法差异、UUID、ZIP 对齐和签名。完整类重编译产物只能用于提取 P-code，不能直接发版。
- 构建报告只记录本地校验；用户明确验收或明确要求执行验收后，按实际证据更新 `android-accepted.json`、方法文档和检查器，再按用户授权提交。离线验收记为 `accepted_offline`，不得记成用户已真机验收。APK、SWF 成品、临时产物和签名凭据不提交 Git；IPA 必须单独授权。

# iOS IPA 工作入口

- 开始 iOS IPA/SWF/AOT 工作前，先读 `ios-accepted.json` 和其中指定的方法文档，运行 `python client-patch/verify_ios_baseline.py` 回读实际 IPA、主可执行文件、主 SWF 的 SHA-256 和包身份。输入缺失或不匹配时不得改用旧包、诊断包或按文件名推测最新包。
- 当前基线为 2026-09-09 应用户要求完成离线验收的深渊续战 Lens IPA，包含一个续战原生方法（26363）、全部 Lens 及之前资料页累计修改；仍为 unsigned，本次不声称真机验收。原 Lens IPA、9 月 8 日资料页包和 r12b 只作历史输入。新任务从当前登记继续；仅复现续战步骤时显式使用 `--reproduce-lens`（Android 为 `--reproduce-lens-v3`），保留所有哈希保护。历史构建器的输入哈希只用于精确复现，不得绕过。
- 保留此前累计功能及 iOS 标题 `CNtips_b` 原有行为；本次 iOS 明确不移植 Android 的标题隐藏。诊断包不作为当前成品，不将 DEBUG 标记带入后续发布。
- 原构建、交付及诊断报告保留生成时状态，后续用户验收单独登记。验收不等于授权提交 Git、重签、部署或清理其他 IPA。
