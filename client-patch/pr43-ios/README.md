# iOS PR43 功能与旧服兼容补丁配方

本目录保存 PR43 已采用功能的 iOS ABC/AOT 移植、Lv120、旧服养成材料兼容及准入轮换源码。需要 Python 3.11+ 和 `lief==1.0.0`；真实构建还需要合法持有的 AIR SDK 51.2.1.5。Python 环境应能正常 `import lief`，已有独立安装可通过调用进程的 `PYTHONPATH` 引入，不要求仓库中的固定本机路径。来源与许可见 [support/SOURCES.md](support/SOURCES.md)。

这是固定历史输入的补丁配方。后续开发基线仍读上一级 `ios-accepted.json`；本配方不会跟随登记提升而改变输入，不更新登记、服务、准入配置或设备。游戏源码、SDK、ABC、IPA、原生对象、私有 config 和构建回执均在仓库外。

## 功能及保留边界

- 移植最终采用的 37 个通用方法、12 个超限方法和 1 个商店辅助方法，追加两套加载 helper 及两闭包，共 30 方法；完整 ABC 从 101466 增至 101496 方法。
- 普通角色沿用旧材料；支持120级且完成普通四次突破后才启用超限材料。新材料定义缺失时只回退展示，确认仍禁用；库存为零独立处理。
- 保留 iOS HUD 的尾部 Number 字段及原引用偏移、旧 flags/activation、静态槽修复、缓存、预载、标题及平台编队行为。Android 的 #52 身份覆盖、#62 离屏生命周期 guard、#102–107 R4 和 x86 原生补丁不移入 iOS。
- 原生链接校验实际目标符号、共享入口、重定位、AOTInfo/full ABC/SWF 配对，以及签名尾部和 TrollStore `ldid` 裁剪边界。未知符号必须从真实对象和原生字节证明，不能使用近似函数。
- 准入轮换只接受固定兼容版，原位替换等长 ID/key，同时更新 full/runtime/native 的实际字符串副本和摘要；逆变换验证原生代码、ABI、表和其余成员保持。

## 固定输入

`support/baseline-contract.json` 锁定 10-04 iOS 公网修复基线：

| 输入 | SHA-256 |
| --- | --- |
| 旧 IPA | `66b1057cc7cd9e66da7a38aa9e4963d7effe2220f0889a9fcff4cfa1eeac77e0` |
| 旧完整 ABC | `a3a7e2b465f14472164a2b7cb61fcdd7b57c3987cb76bf2e8cfa095620270ab8` |
| PR43 旧服兼容 Android SWF（轮换准入前） | `0d88486dc2a7c4016933efffdee7708895361f93d924c201f9b4387aba7ce678` |
| AIR arm64 compiler | `4d37897f71d7cec73c5e9fc108fc130678dab33d711616fcfc35f42119112943` |
| SDK `hm-stubs.o` | `952f0c9ffe34f2e35eb434fdf0dd641d7ecd8baa6bf9d260e258d59e4ca1ecb8` |

Android SWF 与四份逻辑路径资源由旁边 [pr43-port](../pr43-port/README.md) 的固定输入流程准备；四资源目录为其 `inputs/bundle-donor`。284 份依赖 ABC 的文件名与 SHA-256 固定于 `support/dependency-hashes.json`，编译和原生依赖绑定都拒绝未知或变动输入。这里没有复制 SDK 或客户端原生对象。

## 复现步骤

从本目录运行。所有路径变量均指向仓库外私有输入或新的任务输出目录：`$oldIpa`/`$oldFull` 是上表旧基线，`$androidCompatSwf` 是兼容且尚未轮换准入的 SWF，`$iosWork` 是新目录，`$sdk` 是 AIR SDK 根，`$abcDependencies` 是284份依赖ABC目录，`$backgroundWrapper` 是本机已有的隐藏后台命令包装器，`$runtimeStubs` 是原 SDK 对象，`$resources` 是上述四资源逻辑目录。

```powershell
python -B prepare_port.py --input-ipa $oldIpa --input-full-abc $oldFull --android-swf $androidCompatSwf --source-revision old-server-compat --out "$iosWork/prepared"
python -B compile_port.py --prepared "$iosWork/prepared/port.json" --sdk $sdk --dependencies $abcDependencies --background $backgroundWrapper --out "$iosWork/compiled"
python -B link_port.py --prepared "$iosWork/prepared/port.json" --compiled "$iosWork/compiled/compile-report.json" --runtime-stubs $runtimeStubs --dependencies $abcDependencies --out "$iosWork/linked"
python -B package_port.py --linked "$iosWork/linked/link-report.json" --resources $resources --output-root $iosWork --output "$iosWork/compat-unsigned.ipa"
```

准备结果 `full.abc` 预期 SHA-256 `51d8155dc38d04d6c590a978f61de4206a6ac403799209b4979fef29456ce3c9`；既有兼容版未签名 IPA 为 `a4418388ff005313b2e1f2b3380dd7c99d411ac29afb4543e84fae4e505baa7d`。`--source-revision initial` 仅用于复现早期移植阶段，要求其另一份固定 Android SWF；当前目标使用 `old-server-compat`。输出目录必须新建，不能覆盖原载体。跨环境若 ZIP 压缩或工具链改变导致整体身份不符，应核查实际差异，不能删除固定输入保护。

编译仅在 compiler-only 输入恢复旧 owner 的 newclass 上下文并将无关方法置为类型正确的返回桩，最终 full/runtime 不接受这份编译输入。链接要求全部80个目标符号实际生成，并保留旧 flags 和 activation 前缀。后台包装器接受 `--timeout <秒> --cwd <目录> -- <命令...>`，不得在构建时弹出工具窗口。

准入轮换使用外部完整私有配对目录 `$pairDir`，同时含 `config/client-admission.json`、`config/client-admission.keys.json` 和 `before/config/client-admission.keys.json`。新条目平台必须为 ios，旧密钥必须保持；key 不通过命令行、源码或回执传递。

```powershell
python -B rotate_admission.py --input-ipa "$iosWork/compat-unsigned.ipa" --full-abc "$iosWork/prepared/full.abc" --pair-dir $pairDir --new-id ios-184-pr43-compat-public-20261017 --carrier-report "$iosWork/linked/link-report.json" --output-ipa "$iosWork/pr43-compat-admission-unsigned.ipa" --output-full "$iosWork/full-compat-admission.abc" --work "$iosWork/rotation"
```

轮换后完整 ABC 为 `1c3bd2b748f7c1b12e983e9395e175eb7a106e29edd2c709bef58f068dbb3a8d`，未签名 IPA 为 `a7fbe01dca579602fda1ad622ff508c92a92824a954c025ca09f36478111f14d`。该身份要求匹配的私有配对；本目录不生成或部署密钥，不包含重签材料。

## 检查与证据

```powershell
python -B -m unittest -v test_native_pipeline test_rotate_admission test_hud_adapter test_recipe_contract
python -B test_hud_adapter.py --ios-abc $oldFull --android-swf $androidCompatSwf --report "$iosWork/hud-check.json"
python -B test_overlimit_ios.py --ios-abc $oldFull --android-swf $androidCompatSwf --source-revision old-server-compat --ipa $oldIpa --resources $resources --report "$iosWork/overlimit-check.json"
```

单元检查不编译、链接或重封 IPA。`STARPOINT_PR43_IOS_FULL_ABC` 可显式提供上表旧完整 ABC，启用 compiler-only 输入保留检查；未提供则仅跳过这一私有输入检查，不能写成实际 ABC 已验证。契约检查覆盖元数据与依赖身份、未知 IPA 在输出前拒绝，以及所有命令帮助入口的导入闭包。

既有离线证据覆盖50个原入口、30个新方法、80目标符号、3802处兼容版重定位、全部101466旧flags/activation前缀、HUD 16处读取及15处整数转换、六种签名/ldid模型。初始移植只改变IPA的native/SWF/四资源共六成员；准入轮换只改变native/SWF两成员。最终身份及验收边界见 [iOS登记审计](../ACCEPTANCE-PR43-IOS-COMPAT-20261017.md)。这些是结构、字节和离线行为证据，未执行 iOS 原生代码，未覆盖重签安装、设备启动、GPU、公网玩法或性能。

源码整理后的检查已覆盖17项单元/契约检查、真实HUD导入和12个超限方法/四资源检查；同一真实输入重新准备的完整ABC仍为 `51d8155d…`。复用原编译对象的链接结果native仍为 `641a97fd…`，与既有兼容成品逐字节相同；此轮未重编AOT或重封IPA。
