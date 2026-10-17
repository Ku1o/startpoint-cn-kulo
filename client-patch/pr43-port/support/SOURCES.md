# SWF / ABC 支持库来源

本目录是 Android PR43 方法移植所需的最小 Python 支持库。它们沿用
[StarPoint CN 源仓库的 GPL-3.0 许可证](../../../LICENSE)，不是本批重新原创的解析器。
以下来源均为同一仓库 [PR43](https://github.com/Ku1o/startpoint-cn-kulo/pull/43)
的脚本，原提交作者为 `kuronzzhan-droid`（GitHub 用户 ID `297029191`）。

| 本目录文件 | 原仓库相对路径 | 原文件最后修改提交 |
| --- | --- | --- |
| `common.py` | `docs/client-apk-patches-v33/_build-support/perf-tools/common.py` | `722197cd346ccad175d28a1db772e4f8fc9a0f65` |
| `perf2_core.py` | `docs/client-apk-patches-v33/_build-support/perf-tools/perf2_core.py` | `417c27526538707b6c123531bfdf1b08614237d6` |
| `asm.py` | `docs/client-apk-patches-v33/_build-support/perf-tools/asm.py` | `417c27526538707b6c123531bfdf1b08614237d6` |
| `bodies.py` | `docs/client-apk-patches-v33/_build-support/perf-tools/bodies.py` | `417c27526538707b6c123531bfdf1b08614237d6` |
| `swfabc.py` | `docs/client-apk-patches-v33/_build-support/perf-tools/swfabc.py` | `417c27526538707b6c123531bfdf1b08614237d6` |
| `abcfmt.py` | `docs/client-apk-patches-v33/_build-support/perf-tools/abcfmt.py` | `417c27526538707b6c123531bfdf1b08614237d6` |
| `opwalk.py` | `docs/client-apk-patches-v33/_build-support/perf-tools/opwalk.py` | `417c27526538707b6c123531bfdf1b08614237d6` |
| `swftags.py` | `docs/client-apk-patches-v33/_build-support/perf-tools/swftags.py` | `417c27526538707b6c123531bfdf1b08614237d6` |
| `apk_manifest.py` | `docs/client-apk-patches-v33/_build-v34/apk_manifest.py` | `b37291603d6e2e308dbd1194bffd9409ba3c690e` |

归档脚本最初随提交 `417c27526538707b6c123531bfdf1b08614237d6` 引入。
各模块只依赖 Python 标准库及本目录中的模块，不需要原档案目录。
这次整理保留解析、汇编、常量池和校验算法；`common.py` 删除未使用的历史
APK/SWF 固定输入及其读取函数，`swftags.py` 删除命令行统计入口，
`apk_manifest.py` 删除历史 APK 输入与审计文件导出入口。输入与输出由上层
构建器显式传入，不会读写原作者的本地路径。`asm.py` 同时更新同目录模块加载的说明。

本目录不含游戏反编译源码、客户端二进制、构建报告或准入凭据。
