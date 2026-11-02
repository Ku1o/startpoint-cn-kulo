# 独立推送辅助

此工具只收集推送对象事实、调用固定版本 Gitleaks 扫描新增历史。它不自动推送、不安装钩子、不修改 Git 配置，不提供统一的 `allowPush` / `pass` 结论，也不缓存通过结果。已退役的 `git-preflight` 不在执行链中。现行提交审查、独立历史密钥扫描及推送后远端 CI 规则仍分别适用。

## 收集对象事实

```powershell
python <repo>/tools/push-support/push_support.py context --repo <repo>
```

默认使用 `origin` 的实际 push URL、`main`、`HEAD`，可用 `--remote`、`--branch`、`--target` 指定。标准 GitHub HTTPS / SSH 地址受支持，多 push URL、含凭据 HTTPS 地址及其他主机均拒绝。仅执行一次 `gh api graphql`，合并读取仓库权限、默认分支、指定远端引用及 `gitleaks/gitleaks-action@v3` 的当前对象 SHA；不 fetch。所有子进程均设置 `GIT_OPTIONAL_LOCKS=0`、`GIT_NO_LAZY_FETCH=1`，抑制 Git 的可选锁/索引刷新及 partial-clone 懒抓取，不写 Git 配置。stdout 返回 JSON。仅显式提供 `--output <新路径>` 才保存快照，不覆盖已有文件；输出须在源码仓库、实际 Git 目录及 common Git 目录之外，写出前再次解析路径检查。

本地事实包括 HEAD、分支、工作区状态、目标完整 SHA、远端基线对象是否存在、祖先关系、`base..target` 的全部新增可达提交（含合并带入历史），以及基线到目标的差异路径。缺对象、缺远端分支、认证/网络/API 失败时保留未知值并非零退出，不把未知当成零条提交。差异路径只表示两端树的差异，不能替代历史扫描范围。

同时校验固定二进制 SHA256 / `version`，将 action 对象、目标提交 `.github/workflows/hygiene.yml` 的原始字节 SHA256 与 lock 比较，并列出工作树 workflow 是否与目标一致。漂移或未知标记 `needs_review`；action SHA 自身不能证明扫描器版本。lock 记录的是已人工核验 CI 运行对应的版本快照，不能推断未来 action 实际下载的版本。context 无事实错误时退出 0，但漂移仍需人工复核，退出 0 不是推送授权。

## 扫描新增历史

```powershell
python <repo>/tools/push-support/push_support.py scan --repo <repo> --base <完整基线SHA> --target <完整目标SHA> --report <workspace>/work/<本批目录>/gitleaks-redacted.json
```

从同目录 `scanner-lock.json` 读取固定版本、固定 exe 相对路径与 SHA256。两个命令均可通过 `--lock <路径>` 显式选取其他 lock，主要用于隔离测试或人工重核。工具不下载安装更新、不生成或修改 ignore。固定 exe 及 lock 是复用工具输入，应保留，不能当作任务垃圾清理。

scan 要求本机存在两个完整 commit 对象；使用 `git rev-list base..target` 列出所有新增可达提交，既不添加 `--first-parent` / `--no-merges`，也不缩成最后一条提交。非空范围调用固定 exe 的 `detect --source … --redact --exit-code=2 --report-format=json --report-path=… --config <repo/.gitleaks.toml> --gitleaks-ignore-path <repo/.gitleaksignore> --log-opts="-m <base>..<target>"`。显式 `-m` 使 merge 提交相对各父提交产生的补丁也进入扫描，覆盖仅在 merge 结果中首次加入的内容。子进程通过追加 `GIT_CONFIG_COUNT` 设置 `core.longpaths=true`，不写全局或仓库 Git 配置；上述只读环境同样传递给扫描器内部的 Git 子进程。

当前仓库的 `.gitleaks.toml`、`.gitleaksignore` 必须与目标提交中的文件字节一致；JSON 列出两份哈希。缺失、不一致或扫描期间变化都会报错，不能用未提交放宽规则冒充目标验收。版本、二进制、配置、ignore、范围和 CI 实际对象的对应关系仍需按现行规则人工判断。

`--report` 必须是源码仓库、实际 Git 目录及 common Git 目录之外的全新路径，父目录须已存在；启动扫描器写出前再次解析路径检查，不覆盖旧证据。原生 JSON finding 报告由 Gitleaks 以 `--redact` 生成，运行摘要输出 stdout，仅保留安全计数和固定错误分类，不回显可能含源代码或凭据的原始 stdout/stderr。报告仍含 commit、路径等审查信息，按本地证据保存，不提交源仓。

扫描返回：0 为 `clean` 或明确的 `empty_range`，2 为 `findings`，1 为错误。空范围不启动扫描器、不写报告，也不伪称完成扫描。`Filename too long`、部分扫描或 Git 错误即使进程返回 0 也判定扫描失败；报告缺失、损坏或与退出码矛盾同样失败。两个命令的 JSON 均含 `elapsed_seconds`、`started_at_utc`、`finished_at_utc`，便于判断快照时效；无复用缓存或自动 push。

## 缺失、损坏与漂移

源码分发不附带 Gitleaks 可执行文件。首次使用时从 `scanner-lock.json` 的 `archive_url` 下载固定归档，核对 `archive_sha256` 后解压到仓外工具目录，再核对 `binary_sha256`。在该目录保存一份 lock，保持 `binary_relative_path` 指向实际 exe，并用 `--lock <仓外 lock>` 传入。不要把下载的 exe 或私人扫描报告加入 Git。

缺少二进制/lock、SHA256 或版本不符时停止，保留现有证据，人工按可信上游来源重核；工具不会自动替换。action/workflow 漂移时需重新核对当前 CI 的 action、实际扫描器版本、配置与范围，再人工更新锁定快照。不能仅修改期望哈希绕过差异，也不能因本机扫描成功而省略远端实际 SHA 的 hygiene / gitleaks 结果核对。

## 验证辅助器

使用标准库测试，不运行业务工程测试。显式指定本批仓外夹具目录，测试会保留合成 Git 仓和脱敏报告供复核：

```powershell
$env:PUSH_SUPPORT_TEST_ROOT = '<workspace>/work/<本批测试目录>'
python -B <repo>/tools/push-support/tests/test_push_support.py
```

测试包含真实扫描的合并历史、先加后删、合并提交独有内容与默认日志漏扫负对照，以及规则漂移、错误工具身份、未知远端、只读环境和输出边界。固定扫描器及身份锁长期保留；测试下载、中间缓存和重复夹具按工作区清理规则处理，不能因临时产物清理删掉复用工具。
