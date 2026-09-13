# 校奈芙多球直击增益脚本：合并核对说明

已对照发送方最终完整 ZIP，确认这是供体脚本的一处参数类型错误。接收方提出改为 `DoNothing` 的方向正确。

## 精确修正

逻辑文件：

```text
battle/action/skill/action/ability_skill/ruin_girl_campus$ruin_girl_campus_multiball_direct.action.dsl.amf3.deflate
```

`FindAllSubjects` 命令第 8 个参数（命令数组下标 8）为 `IfTargetNotFound` 枚举，应从 `['Block', []]` 改成 `['DoNothing']`。

```diff
- ["FindAllSubjects", 72, 82, [], [], [], [], [], ["Block", []], ...]
+ ["FindAllSubjects", 72, 82, [], [], [], [], [], ["DoNothing"], ...]
```

相邻 `FindMultiballSubjects` 的第 5 个参数是动作表达式，其 `['Block', []]` 合法且应保留。不要全局替换空动作块。A4 的同类协力球选取动作也无需套用这项修改。

这是参数类型修正，不是平衡改动。保留原有球数统计、每球独立乘区、倍率、目标筛选、主位及共鸣限制、状态持续帧与覆盖逻辑。

只需重编码该资源文件并按接收方流程更新资源摘要、纳入新的 CDN 增量，无需修改 APK。修复后在接收方客户端验证进入战斗、召唤球及球消失时的增益表现。

## 发送方复核证据

- 最终 ZIP 内 `assets/full68-005.zip` 含原问题文件，SHA256：`04d452d5af27ab06f5fce3a034d308a9e32d87d0166364a8f94f6e822dd7f5d8`。
- 8 个校奈芙技能／能力／强化弹射程序的 `IfTargetNotFound` 槽位专项检查，仅发现这 1 处错误。
- 内存候选仅改变该参数；还原后整棵动作树与供体相等，AMF 编解码往返通过。细节见 `package-review.json`。
- 本轮完成核查及说明，尚未修改发送方源码、发布资源或已封存分享包；未代替接收方运行实测。
