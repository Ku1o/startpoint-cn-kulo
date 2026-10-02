# 启动缓存、空更新与深渊圆角按钮（本地候选）

后续运行期缓存方案见 [PERIODIC-10M.md](./PERIODIC-10M.md)。它是启动清理的独立客户端变体：每十分钟只清理 `cache/app` 与 `cache/.AIR`，不改变本 README 中历史三项修复的验收范围。

2026-09-12 后续登记：用户已明确验收 Android 与 iOS 并授权提交，见 [统一验收记录](../ACCEPTANCE-CACHE-PARTY-20260912.md)。下文保留开发与构建时的状态，不将原报告改写为真机逐项验收。新任务从当前登记成品接续；本目录构建器只用于其锁定历史步骤的精确复现。

2026-09-12。仅本地实现和 MuMu 设备-1 验证，未提交、推送、更新验收登记或发布云服。

## 三项行为

1. **消除空更新**：服务端 `/asset/get_path` 对资源版本已达到目标且确实没有归档任务的请求返回 `full:null / diff:null / asset_update:false`。客户端在原生响应解析之前兼容旧服务端的空对象/空数组，随后仍走原生 `NoNeedToDownload` 流程。不会按“显示 0 MB”或包体大小直接跳过下载；首次下载、实际小包、增量更新保留。切换账号只重置账号相关 `misc_data`，保留下载模式、声音和其他设备设置。
2. **覆盖安装首次启动清理**：在 Android 原生包装的 `instantiateClassLoader` 和旧系统 `attachBaseContext` 入口加入清理，先执行再加载 AIR。仅访问应用私有 `cache/app`、`cache/.AIR`；不碰 `Local Store`、下载资源、账号、SharedObject、`files`、`shared_prefs`、存档或数据库。以构建 UUID、已安装 APK 的路径、修改时间和长度识别安装，标记位于 `no_backup`，因此同版本、同 APK 再覆盖也会触发。文件锁防重复执行；清理成功后原子提交标记，失败不阻止启动且下次重试；普通重开跳过。
3. **深渊圆角按钮**：`AbyssDetails.attach` 使用客户端已有 Starling Canvas/Polygon 绘制单个凸多边形，圆角半径为按钮高度的 20%，每个角 8 段。沿用按钮尺寸、颜色、文字、点击处理和详情内容；不新增纹理、资源包或战斗逻辑。

不是定时清理脚本，不会在战斗或普通场景切换时反复清理。

## 累计输入与变更边界

- 输入为 r15 登录 + 深渊详情 + 属性通道 + Lens 0910 的累计内网 APK，APK SHA-256 `27de717e8864ea35a329032fa3f7dc23e8d99e3f6187b411a39f321d1509a200`。运行前已通过登记的 LAN 祖先校验；输入还与设备-1 原安装包逐字节一致。
- 输入 SWF `c667815ff871e12705e665267640db480f7c959e1c6bb4d852016f1e4923d6ed`，原 main ABC 287、共 96515 个方法体。
- 只移植 `286:0 PlayerLogin.title/closure:0`、`285:7 AbyssDetails.attach`；`287:47796 AssetGetPathRealRemote.successHandler` 只插入一次兼容处理。追加独立 EmptyUpdate ABC（5 方法），main 移到 288。其余方法和既有类结构保留，没有重编译整份游戏类。
- APK 成员只变更 SWF、强制更新的 AIR UUID、主 DEX。原生 35 个方法经独立反汇编核对，去掉两个入口插入后可恢复原内容。新增两个原生辅助类；编译用 Android API 桩不入包。
- 包名 `com.leiting.wf`，versionName `1.8.1`，versionCode `1008001`，AIR 33.1.1.620 与原始原生库保持不变。沿用固定签名，证书 SHA-256 `569D19A3578D4CBA16E3D6E7AD8CCAB4FA667EFC758DEEF6C9BE3ADB99919894`。
- 没有 CDN 或资源版本改动，没有 IPA 改动。当前本地资源仍为 1.4.105。

## 验证结果

- `npm run build` 通过；`node --test tests/asset-empty-update.test.js tests/session-cdn-consolidation.test.js tests/local-client-compat.test.js`，5 项通过。覆盖 Android/iOS 请求、已有版本、较高缓存版本、首次小包下载、真实增量任务、三种下载模式与旧平台配置兼容。
- FFDec 独立解析全部 96515 个既有方法体，实际差异只有上述 3 处；主方法插入可逆。DEX 独立反汇编恢复全部 35 个原生方法。签名 v1/v2、zipalign、全部 APK 成员比对通过。
- **MuMu 安卓设备-1，index 1，Android 15，ADB 127.0.0.1:16416**：首次覆盖启动清理，缓存内实际 SWF 哈希与新包一致；普通重开跳过并保留缓存哨兵；同一 APK 再覆盖后哨兵被清除，重新记录安装。记住的账号可直接登录，下载资源继续可用。
- 专门将设备下载状态临时从 1 改成 0，保留 1.4.105 资源和所有其他设置，向未修复的旧服务端请求。实际出现一次 `asset/get_path`，没有 `asset/version_info`，没有空更新弹窗，直接到主页，模式自动回到 1。原设置文件已恢复原始字节并复核。
- 同一设备运行原生文件操作夹具：首次运行、重复启动、同载荷重新安装、新载荷、标记写入失败后的重试，以及下载文件/设置/账号目录保护均通过。仅在临时目录运行，没有拿真实存档做破坏性测试。
- 深渊第 2 战编队页已肉眼确认四角圆弧，点击详情、关闭、再次打开均正常。测试入口为：活动 → 终始之战 → 完成 → 深渊连战。
- 未验证其他手机型号和 Android 旧版本；未进行整塔战斗或 TCP 压力测试，这些不属于此次三个改动。

## 存档与本地运行

没有更改存档结构、保存的 ID、账号归属、服务端表或导入导出协议；既有导入导出兼容性不受此改动影响。设备清理限定在启动缓存，账号切换仍重置原有账号相关本地选择。存档导入破坏性回归不适用。

本地运行镜像已备份并同步以下未提交试用文件，逐一校验哈希后重启：

```
src/routes/cn/asset.ts
out/routes/cn/asset.js
src/lib/version.ts
out/lib/version.js
```

备份：`F:/startpoint-cn-main/.codex-backups/20260912-005800-empty-update-local-trial/`。
详细设备记录、原 APK 与私有设置备份位于 `F:/codex/work/client-local-three-fixes-20260912/`；私有备份不得提交、同步或打包。

## 复现

复现本步骤时先运行 `python client-patch/verify_android_baseline.py --variant lan --record client-patch/accepted-history/android-lens0910-20260910.json`，再以一个不存在的工作目录运行：

```
python client-patch/startup-cache/build.py F:/codex/work/<new-build-directory>
```

工具路径与输入哈希均固定在构建器中，凭据只由现有 DPAPI 签名进程读取。每次分配新的 AIR UUID。`StartupCacheTest.java` 应编译为测试 DEX，在指定 MuMu 的 `app_process` 中运行；文件重命名语义按 Android 验证，不用 Windows 文件系统替代。

## 公网测试包（2026-09-12）

用户希望先由云服玩家测试，暂不更新服务端。`build_public_apk.py` 从已在设备-1 实测的三项修复 LAN 成品接续（APK SHA-256 `68cfbb9044d172acc20bd86dd86c6f9ac44b2a9c845d294147474d5c1e3e4900`），仅将 DevConfig 构造器唯一引用的地址常量切换到验收登记的 `http://175.178.160.158:8001`，同时更新 AIR UUID 和原生清理载荷标识。该公网转换不会重新移植或编译游戏逻辑；96,520 个 SWF 方法体逐一保持，其他 SWF 标签逐字节保持，6 个原生类在还原 UUID 后反汇编一致。

公网成品：`outputs/client-cache-rounded-public-20260912/StarPoint-CN-1.8.1-cache-rounded-public-20260912.apk`。APK SHA-256 `32006941eff3a0294e9895aafba4668c8a4691bce1459740cb46afc258492f56`，SWF SHA-256 `2b72ea4140a759c33fc6b86ebfa1fdfd6acd2478fe911d8545a0f3995e15ee93`，新 UUID `3649f84f-5690-4601-81cb-e5d6d09ee275`。签名 v1/v2、固定证书、ZIP 对齐、嵌入载荷和其他 APK 成员比对通过。旧服务端空响应兼容沿用上述已完成的本地设备测试；此公网 APK 未进行云服登录实测，没有更新云服或验收登记，也没有创建提交。MuMu 设备-1 保留原 LAN 测试版。

三项功能不依赖本次服务端补丁，云服可以暂不更新；此前累计客户端所需的账号登录与内容支持仍沿用现有云服能力。正常真实增量下载不会被屏蔽。

复现：`python -X utf8 -B client-patch/startup-cache/build_public_apk.py --work <新工作目录> --out <新交付目录>`。先验证精确 LAN 成品和已验收公网/内网祖先，所有外部进程同步执行并有超时清理。
