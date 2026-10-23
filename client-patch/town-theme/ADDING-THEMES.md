# 追加主城主题

主题列表来自服务端已核验目录，后台页面和支持本协议的客户端不写死五套主题。新增主题仍须符合原生 `town_content` 的 20 列结构及现有背景、mask、粒子和音乐读取方式；增加新渲染行为或改变原生字段含义，需要另做客户端修改与验证。未安装主城主题协议补丁的旧客户端不能使用后台手动选择。

## 发布顺序

1. 为新主题分配稳定目录 key 与不冲突的原生主表 ID。通过正常 CDN 增量发布主表和全部依赖资源，保留原有行与资源。不要为了让主题全年可选改写全表日期、节日标记、服务器时钟或活动开关。
2. 在隔离的目标 checkout 准备完整元数据 spec；保留已有主题，仅增加新项。中文名称和说明由元数据提供，页面无需修改。新主题的资源需要先在实际客户端验证原生兼容性。
3. 用只读资源 checkout 的有效 manifest 和稀疏解析器运行下述工具。先 dry-run，确认资源版本、manifest、主表行和图片无误，再加 `--write`。目标 checkout 与只读资源 checkout 必须分开。
4. 将核验得到的 `assets/town_themes.json`、`assets/town_theme_resource_receipt.json` 和引用的 WebP 作为同批服务端文件部署，在启动或明确资源登记时重新加载目录。manifest 与 receipt 必须来自同一快照；即使本次 CDN 改动不涉及主城，manifest 变化后也须重新生成核验目录。
5. 后台重新读取目录，核对缩略图和中文名，再手动选择并二次确认。玩家下次正常登录后切换外观与默认音乐，本地自选音乐保留。当前在线场景不热切换，也不自动发起全服重登。

## 元数据与命令

`themes` 是完整目录。不得将已启用的旧主题遗漏；工具会拒绝删除已有 key。下面的 ID、名称和版本只是格式示例，必须替换为有效链中真实存在且已验证的行和版本。

```json
{
  "schemaVersion": 1,
  "resourceVersion": "1.4.999",
  "themes": [
    {
      "id": "sample_theme",
      "name": "示例主题",
      "description": "这里填写实际外观说明。",
      "nativeTownContentId": 123
    }
  ]
}
```

工具复用可信原生导出器，要求导出器提供 `resolve(root, logicals)`、`parse_rows(raw, logical)`、`member(logical)`，涉及粒子时还需 `core.AMF3Reader`。`resolve` 必须沿实际启用 CDN 链稀疏解析获胜成员，返回原始字节与 archive/sha256 身份，以及 `assetVersion`、`manifestSha256`、有序 `actualChain`（archive/size/mtimeNs）。解析器是明确指定、可执行的本地 Python 依赖；登记工具不下载或安装它，也不使用任意缓存 JSON 冒充原生主表。

```powershell
python -B tools/build-town-theme-catalog.py `
  --repo <隔离目标checkout> `
  --resource-root <只读资源checkout> `
  --exporter <可信稀疏原生导出器.py> `
  --spec <完整主题元数据.json>
```

缺少 `--write` 时只在内存完成验证与 WebP 编码，输出 JSON 摘要，不生成目录、receipt、缩略图或中间文件。确认结果后，以相同参数追加 `--write` 执行登记。`--repo` 不能等于或位于 `--resource-root` 内，任何写入目标经真实路径解析后也不能进入只读资源根或 `.cdn`。只读资源根必须传实际源码资源 checkout，不能用另一个路径别名规避保护；本地项目实际入口由工作区规则确定。

工具先解析 `master/town/town_content.orderedmap`，依据选中行读取：

- 第 6、7 列背景和模糊背景 `.png`；第 8 列非 `(None)` 时读取 mask `.png`。
- 第 9 列非 `(None)` 时读取粒子的 `.parts.amf3.deflate` 与 `.timeline.amf3.deflate`，以及同级目录的 `sprite_sheet.png` 和 `sprite_sheet.atlas.amf3.deflate`。这与原生 `TownAssetPathCollectionBuilder` 把粒子文件名替换成 `sprite_sheet` 的规则一致；例如 `town/particle/snowfall` 使用 `town/particle/sprite_sheet`。
- 第 19 列默认音乐 `.mp3`。

所有列号均从 0 开始。工具逐个回读实际 ZIP 成员，核对 SHA、大小、native logical hash 路径、获胜链身份，完整解码 PNG。粒子使用有界 raw DEFLATE（兼容 zlib 包装）与 AMF3 解码，校验 atlas 名称唯一、矩形位于 spritesheet 内，parts 的原生 `i[].p` 图片引用必须落入 atlas；嵌套 parts、声音或其他未知引用不得隐式放行。音乐仅检查头部，实际播放另验。主表行的 SHA 采用与 JavaScript `JSON.stringify(row)` 一致的 UTF-8 紧凑数组编码。receipt 固定为 `town_theme_resource_receipt.json`；每项记录完整 logical path（包括后缀）、原始字节 SHA、大小及成员来源；catalog 与 receipt 都绑定资源版本，catalog 另绑定 receipt 原始字节 SHA。

工具还从这次获胜的完整主表生成每个主题的 `originalPeriods`，供后台显示原版档期。第 6 至 19 列全部资源和行为字段逐项完全相同的行归为同一主题别名，第 0 至 5 列身份和日期不参与分组；保留全部别名，不仅保留 spec 选中的原生 ID。每项严格包含 `nativeTownContentId`、`kind`、`start`、`end`，按原生 ID 数字升序稳定输出：

- `kind=1` 生成 `kind: "event"`，保留第 2/3 列完整 `YYYY-MM-DD HH:mm:ss`，按原生 UTC+8 解释；要求有效日历日期且开始不晚于结束。不会去掉年份变为年度规则。
- `kind=2` 生成 `kind: "annual"`，保留第 4/5 列完整 `MM-DD HH:mm:ss`，按原生 UTC+8 解释。允许跨年区间；拒绝 02-29、无效日期、无效时间或格式不完整的数据。
- `kind=0` 不生成档期；没有档期的主题输出空数组。属于同一主题的无效日期或不支持的 kind 会使登记失败，不会跳过后包装为正常档期。

receipt 的每个主题新增 `originalPeriodsSha256`，计算方式为 `SHA256(UTF8(JSON.stringify(originalPeriods)))`，与 catalog 的同一完整数组绑定；主表来源继续由 receipt 的 master 获胜成员身份绑定。原版档期是原始资源证据，与运营人员另设的每年日期分别维护；登记不会调整资源日期或运行中的主题选择。升级工具后需使用同一快照重新登记成组文件，新 loader 应兼容没有该字段的旧目录与 receipt。登记工具不读取或改写运营年度设置。

确有原生支持、并已单独验证的外部引用时，可在相应 spec 主题追加可选的 `extraDependencies`。每项含 `reference`（AMF 中的准确引用值）、`evidence`（具体原生消费路径及验证记录说明）和 `resources`（非空数组，每项严格包含 `path`、`sha256`、`size`）。资源使用完整 logical path，哈希和字节数须对应实际启用链，工具将重新稀疏读取并核对，而不是信任声明。引用缺少声明、身份不匹配或 AMF 格式不支持时直接失败；声明随 receipt 保留，不加入 catalog 页面字段。声明资源不等于证明一种新粒子机制可运行；新机制须先核查客户端语义再扩展核验器。

缩略图由主背景原始 PNG 生成，保持比例且最大 420×540，WebP quality=90、method=6，以最终字节 SHA 命名并回读验证。游戏特有的小写 PNG magic 仅在内存解码副本中规范化，资源哈希仍对应原始字节。工具不预加载音频，不导出整套 CDN，也不修改数据库、HTTP 运营设置、CDN 或 SWF。

## 验证与回退

离线字节、atlas 图片引用闭合与图片核验不等于游戏内验收。粒子的动画和行为语义、声明的外部依赖消费方式、遮罩表现、透明边缘、音乐实际可播放与音量、主城交互和不同平台纹理仍需按目标客户端验证；不能仅凭 AMF 解析、deflate 或 MP3 头通过宣称可用。若原生行使用新字段语义或新的间接依赖，先扩展核验方法并验证资源闭合，再登记。

部署前保留原目录、receipt 和 WebP；发布采用同批替换，新 catalog 最后生效。文件逐个原子替换不能保证跨文件事务，发布中断时应恢复整组已知版本，再重新启动或加载。目录、receipt、图片或 manifest 身份不匹配会降级自动规则；不要通过移除校验、手改 receipt 的哈希或伪造已核验状态绕过失败。

回退时先在后台选择自动跟随日期并确认读回，再按正式资源回退流程恢复已验证的目录/receipt/图片与配套 manifest。保留旧资源与原生 ID，避免已下载客户端引用缺失。新增原生兼容主题通常只需 CDN 主表/资源及目录更新，无需重新制作 SWF 或修改后台页面；这不自动授权资源发布、客户端打包或云端部署。
