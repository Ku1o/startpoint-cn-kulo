"""Render pool prose with the native rich-text paragraph layout contract."""
import html


def render_notice(title: str, paragraphs: list[str]) -> str:
    if not paragraphs or any(not text.strip() for text in paragraphs):
        raise ValueError('A gacha notice requires nonempty paragraphs')
    body = '<br/>\n'.join('    <p>' + html.escape(text) + '</p>' for text in paragraphs)
    # Bare body text inherits the container's line-height, not the P style.
    # Preserve the original game template so wrapping uses paragraph metrics.
    return ('<!DOCTYPE html/>\n<html lang="zh-CN">\n<head>\n'
            '  <meta charset="utf-8"/>\n  <title>' + html.escape(title) + '</title>\n'
            '  <link rel="stylesheet" type="text/css" href="style.css"/>\n'
            '</head>\n<body class="body" style_id="1">\n'
            '  <div class="container">\n' + body + '\n  </div>\n</body>\n</html>\n')
