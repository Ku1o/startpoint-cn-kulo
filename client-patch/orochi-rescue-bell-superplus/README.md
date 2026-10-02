# 救援铃铛“超级+”内置标签排版

救援铃铛窄难度条由 `battle/common/attention/hud_attention_label.parts.amf3.deflate` 的 Flatomo PartsAnimation 提供。第 6 帧使用已有图集中的“超”“级”“+”字形；本方法把三字排列到一个紧凑、居中的三字布局中，并更新 APK 内置 `assets/bundle.zip.sha1`，让 AIR 重新提取修改后的 bundle。

## 生成内置资源

`build_embedded_layout.py` 接受一个 APK 和一份 `hud_attention_label.parts.amf3.deflate` 输入，输出未签名的 APK。输入资源可以是 466 字节的官方基础 payload，也可以是已经补齐第 6 帧的 477 字节候选 payload：

```powershell
python client-patch/orochi-rescue-bell-superplus/build_embedded_layout.py `
  --input-apk <source.apk> `
  --payload <hud_attention_label.parts.amf3.deflate> `
  --output-apk <unsigned-output.apk>
```

脚本只改内层资源和外层 bundle 标记，保留其他 APK 成员；它不修改 SWF、网络地址、准入配置、CDN manifest 或签名。输出仍须经过现有 Android 打包器的地址转换、`uniqueappversionid` 更新、`zipalign` 和 `apksigner` 流程。

## 公网与内网

排版资源属于同一个客户端修改，公网 APK 与内网 APK 共用这套方法和同一个 `client` 提交。两者的差异在封包阶段：SWF 内的服务端地址、准入配对和对应的签名/发布配置按目标环境取值。当前只制作并验收内网 APK；公网 APK 和 iOS IPA 暂不生成，也不作为本提交的成品。

## 校验

脚本会回读 AMF3 结构，确认第 6 帧根节点段和“超/级/+”三段存在，验证内层目标资源 SHA-256，以及 `assets/bundle.zip.sha1` 与实际 bundle 的 SHA-1 一致。APK、SWF、签名材料和临时 bundle 不提交 Git。

排查顺序、缓存失效原因、APK 与 CDN 的载体区别，以及公网/内网共用方法的经验记录见 [LESSONS.md](./LESSONS.md)。

## 后续客户端组合

排版修复之后的客户端步骤不能漏掉累计功能：先按 [C8016-PRELOAD.md](./C8016-PRELOAD.md) 替换现有 SWF helper，再按 [`startup-cache/PERIODIC-10M.md`](../startup-cache/PERIODIC-10M.md) 叠加十分钟 AIR 缓存清理。组合顺序是“紧凑排版 → C8016 v3 helper → 10 分钟缓存”，每一步都生成新的 AIR `uniqueappversionid`；公网地址转换只在确有发布需求时复用同一方法。
