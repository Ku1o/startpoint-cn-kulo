# iOS 公网 R4 累计成品验收

用户在 R4 HUD 修正版交付后明确表示：“ipa也验收了，然后提交修改内容到github”。本次将该成品登记为 `user_accepted`，并归档本会话的 iOS 累计移植及修复方法。用户验收与 Codex 的离线核对分别记录；没有取得逐项真机测试日志，不推断用户已逐项测试全部功能。

## 当前唯一直接基线

- IPA：`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-login-abyss-hud-public-fix-r4-20260911-unsigned.ipa`
- SHA-256：`560d5787411dfa1b603a9c8f0b4fba46f045e02531256e476df5b6474d822fae`
- 原生程序：`44d1b32d27a7564eec03207a4cc1f8fb74573185fba2ea624444180182b428be`
- 主 SWF：`7558dbdf13ad6c24c6249a85d3dffbef2527b36c92f2da6d3c9edb37d61b1f83`
- 完整 ABC：`F:/codex/ios-artifacts/login-abyss-hud-public-fix-r4-20260911/cumulative-full-r4.abc`
- 完整 ABC SHA-256：`7151e3d2ffb4e03e2204e5630011d98e5e8a7c0d3f29c073c7bafbe71b6547e8`
- AOT SHA-1：`790739d3540c5cd857354d2c23487504c302e55e`；101182 个方法。
- 身份：`com.kulo.wf`、1.8.4 / 1.8.46；公网初始地址 `http://175.178.160.158`。

登记 [ios-accepted.json](./ios-accepted.json) 指向原始 unsigned 交付物及配套完整 ABC，不重打包、重签或安装，不修改原离线报告。用户使用 TrollStore，登记不包含其设备重签后的文件或签名哈希。

## 本次归档范围

1. 登录及标题/菜单流程：账号登录、旧存档绑定、继承/重置码、记住登录及多账号管理；继续游戏后停留标题再开始。
2. 深渊简短摘要、可滚动详情和关卡属性伤害通道；保留之前的深渊跨层阵容复用与全部旧 MOD/Lens 功能。
3. Lens 0910 的灼晒耐性、夏白/杰拉尔语音轮换、资源回退和预加载，保留 iOS 原有标题行为。
4. 启动及 TrollStore 修复：LINKEDIT 重定位数据位于字符串表和签名之前，避免重签截断或覆盖造成启动闪退。
5. R3 公网修复：版本查询前就使用实际公网初始地址，避免登录面板保留官网地址。
6. R4 F1009 修复：语音计数存储移至 Number 尾部槽，恢复旧字段位置，保留原生状态栏初始化和语音轮换。
7. 构建、验证与入口规范：防止错误签名布局、初始地址或字段偏移回退；同步登记当前基线和完整 ABC 身份。

方法见 [累计说明](./ios-cumulative-login/README.md)、[R2](./ios-cumulative-login/TROLLSTORE-FIX-R2-20260911.md)、[R3](./ios-cumulative-login/PUBLIC-ENDPOINT-FIX-R3-20260911.md) 和 [R4](./ios-cumulative-login/HUD-F1009-FIX-R4-20260911.md)。IPA、ABC/SWF 成品、本地依赖、编译对象、日志和凭据不进入 Git。

## 验证与历史边界

本次重新回读实际 R4：3568 个 ZIP 成员和 CRC、包身份、完整 ABC 与原生 AOT 标识、实际原生字段读取、81 项 HUD 重定位、101181 个其他方法不变、公网初始地址、保留的 dyld rebase 及三种 TrollStore 签名大小模型通过。旧 R3 可被字段错位负例捕获；原始/R1/R2/R3 的历史身份仍锁定在相应复现脚本中。

[Sep 9 原登记](./accepted-history/ios-abyss-autostart-20260909.json) 原字节归档。当前校验器支持旧登记的显式 `--record`，也核对新登记的完整 ABC；传入旧 IPA 或缺失/不匹配的完整 ABC 必须拒绝。历史累计准备器需 `--reproduce-accepted-20260909` 才使用旧登记，不允许为新任务绕过基线哈希。

本次验收只登记已有客户端成品，不改变账号协议、存储路径、存档内容、数据库或迁移。R4 仅使用战斗期间的语音计数，无新增存档影响，因此不运行无关的存档导入操作。

源码在 staging 提交并推送，未授权合并 main。本次仅归档客户端开发工具、文档和验收记录，服务器无运行时变动，无需同步 `F:/startpoint-cn-main` 或重启；未要求、未制作云服整合包。其他任务的未提交内容保留原状。
