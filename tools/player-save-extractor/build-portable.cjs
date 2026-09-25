// Builds an explicit, standalone Windows x64 tool package; never a server overlay.
const fs = require('node:fs')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const { createHash } = require('node:crypto')
const root = path.resolve(__dirname, '../..')
const outputRoot = path.resolve(process.argv[2] || path.join(root, 'outputs/player-save-extractor'))
if (process.platform !== 'win32' || process.arch !== 'x64') throw new Error('Build with Windows x64 Node.js')
if (outputRoot.split(/[\\/]/).some(p => p.toLowerCase() === '.cdn')) throw new Error('CDN output is forbidden')
let ancestor = outputRoot
while (!fs.existsSync(ancestor)) ancestor = path.dirname(ancestor)
if (fs.realpathSync(ancestor).split(/[\\/]/).some(p => p.toLowerCase() === '.cdn')) throw new Error('CDN junction output is forbidden')
const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\..*$/, '').replace('T', '-')
const name = `StarPoint-PlayerSaveExtractor-Windows-x64-${stamp}`
const directory = path.join(outputRoot, name)
fs.mkdirSync(directory, { recursive: true })

function run(exe, args, options = {}) {
    const child = spawnSync(exe, args, { cwd: root, encoding: 'utf8', windowsHide: true, ...options })
    if (child.status !== 0) throw new Error(child.error?.message || child.stderr || child.stdout || `exit=${child.status}`)
    return child.stdout
}
function copy(source, destination = source) {
    const target = path.join(directory, destination)
    fs.mkdirSync(path.dirname(target), { recursive: true })
    fs.copyFileSync(path.isAbsolute(source) ? source : path.join(root, source), target, fs.constants.COPYFILE_EXCL)
}
function filesBelow(dir) {
    return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
        if (entry.isSymbolicLink()) throw new Error(`Unexpected link: ${entry.name}`)
        const filename = path.join(dir, entry.name)
        return entry.isDirectory() ? filesBelow(filename) : [filename]
    })
}
function hash(file) { return createHash('sha256').update(fs.readFileSync(file)).digest('hex') }

// Compile into the package so an open source-tree GUI need not be overwritten.
const compiler = path.join(process.env.WINDIR, 'Microsoft.NET/Framework64/v4.0.30319/csc.exe')
const guiPath = path.join(directory, 'tools/player-save-extractor/PlayerSaveExtractor.exe')
fs.mkdirSync(path.dirname(guiPath), { recursive: true })
run(compiler, ['/nologo', '/target:winexe', '/platform:anycpu', '/optimize+', '/codepage:65001', `/out:${guiPath}`,
    '/reference:System.dll', '/reference:System.Core.dll', '/reference:System.Drawing.dll',
    '/reference:System.Windows.Forms.dll', '/reference:System.Web.Extensions.dll', path.join(__dirname, 'MainForm.cs')])

for (const file of [
    'tools/extract_player_save.cjs', 'tools/extract_player_save_gui_worker.cjs',
    'tools/player-save-extractor/MainForm.cs', 'tools/player-save-extractor/build.ps1',
    'out/data/snapshots/player-snapshot.js', 'out/lib/storage-layout.js', 'out/lib/cached-statement.js',
    'out/lib/memory-diagnostics.js', 'out/lib/process-memory-probe.js', 'tools/capture-native-memory.ps1',
    'out/utils.js',
    'src/data/snapshots/player-snapshot.ts', 'src/lib/storage-layout.ts', 'src/utils.ts',
    'LICENSE',
]) copy(file)
copy(process.execPath, 'node.exe')
copy('tools/player-save-extractor/PORTABLE-README.txt', '使用说明.txt')
fs.writeFileSync(path.join(directory, '双击提取玩家存档.cmd'), '@echo off\r\nstart "" "%~dp0tools\\player-save-extractor\\PlayerSaveExtractor.exe"\r\n', 'ascii')

const dependencyFiles = [
    'better-sqlite3/package.json', 'better-sqlite3/LICENSE', 'better-sqlite3/build/Release/better_sqlite3.node',
    'bindings/package.json', 'bindings/bindings.js', 'bindings/LICENSE.md',
    'file-uri-to-path/package.json', 'file-uri-to-path/index.js', 'file-uri-to-path/LICENSE',
]
for (const file of dependencyFiles) copy(`node_modules/${file}`)
for (const file of filesBelow(path.join(root, 'node_modules/better-sqlite3/lib'))) copy(file, path.relative(root, file))
fs.mkdirSync(path.join(directory, 'licenses'))
if (process.version !== 'v24.21.0') throw new Error('Update the bundled Node license for this runtime version before packaging')
copy('tools/player-save-extractor/NODE-LICENSE.txt', 'licenses/Node.js-LICENSE.txt')
fs.writeFileSync(path.join(directory, 'licenses/THIRD-PARTY.txt'),
    `Node.js ${process.version} (Windows x64, ABI ${process.versions.modules}); see Node.js-LICENSE.txt.\n` +
    'better-sqlite3 12.11.1, bindings and file-uri-to-path: MIT; licenses included in each package directory.\n' +
    'StarPoint CN: GPL-3.0-or-later; LICENSE and corresponding tool / snapshot source included.\n')

const entries = filesBelow(directory).map(file => ({
    path: path.relative(directory, file).replace(/\\/g, '/'), bytes: fs.statSync(file).size, sha256: hash(file),
})).sort((a, b) => a.path.localeCompare(b.path))
for (const entry of entries) {
    if (/^(?:\/|[a-z]:)|(?:^|\/)\.\.(?:\/|$)|(?:^|\/)(?:\.cdn|\.database|\.git|secrets|admin-backups|production)(?:\/|$)|\.(?:db|sqlite|sqlite3|jks|pem|key|log)$|(?:^|\/)\.env(?:$|\.)/i.test(entry.path)) {
        throw new Error(`Forbidden package member: ${entry.path}`)
    }
}
fs.writeFileSync(path.join(directory, 'manifest.json'), JSON.stringify({
    name, platform: 'win32-x64', nodeVersion: process.version, nodeAbi: process.versions.modules,
    scope: 'standalone-player-save-extraction-only', files: entries,
}, null, 2))
const archive = `${directory}.zip`
run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
    'Compress-Archive -LiteralPath $env:SP_EXTRACTOR_PACKAGE_DIR -DestinationPath $env:SP_EXTRACTOR_PACKAGE_ZIP -CompressionLevel Optimal'], {
    env: { ...process.env, SP_EXTRACTOR_PACKAGE_DIR: directory, SP_EXTRACTOR_PACKAGE_ZIP: archive },
    timeout: 120000,
})
fs.writeFileSync(`${archive}.sha256`, `${hash(archive)}  ${path.basename(archive)}\n`)
fs.writeFileSync(`${archive}.files.txt`, entries.map(entry => `${entry.sha256}  ${entry.bytes}  ${entry.path}`).join('\n') + '\nmanifest.json (package manifest)\n')
console.log(JSON.stringify({ directory, archive, bytes: fs.statSync(archive).size, sha256: hash(archive), files: entries.length + 1 }, null, 2))
