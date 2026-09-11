# 透明成品处理记录

已选构图由内置 image_gen 生成，提示词见 `approved-preview-prompt.md`。本任务再次请求内置工具提供 alpha，但输出为 RGB，含可见棋盘格，因此弃用该结果，未放入正式图或增量包。

弃用文件：`<USER_HOME>/.codex/generated_images/01a08662-dc5d-7360-bf14-fd3e253f838d/exec-c928f889-bb48-4dd1-8da2-9d58b6dd3fc8.png`。

用户随后明确回复：**允许本地脚本处理，保留已选构图（推荐）**。最终输入重新选择用户批准的白底宽版（SHA-256 `91af3cc31e0cccdcfc50d3c11f660f5c1700c0aeaf1c2d1520da4beba63bbf29`），未采用弃用图片。

正式方法：移除中性白底与轮廓白色混色，保留红金像素及原有四字和装饰布局；围绕主体裁去空白，预乘 alpha 等比缩至 314×45（整数像素取整），居中置于透明 320×50。并列检查深灰、浅白、蓝灰、粉色背景；未绘制新文字，未重画构图。没有使用 OpenAI API/CLI 回退。

## 内置工具此次尝试的完整提示词

Use case: background-extraction.
Edit target: the supplied approved wide red-and-gold Chinese game title badge, not the older small badge.
Primary request: deliver the same selected wide badge as a clean, truly transparent PNG asset for a 320 x 50 pixel game title. Keep the entire existing silhouette and relative proportions unchanged: compact left red Chinese knot with gold coin and short tassels, two golden clouds, long red silk ribbon with gold edges and twin right tips.
Text (verbatim): 特别鸣谢. Preserve these exact four bold, well-formed Chinese glyphs and their layout; do not add other text.
Change only the white background into real alpha transparency. Preserve the interior gold/cream highlights and letter faces; no white fringe around the outer contour, no fake checkerboard pixels, no ground shadow. No cropping of any ornament or tip, no horizontal stretching.
Output a tightly framed 320 x 50 RGBA PNG if supported. Visible badge width 314-316 pixels, proportional height about 45 pixels, centered with transparent margins. A larger transparent image with the same badge geometry is acceptable if fixed native pixel dimensions cannot be provided. Preserve actual alpha in the file.
