# 客户端接入校验（Android / iOS）

本功能针对“旧包或其他包只改服务器地址就能接入”。客户端内置独立的构建编号及准入密钥；服务端发一次性随机挑战，验证 HMAC 后签发初始有效期 30 分钟的内存凭证。登录成功后凭证与账号会话绑定，游戏 HTTP 和共斗 TCP 均校验，成功校验的已绑定游戏请求自动把有效期延长到当前时刻之后 30 分钟。不会上传整份安装包，也不逐请求计算 APK 文件哈希。

这是轻量构建准入，不是设备证明或完整 APK 签名远程认证。有人反编译并提取内置准入密钥、移植协议后仍可能仿造客户端；符合本次阻止普通旧包改地址的范围。

## 管理员如何修改

运行目录放两个文件：

- `config/client-admission.json`：日常可编辑的允许列表。
- `config/client-admission.keys.json`：打包工具生成的构建准入密钥，保留在服务器和本地打包目录，不提交 Git、不发群。与 Android 签名私钥、签名密码无关。

允许列表示例（编号必须使用对应 APK 构建报告里的 `build_id`）：

```json
{
  "enforce": true,
  "updateMessage": "当前客户端版本已停止支持，请到群聊下载新版安装包。",
  "builds": [
    {
      "id": "android-release-previous",
      "platform": "android",
      "name": "上一版，保留到过渡期结束",
      "enabled": true,
      "allowUntil": "2026-09-22T23:59:59+08:00"
    },
    {
      "id": "android-release-current",
      "platform": "android",
      "name": "当前版本",
      "enabled": true,
      "allowUntil": null
    },
    {
      "id": "ios-release-current",
      "platform": "ios",
      "name": "iOS 当前版本",
      "enabled": true,
      "allowUntil": null
    }
  ]
}
```

- 多个 APK：保留多条记录，同时允许；`name` 只是备注，修改它不影响识别。
- Android / iOS 共用此列表，`platform` 仅允许 `android` 或 `ios`；旧条目未填时按 `android` 解释。每个构建编号全局唯一，使用各自独立的密钥。平台归属由服务端配置决定，不采信 User-Agent 或客户端自报平台来豁免校验。更改已有条目的平台会使其旧凭证和未完成挑战失效。
- 停用：将该条 `enabled` 改成 `false`，或删除整条记录。
- 限时允许：`allowUntil` 填带时区的时间；`null` 表示不限时。使用真实系统时间，不跟随游戏活动虚拟时钟。
- 服务每 2 秒重读配置；有效修改不需要重启。已有连接在下一条游戏请求时被拒绝，TCP 空闲连接不会仅因配置变化立即断开。
- 覆盖时 JSON 不完整或密钥缺失，保留上一份有效配置并记录错误；首次启动没有有效配置则拒绝游戏接入。管理员接口仍可用。
- 建议先写临时文件再改名替换。新增 APK 时先覆盖包含旧、新密钥的密钥文件，再覆盖允许列表，避免中间状态缺少密钥。删除允许列表条目后再按需删其密钥。
- 每次带 APK 变动的后续授权云服更新，应交付配套允许列表及准入密钥；无 APK 变化时不要用默认空列表覆盖管理员配置。更新只合并指定版本，保留其他仍允许版本和手工期限。

配置不能含注释。未识别字段、重复编号和没有对应密钥的条目会被拒绝加载。没有 `downloadUrl`，游戏只显示去群聊获取安装包的文字。

## 第一次上线和回退

仓库默认配置为 `enforce: false`、空列表，防止首次同步立刻封住现有玩家。部署服务代码后，配上新 APK 的构建记录与密钥，先保持 `false` 发群；准备完成后改为 `true`。只有启用 `true` 才会拦截无准入协议的旧包。

**旧 APK 不能靠加入版本号获得新协议能力。** 多版本严格放行适用于已经内置准入协议的 APK。第一批遗留包的过渡期通过全局 `enforce: false` 控制，期间普通改地址包仍可能进入。

用户于 2026-09-15 指定“先做好服务端，到时候再做客户端”。服务端已支持 Android/iOS 共用协议及独立构建管理，iOS 协议用模拟客户端验证，尚未移植到 IPA；Android r6 仍是上一轮测试包。本轮没有改动或重打 APK/IPA。双端客户端完成并验证后再安排严格模式上线，当前遗留 iOS 不会因平台字段自动获得放行。

紧急恢复旧包：改回 `enforce: false`。若新版 APK 本身仍需可用，还应恢复它的条目和配套密钥；携带无效凭证的请求不会自动降级成旧包。服务重启后凭证失效，新版可重新握手并通过原登录恢复接口绑定；不修改账号或存档。

凭证与挑战在同一个 Node 进程内，当前 HTTP 和 TCP 共用该实例。未来若部署多进程或多节点，必须使用共享存储或保证 HTTP/TCP 到同一进程，不能直接沿用独立内存模式。

### 续期及断线处理

普通游戏 HTTP 请求和每条 TCP 入站消息都会轻量检查内存凭证。已绑定账号且校验成功的游戏请求会延长原凭证到当前时间之后 30 分钟，因此持续共斗即使没有 HTTP 请求也不会仅因跨越最初 30 分钟而断开。凭证字符串保持不变，不要求重连；标题资源、无账号请求及校验失败请求不会延长有效期。每 2 秒刷新的是服务端配置，不是客户端重新握手。

完全闲置超过 30 分钟后，过期凭证不能直接执行游戏请求；已绑定凭证在过期后 5 分钟内仍可携带同一账号会话调用 `/client-admission/renew` 恢复。超过宽限时间或服务重启后需要重新握手，再通过现有 `/player-auth/resume` 恢复账号。宽限只适用于续期，不放行过期的战斗/结算请求；停用、删除、密钥轮换或版本允许期限到期不受宽限保护。

新接口附带服务端相对时长和恢复动作，供后续两端客户端实现后台提前续期、有限重试、挂起恢复。当前 r6 不具备完整的新恢复交互。服务端规则与 3 小时加速 TCP 测试已完成；网络物理中断、服务进程重启本身仍会断开 TCP，不能承诺不断线。双端实际游戏的长时/网络恢复验证留待客户端阶段。接口字段和客户端待办见 [SERVER-PROTOCOL.md](SERVER-PROTOCOL.md)，本轮测试见 [SERVER-TEST-20260915.md](SERVER-TEST-20260915.md)。

## 构建与验证

`build.py` 每次先校验 accepted registry 的实际 APK，然后注入独立 helper 和小范围方法钩子。当前方法位置针对 2026-09-13 累计基线，保留其余原有功能；基线升级时需重新审查位置。

```powershell
python client-patch/client-admission/build.py --variant public --build-id android-release-current --keys outputs/client-admission-private/client-admission.keys.json --work outputs/client-admission-work/public-current --out outputs/client-admission-current --name StarPoint-CN-admission-public.apk
```

每个新发布版本分配新编号；修改服务器文件里的密钥不能更新用户已安装 APK。构建目录必须是不存在的新目录。密钥及生成的 BuildConfig 源码只放忽略目录。APK 使用既有签名证书，SWF、Manifest、DEX 缓存身份同步更换新 UUID；成品回读检查 ZIP 对齐、v1/v2 签名和其他成员原字节。

主要原方法：主 ABC 291 的 RemoteUtil 29670、RequestQueue 29697/29701、TCP 握手 31405；登录 helper ABC 286 方法 37。测试包另改服务器地址 92013 和独立偏好存储 91935。原有类/traits/方法签名保持，仅登录请求包装增加两个临时局部寄存器。

```powershell
node tests/client-admission.test.cjs
node tests/client-admission-tcp.test.cjs
node tests/client-admission-lifecycle.test.cjs
node tests/player-login-integration.test.js
```

本地模拟器专用启动器 `start-local-test.ps1` 使用隔离端口和 `DATA_DIR`，从忽略的 `outputs/android-build-local.json` 读取本机地址。`local-qa.cjs` 只操作该隔离测试配置。该测试包不能用于连接现有公网服务。

不涉及数据库表、角色/道具 ID、账号归属或 V1/V2 存档结构变化。TCP 测试使用真实 socket、桩游戏处理器，只证明接入边界，不代表已完成双人共斗战斗测试。具体模拟器结果与构建摘要见 `TEST-20260915.md`。
