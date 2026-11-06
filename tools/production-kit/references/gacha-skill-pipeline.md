# 完整扭蛋池的离线技能管线

通过 `gacha_pipeline.py init --with-skills` 配置，`build` 录制或核验复用，生成完整UI审图后停在needs_visual_review；实际审查后 `review-skills`，再 `resume` 编码、组装完整HTML、检查浏览器并录制整轮。只写离线任务目录和独立AIR缓存，不操作游戏服务器或数据库。资源保护、环境与恢复沿[主管线](gacha-production-pipeline.md)。

## 配置与来源

```json
{
  "featureOrder": [
    {"kind": 0, "page": "cover"},
    {"kind": 2, "roleId": 12345, "skillKey": "declared-preview-key", "page": "skill-a"},
    {"kind": 0, "page": "poster-a"}
  ],
  "skillPreview": {
    "schemaVersion": 1,
    "roles": [{"roleId": 12345, "native": {"file": "native/12345.json", "sha256": "<actual digest>"}}],
    "limits": {"maxHtmlCharacters": 4500000, "width": 360, "fps": 60},
    "keyframes": {"12345": [12, 80, 150]},
    "notes": ["离线场景说明"]
  }
}
```

以上为字段示例，ID、摘要和场景必须换为真实来源。页面顺序由feature表决定；已核常见官方样本为封面→角色技能→人物页，不凭印象反转。characters.posterPage关联海报，不能把非数字页键当角色ID。keyframes用录制tick，审查reviewedFrames用实际战斗帧号，两者不混用。skillKey和离线poolId不表示正式业务注册。

原生角色配置见[录制适配器](../scripts/gacha_capture/README.md)。素材闭包固定客户端、角色、技能DSL、地形、回放和工具身份。旧录制可声明 `reuseRun:{build:{file,sha256},result:{file,sha256}}`，两者须同一运行目录；重新核对实际场景、配置、帧序和原生回执。仅有MP4或旧“通过”文字不足以复用。

## 场地、敌人与时长

先读技能DSL、原生日志和官方Gacha场地，逐角色写明机制、目标、站位、施放时机、关键反馈、回弹路径、机位与UI可见范围。详情页场地只作来源/执行对照，不能直接当卡池场地；旧角色的敌人数量、位置和窗口不是通用参数。

| 技能机制 | 场景选择与观察 |
| --- | --- |
| 近身、突进、追踪 | 使用实际可选中的现有敌人，让自然运动进入有效距离，展示位移/接触与后续回弹 |
| 远程、直线弹道 | 按真实方向和距离布置目标，保留出手、飞行和命中间隔，避免主要弹道进入顶部/底部UI |
| 范围、多目标、持续区域 | 现有敌人分布体现真实范围及反馈，不伪造碰撞或扩展伤害范围 |
| 辅助、召唤、场地装置 | 展示实际状态、对象和作用条件，没有直接伤害时不虚构命中数字 |

敌人、石块、角色版本和目标关系记录实际ID/来源；候选场景只改声明字段，可反向还原官方输入，保留未知回放命令和战斗引擎。球由原生回放运动，技能由原生施放；改场地、球位或窗口后重新执行受影响角色，不能在视频里移动弹珠或贴命中特效。

演示时长按角色决定，覆盖起手、主效果、反馈和必要收尾。过长时从原生日志找结束点及原生淡出，改变候选窗口并证明此前有效动作保全；不统一给所有角色几秒、不加速或只剪MP4。原生默认静音且无全屏技能立绘切入，减负模式跳页行为另核。

## 背景缺口与完整UI

顶部/侧边空带先对照同帧原生PNG、完整UI合成和最终HTML，区分源背景覆盖、视口/裁切、播放器留白与编码问题。源背景覆盖不足应修对应原生背景的变换/覆盖与引用，按资源坐标和定点比例计算；保全前景动作、地形碰撞、球/目标状态、机位、裁切及窗口。个案偏移不作全场地默认，不能用HTML补色或视频遮罩掩盖原生缺口。

复核受影响边界连续帧并对比整段轨迹、目标/命中记录和时序。球心安全仅为预警，必须看身体、武器、核心特效、反馈、回弹和收尾，覆盖顶栏、左右按钮、箭头、像素头像与底栏。只抬底部石台可能把人物弹入顶部或侧边；每次修改追踪后续运动，不只看修改处。

背景为Movie族时，交付Movie、timeline、atlas和图像四件套，闭合内部图片路径；同时交付必要replay/terrain及五表连接片段。独立命名的资源结构通过仍不等于在目标客户端实际执行，不能只交修好的录像而遗漏源资源。

## 审查记录与完整产物

每个角色独立填写：

```json
{
  "schemaVersion": 1,
  "reviewManifest": {"file": "<build>/skills/REVIEW-REQUIRED.json", "sha256": "<actual digest>", "bytes": 123},
  "roles": [{
    "roleId": 12345, "decision": "accept",
    "audit": {"file": "<actual UI-AUDIT.json>", "sha256": "<actual digest>", "bytes": 123},
    "coverage": ["setup", "main-action", "feedback", "rebound-and-tail"],
    "reviewedFrames": [101, 171, 300],
    "observations": "实际看到的关键动作和仍有的外围重叠"
  }]
}
```

复制本轮manifest绑定，帧号必须存在且有对应带摘要的同帧对照图。过期audit、虚构帧、变化的图片/原生资源被拒绝。几何零告警不代替视觉决定，review-skills不等于用户采用；[美术审查](gacha-production-pipeline.md#预览与美术审查)另做。

BUILD绑定原生回执、PNG有序摘要、UI审图、编码片段、HTML、浏览器回执及整轮录像。编码保持原帧率、完整窗口和逻辑视口；低码率会软化光效，需看最终片段。HTML字符预算来自具体应用版本，需要按实际渲染入口核实。制作者视觉检查、离线原生执行、用户采用、目标客户端接入和手机验收分别记录。
