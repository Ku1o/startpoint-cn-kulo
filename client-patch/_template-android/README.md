# Android 客户端补丁专题模板

新专题复制本目录为 `client-patch/<专题名>/` 再实现，不改已验收的累计目录（如 `author-merge-20261001/`）。开工前先读 [AGENTS.md](../AGENTS.md)、[README.md](../README.md) 和 [ANDROID-BASELINE.md](../ANDROID-BASELINE.md)。

## 基线

起点固定为 [android-accepted.json](../android-accepted.json) 的 **public** 条目，钉在 [baseline.json](./baseline.json)：

| 字段 | 值 |
| --- | --- |
| 准入 ID | `android-181-author-1047-public-20261001` |
| APK SHA-256 | `955d1fef6844285f06f37ab9fa997b33721ca2a67caa6a547874ba662a2a40cf` |
| 内嵌 SWF SHA-256 | `b0b44b37d4f5d6492ff17f58158823515ea8e2875291974a3c29a0aff10246f6` |
| AIR UUID | `7c47c340-fe66-4755-ab66-599a33aa18a2` |
| 主 ABC 索引 | 361 |

登记表更新后，`build_swf.py` 和 `verify_patch.py --self-test` 会因 `baseline.json` 不再匹配而失败；此时先把专题重新钉到新基线并复核补丁，不要改检查。

## 文件

- `baseline.json`：基线钉。
- `build_swf.py`：校验输入 APK（复用 `verify_android_baseline.py`）→ 取内嵌 SWF → `apply_patch` → 输出 `patched.swf` 与 `build-report.json`。要求传入新的 AIR UUID，输出目录必须在仓库外。
- `verify_patch.py`：`--self-test` 只核对基线钉；`--out-dir` 回读构建报告与 SWF，核对血统、哈希和新 UUID，再执行专题自己的 `check_patch`。

实现时只需填 `apply_patch` 和 `check_patch`，其余保护保持原样。

## 用法

```bash
python -B client-patch/<专题名>/verify_patch.py --self-test
python -B client-patch/<专题名>/build_swf.py --apk <基线APK> --out-dir <仓库外目录> --uuid <新UUID>
python -B client-patch/<专题名>/verify_patch.py --out-dir <同一目录>
```

## 边界

- 只交补丁源码、验证器和本说明；APK、SWF、签名材料、准入密钥不进 Git。
- 改 SWF 必须换新的 AIR UUID。
- 出包、签名、登记 `android-accepted.json`、iOS 移植都由所有者完成。
- 构建报告记 `device_tested: false`；离线检查不等于真机验收。

## 专题说明（复制后填写）

- 目标：
- 改动的方法体 / 常量：
- 服务端配套：
- 已实际运行的验证：
- 已知限制：
