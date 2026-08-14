# 漫画系统(Comic)
> 状态: 已实现   关键文件: web/public/comic/, src/.../comic.ts

本文档描述漫画系统的实现:图片目录格式、源文件、处理流程及已知问题。

## Comic system

Comics stored as processed images under `web/public/comic/{kind}/`:

| Directory | Format | Size | Use |
|-----------|--------|------|-----|
| `main/` | PNG | ≤2048px high (GPU limit) | Detail page |
| `thumbnail_l/` | JPEG | 984×623 | Header banner |
| `thumbnail_s/` | JPEG | 298×256 | 3×3 grid tiles |

**Source**: `docs/漫画/【弹射小世界】漫画/` (409 files) + `docs/漫画/【史黛拉的弹射世界讲座】/` (13 files).

**Processing**: Pillow script — resize to target width → top-crop `(0,0,w,h)` → RGBA→RGB for JPEG. `comic.ts` parses filenames by regex (`/第(\d+)[话课]/`) to extract episode number and title. Titles must NOT include episode prefix (client displays it separately).

**Known issues**: F3766 if main exceeds 2048px (GPU texture limit), C2035 if `getLatestComicData()` can't find `episode=totalCount` on first page (must sort descending).
