# iOS 公网账号空记录恢复（2026-09-15）

当前准入 IPA 的原生程序中，账号读取方法在文件存在后调用 `FileUtil.readBinaryFile`、`CompressUtil.uncompress`，没有空文件检查；账号保存方法在写新数据前删除旧文件。这两段机器码与已验收商店 IPA 一致，属于原有缺陷。结论来自代码审阅，尚无 iOS 损坏记录的真机复现。

iOS `DeviceLocalStore.save/getMaybe` 使用其原有 Application 扩展存储，未使用 Android 的 `writeFile/readFile` 路径，因此此次保留 iOS 设备记录全部方法。

## 输入和输出

- 验证已验收祖先后，直接输入最新正式准入 IPA：`outputs/ios-admission-public-20260915/StarPoint-iOS-1.8.4-admission-public-20260915-unsigned.ipa`，SHA-256 `764a7c5183a8605f58364e786a08a59f65333403bded9918dd3b544a85112f09`。
- 直接输入完整 AOT：`F:/codex/work/ios-admission-public-20260915/admission-full.abc`，SHA-256 `86e787a8d169cabfee94e8420d56ff1bf8ed928afdb04e367d9967cf91844ae3`，101,283 方法。不能以 stripped ABC 或更早完整 ABC 代替。
- 成品：`outputs/ios-admission-public-reopen-fix-20260915/StarPoint-iOS-1.8.4-admission-public-reopen-fix-20260915-unsigned.ipa`。
- IPA SHA-256：`90d6757bc45c8562926f7ea53b0455c219b9867bf91cbab4314237cab4ffb3f6`。
- 原生程序 SHA-256：`abfbfad2949dfaf26cb9440a63c1cbb8893559078b91a32e868c5c843165b0fa`；SWF SHA-256：`53db3699e912ea4f41c4945bb1c36117f18b39c40d5ce57a60546798456da9b4`。
- 完整 AOT 输出：成品目录 `record-recovery-full.abc`，SHA-256 `507109bf13ff1b665b521d135057e42f76f924d1f14960b8264ae4f2362ef96c`，101,287 方法，保留供后续累计制作。
- 保留 `com.kulo.wf`、1.8.4 / 1.8.46、公网初始与游戏地址 `http://175.178.160.158`（端口 80）、TrollStore unsigned 交付方式。
- 沿用 `ios-184-admission-20260915` 与原准入材料；Android 同批继续使用 `android-181-r10-20260915`，没有推进新号或改变服务器配置。

## 修改和保留

| 原生方法 ID | 变化 |
| --- | --- |
| 31752 `AccountLocalStore_Impl_.get` | 空账号文件返回原来的 `Option.None`，进入既有登录恢复流程。 |
| 31756 `AccountLocalStore_Impl_.saveAccountData` | 同目录临时文件写完、关闭并确认长度后替换；写入失败保留旧记录。 |

使用 Android 已测试修复中的两个共同账号方法和 `cn.storage.LocalRecordIO` 作为行为参考。iOS 方法签名、类字段、activation 布局、原有格式和文件选取保持；新类增加 4 个方法。仅编译该账号类的 lexical initializer 作为上下文，其旧原生初始化代码仍然保留。不能把编译器占位方法写入实际旧函数入口。

保留其余 101,281 个旧方法、原有准入类和全部累计功能。原 `__CNADMIT` 段逐字节不变。iOS 的设备存储、商店、觉醒、登录、缓存、HUD、Lens、深渊、五重、原切队与 CNtips_b 行为均保持；不引入 Android R8/R9/R10 性能改造、队伍缓存或任何诊断/日志导出入口。

服务器账号归属、数据库、玩家进度、存档 ID 和 V1/V2 存档导入导出格式保持原样。空文件无法还原已经丢失的本地登录数据，需要使用原账号登录。

## 原生布局与验证

当前输入已有 17 个 Mach-O 段，经典 dyld rebase 的段索引只有 4 位。新代码放入 RX `__CNRECIO`，扩展已有 RW `__CNADTAB`（索引 15）的尾部存放新表；新 rebase 使用该原段内的真实偏移，不重复修正旧位置。原段地址和内容不迁移，仅更新本次入口和派生指针。LINKEDIT 元数据仍在字符串表及签名边界之前，保持 TrollStore/ldid 重签兼容。

独立验证已通过：

- 3,568 个 IPA 成员核验，仅主程序和主 SWF 改变；包身份、初始公网地址、实际准入号/密钥及旧方法布局保持。
- 2 个账号方法、4 个辅助方法与已测试参考的规范化指令一致；6 个实际链接函数的非重定位机器码与编译对象一致。
- 96 个原生重定位、28 个长跳转桥接、92,814 个新增 rebase，以及其余旧原生字节边界检查通过。
- 3 种 ldid 签名尾部替换模型通过；10 项回归覆盖历史签名裁剪、rebase 0xF0、错误初始地址、HUD 字段错位、跳转边界和实际新方法表只执行一次 ASLR 修正。
- Android 内网相同辅助类已通过 8 项真实 AIR 文件系统用例及空账号启动检查。

以上为离线与共享逻辑验证，**未 iOS 真机测试**。建议用户通过 TrollStore 覆盖安装后，检查启动、原账号登录、完全退出游戏再打开，以及普通游戏流程；不要清除应用数据来代替验证。

## 复现

设置 `STARPOINT_IOS_RECORD_WORK` 为新的不存在路径后依次执行 `prepare.py`、`compile.py`、`build.py`、`verify.py`、`test_regressions.py`。输入哈希锁定且与当前已验收祖先分别核验，不覆盖历史输出或 accepted registry。使用仓库既有 AIR SDK 和本地原生分析工具，原生编译为无界面子进程。
