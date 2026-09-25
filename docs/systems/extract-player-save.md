# 从数据库备份恢复单个玩家的进度

## 双击启动（Windows）

需要带去另一台 Windows 云服时，使用便携 ZIP：完整解压到独立目录，双击包内的 `双击提取玩家存档.cmd`。便携包自带 Windows x64 Node.js、SQLite 原生模块和所需存档代码，无需云服安装 npm 依赖，也无需覆盖服务端目录。只输出单人 JSON，不创建数据库备份。包内 `使用说明.txt`、`manifest.json` 和 ZIP 旁的 SHA-256 文件分别提供操作说明和完整性校验。

生成便携包：`node tools/player-save-extractor/build-portable.cjs`；默认输出到 `outputs/player-save-extractor/`。隔离验证入口：`node tests/player-save-portable.test.cjs <解压后的便携目录>`。Node.js v24.21.0 的许可原文取自 `https://raw.githubusercontent.com/nodejs/node/v24.21.0/LICENSE`，随包保留。

双击项目根目录的 `双击提取玩家存档.cmd`，或直接打开 `tools/player-save-extractor/PlayerSaveExtractor.exe`。

Git 只保存源码及生成脚本，不保存 EXE、Node.js、安装依赖或便携 ZIP。首次克隆后，先按项目方式安装依赖并生成 `out`，再运行 `tools/player-save-extractor/build.ps1` 生成本地窗口入口；使用已提供的便携 ZIP 则无需这些步骤。

1. 点击“选择文件”，选择数据库；也可在路径框粘贴数据库文件或目录。
2. 输入游戏内 viewer id，点击“查询玩家存档”。
3. 核对玩家名；如果有多个存档，在列表中选择需要提取的一个。
4. 点击“选择位置并导出”，选择 JSON 的保存位置。窗口显示提取成功及文件位置。

窗口只负责复制出指定玩家的存档，不创建数据库备份，不导入存档，也不执行数据库恢复。

无需输入命令。查询和导出在后台进程运行，窗口保持响应；操作期间先等待完成再关闭。取消文件选择不会导出，也不会覆盖已有文件。修改数据库或 viewer id 后必须重新查询，避免沿用上一次的存档选择。

这是项目内的 Windows 窗口入口，需保留当前目录结构及已有 Node.js 24 LTS+、`node_modules`、`out` 依赖，不能只把 EXE 拷到另一台电脑使用。程序复用下述只读提取逻辑，存档格式和导入行为不变。开发时可运行 `tools/player-save-extractor/build.ps1`，用 Windows 自带的 .NET Framework 编译器重新生成 EXE，无需构建服务器。

## 命令行入口

在项目根目录使用独立工具，不需要启动服务。依赖现有 Node.js、better-sqlite3 和 `out/data/snapshots/player-snapshot.js`。工具通过备份中的 `sessions.token`（`type = 2`）找到 viewer id 对应的账号，再找到该账号的玩家存档；viewer id 与内部 `players.id` 不同。

```powershell
node tools/extract_player_save.cjs --database "F:/backup/wdfp_data.db" --viewer-id 123456789 --output "F:/recovery/save.json"
```

路径仅为示例，请替换为实际备份、序号和已经存在的输出目录。`--database` 也可以指定包含 `wdfp_data.db` 的目录；必须显式指定，不读取 `DATA_DIR`，不会误用默认运行库。省略 `--output` 时，在当前目录生成带序号、内部玩家 ID 和时间的 JSON 文件，不覆盖已有文件。

一个账号可能有多个存档。先查看候选，再明确选择；工具不会根据当前服务器或 `active_account.json` 的选择状态猜测目标：

```powershell
node tools/extract_player_save.cjs --database "F:/backup" --viewer-id 123456789 --list
node tools/extract_player_save.cjs --database "F:/backup" --viewer-id 123456789 --player-id 42 --output "F:/recovery/save.json"
```

恢复步骤：

1. 选取误删前的完整 SQLite 备份；ZIP 先解压。若备份包含 `wdfp_data.db-wal`、`wdfp_data.db-shm`，保留同目录同名文件，不可只复制正在运行中的 `.db` 来制作备份。已丢失的 WAL 无法由本工具补回。
2. 运行提取命令，核对成功结果中的 viewer id、玩家名及内部玩家 ID。
3. 让玩家创建并确认一个目标存档。在管理后台打开该目标存档的页面，使用已有导入功能上传提取的 JSON。后台会先保存目标存档的回滚备份，再恢复进度。

提取使用只读连接和一致性读事务，不启动数据库初始化或迁移。SQLite 读取 WAL 数据库时可能维护配套共享内存文件，因此应对备份副本操作。工具不修改备份中的业务数据，不写入在线数据库。

输出沿用完整 V2 玩家存档格式，包括角色、装备、物品、任务、编队及存档归档历史；排除项沿用现有规则并记录在 JSON 的 `summary.excludedState`。账号密码、登录令牌、设备绑定、好友关系、排行榜等服务器公共记录不随存档迁移。导入保留目标账号及 UID；该功能恢复玩家进度，不重建已删除的账号身份或原 viewer id。

支持当前 V2 逻辑结构及现有压缩存储兼容结构。不会伪造 schemaFingerprint 或补空表掩盖丢失进度。较旧备份缺少必需表、包含未分类玩家表、结构不兼容或数据损坏时会报错；应使用匹配结构的工具版本，或在独立副本上完成受支持的迁移。即使提取成功，目标服务器仍会检查存档结构是否匹配。现有 V1/V2 导入行为未变更。

测试入口：`node --test tests/extract-player-save.test.cjs`。测试仅使用隔离数据库，覆盖 viewer 映射、多存档归属、只读提取、旧/压缩存储、错误拒绝及后台导入和回滚备份。
