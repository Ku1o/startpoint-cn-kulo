# 服务端续期与 Android/iOS 协议补齐

## 用户范围

2026-09-15 用户要求“补齐一下，把 ios 的也一起做好，服务端搞好了到时候再做客户端”。本轮完成服务端共同协议、生命周期处理、测试及接口交接。未编辑客户端 AS/SWF/DEX，未制作、签名、安装 APK 或 IPA，未提升任何 accepted registry。iOS 是协议测试覆盖，不能写成 IPA 已完成或真机验收。

## 已完成

- 有效且绑定账号的游戏 HTTP/TCP 请求将原凭证延长到当前时刻后 30 分钟，连续共斗无需依赖普通 HTTP 才能续期。凭证字符串不轮换，不主动关闭已有连接。
- 已绑定凭证过期后 5 分钟内可携同一账号会话调用续期接口；过期期间游戏请求仍拒绝，未绑定凭证无此宽限。超过宽限后重新握手及恢复账号。
- 版本停用、删除、允许期限到期、平台改变、密钥轮换优先于续期；撤销还会清理未完成挑战。无效/错绑请求不续期。
- Android/iOS 在同一配置中分别登记，平台归属取自服务端条目，不信任平台标识作为豁免；缺省平台保留旧 Android 配置兼容性。
- 返回 `expires_in_ms`、`renew_after_ms`、`renew_grace_ms`、`server_time` 和恢复 `action`，供后续客户端实现无感提前续期、有限退避和挂起恢复。服务重启后的未知凭证提示重新握手，不直接误报安装包过旧。

## 验证

| 检查 | 结果和限制 |
| --- | --- |
| 原核心/HTTP 回归 | 34 项，通过；含旧 v1 兼容、多构建、拒绝路径、热加载及资源回复回归 |
| 新生命周期 HTTP | 47 项，通过；使用 Fastify 注入、真实账号注册/resume/logout 和隔离数据库；Android/iOS 活动续期、宽限、重试、长挂起、模拟准入存储重启后恢复及账号退出拒绝 |
| TCP | 36 项，通过；真实 socket、真实配置定时器，仅准入时钟加速，Android/iOS 两条连接各跨 3 小时且无需 HTTP/显式续期；覆盖停用一端保留另一端、长闲置拒绝和宽限后重连 |
| 编译产物 | 上述三组对生成的 `out/` 准入实现运行同样通过；生命周期使用现有源码账号处理器，TCP 游戏处理器为桩 |
| 既有玩家登录回归 | 63 项及拒绝路径通过；独立临时数据库 |
| 类型检查 | `npx tsc --noEmit -p outputs/client-admission-work/tsconfig.json` 通过，仅范围限定为 src，避开已有 outputs 测试源扫描问题 |
| 完整构建 | 在 `outputs/client-admission-server-20260915/build` 复制当前 src、原 package/tsconfig/tailwind 配置和页面，复用只读依赖/JSON 输入；原 `npm run build` 的 TS 与 CSS 均通过；只回写本任务两份对应 JS，核对源码输入与输出哈希一致 |
| 实际本地服务 | 重新启动之前的隔离测试服务，HTTP 8002/TCP 8013，进程 22004；通过真实网络请求检查 v1 挑战/证明、续期保留 token、相对时长、无凭证拒绝和未知凭证恢复动作；摘要在 `outputs/client-admission-server-20260915/live-smoke.json` |

3 小时测试是加速推进准入时钟、使用真实 TCP 消息的协议测试，并非模拟器挂机 3 小时。没有进行双人战斗、iPhone/IPA 或新版 APK 的设备测试。网络物理中断、服务进程重启仍可能使共斗断开；本轮解决的是凭证生命周期带来的额外断线，不承诺游戏房间跨重启保留。

无存档表、持久化字段、角色/道具 ID、账号归属、V1/V2 导入导出格式改动。所有新测试使用独立目录；本地运行镜像和真实玩家数据未变。

## 交付与运行状态

- 分支 `staging`，HEAD `afdef6811e344a7cb8ac1966fbf29e8601ef2ed3`。已刷新远端引用，`staging` 与 `origin/staging` 差异为 0/0；`origin/staging` 比 `origin/main` 多 2 个既有提交。本轮未提交/推送，不更新 main。
- 本轮功能修改：`src/lib/client-admission.ts`、`src/multi/tcp/server.ts`；生成：`out/lib/client-admission.js`、`out/multi/tcp/server.js`。保留首轮 `src/cn-server.ts` / `out/cn-server.js` 的接入依赖。
- 原 `config/client-admission.json` 仍为兼容默认，未打开正式严格模式。管理员字段用法见 README，客户端交接见 SERVER-PROTOCOL。
- 仅重启源仓库的隔离测试实例；未复制任何文件到 `F:\startpoint-cn-main`，因此没有正式镜像覆盖备份。隔离服务沿用本任务独立数据和配置，继续运行供本地测试。
- 未要求、未制作云服务器整合包，未连接、覆盖或重启云服。后续授权交付文件已追加 PENDING-CLOUD-OVERLAY；该文件既有其他任务条目保留。
- 其他现存脏文件、角色资源、诊断客户端、工坊文件等原有用户修改均保留。原 r6 APK SHA-256 仍为 `2e02a8602f0f6701aa60249416983b2c2c8c8fb72d74794ccee774d3478675de`。

### 对应产物 SHA-256

| 文件 | SHA-256 |
| --- | --- |
| src/lib/client-admission.ts | `a52703367f07643df2890c0c822042fc6f58b34530296a64ce2679bf8d54cc43` |
| src/multi/tcp/server.ts | `691cfa8add850b4cb32fa612e5f94b3fe6365e471c6596ab1df3c6ace1c550a5` |
| out/lib/client-admission.js | `772719839c1e304fb3a26855aaffa4ca255e9d187e1676412424340e28545029` |
| out/multi/tcp/server.js | `59018c2a529aefa8b3376c3a55b5ef5504bddaed8f0dbe089d267d910cf07683` |
