// Native GUI protocol: one JSON request on stdin and one JSON response on stdout.
// Paths and user input never pass through a command shell.
console.log = (...args) => console.error(...args)
let input = ''
process.stdin.setEncoding('utf8')
process.stdin.on('data', chunk => {
    input += chunk
    if (input.length > 65536) {
        process.stdout.write(JSON.stringify({ ok: false, error: '请求过大' }))
        process.exit(1)
    }
})
process.stdin.on('end', () => {
    try {
        const options = JSON.parse(input)
        if (!options || typeof options !== 'object' || Array.isArray(options)) throw new Error('请求格式无效')
        if (!options.list && !options.output) throw new Error('请选择输出文件')
        const result = require('./extract_player_save.cjs').extractPlayerSave(options)
        process.stdout.write(JSON.stringify({ ok: true, result }))
    } catch (error) {
        process.stdout.write(JSON.stringify({ ok: false, error: error.message }))
        process.exitCode = 1
    }
})
