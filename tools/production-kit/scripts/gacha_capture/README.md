# 原生卡池录制适配器

`gacha_capture.py` 以独立 AIR 应用运行固定 Android C8601 客户端中的原生 `SkillPreviewBattle`。适配器只支持其已核对的 SWF SHA、原生资源格式和 60 fps 视口。录制会写入新的本地工作目录和独立的 AIR 私有缓存。它提供离线执行与逐帧证据，设备验收和完整界面可见性另有验收。

Python 入口为 `validate(config_path)`、`capture(config_path, new_run_dir)` 和 `verify(config_path, run_dir)`。三者均返回可序列化的字典。旧录制须提供完整的构建、原生结果、配置、资源和 PNG，使用 `verify` 读取。新录制同时落盘 `CAPTURE.json`。

配置 `schemaVersion: 1` 包括下列字段。

- `adapter` 为 `c8601-air-v1`，客户端 `clientSwf` 用 `{file, sha256, bytes}` 固定。
- `toolchain` 指定 `supportRoot` 及绑定的 `java`、`compiler`、`adl`、`backgroundRunner`。在 Windows 使用已配置的后台桌面启动器，编译与录制没有可配置的命令字符串。
- `assets` 绑定一份 `{schemaVersion: 1, files: [...]}` 的清单。归档记录包含 `logical/root/archive/member/bytes/sha256`，APK 内嵌 ZIP 可额外提供 `outerMember/outerMemberSHA256`。相对资源路径相对该清单解析。
- `preview` 指定 `roleId/poolId/questId/log/clip/enablesAbility/enablesPowerFlip/terrain/fieldData/field/zone`。回放和地形来自同一个资源清单，关卡与地形以原生主表读回核对。完整素材闭包应预先解析并固定到清单，缺项会使录制失败。
- `protectedRoots` 标记源码、冻结输入和其他禁止写入的目录。输出须为已存在任务目录中的新目录。

候选回放增加 `kind: replay`、`candidateFile`、归档 `sourceProof` 和精确 `allowedChanges`。候选只能调整弹珠初态或在全部原命令之后缩短 `end_frame`。还原字段后完整类型树须等于原件。候选地形以 `kind: terrain` 声明，保留原逻辑名，并附逐对象坐标改动。已存在的石台、指定生成点或定位标记可在明确的坐标白名单内移动。边界和其他字段由完整树反解检查保护。

回执固定 SWF、实际场景、回放、资源、原生 Finish、起止、技能执行、血量、原生结果和全部 PNG。每帧清单有 `name/sha256`。序列摘要为对按编号拼接的 `<name> <sha256>\n` ASCII 记录取 SHA-256。旧录制额外保留所用场景书的身份。将该回执交给技能媒体阶段及完整界面审查。
