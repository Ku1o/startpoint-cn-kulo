# iOS PR43 支持代码来源

本目录沿用 [StarPoint CN GPL-3.0 许可证](../../../LICENSE)。这些文件是已有客户端补丁工具的必要定义摘取，保留解析、ARM64重定位和匹配算法；不包含游戏反编译源码、AIR SDK、原生对象、客户端载荷或凭据。

| 文件 | 来源与保留范围 |
| --- | --- |
| `pr43_backend.py` | 仓库 `client-patch/ios-cumulative-login/build_native.py` 的 commands/segments/file_offset/uleb/read_rebase/constant；只保留实际调用的解析定义 |
| `runtime_symbols.py` | 仓库 `client-patch/ios-cumulative-login/map_runtime.py` 的 function/relocs/derive；保留真实对象与原生字节匹配 |
| `aot_helpers.py` | 2026-08-30本地 iOS Rush 排行榜工具 `build_ios_rush_leaderboard_ipa.py` 的常量、ARM64重定位、SWF摘要、函数和对象重定位读取定义；移除旧构建入口及本机路径 |
| `fill_ios_aot_stub_bodies.py` | 同批本地 `fill_ios_aot_stub_bodies.py` 的 return_stub；仅用于compiler-only输入 |
| `ios-method-map.json` | 本批按QName、签名和字段核对生成的Android/iOS方法映射；只保留配方消费的标签、方法编号和身份事实 |
| `baseline-contract.json` | 固定10-04 iOS输入的非秘密身份字段，移除成品路径、历史回执及登记状态 |
| `runtime-helper-map.json` / `additional-helper.json` / `runtime-extra-map.json` | 既有Rush/Lens/累计登录原生工具的符号地址与验证字节事实；只保留本链接器读取的字段，移除原任务路径 |
| `dependency-hashes.json` | 本批实际284份私有编译依赖ABC的文件名和身份；不包含ABC载荷 |
| `fixed_inputs.py` | 本批元数据身份和依赖目录校验入口；元数据文件SHA-256固定在源码 |

主工具 `prepare_port/compile_port/link_port/package_port/rotate_admission`、`overlimit_ios`、`hud_adapter` 和四个原测试接续本批已完成的iOS移植实现。这次整理只改输入路径、依赖导入、固定元数据和调用契约，不以新算法替换原生行为。

已发布的共享ABC导入、类追加、端点和签名布局逻辑继续复用仓库 `client-patch/lens0907-0908/`、`client-patch/ios-cumulative-login/`、`client-patch/ios-shop-first-open/veneers.py`；Android支持库复用 `client-patch/pr43-port/support/`。其PR43原作者关联及许可见 [Android支持库来源](../../pr43-port/support/SOURCES.md)。LIEF依赖通过正常Python环境引入，不随本目录复制。
