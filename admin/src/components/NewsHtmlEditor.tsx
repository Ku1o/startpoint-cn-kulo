import { useEffect, useRef, useState } from "react"
import { Button, Input, InputNumber, Modal, Space, Tooltip } from "antd"
import {
    BoldOutlined,
    CodeOutlined,
    FontSizeOutlined,
    PictureOutlined,
    ScissorOutlined,
    UnorderedListOutlined,
} from "@ant-design/icons"

interface NewsHtmlEditorProps {
    value?: string
    onChange?: (value: string) => void
}

interface ImageFormState {
    url: string
    alt: string
    width: string
    height: number
}

const DEFAULT_IMAGE: ImageFormState = {
    url: "https://",
    alt: "",
    width: "100%",
    height: 360,
}

function escapeAttribute(value: string): string {
    return value
        .replace(/&/g, "&amp;")
        .replace(/\"/g, "&quot;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
}

function bodyHtml(value: string): string {
    const trimmed = value.trim()
    if (!trimmed) return ""
    if (!/<!doctype|<html[\s>]/i.test(trimmed)) return trimmed
    const document = new DOMParser().parseFromString(trimmed, "text/html")
    return document.body.innerHTML
}

/**
 * The game parses announcement content as XML, although the editor works on
 * an HTML DOM. HTML serialization omits the closing slash on void elements,
 * so restore XML self-closing syntax before sending the value to the server.
 */
function xmlSafeFragment(value: string): string {
    return value.replace(/<(img|br|hr)\b([^>]*)>/gi, (_full, tag: string, attributes: string) => {
        const trimmed = attributes.trimEnd()
        return trimmed.endsWith("/")
            ? `<${tag}${attributes}>`
            : `<${tag}${attributes} />`
    })
}

/**
 * The game parser reads a complete XML-shaped HTML document. Keep the editor
 * pleasant to use by letting the visual canvas work with body fragments, then
 * wrapping every non-empty change before it leaves the component.
 */
function toNewsDocument(body: string): string {
    const trimmed = body.trim()
    if (!trimmed) return ""
    if (/<!doctype|<html[\s>]/i.test(trimmed)) return trimmed
    if (/^<body[\s>]/i.test(trimmed)) return `<html lang="zh">${trimmed}</html>`
    return `<html lang="zh"><body>${trimmed}</body></html>`
}

function editorHtml(editor: HTMLElement): string {
    const text = (editor.textContent ?? "").replace(/\u00a0/g, " ").trim()
    const meaningfulElement = editor.querySelector("img, hr, table, ul, ol")
    if (!text && !meaningfulElement) return ""
    return toNewsDocument(xmlSafeFragment(editor.innerHTML))
}

/**
 * Visual editor for the limited HTML understood by the CN client. The source
 * view is kept as an advanced escape hatch, but is hidden during normal use.
 */
export function NewsHtmlEditor({ value = "", onChange }: NewsHtmlEditorProps) {
    const editorRef = useRef<HTMLDivElement | null>(null)
    const selectionRef = useRef<Range | null>(null)
    const [sourceMode, setSourceMode] = useState(false)
    const [imageOpen, setImageOpen] = useState(false)
    const [imageForm, setImageForm] = useState<ImageFormState>({ ...DEFAULT_IMAGE })

    const update = (next: string) => {
        onChange?.(next)
    }

    useEffect(() => {
        const next = bodyHtml(value)
        if (sourceMode || !editorRef.current) return
        if (editorRef.current.innerHTML !== next) editorRef.current.innerHTML = next
    }, [sourceMode, value])

    const rememberSelection = () => {
        const editor = editorRef.current
        const selection = window.getSelection()
        if (!editor || !selection || selection.rangeCount === 0) return
        const range = selection.getRangeAt(0)
        if (editor.contains(range.commonAncestorContainer)) selectionRef.current = range.cloneRange()
    }

    const restoreSelection = () => {
        const editor = editorRef.current
        if (!editor) return
        editor.focus()
        const selection = window.getSelection()
        if (!selection) return
        selection.removeAllRanges()
        if (selectionRef.current) selection.addRange(selectionRef.current)
    }

    const runCommand = (command: string, argument?: string) => {
        restoreSelection()
        document.execCommand(command, false, argument)
        const editor = editorRef.current
        if (editor) update(editorHtml(editor))
        rememberSelection()
    }

    const openImageDialog = () => {
        rememberSelection()
        setImageForm({ ...DEFAULT_IMAGE })
        setImageOpen(true)
    }

    const insertImage = () => {
        const url = imageForm.url.trim()
        if (!/^https:\/\/[^\s"<>]+$/i.test(url)) return
        const width = imageForm.width.trim() || "100%"
        const height = Number.isFinite(imageForm.height) && imageForm.height > 0
            ? Math.round(imageForm.height)
            : DEFAULT_IMAGE.height
        const alt = escapeAttribute(imageForm.alt.trim())
        restoreSelection()
        document.execCommand(
            "insertHTML",
            false,
            `<div class="center"><img src="${escapeAttribute(url)}" width="${escapeAttribute(width)}" height="${height}"${alt ? ` alt="${alt}"` : ""} /></div>`,
        )
        const editor = editorRef.current
        if (editor) update(editorHtml(editor))
        setImageOpen(false)
    }

    const toggleSourceMode = () => {
        if (!sourceMode) rememberSelection()
        setSourceMode(current => !current)
    }

    return (
        <div className="news-rich-editor">
            <Space wrap size={[6, 6]} className="news-rich-editor-toolbar">
                <Tooltip title="正文段落">
                    <Button size="small" onMouseDown={event => event.preventDefault()} onClick={() => runCommand("formatBlock", "p")}>
                        正文
                    </Button>
                </Tooltip>
                <Tooltip title="游戏内黑橙横条标题，输出 h1">
                    <Button size="small" icon={<FontSizeOutlined />} onMouseDown={event => event.preventDefault()} onClick={() => runCommand("formatBlock", "h1")}>
                        一级标题
                    </Button>
                </Tooltip>
                <Tooltip title="加粗选中文字">
                    <Button size="small" icon={<BoldOutlined />} onMouseDown={event => event.preventDefault()} onClick={() => runCommand("bold")}>
                        加粗
                    </Button>
                </Tooltip>
                <Tooltip title="项目符号列表">
                    <Button size="small" icon={<UnorderedListOutlined />} onMouseDown={event => event.preventDefault()} onClick={() => runCommand("insertUnorderedList")}>
                        列表
                    </Button>
                </Tooltip>
                <Tooltip title="插入分隔线">
                    <Button size="small" icon={<ScissorOutlined />} onMouseDown={event => event.preventDefault()} onClick={() => runCommand("insertHorizontalRule")}>
                        分隔线
                    </Button>
                </Tooltip>
                <Button size="small" icon={<PictureOutlined />} onMouseDown={event => event.preventDefault()} onClick={openImageDialog}>
                    插入图片
                </Button>
                <Tooltip title="需要精细调整 HTML 时再打开">
                    <Button size="small" icon={<CodeOutlined />} onMouseDown={event => event.preventDefault()} onClick={toggleSourceMode}>
                        {sourceMode ? "返回可视编辑" : "高级编辑"}
                    </Button>
                </Tooltip>
            </Space>

            {sourceMode ? (
                <Input.TextArea
                    value={value}
                    rows={14}
                    className="news-html-editor news-rich-editor-source"
                    onChange={event => update(event.target.value)}
                />
            ) : (
                <div
                    ref={editorRef}
                    className="news-rich-editor-canvas"
                    contentEditable
                    suppressContentEditableWarning
                    data-placeholder="在这里输入公告正文；主标题填写在上方，需要游戏内横条时再使用“一级标题”"
                    onInput={event => update(editorHtml(event.currentTarget))}
                    onMouseUp={rememberSelection}
                    onKeyUp={rememberSelection}
                    onBlur={rememberSelection}
                />
            )}
            <div className="news-rich-editor-help">
                上方标题是公告主标题；正文里的“一级标题”会在游戏内显示为黑橙横条。保存时会自动补齐客户端需要的 html/body 外壳；图片地址填写 Cloudflare 等图床提供的 HTTPS 地址。
            </div>
            <Modal
                open={imageOpen}
                title="插入公告图片"
                okText="插入图片"
                cancelText="取消"
                onOk={insertImage}
                onCancel={() => setImageOpen(false)}
                okButtonProps={{ disabled: !/^https:\/\/[^\s"<>]+$/i.test(imageForm.url.trim()) }}
                destroyOnHidden
            >
                <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                    <Input
                        value={imageForm.url}
                        addonBefore="HTTPS URL"
                        placeholder="https://example.com/announcement.png"
                        onChange={event => setImageForm(current => ({ ...current, url: event.target.value }))}
                    />
                    <Input
                        value={imageForm.alt}
                        addonBefore="替代文字"
                        placeholder="可选"
                        onChange={event => setImageForm(current => ({ ...current, alt: event.target.value }))}
                    />
                    <Space.Compact block>
                        <Input
                            value={imageForm.width}
                            addonBefore="宽度"
                            placeholder="100% 或 400"
                            onChange={event => setImageForm(current => ({ ...current, width: event.target.value }))}
                        />
                        <InputNumber
                            value={imageForm.height}
                            addonBefore="高度 px"
                            min={1}
                            max={4096}
                            precision={0}
                            onChange={height => setImageForm(current => ({ ...current, height: Number(height ?? DEFAULT_IMAGE.height) }))}
                        />
                    </Space.Compact>
                </Space>
            </Modal>
        </div>
    )
}

export default NewsHtmlEditor
