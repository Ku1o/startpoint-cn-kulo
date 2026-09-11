# TrollStore 重签裁剪导致的启动闪退：R2

用户提供的 10:55:48 新日志明确为 `DYLD / unknown rebase opcode 0xF0`，仍在游戏入口之前退出。用户随后确认两次均由 **TrollStore（巨魔商店）** 安装。

## 已定位的封装缺陷

第一份修正只把新 rebase 流移到签名之前，但放在符号字符串表之后。[TrollStore 的签名入口](https://github.com/opa334/TrollStore/blob/main/RootHelper/main.m) 先调用 `ldid`；[所用 ldid 的 Allocate 实现](https://github.com/opa334/ldid/blob/aaf8f23d7975ecdb8e77e3a8f22253e0a2352cef/ldid.cpp#L1470-L1492) 会取 `LC_SYMTAB.stroff + strsize` 并向上对齐 16 字节，作为待签内容长度，即便原签名偏移更靠后。

第一份修正版的字符串表结束在 `0x7b95f60`，恰好是新增 rebase 流的起点。按此流程重签时，新签名的 `FA DE 0C C0` 头会写在 rebase 起点。dyld 将首字节 `FA` 的高四位识别为不支持的 `0xF0` 指令，与用户日志吻合。

此处已用实际交付字节和源码规则重现，不再只依赖“替换旧签名尾部”的假设。没有获得设备上已重签的二进制，也没有在 Windows 上运行完整 TrollStore/ldid 或 iOS 进程；以下签名验证是按所审查源码实现的分配、截断及签名区域写入模型，不声称完成实际签名或真机启动。

审查固定到 ldid `aaf8f23d7975ecdb8e77e3a8f22253e0a2352cef`，源码 SHA-256 `ab5e4a3e841a6b18020cae6489e3b026a536a8119e08edc51c5ca59fd8e58d2a`。源码及 TrollStore/ChOma 参考文件保存在本轮工作目录的 `references/`，不将外部代码或签名材料打进游戏包。

## R2 修改

- 新 rebase 流插在原符号字符串表之前；保持字符串表作为最后一段加载元数据，签名区紧随其后。
- 同步更新 `LC_SYMTAB.stroff`、签名偏移、rebase 偏移及 LINKEDIT 大小。符号字符串内容和索引、所有重定位条目保持原样。
- 构建及独立验证均强制检查：`align16(stroff + strsize) == signature.dataoff`，所有加载元数据位于此边界之前。未满足时拒绝交付。
- 固化 TrollStore 的实际边界到 `client-patch/AGENTS.md` 和回归测试，保留两份失败 IPA 作测试输入。

沿用同一已验收基线和同一组 r8 原生编译对象，没有重编译登录/战斗代码。原生允许改动范围之外的字节、累计功能、公网连接、主 SWF 与完整 AOT 输入均保持；本次不改 APK、服务器、CDN、存档 ID/格式/账号协议或存储位置。

## 验证结果

八项回归通过，覆盖：

1. 拦截初版位于旧签名之后的数据布局。
2. 初版 rebase 地址与第一份崩溃日志的非法地址完全一致。
3. 模拟签名替换重现初版 rebase 被丢弃。
4. 拦截第一修正版超出 ldid 字符串表边界的布局。
5. 按 ldid 裁剪第一修正版，在 rebase 起点写入签名头，重现 `0xF0`。
6. R2 在直接替换三种大小签名区域后保留全部加载数据。
7. R2 在 ldid 分配/裁剪后三种签名尺寸下保留全部加载数据与重定位条目。
8. 修复前后所有游戏代码、数据和段起始地址保持，仅相关加载命令与 LINKEDIT 排列改变。

完整独立检查再次通过：3568 个 IPA 成员、14 个现有原生入口、111 个新增方法、3532 处原生重定位及 92709 项新增 dyld rebase。签名模拟不生成供安装的签名产物，也没有使用证书、私钥或管理员凭据。

## 交付及复测

- IPA：`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-login-abyss-lens-trollstore-fix-r2-20260911-unsigned.ipa`
- SHA-256：`171f0eb1d1671c9684c1ee9829af4b7f29a9ccc7481ec42144743c51cc2e6d7c`
- 原生 SHA-256：`ae47dc3f1bcdf419476cc7e54ddf24aa5819f055b9892d33e8ede3965c2f5824`
- 主 SWF SHA-256：`547d3436f4e558df2a3ce0a4f6660bde94da2283009172a59007c92c476a9dc3`（与前两包相同）。
- 工作目录：`F:/codex/work/ios-cumulative-launch-fix-r2-20260911/`。
- 报告目录：`F:/codex/ios-artifacts/login-abyss-lens-trollstore-fix-r2-20260911/`。

请使用巨魔覆盖安装 **文件名含 `trollstore-fix-r2` 的包**，先检查是否进入登录面板，再检查旧存档绑定、继续游戏返回标题及进入主城。不要求卸载或清除存档。仍待用户真机反馈；未推进验收登记、未提交或同步服务器。源码基点仍为 `staging / f440d283f84b84671d7cd2cfebdbe66d2d775448`，该原提交已在远端。
