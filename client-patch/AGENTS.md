# Android APK/SWF 工作入口

- 开始 Android APK/SWF 任务前，先读本目录 `ANDROID-BASELINE.md` 和 `android-accepted.json`，再读具体补丁文档。JSON 中登记的已验收公网/内网成品是当前直接基线；其他文档中的旧哈希只代表历史步骤。
- 在修改前运行 `python client-patch/verify_android_baseline.py --variant public` 或 `--variant lan`，回读实际 APK、内嵌 SWF 和 AIR UUID。输入缺失或不匹配时不得按日期、文件名或旧报告另选 APK，也不得跳过哈希保护。
- 每次改动都从当前累计包继续；保留历史 MOD、幻想连战、轮播、排行榜、继承入口、深渊装备限制，以及本会话的关注按钮直接可见性、原生本人资料路由和 `CNtips_b` 隐藏。具体方法和失败原因见 `rush-leaderboard/TITLE-CNTIPS.md`。
- 旧步骤构建器锁定各自的历史输入，用于解释或复现该步骤；不能把任一中间产物直接当成最新成品。不同 UUID 会改变 APK 哈希，串联重建时不得为通过旧步骤的哈希检查而复用 UUID。
- 改动 SWF 时分配新 `uniqueappversionid`，保持包名、版本身份和签名证书；回读最终载荷、方法差异、UUID、ZIP 对齐和签名。完整类重编译产物只能用于提取 P-code，不能直接发版。
- 构建报告只记录本地校验；只有用户明确验收后才更新 `android-accepted.json`，同时更新对应方法文档和可复现脚本，再按用户授权提交。APK、SWF 成品、临时产物和签名凭据不提交 Git；IPA 必须单独授权。
