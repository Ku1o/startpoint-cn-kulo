# iOS 商店首次打开优化：公网累计版（用户已验收）

用户于 2026-09-13 要求先完成 Android 公网版并提交，再制作 iOS 公网版，iOS 等验收后提交。
制作阶段仅完成本地候选和离线验证，原始候选及构建报告保持当时状态。

2026-09-13 三会话整合时先登记为 `accepted_offline`；随后用户明确确认“ios的也验收了，然后提交修改内容”，现按 `user_accepted` 更新 `ios-accepted.json`，见 [验收记录](../ACCEPTANCE-IOS-SHOP-FIRST-OPEN-20260913.md)。原离线登记保存在 `accepted-history/ios-shop-first-open-offline-20260913.json`。登记原交付 IPA，不重新编译、重签或安装；当前共斗加载诊断不在本次提交范围。

## 精确输入与产物

- iOS 输入由独立注册表核验：`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-record-holder-public-20260912-unsigned.ipa`。
  SHA-256：`93695c623782164c243ace5bafd52c8ba170778d2fd9fd73199ef5c8840b2470`。
- Android 行为参考为本次已登记公网包，SHA-256：
  `35e0e7c777798594d68c9bcd74c507c6f0b7d065453e0425c301258c6bc38ac6`，制作代码提交 `0691fef4208bb56263984fcfbc2a4dae846cc188`。
- iOS 候选：`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-shop-first-open-public-20260913-unsigned.ipa`。
  SHA-256：`544ec90332845ff6c6b06e98aad691c0d9f10c725470eceeb4237c8bdbd65361`。
- 完整 AOT ABC 与候选登记资料：`F:/codex/ios-artifacts/shop-first-open-public-20260913/`。
  ABC SHA-256：`10772c48345fc196e8c76d1442c350915175a2c6ca514fa610bb23afed7981bc`，方法总数 101214。
- 工作目录：`F:/codex/work/shop-public-release-20260913/ios-port`；可用 `STARPOINT_IOS_SHOP_WORK` 指定新的独立目录。
- 保持 `com.kulo.wf`、1.8.4 / 1.8.46，沿用用户的 TrollStore unsigned 交付方式。
  iOS 初始公网地址仍为 `http://175.178.160.158`，使用它原有的端口 80。

## 变更范围

| iOS 方法 ID | 作用 |
| --- | --- |
| 27170 | 活动商品列表使用活动类型与 ID 的成员索引 |
| 27172 | 活动商品存在性查询使用同一成员索引 |
| 89719 | 商店首页存在性判断提前返回 |
| 79342 | 常驻活动文件夹存在性判断提前返回 |
| 73812 | 觉醒任务回调重新获取角色、等级并刷新能力页签 |

新增 `cn.shop.ShopFirstOpen` 的 8 个方法。索引只保留主表成员关系，按主表对象隔离，换底层表时重建；
不缓存玩家库存或开放状态。商品、价格、限购、时间判断、顺序、兑换、箱池及图片加载逻辑保持。
没有增加旧类实例字段，保留既有方法签名、activation 字段及类布局。

保留 iOS 自己的昵称、来源文件夹、登录、缓存、圆角、HUD、Lens、五重和此前全部累计修复。
不移植 Android 专属切队或标题隐藏行为，不加入共斗加载改造。

## 原生链接与离线验证

新增 `__CNSHOP` 与 `__CNSHTAB`，把新增加载器数据放在符号字符串表之前，保持 TrollStore/ldid 的签名裁剪边界。
首次链接因部分运行时调用超过 BRANCH26 距离而被检查拦截；最终使用 32 个附近跳转桥接，保留原 B/BL 调用类型，
桥接仅使用 IP0/x16，由 ADRP、ADD、BR 组成，不改变参数寄存器、栈或 LR。
规则依据 [Arm AAPCS64 的链接器临时寄存器约定](https://github.com/ARM-software/abi-aa/blob/main/aapcs64/aapcs64.rst#use-of-ip0-and-ip1-by-the-linker)。

编译无警告。独立回读全部 3568 个 IPA 成员，仅主可执行文件和 SWF AOT 摘要发生变化；
101201 个其他旧方法保持，5 个替换方法及 8 个辅助方法与已登记 Android 的规范化指令一致。
核验 351 个原生重定位、32 个桥接目标和 92741 个新增 rebase；原生旧段除派生指针和指定入口外保持原字节。
三种 ldid 重签大小模型通过，初始公网地址、HUD 字段偏移和既有启动缓存实现保持。

9 项回归通过：4 项桥接测试覆盖实际超距故障、BRANCH26 边界、页边界和 ASLR、非法目标；
5 项既有回归覆盖签名截断、未知 rebase opcode 0xF0、旧初始地址以及 HUD 字段错位。
桥接使用独立 Capstone 解码，不调用同一编码器来判定自身正确。
商店辅助逻辑复用与相同规范化指令及 Android 原始辅助 ABC 绑定的 698 项 AIR 断言，不重复运行桌面 AIR。

以上由 Codex 执行的是离线代码、身份和布局验证；用户之后单独确认 iOS 已验收，未提供逐功能真机测试明细。不把这份确认扩展为具体耗时、闪退改善幅度或共斗诊断的验收。

## 复现与验收

```powershell
python -B -X utf8 client-patch/ios-shop-first-open/prepare.py
python -B -X utf8 client-patch/ios-shop-first-open/compile.py
python -B -X utf8 client-patch/ios-shop-first-open/test_veneers.py
python -B -X utf8 client-patch/ios-shop-first-open/build.py
python -B -X utf8 client-patch/ios-shop-first-open/verify.py
python -B -X utf8 client-patch/ios-shop-first-open/test_regressions.py
```

输入须符合脚本锁定的 iOS／Android 哈希，不使用旧包或 stripped ABC 替代完整 AOT 输入。
本步骤复现固定读取 `accepted-history/ios-record-holder-20260912.json`；它只用于重现这一步，后续新功能仍从当前 `ios-accepted.json` 继续。
原生编译器作为受控无界面子进程运行，有超时和进程树清理；这些步骤不启动完整游戏或桌面 AIR。

制作阶段建议用户设备重点检查：覆盖安装启动和登录；重开游戏首次进入商店及活动道具／兑换；商品、价格、库存与兑换；
离开重进、切账号及觉醒页即时解锁；进入普通战斗与特殊模式，确认既有表现。
用户已确认本 IPA 验收通过；上述建议不等同于用户逐项反馈。原构建报告保留生成时状态；提交状态以本轮交付记录为准。

本次无新服务端接口、数据库、存档字段或 CDN 分包，不要求部署本任务早前的服务端查询优化。
报告中的 `server_endpoint_required` 沿用原链接器字段，表示客户端依赖既有服务，不能解释为本候选新增了部署要求。
