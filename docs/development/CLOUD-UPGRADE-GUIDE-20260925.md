# 2026-09 云服升级与回滚教程

本教程对应服务端结算优化、Node.js 24 运行时升级、中秋国庆月饼十连池 1.4.118，以及作者 1.4.1047 风巨蜥资源 1.4.119。整合包是相对上一份已覆盖到 1.4.117 的增量包，解压目标为服务端项目根目录。

## 升级前准备

1. 确认当前服务端处于维护窗口，记录项目目录、Node.js 版本、当前 CDN 版本和服务进程启动命令。
2. 停止服务后备份 `.database/` 中的 `wdfp_data.db`、`wdfp_data.db-wal`、`wdfp_data.db-shm`（存在时），以及当前 `package.json`、`package-lock.json`、`out/`、`assets/asset-patch/manifest.json` 和 `assets/asset-patch/active/`。备份目录应带时间戳，不能覆盖上一份备份。
3. 检查工作目录没有未保存的运行时修改。不要把 `.cdn/`、日志、数据库、密钥、玩家备份或其他 `production/` 散文件放进覆盖包。

## Node.js 24 与服务端文件

1. 在 Windows x64 安装 Node.js `v24.21.0` 或更高的 Node.js 24 LTS。升级后在服务端项目根目录执行：

   ```powershell
   node --version
   npm --version
   npm ci --omit=dev
   ```

2. 将整合包解压到项目根目录，保留已有 `.env`、数据库、日志和运行状态文件。包内的 `package.json` / `package-lock.json` 要与 `out/` 一起更新；不要从其他项目复制 `node_modules`。
3. 本批没有数据库表或存档格式迁移。若服务启动前需要确认数据库完整性，可执行：

   ```powershell
   node -e "const Database=require('better-sqlite3'); const db=new Database('.database/wdfp_data.db',{readonly:true}); console.log(db.pragma('integrity_check',{simple:true})); db.close()"
   ```

   预期输出为 `ok`。

## CDN 与内容更新

1. 保留清单中上一版本已经启用的分包，并把整合包中的 `assets/asset-patch/manifest.json` 和两个 active ZIP 原样写入对应路径：
   - `1.4.117 → 1.4.118`：中秋国庆月饼十连池；
   - `1.4.118 → 1.4.119`：作者 1.4.1047 风巨蜥累计资源。
2. 不要拆开或重新压缩 ZIP，也不要把 ZIP 内部的 `production/` 成员改成外层散文件。部署前用随包清单和 SHA-256 文件核对名称、大小、成员数和哈希。
3. 中秋池使用虚拟长期开放区间，客户端提示的现实活动时间为 2026-09-25 12:00 至 2026-10-09 12:00。它没有服务端真实时钟自动关闭；活动结束时应另发 CDN 增量隐藏入口，不修改本批历史包。

## 准入与客户端

本批服务器覆盖包不包含 APK/IPA。客户端安装包、准入号和密钥必须使用对应发布批次的受验收成品及仓库外的完整配对配置；不要从客户端包或其他非受限文件复制密钥。若本次发布实际更换准入号，先按客户端发布记录核对 Android/iOS 的平台、版本、截止时间和密钥配对，再把完整 `config/client-admission.json` 与 `config/client-admission.keys.json` 放入受限的服务器交付目录。没有准入变更时沿用云服现有配对。

## 启动与验收

1. 用原来的服务启动命令启动服务，确认监听端口（通常为 8001/8003）和进程日志无启动异常。
2. 检查健康接口、登录/账号恢复和玩家存档读写；抽样执行一次单人结算，确认日志可以出现 `[SINGLE-SETTLEMENT]` 和 `[SQLITE-COMMIT]` 诊断行。
3. 验证内容接口返回 CDN `1.4.119`，中秋池 `990003`、月饼道具 `999019` 和作者角色说明可读；抽奖、十连保底、兑换、存档导入导出及失败回滚应使用隔离账号或测试数据库。
4. 确认客户端更新接口为同一份 manifest，Android 与 iOS 下载的两个 active ZIP 哈希分别与随包清单一致。手机裁切、动效、长时间联机和 iOS 真机验收仍应按客户端验收记录单独安排。

## 回滚

1. 停止服务，保留失败启动日志和当前数据库副本。
2. 从本次时间戳备份恢复 `package.json`、`package-lock.json`、`out/`、清单和 active ZIP；恢复 Node.js 20 仅适用于旧版本代码，旧依赖不能与本批 `node_modules` 混用。
3. 必要时恢复数据库的 `db`、`-wal`、`-shm` 三个文件，启动旧版本并再次执行 `integrity_check`、登录、存档读取和健康接口检查。
4. CDN 回退必须恢复完整的上一版 manifest 与对应分包链，不能只删除 1.4.119 ZIP。回滚不删除云端已有文件，也不改写玩家存档。

升级记录应填写执行时间、操作者、包文件 SHA-256、服务进程版本、健康检查结果和回滚点；云服实际部署完成后再补写部署状态。
