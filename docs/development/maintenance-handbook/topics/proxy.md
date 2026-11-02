# SP-PROXY-001 · Windows portproxy、代理信任与登录限流

适用：StarPoint CN Windows HTTP 入口、iOS 80 入口、来源地址/限流、登录兼容或 CDN 归属。状态：历史配置和限定 hook 回归已验证；实际云端代理链路须按目标机器核对。

## 入口和来源地址

历史方案采用 netsh portproxy 的 80→回环 8001 转发，iOS HTTP 与独立 HTTPS CDN 分流；它不是有效 Nginx 配置的证明。当前入口以云服代理说明（历史本地记录）和实际机器为准，不自动换代理、端口、客户端 origin 或 CDN_BASE_URL。

代理信任默认 false。L4 回环转发的伪造 XFF 不能改变限流桶；真正 L7 代理须显式信任精确来源地址，并覆盖转发头。portproxy 丢失的真实源 IP 不能由身份限流代码恢复，iOS 仍可能共享 IP 桶。验证覆盖直连/L4 伪造头、显式可信 loopback L7 的多客户端、query/编码路径及 debug 排除，不将 per-identity 宣称为真实客户端 IP。

CDN_BASE_URL 决定下载 URL，Node 仍可能生成清单和读取本地 ZIP 元数据；Cloudflare 域名不证明 R2 存储。流式传输只影响经过 Node 的请求，下载清单排序对 Cloudflare 链仍有效。

## 登录、身份与兼容数据

账号密码为主入口；旧引继路由和旧存档绑定凭据仍有兼容用途，已绑定账号禁止旧 take_over。不因主入口不用旧引继而删除旧存档数据。

同时保留身份密码类、有效会话账号和共享来源总额限制；无效会话不能获得有效身份桶。成功和失败均计数，总来源预算限制身份轮换；session 必须查当前数据库后才用 account_id，不能按 token 自带字段切桶。具体额度属于配置和实现快照，见历史整合记录（历史本地记录），变更时核对当前实现。

身份规范化与认证消费者一致：code/readCode 去空白、连字符后转大写再摘要；local-claim-preview 按 viewer，忽略的 code 字段不能改变分支。用跨 IP code 变体及附随机 code 的 local claim 验证绕过，而非只测正常请求。

全部旧参数、当时源码/本地加载状态及实测范围保留在原条目历史（历史本地记录）。历史本机连通或源码加固不等于当前云端链路验收。
