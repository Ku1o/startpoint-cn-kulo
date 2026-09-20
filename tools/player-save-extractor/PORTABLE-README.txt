StarPoint CN 玩家存档提取器 — Windows x64 便携版

使用方法
1. 将整个 ZIP 解压到一个独立目录，例如 D:\PlayerSaveExtractor。
2. 双击“ 双击提取玩家存档.cmd ”。
3. 选择数据库文件，输入游戏内 viewer id，点击“查询玩家存档”。
4. 核对玩家名称；若有多个存档，选择其中一个。
5. 点击“选择位置并导出”，保存单人存档 JSON。

功能只有提取存档：只读取你选定的数据库，输出一个 JSON。
不备份数据库，不恢复或覆盖玩家存档，不连接游戏服务。
不需要覆盖云服项目、不需要停服或重启服务。
包内已经带有 Node.js 和 SQLite 读取依赖，无需安装 npm 依赖。
保留解压后的完整目录结构，不能只拷贝 EXE。
适用于带桌面环境的 64 位 Windows Server；窗口需要系统 .NET Framework 4.5 或以上。

注意
- viewer id 是游戏内玩家序号，不是内部存档 ID。
- 支持选择数据库文件，或含 wdfp_data.db 的目录。
- 如果原数据库有配套的 -wal / -shm 文件，请放在原数据库同一目录，勿单独丢弃。
  SQLite 可能维护配套共享内存文件；工具不修改数据库中的玩家数据。
- 输出文件已存在时会拒绝覆盖，请换一个文件名。
- 旧数据库缺表、未知玩家进度表或结构不匹配时会显示错误，不自动迁移数据库。
- 输出使用已有 V2 玩家存档格式，不包含账号密码和登录令牌。

可选命令行（在解压目录打开终端）
.\node.exe tools\extract_player_save.cjs --database "D:\backup\wdfp_data.db" --viewer-id 123456789 --output "D:\save.json"

manifest.json 记录包内文件及 SHA-256；ZIP 旁的 .sha256 文件用于核对下载完整性。
LICENSE、licenses 目录及各依赖目录附有许可信息；src 与工具源码用于复核实现。
