# 战阵之宴离线重置教程

本教程用于把一个受支持的战阵活动恢复为全新一轮。当前活动为 `event_id=7`。

重置会清除该期活动的全局击破进度、击破流水、总奖励领取记录、关卡进度、活动任务状态、兼容 Rush 状态和未完成战斗。它不会回收已经发到玩家背包里的奖励，也不会修改账号、存档、货币、背包或战阵三套编队。

因此，重置后玩家可以重新推进并再次领取活动奖励；已经获得的奖励仍然保留。

## 1. 重置前准备

1. 通知玩家退出客户端，避免停服后仍有战斗结算。
2. 确认项目根目录、数据库目录和目标活动 ID。
3. 记录当前战阵总击破数、奖励领取状态和活动时间，便于重置后核对。
4. 确保磁盘至少能容纳一份 `wdfp_data.db` 完整备份。

默认数据库目录是项目根目录下的 `.database`。如果云服通过 `DATA_DIR` 使用其他目录，以下命令中的数据目录必须替换为实际绝对路径。

## 2. 只读预览

只读预览可以在服务运行时执行，不会写入数据库：

```bash
npm run raid:reset -- --data-dir /服务器项目根/.database --event-id 7
```

Windows 本地示例：

```powershell
Set-Location 'F:\startpoint-cn-main'
npm run raid:reset -- --data-dir 'F:\startpoint-cn-main\.database' --event-id 7
```

检查输出中的 `mode` 应为 `dry-run`，并确认 `rowsToDelete` 只包含预期的活动状态。

## 3. 停止游戏服务

正式重置前必须停止游戏服务。使用云服当前实际采用的进程管理方式，例如 systemd、PM2、Docker Compose 或直接运行的 Node 进程。不要在服务仍可写入数据库时继续。

停服后确认游戏端口已经没有监听进程。Windows 本地端口检查示例：

```powershell
Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue
```

这条命令应当没有输出。

## 4. 正式重置

在项目根目录执行：

```bash
npm run raid:reset -- --data-dir /服务器项目根/.database --event-id 7 --apply --server-stopped --confirm RESET-RAID-7
```

Windows 本地示例：

```powershell
Set-Location 'F:\startpoint-cn-main'
npm run raid:reset -- --data-dir 'F:\startpoint-cn-main\.database' --event-id 7 --apply --server-stopped --confirm RESET-RAID-7
```

工具会在删除数据前创建完整数据库备份：

```text
.database/admin-backups/raid-event-reset-7-<时间戳>/
├── wdfp_data.db
├── wdfp_data.db.version
└── backup-info.json
```

输出必须包含：

```text
"reset": "completed"
```

如果命令失败，不要启动服务；先保留命令输出和自动备份，检查数据库目录及磁盘空间。

## 5. 重启与验收

使用停服前相同的进程管理方式启动服务，然后检查：

- 游戏端口恢复监听；
- 服务启动日志没有数据库迁移或资源加载错误；
- 战阵总击破数从头开始；
- 关卡、活动任务和未完成战斗已重置；
- 三套战阵编队保持原样；
- 玩家账号、货币、背包和已经获得的奖励保持原样；
- 300 次奖励预览为星导石 ×2000、深渊十连券 `999014` ×25；
- 单次 Boss 击破奖励仍按 Mana ×500 与锻造石 `100000` ×25 解析。

可以再次执行只读预览。刚完成重置时，所有 `rowsToDelete` 应为 `0`；玩家开始新一轮活动后，对应数字会重新增长。

## 6. 从自动备份回滚

仅在重置结果不符合预期时回滚：

1. 再次停止游戏服务并确认端口不再监听。
2. 额外备份当前 `.database/wdfp_data.db`、版本文件以及存在的 `-wal`、`-shm` 文件。
3. 将自动备份目录中的 `wdfp_data.db` 和 `wdfp_data.db.version` 复制回实际数据库目录。
4. 将旧的 `wdfp_data.db-wal` 与 `wdfp_data.db-shm` 移出数据库目录，避免旧 WAL 作用到恢复后的数据库；保留它们用于排查，不要直接丢弃。
5. 启动服务并重新检查战阵状态、账号和背包。

不要在服务运行时覆盖数据库文件，也不要只恢复 `.db` 而让旧的 WAL/SHM 留在原位。
