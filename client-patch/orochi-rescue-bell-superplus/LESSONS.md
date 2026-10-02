# 客户端资源修复经验

## 先确认文字的真正来源

救援铃铛窄小红色难度条不是 SWF 文本字段。SWF 只选择并播放 `hud_attention_label` 的时间轴帧；字形和坐标来自 Flatomo PartsAnimation：

`battle/common/attention/hud_attention_label.parts.amf3.deflate`

时间轴第 6 帧对应 `chokyu_plus`，使用图集里的“超”“级”“+”图形。只改 SWF 或难度数据不会补出这个窄标签的字形。

## APK 内置 bundle 与 CDN 是两条载体

同一逻辑资源可以同时出现在 APK 的 `assets/bundle.zip` 和 CDN 增量中，但它们不是同一条运行时读取路径。使用内置 bundle 的 APK 可以在不读取 CDN 增量的情况下显示文字；CDN 增量只有在客户端实际请求并合并 active 资源链时才会生效。

因此，看到 CDN 资源内容正确，不能证明当前 APK 已经读取了它。排查时要记录实际读取路径和字节哈希，不能只比较两份资源是否相同。

## 修改 APK 内置资源必须同步缓存标记

修改 `assets/bundle.zip` 后必须更新同级的 `assets/bundle.zip.sha1`。AIR 启动缓存会用这个标记判断 bundle 是否已经提取；标记仍是旧值时，客户端会继续复用旧的本地资源，即使 APK 里已经放入了新的 payload。

这次排查中，旧资源为 466 字节空白 payload；排版修复后的 payload 为 480 字节，bundle 标记改为实际 bundle 的 SHA-1 后才触发重新提取。这个问题属于缓存失效，不属于资源下载失败。

## 排版优先复用已有布局

“超级+”采用现有三字难度标签的间距和矩阵，只替换字形：`超` 使用 matrix10，`级` 使用 matrix9，`+` 使用 matrix11。这样能保持标签中心和字间距一致，避免沿用两字“超级”的坐标后让加号压住“级”。

## 公网与内网共用修改提交

资源修改方法、Flatomo 结构和 bundle 缓存规则属于同一份客户端实现。公网与内网的差异在封包参数：SWF 服务端地址、准入配对、AIR `uniqueappversionid` 和签名配置。仅因目标地址不同，不要复制一份公网排版提交；等真正需要发布公网 APK 时，复用同一方法重新封包即可。

## 最小验收顺序

1. 读取并回写 AMF3，确认时间轴第 6 帧和三段字形结构可 round-trip。
2. 回读 APK 内层目标资源，检查 payload SHA-256。
3. 回读 `assets/bundle.zip.sha1`，确认等于实际 bundle SHA-1。
4. 检查 SWF 地址转换、AIR UUID、准入配对、zipalign 和 V1/V2 签名。
5. 先做离线渲染，再做内网实机验收；公网 APK、IPA、CDN 增量和云服交付按实际需求单独授权。
