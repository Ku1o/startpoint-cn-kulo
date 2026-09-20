using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal sealed class SaveExtractorForm : Form
{
    private readonly TextBox database = new TextBox();
    private readonly TextBox viewer = new TextBox();
    private readonly ComboBox players = new ComboBox();
    private readonly Button browse = new Button();
    private readonly Button lookup = new Button();
    private readonly Button export = new Button();
    private readonly TextBox status = new TextBox();
    private readonly ProgressBar progress = new ProgressBar();
    private readonly Timer timer = new Timer();
    private readonly JavaScriptSerializer json = new JavaScriptSerializer();
    private Process worker;
    private Task<string> stdout;
    private Task<string> stderr;
    private bool listing;
    private string lookupDatabase;
    private string lookupViewer;
    private readonly string projectRoot;

    private sealed class PlayerChoice
    {
        public long Id;
        public string Name;
        public override string ToString() { return Name + "    （存档 ID：" + Id + "）"; }
    }

    public SaveExtractorForm()
    {
        projectRoot = Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "../.."));
        Text = "StarPoint CN · 玩家存档提取器";
        ClientSize = new Size(720, 535);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Microsoft YaHei UI", 10F);
        BackColor = Color.FromArgb(247, 249, 252);
        AddLabel("从数据库提取玩家存档", 24, 22, 660, 35, 19F);
        AddLabel("选择数据库，按游戏内 viewer id 将单个玩家的存档复制为 JSON。", 26, 66, 665, 30, 10F);
        AddLabel("1  数据库文件", 26, 110, 640, 25, 10F);
        database.SetBounds(26, 141, 553, 30);
        database.AccessibleName = "数据库路径";
        Controls.Add(database);
        ConfigureButton(browse, "选择文件", 588, 139, 105, 34);
        AddLabel("2  Viewer ID", 26, 189, 185, 25, 10F);
        viewer.SetBounds(26, 220, 432, 30);
        viewer.AccessibleName = "Viewer ID";
        Controls.Add(viewer);
        ConfigureButton(lookup, "查询玩家存档", 474, 218, 219, 34);
        AddLabel("3  选择要提取的存档", 26, 268, 400, 25, 10F);
        players.SetBounds(26, 299, 432, 32);
        players.AccessibleName = "玩家存档列表";
        players.DropDownStyle = ComboBoxStyle.DropDownList;
        players.DropDownWidth = 580;
        Controls.Add(players);
        ConfigureButton(export, "选择位置并导出", 474, 297, 219, 36);
        export.BackColor = Color.FromArgb(35, 99, 206);
        export.ForeColor = Color.White;
        export.FlatStyle = FlatStyle.Flat;
        export.FlatAppearance.BorderSize = 0;
        export.Enabled = false;
        status.SetBounds(26, 360, 667, 107);
        status.Multiline = true;
        status.ReadOnly = true;
        status.ScrollBars = ScrollBars.Vertical;
        status.BorderStyle = BorderStyle.None;
        status.BackColor = BackColor;
        status.AccessibleName = "操作结果";
        status.Text = "请选择数据库并输入 viewer id。\r\n数据库文件或目录路径也可直接粘贴到路径框。";
        Controls.Add(status);
        progress.SetBounds(26, 478, 667, 5);
        progress.Style = ProgressBarStyle.Marquee;
        progress.Visible = false;
        Controls.Add(progress);
        AddLabel("只读提取 · 只生成单人存档 JSON · 不修改原数据库", 26, 495, 667, 25, 9F);
        database.TextChanged += delegate { InvalidateLookup(); };
        viewer.TextChanged += delegate { InvalidateLookup(); };
        players.SelectedIndexChanged += delegate { export.Enabled = worker == null && players.SelectedItem != null; };
        browse.Click += delegate { ChooseDatabase(); };
        lookup.Click += delegate { FindPlayers(); };
        export.Click += delegate { ExportSave(); };
        timer.Interval = 100;
        timer.Tick += delegate { PollWorker(); };
        FormClosing += delegate(object sender, FormClosingEventArgs e) {
            if (worker != null) { e.Cancel = true; status.Text = "正在处理，请等待本次操作结束后再关闭窗口。"; }
        };
        FormClosed += delegate { timer.Dispose(); };
        AcceptButton = lookup;
    }

    private void AddLabel(string text, int x, int y, int width, int height, float size)
    {
        var label = new Label { Text = text, AutoSize = false, ForeColor = Color.FromArgb(44, 57, 77), Font = new Font(Font.FontFamily, size) };
        label.SetBounds(x, y, width, height);
        Controls.Add(label);
    }

    private void ConfigureButton(Button button, string text, int x, int y, int width, int height)
    {
        button.Text = text;
        button.SetBounds(x, y, width, height);
        Controls.Add(button);
    }

    private void InvalidateLookup()
    {
        players.Items.Clear();
        export.Enabled = false;
        lookupDatabase = lookupViewer = null;
        status.Text = "选择数据库并输入 viewer id 后，点击“查询玩家存档”。";
    }

    private void ChooseDatabase()
    {
        using (var dialog = new OpenFileDialog { Title = "选择要提取存档的数据库", Filter = "SQLite 数据库 (*.db;*.sqlite;*.sqlite3)|*.db;*.sqlite;*.sqlite3|所有文件 (*.*)|*.*", CheckFileExists = true, Multiselect = false })
            if (dialog.ShowDialog(this) == DialogResult.OK) database.Text = dialog.FileName;
    }

    private Dictionary<string, object> Request()
    {
        return new Dictionary<string, object> { { "database", database.Text.Trim() }, { "viewerId", viewer.Text.Trim() } };
    }

    private void FindPlayers()
    {
        if (worker != null) return;
        if (String.IsNullOrWhiteSpace(database.Text) || String.IsNullOrWhiteSpace(viewer.Text)) {
            status.Text = "请先选择数据库，并填写游戏内的 viewer id。";
            return;
        }
        players.Items.Clear();
        export.Enabled = false;
        var request = Request();
        request["list"] = true;
        StartWorker(request, true);
    }

    private void ExportSave()
    {
        var player = players.SelectedItem as PlayerChoice;
        if (worker != null || player == null) return;
        if (lookupDatabase != database.Text.Trim() || lookupViewer != viewer.Text.Trim()) { InvalidateLookup(); return; }
        using (var dialog = new SaveFileDialog {
            Title = "保存提取的玩家存档", Filter = "玩家存档 (*.json)|*.json", DefaultExt = "json", AddExtension = true,
            CheckPathExists = true, OverwritePrompt = false,
            FileName = "save_" + lookupViewer + "_" + player.Id + "_" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".json"
        }) {
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            if (File.Exists(dialog.FileName)) { status.Text = "该输出文件已存在，请重新选择一个文件名。已有文件未被覆盖。"; return; }
            var request = Request();
            request["playerId"] = player.Id;
            request["output"] = dialog.FileName;
            StartWorker(request, false);
        }
    }

    private string NodePath()
    {
        var candidates = new List<string> { Path.Combine(projectRoot, "node.exe") };
        foreach (string entry in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator))
            if (!String.IsNullOrWhiteSpace(entry)) candidates.Add(Path.Combine(entry.Trim().Trim('"'), "node.exe"));
        foreach (string candidate in candidates) if (File.Exists(candidate)) return candidate;
        throw new Exception("未找到 Node.js。请在安装了项目运行环境的电脑上使用此工具（Node.js 20 或以上）。");
    }

    private void Busy(bool value)
    {
        database.Enabled = viewer.Enabled = browse.Enabled = lookup.Enabled = players.Enabled = !value;
        export.Enabled = !value && players.SelectedItem != null;
        progress.Visible = value;
    }

    private void StartWorker(Dictionary<string, object> request, bool isList)
    {
        try {
            string script = Path.Combine(projectRoot, "tools", "extract_player_save_gui_worker.cjs");
            if (!File.Exists(script)) throw new Exception("缺少提取工具文件，请保留程序在项目 tools/player-save-extractor 目录内使用。");
            var info = new ProcessStartInfo(NodePath(), "\"" + script + "\"") {
                WorkingDirectory = projectRoot, UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
            };
            worker = Process.Start(info);
            stdout = worker.StandardOutput.ReadToEndAsync();
            stderr = worker.StandardError.ReadToEndAsync();
            // Explicit UTF-8: names and paths must survive non-ASCII Windows locales.
            byte[] bytes = Encoding.UTF8.GetBytes(json.Serialize(request));
            worker.StandardInput.BaseStream.Write(bytes, 0, bytes.Length);
            worker.StandardInput.Close();
            listing = isList;
            Busy(true);
            status.Text = isList ? "正在读取数据库，查找玩家存档…" : "正在提取并校验存档，请稍候…";
            timer.Start();
        } catch (Exception error) {
            if (worker != null) { worker.Dispose(); worker = null; }
            Busy(false);
            status.Text = "无法开始操作：" + error.Message;
        }
    }

    private void PollWorker()
    {
        if (worker == null || !worker.HasExited || !stdout.IsCompleted || !stderr.IsCompleted) return;
        timer.Stop();
        try {
            var response = json.Deserialize<Dictionary<string, object>>(stdout.Result);
            if (response == null || !response.ContainsKey("ok")) throw new Exception("提取进程未返回有效结果，请检查项目运行环境。" + stderr.Result);
            if (!(bool)response["ok"]) throw new Exception(Convert.ToString(response["error"]));
            var result = (Dictionary<string, object>)response["result"];
            if (listing) {
                foreach (Dictionary<string, object> row in (IEnumerable)result["candidates"])
                    players.Items.Add(new PlayerChoice { Id = Convert.ToInt64(row["id"]), Name = Convert.ToString(row["name"]) });
                lookupDatabase = database.Text.Trim();
                lookupViewer = viewer.Text.Trim();
                if (players.Items.Count == 1) players.SelectedIndex = 0;
                status.Text = players.Items.Count == 1 ? "已找到玩家存档。请核对名称，然后点击“选择位置并导出”。" : "找到 " + players.Items.Count + " 个存档，请在列表中明确选择需要恢复的一个。";
            } else {
                status.Text = "提取成功：" + result["playerName"] + "\r\n保存到：" + result["output"] + "\r\n共 " + result["rowCount"] + " 行。";
            }
        } catch (Exception error) {
            status.Text = "操作失败：" + error.Message;
        } finally {
            worker.Dispose(); worker = null; Busy(false);
        }
    }

    [STAThread]
    private static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try { Application.Run(new SaveExtractorForm()); }
        catch (Exception error) { MessageBox.Show(error.Message, "玩家存档提取器启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error); }
    }
}
