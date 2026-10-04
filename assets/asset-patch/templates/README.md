# 资源候选包模板

协作者交付客户端资源改动时，只出**候选包**：ZIP 放 `assets/asset-patch/active/candidates/`，不进入正式版本链，正式版本号由所有者分配。

## 交付物

1. 候选 ZIP：`assets/asset-patch/active/candidates/<文件名>.zip`。成员路径沿用 `production/upload/<2位>/<hash>` 布局。
2. 审计目录：`assets/asset-patch/audit/<id>/`，至少包含按 [candidate-manifest-entry.template.json](./candidate-manifest-entry.template.json) 填写的 `manifest-entry.json`，以及制作时生成的 `report.json`。
3. PR 正文：把下面的清单贴进 PR 模板的「改动说明」与「验证」。

不修改 `assets/asset-patch/manifest.json` 的正式条目、不推进 `cdn_version`、不在 `.cdn/` 内放任何文件；这些由所有者在采纳时处理。

## 生成哈希

```bash
python -B assets/asset-patch/templates/candidate_report.py assets/asset-patch/active/candidates/<文件名>.zip
```

输出的 JSON 直接填入 `archive_integrity`（ZIP 大小、SHA-256、成员列表和逐成员 SHA-256）。脚本只读，拒绝不在 `candidates/` 下、含不安全路径或重名成员的 ZIP。

## PR 必附清单

- [ ] 基线：制作时的 `origin/staging` 提交与 `manifest.json` 的 `cdn_version`，依赖的上一个 ZIP
- [ ] ZIP 与成员哈希（`candidate_report.py` 输出）
- [ ] 内容清单：每个成员对应的客户端逻辑路径和类型
- [ ] 改了哪些表和资源，涉及哪些 ID 及引用关系
- [ ] 服务端影响（需要的服务端表或代码改动，及对应 PR）
- [ ] 客户端影响（是否需要 SWF/APK 改动）
- [ ] 存档影响（新增 ID、迁移、回退后残留数据）
- [ ] 测试范围：只写实际运行过的检查与结果
- [ ] 已知限制
- [ ] 回退方式

## 约定

- `candidate_only: true`、`enabled: false`；`version` 留给所有者填写。
- 不复用旧资源链（1.4.217 → 1.4.427）的版本号或 ZIP。
- 基于当前主线重做，不直接搬运旧链产物。
