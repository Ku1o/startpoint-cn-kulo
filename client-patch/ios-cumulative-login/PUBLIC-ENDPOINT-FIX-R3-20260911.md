# iOS 公网登录地址修正 R3

用户报告 R2 可以启动，但旧存档检测弹出“暂时连接不上服务器”。本次仅修正客户端，保持被 Defender 隔离的旧依赖文件不动，也不读取该目录。

## 原因与证据边界

- R2 的实际 ARM64 `DevConfig_gf_ios` 构造器（方法 5060）在文件偏移 `0x33d08a0` 加载主 AOT 字符串池 `0x39ad` 的 `https`，在 `0x33d08b0` 加载 `0x39ae` 的 `shijtswygamegf.leiting.com`。它的初始配置仍是官网；不能用其他 SDK 字符串中出现的公网 IP 证明登录地址正确。
- `TitleScene.run → initGbits → versionLogic.queryVersion` 异步查询成功后，`onQueryVersionSuccess` 才用配置中的 `apiScheme` 和 `apiPath` 改写 `devConfig.apiServer`。
- 新 `TitleScene.afterTransition` 调用 `PlayerLogin.title`，后者读取 `getServerApiPath()`，`show()` 将它保存到静态 `api/origin`；后续 `request()` 和“重新检测本机记录”重试直接使用保存的 `origin`。没有等待版本查询的保护，也没有同步后续地址变化。
- Android 的构造器在此前公网/内网打包时已经改过初始地址；原样移植登录模块到 iOS 时遗漏了这个平台差异。这是确定存在的初始化缺口；用户提供的服务端日志没有逐条正常登录请求，不能仅凭日志确定该设备的具体错误 URL。R3 仍需要真机复测验证实际症状是否解除。
- 2026-09-11 本机从公网读取 `/shijtswy/version/client_release_ios.dis`，返回 `apiScheme=http`、`apiPath=175.178.160.158`。对 `/player-auth/resume`、`/player-auth/local-claim-preview` 发送空对象分别得到 HTTP 200 的 `SESSION_INVALID` 和 `manual_required`。没有使用真实账号、密码、令牌或存档标识。

## 修改范围

直接输入为 R2 IPA（SHA-256 `171f0eb1d1671c9684c1ee9829af4b7f29a9ccc7481ec42144743c51cc2e6d7c`），完整 AOT 输入仍为首版累计移植保留的 `cumulative-full-r8.abc`（SHA-256 `b3d4c1e7aea35df9f50bf080d201f7f84de1a0ecd0943359de25d399b7dbef40`）。先核对登记的 9 月 9 日原始基线，R2 的继承记录保持原样。

`public_endpoint.py`：

1. 将构造器一条 `MOV W1` 的常量索引从 HTTPS 改为既有 HTTP 字符串索引 33074。没有全局替换共享 `https` 常量。
2. 将主 AOT 主机字符串 `0x39ae` 从官网域名改为 `175.178.160.158`；完整 ABC 与当前生效的 runtime ABC 同步修改，其他池项、方法、类和槽不变。
3. runtime ABC 缩短后在原分配区域内补零，更新 AOT 长度、完整 ABC SHA-1 和主 SWF 对应身份。所有 Mach-O 加载命令、函数指针、签名区域及重定位流都不变。
4. 初始 origin 采用 `http://175.178.160.158`，默认 80 端口，完全匹配云服返回格式，不附加 `:80`，避免同一服务器在记住账号的存储中形成不同键。

输出为 `F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-login-abyss-lens-public-fix-r3-20260911-unsigned.ipa`，SHA-256 `61a545ea867e97837fee2204c1649e362d6e3be2d98aa80abd3931111354a9af`。原 R2 文件不覆盖，R3 仍为 unsigned，保持 `com.kulo.wf / 1.8.4 / 1.8.46`。

工作目录：`F:/codex/work/ios-public-endpoint-fix-r3-20260911/`。交付报告及后续完整 AOT 输入：`F:/codex/ios-artifacts/login-abyss-lens-public-fix-r3-20260911/`。

## 验证与复现

在源仓库运行：

```powershell
python -X utf8 -B client-patch/verify_ios_baseline.py
python -X utf8 -B client-patch/ios-cumulative-login/public_endpoint.py --output-ipa F:/codex/ios-artifacts/R3-reproduce-unsigned.ipa --report-dir F:/codex/work/ios-public-endpoint-reproduce/output
python -X utf8 -B client-patch/ios-cumulative-login/verify_public_endpoint.py --report-dir F:/codex/work/ios-public-endpoint-reproduce/output
```

输入哈希固定，输出必须不存在。没有启动 AIR/ADL、重新编译、签名或安装。后续扩展必须保留新的完整 `cumulative-full-r3.abc` 和原生指令差异；不能把 stripped ABC 当作完整编译输入，也不能只重复旧 R2 步骤后交付。

独立验证已通过：回读 3568 个 ZIP 成员及 CRC，仅主程序与主 SWF 改变；Capstone 解码两处实际常量加载；用真实 R2 证明公网初始化检查会拒绝旧包；全部 101182 个方法体保持，仅一个主机池项改变；恢复四个明确允许的原生区域后，与 R2 逐字节一致；所有加载命令和重定位流一致；三种签名大小的 ldid 裁剪模型保留全部加载数据。模型不是实际巨魔签名或真机联网验证。

存档影响：没有更改数据库、账号绑定协议、物品/角色 ID、iOS 游戏存储路径、存档读写函数或导入导出逻辑。新登录默认 origin 与云服一致；旧版已经按公网 origin 保存的账号继续使用同一键。没有执行真实存档导入、绑定或替换。无需部署服务端或重制 CDN。

请用巨魔覆盖安装 R3，保留原应用数据，测试“重新检测本机记录”、旧存档绑定或账号登录，再测试“继续游戏 → 原标题 → 点击开始”。若仍报错，保留错误页面和发生时间以便区分版本查询、登录请求和后续游戏请求。

源码仍在 `staging / f440d283f84b84671d7cd2cfebdbe66d2d775448`，本次未提交/推送、未同步运行镜像、未制作或部署云服包，未推进验收登记。
