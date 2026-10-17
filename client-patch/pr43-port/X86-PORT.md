# Android x86_64 适配中间步骤

`x86_port.py` 将已核验的 15 个 x86_64 库和 13 个 ANE 平台补到显式选择的 APK。输入 APK 可以是保留相同原生/ANE 接口的最终功能包；没有固定到历史 v33 或旧游戏 SWF。每次调用必须传入该 APK 的 SHA-256 及输入目录树哈希，输出只能写到显式给定的任务输出根目录，已有文件拒绝覆盖。

脚本只修改 ANE 描述中的平台声明并增加缺少的库、平台资源。游戏 SWF、DEX、ARM 原生库、AndroidManifest、AIR application.xml 等原成员逐字节回读比较；已有不同的 x64 库或 ANE 资源直接报错。仅移除根 `META-INF/` 下明确的 APK v1 签名文件；嵌套元数据保留。原压缩类型、时间、权限、注释、extra 字段保留。ZIP 重写移除旧 APK Signing Block，输出仍须独立 zipalign 和签名，本步骤不进行这两项操作。

前置兼容检查包括：基包与新增运行时均为 AIR 33.1.1.620、ARM64/x64 平台标记；新增库全部 ELF64 x86-64；15 个库名与基包 ARM64 名单一致；Core、SocketHelper、entryexpro 的实际动态导出 Java API 集合相同；DT_NEEDED 依赖仅引用这套库或明确列出的 Android 系统库；13 个 ANE 的 initializer/finalizer 平台结构一致；全部 ARM64 平台资源与已核验 x64 输入逐字节一致。发现平台目录内 ELF 时拒绝直接克隆。此检查不能证明 SDK 桩内部语义、所有动态注册方法或设备兼容。

目录树哈希由 `tree_hash(path)` 计算：按相对路径各段 casefold 后的元组排序（兼容已核验的 Windows 路径顺序，同序时按原 POSIX 路径打破平局），每文件将 UTF-8 的 `POSIX路径 + NUL + 十进制字节数 + NUL + SHA256 + LF` 加入 SHA-256。调用前应将该值与已经核验的输入来源对应，而不是在未知输入上计算后直接信任。

```powershell
python -B x86_port.py --base $baseApk --base-sha256 $baseSha --inputs $nativeInputs --inputs-sha256 $inputsSha --output "$clientWork/x86/final.unsigned.apk" --output-root "$clientWork/x86"
python -B -m unittest -v test_x86_port
```

2026-10-17 旧正式 LAN 基线离线演练：新增 1953 个成员（15 库及 1938 个 ANE 资源），13 个描述文件增加 x64 平台。三库 Java 导出 API 分别为 129、24、46 项，ARM64 与 x64 集合完全相同。这是未签名中间包与静态兼容检查结果，没有安装、启动或设备验收；历史 v33-x86 的模拟器测试不作为本轮实测。

覆盖安装还需另行验证 AIR 的 `cache/app` 更新，不能只依赖 versionCode 升高。缓存处理应保留玩家进度、资源下载与现有缓存策略。

完整输入准备和组合顺序见 [README.md](README.md)，所有路径通过参数传入。
