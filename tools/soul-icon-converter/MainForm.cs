using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Windows.Forms;

namespace SoulIconConverter
{
    internal sealed class MainForm : Form
    {
        private readonly List<IconWorkItem> items = new List<IconWorkItem>();
        private readonly ListView fileList = new ListView();
        private readonly PixelPreviewBox sourcePreview = new PixelPreviewBox();
        private readonly PixelPreviewBox soulPreview = new PixelPreviewBox();
        private readonly GamePreviewBox gamePreview = new GamePreviewBox();
        private readonly Label sourcePathLabel = new Label();
        private readonly Label soulPathLabel = new Label();
        private readonly Label gamePreviewLabel = new Label();
        private readonly TextBox outputDirectoryText = new TextBox();
        private readonly ToolStripStatusLabel statusLabel = new ToolStripStatusLabel();
        private readonly Button convertButton;

        internal MainForm(string[] startupPaths)
        {
            Text = "魂珠图标一键转换工具";
            StartPosition = FormStartPosition.CenterScreen;
            AutoScaleDimensions = new SizeF(96.0f, 96.0f);
            AutoScaleMode = AutoScaleMode.Dpi;
            MinimumSize = new Size(1180, 760);
            ClientSize = new Size(1360, 860);
            BackColor = Color.FromArgb(22, 25, 32);
            ForeColor = Color.FromArgb(235, 239, 247);
            Font = new Font("Microsoft YaHei UI", 9.0f, FontStyle.Regular);
            AllowDrop = true;

            Panel header = BuildHeader(out convertButton);
            Panel listPanel = BuildListPanel();
            TableLayoutPanel previews = BuildPreviewArea();
            soulPathLabel.Text = "选择图片后实时生成";
            gamePreviewLabel.Text = "五星装备格 + 五星魂珠格";

            // WinForms applies Dock layout in reverse z-order. Add the Fill control
            // first so the header and bottom list reserve their space before it.
            Controls.Add(previews);
            Controls.Add(listPanel);
            Controls.Add(header);

            StatusStrip status = new StatusStrip();
            status.BackColor = Color.FromArgb(17, 20, 26);
            status.ForeColor = Color.FromArgb(188, 199, 218);
            status.SizingGrip = false;
            status.AutoSize = false;
            status.Height = 36;
            status.Padding = new Padding(8, 0, 8, 0);
            statusLabel.Text = "就绪：请选择或拖入原始 20×20 装备 PNG。";
            statusLabel.Spring = true;
            statusLabel.TextAlign = ContentAlignment.MiddleLeft;
            statusLabel.Padding = new Padding(0, 3, 0, 3);
            status.Items.Add(statusLabel);
            Controls.Add(status);

            DragEnter += HandleDragEnter;
            DragDrop += HandleDragDrop;
            previews.AllowDrop = true;
            previews.DragEnter += HandleDragEnter;
            previews.DragDrop += HandleDragDrop;
            sourcePreview.AllowDrop = true;
            soulPreview.AllowDrop = true;
            gamePreview.AllowDrop = true;
            sourcePreview.DragEnter += HandleDragEnter;
            sourcePreview.DragDrop += HandleDragDrop;
            soulPreview.DragEnter += HandleDragEnter;
            soulPreview.DragDrop += HandleDragDrop;
            gamePreview.DragEnter += HandleDragEnter;
            gamePreview.DragDrop += HandleDragDrop;

            if (startupPaths != null && startupPaths.Length > 0)
            {
                Shown += delegate { AddPaths(startupPaths); };
            }
        }

        private Panel BuildHeader(out Button oneClickButton)
        {
            Panel panel = new Panel();
            panel.Dock = DockStyle.Top;
            panel.Height = 168;
            panel.Padding = new Padding(18, 10, 18, 8);
            panel.BackColor = Color.FromArgb(31, 35, 44);

            TableLayoutPanel layout = new TableLayoutPanel();
            layout.Dock = DockStyle.Fill;
            layout.ColumnCount = 1;
            layout.RowCount = 3;
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 56.0f));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 52.0f));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100.0f));
            panel.Controls.Add(layout);

            TableLayoutPanel titleRow = new TableLayoutPanel();
            titleRow.Dock = DockStyle.Fill;
            titleRow.ColumnCount = 2;
            titleRow.RowCount = 1;
            titleRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 480.0f));
            titleRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100.0f));
            layout.Controls.Add(titleRow, 0, 0);

            Label title = new Label();
            title.Text = "魂珠图标一键转换工具";
            title.Font = new Font("Microsoft YaHei UI", 16.0f, FontStyle.Bold);
            title.ForeColor = Color.FromArgb(242, 247, 255);
            title.AutoSize = false;
            title.Dock = DockStyle.Fill;
            title.TextAlign = ContentAlignment.MiddleLeft;
            title.AutoEllipsis = true;
            title.Margin = new Padding(0, 0, 18, 0);
            titleRow.Controls.Add(title, 0, 0);

            Label detail = new Label();
            detail.Text = "365 对原游戏图标拟合 · 20×20 · Alpha 原样保留 · 支持批量";
            detail.ForeColor = Color.FromArgb(157, 175, 204);
            detail.AutoSize = false;
            detail.Dock = DockStyle.Fill;
            detail.TextAlign = ContentAlignment.MiddleLeft;
            detail.Margin = new Padding(0);
            titleRow.Controls.Add(detail, 1, 0);

            TableLayoutPanel actionRow = new TableLayoutPanel();
            actionRow.Dock = DockStyle.Fill;
            actionRow.ColumnCount = 7;
            actionRow.RowCount = 1;
            actionRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            actionRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            actionRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            actionRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            actionRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100.0f));
            actionRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            actionRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            layout.Controls.Add(actionRow, 0, 1);

            Button selectButton = CreateButton("选择图片", 130);
            selectButton.Click += SelectFiles;
            actionRow.Controls.Add(selectButton, 0, 0);

            oneClickButton = CreateButton("一键转换", 140);
            oneClickButton.BackColor = Color.FromArgb(35, 137, 218);
            oneClickButton.Click += ConvertAll;
            actionRow.Controls.Add(oneClickButton, 1, 0);

            Button clearButton = CreateButton("清空", 80);
            clearButton.Click += ClearItems;
            actionRow.Controls.Add(clearButton, 2, 0);

            Label outputLabel = new Label();
            outputLabel.Text = "输出目录";
            outputLabel.AutoSize = true;
            outputLabel.ForeColor = Color.FromArgb(190, 201, 219);
            outputLabel.Anchor = AnchorStyles.Left;
            outputLabel.Margin = new Padding(14, 0, 8, 0);
            actionRow.Controls.Add(outputLabel, 3, 0);

            outputDirectoryText.Dock = DockStyle.Fill;
            outputDirectoryText.Margin = new Padding(0, 7, 8, 6);
            outputDirectoryText.BackColor = Color.FromArgb(20, 23, 30);
            outputDirectoryText.ForeColor = Color.FromArgb(235, 239, 247);
            outputDirectoryText.BorderStyle = BorderStyle.FixedSingle;
            actionRow.Controls.Add(outputDirectoryText, 4, 0);

            Button chooseFolderButton = CreateButton("选择目录", 120);
            chooseFolderButton.Click += ChooseOutputDirectory;
            actionRow.Controls.Add(chooseFolderButton, 5, 0);

            Button openFolderButton = CreateButton("打开目录", 120);
            openFolderButton.Click += OpenOutputDirectory;
            actionRow.Controls.Add(openFolderButton, 6, 0);

            Label hint = new Label();
            hint.Text = "也可以把一个或多个 PNG（或包含 PNG 的文件夹）直接拖到窗口。输出不会覆盖已有文件。";
            hint.AutoSize = false;
            hint.Dock = DockStyle.Fill;
            hint.TextAlign = ContentAlignment.MiddleLeft;
            hint.ForeColor = Color.FromArgb(130, 145, 168);
            hint.Margin = new Padding(0);
            layout.Controls.Add(hint, 0, 2);

            return panel;
        }

        private TableLayoutPanel BuildPreviewArea()
        {
            TableLayoutPanel table = new TableLayoutPanel();
            table.Dock = DockStyle.Fill;
            table.ColumnCount = 3;
            table.RowCount = 1;
            table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.3333f));
            table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.3333f));
            table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.3334f));
            table.RowStyles.Add(new RowStyle(SizeType.Percent, 100.0f));
            table.BackColor = Color.FromArgb(22, 25, 32);

            Panel left = new Panel();
            left.Dock = DockStyle.Fill;
            left.Padding = new Padding(18, 14, 7, 12);
            table.Controls.Add(left, 0, 0);

            Panel right = new Panel();
            right.Dock = DockStyle.Fill;
            right.Padding = new Padding(7, 14, 7, 12);
            table.Controls.Add(right, 1, 0);

            Panel game = new Panel();
            game.Dock = DockStyle.Fill;
            game.Padding = new Padding(7, 14, 18, 12);
            table.Controls.Add(game, 2, 0);

            BuildPreviewPanel(left, "原装备图标", sourcePreview, sourcePathLabel);
            BuildPreviewPanel(right, "魂珠风格结果", soulPreview, soulPathLabel);
            BuildPreviewPanel(game, "游戏内效果预览", gamePreview, gamePreviewLabel);
            return table;
        }

        private static void BuildPreviewPanel(
            Control parent,
            string titleText,
            Control preview,
            Label pathLabel)
        {
            Panel card = new Panel();
            card.Dock = DockStyle.Fill;
            card.BackColor = Color.FromArgb(31, 35, 44);
            card.Padding = new Padding(1);
            parent.Controls.Add(card);

            TableLayoutPanel layout = new TableLayoutPanel();
            layout.Dock = DockStyle.Fill;
            layout.ColumnCount = 1;
            layout.RowCount = 3;
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100.0f));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 44.0f));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100.0f));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 48.0f));
            card.Controls.Add(layout);

            Label title = new Label();
            title.Text = titleText;
            title.Dock = DockStyle.Fill;
            title.TextAlign = ContentAlignment.MiddleCenter;
            title.Font = new Font("Microsoft YaHei UI", 11.0f, FontStyle.Bold);
            title.ForeColor = Color.FromArgb(226, 232, 244);
            title.Margin = new Padding(4, 2, 4, 2);
            layout.Controls.Add(title, 0, 0);

            pathLabel.Text = "尚未选择";
            pathLabel.Dock = DockStyle.Fill;
            pathLabel.Padding = new Padding(10, 4, 10, 4);
            pathLabel.TextAlign = ContentAlignment.MiddleCenter;
            pathLabel.AutoEllipsis = true;
            pathLabel.ForeColor = Color.FromArgb(154, 168, 192);
            pathLabel.Margin = new Padding(0);
            layout.Controls.Add(pathLabel, 0, 2);

            preview.Dock = DockStyle.Fill;
            preview.Margin = new Padding(0);
            layout.Controls.Add(preview, 0, 1);
        }

        private Panel BuildListPanel()
        {
            Panel panel = new Panel();
            panel.Dock = DockStyle.Bottom;
            panel.Height = 240;
            panel.Padding = new Padding(18, 8, 18, 10);
            panel.BackColor = Color.FromArgb(25, 28, 36);

            TableLayoutPanel layout = new TableLayoutPanel();
            layout.Dock = DockStyle.Fill;
            layout.ColumnCount = 1;
            layout.RowCount = 2;
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100.0f));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 38.0f));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100.0f));
            panel.Controls.Add(layout);

            Label title = new Label();
            title.Text = "待处理文件";
            title.Dock = DockStyle.Fill;
            title.Font = new Font("Microsoft YaHei UI", 10.0f, FontStyle.Bold);
            title.ForeColor = Color.FromArgb(211, 220, 235);
            title.TextAlign = ContentAlignment.MiddleLeft;
            title.Padding = new Padding(4, 0, 0, 0);
            title.Margin = new Padding(0);
            layout.Controls.Add(title, 0, 0);

            fileList.Dock = DockStyle.Fill;
            fileList.View = View.Details;
            fileList.FullRowSelect = true;
            fileList.HideSelection = false;
            fileList.MultiSelect = false;
            fileList.BackColor = Color.FromArgb(18, 21, 27);
            fileList.ForeColor = Color.FromArgb(226, 232, 244);
            fileList.BorderStyle = BorderStyle.FixedSingle;
            fileList.Columns.Add("文件", 320);
            fileList.Columns.Add("尺寸", 90);
            fileList.Columns.Add("状态", 190);
            fileList.Columns.Add("输出位置", 650);
            fileList.SelectedIndexChanged += SelectedFileChanged;
            fileList.Resize += delegate { AdjustFileListColumns(); };
            layout.Controls.Add(fileList, 0, 1);

            return panel;
        }

        private static Button CreateButton(string text, int width)
        {
            Button button = new Button();
            button.Text = text;
            button.Size = new Size(width, 38);
            button.MinimumSize = new Size(width, 38);
            button.Anchor = AnchorStyles.Left;
            button.Margin = new Padding(0, 5, 8, 5);
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderColor = Color.FromArgb(75, 85, 104);
            button.FlatAppearance.BorderSize = 1;
            button.BackColor = Color.FromArgb(49, 56, 70);
            button.ForeColor = Color.White;
            button.Cursor = Cursors.Hand;
            return button;
        }

        private void AdjustFileListColumns()
        {
            if (fileList.Columns.Count != 4 || fileList.ClientSize.Width <= 0)
            {
                return;
            }

            int available = Math.Max(760, fileList.ClientSize.Width - 4);
            int sizeWidth = 90;
            int statusWidth = 190;
            int fileWidth = Math.Max(260, (int)(available * 0.28f));
            int outputWidth = Math.Max(260, available - fileWidth - sizeWidth - statusWidth);
            fileList.Columns[0].Width = fileWidth;
            fileList.Columns[1].Width = sizeWidth;
            fileList.Columns[2].Width = statusWidth;
            fileList.Columns[3].Width = outputWidth;
        }

        private void SelectFiles(object sender, EventArgs e)
        {
            using (OpenFileDialog dialog = new OpenFileDialog())
            {
                dialog.Title = "选择原始 20×20 装备图标";
                dialog.Filter = "PNG 图片 (*.png)|*.png";
                dialog.Multiselect = true;
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    AddPaths(dialog.FileNames);
                }
            }
        }

        private void ChooseOutputDirectory(object sender, EventArgs e)
        {
            using (FolderBrowserDialog dialog = new FolderBrowserDialog())
            {
                dialog.Description = "选择魂珠图标输出目录";
                if (Directory.Exists(outputDirectoryText.Text))
                {
                    dialog.SelectedPath = outputDirectoryText.Text;
                }

                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    outputDirectoryText.Text = dialog.SelectedPath;
                }
            }
        }

        private void OpenOutputDirectory(object sender, EventArgs e)
        {
            string directory = outputDirectoryText.Text.Trim();
            if (string.IsNullOrEmpty(directory))
            {
                MessageBox.Show(this, "请先选择图片或设置输出目录。", Text,
                    MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            Directory.CreateDirectory(directory);
            Process.Start("explorer.exe", directory);
        }

        private void HandleDragEnter(object sender, DragEventArgs e)
        {
            if (e.Data != null && e.Data.GetDataPresent(DataFormats.FileDrop))
            {
                e.Effect = DragDropEffects.Copy;
            }
        }

        private void HandleDragDrop(object sender, DragEventArgs e)
        {
            if (e.Data == null || !e.Data.GetDataPresent(DataFormats.FileDrop))
            {
                return;
            }

            string[] paths = (string[])e.Data.GetData(DataFormats.FileDrop);
            AddPaths(paths);
        }

        private void AddPaths(IEnumerable<string> paths)
        {
            List<string> expanded = new List<string>();
            foreach (string rawPath in paths)
            {
                if (Directory.Exists(rawPath))
                {
                    expanded.AddRange(Directory.GetFiles(rawPath, "*.png", SearchOption.TopDirectoryOnly));
                }
                else if (File.Exists(rawPath))
                {
                    expanded.Add(rawPath);
                }
            }

            int added = 0;
            foreach (string rawPath in expanded)
            {
                string path = Path.GetFullPath(rawPath);
                if (!string.Equals(Path.GetExtension(path), ".png", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                if (items.Any(delegate(IconWorkItem existing)
                    { return string.Equals(existing.InputPath, path, StringComparison.OrdinalIgnoreCase); }))
                {
                    continue;
                }

                IconWorkItem item = new IconWorkItem();
                item.InputPath = path;
                item.Status = "待转换";
                try
                {
                    using (Bitmap bitmap = SoulTransformer.LoadBitmapUnlocked(path))
                    {
                        item.SizeText = string.Format("{0}×{1}", bitmap.Width, bitmap.Height);
                        if (bitmap.Width != 20 || bitmap.Height != 20)
                        {
                            item.Status = "尺寸不符";
                        }
                    }
                }
                catch (Exception exception)
                {
                    item.SizeText = "无法读取";
                    item.Status = ShortMessage(exception.Message);
                }

                ListViewItem row = new ListViewItem(Path.GetFileName(path));
                row.SubItems.Add(item.SizeText);
                row.SubItems.Add(item.Status);
                row.SubItems.Add(string.Empty);
                row.Tag = item;
                item.Row = row;
                items.Add(item);
                fileList.Items.Add(row);
                added++;
            }

            if (items.Count > 0 && string.IsNullOrWhiteSpace(outputDirectoryText.Text))
            {
                outputDirectoryText.Text = Path.Combine(
                    Path.GetDirectoryName(items[0].InputPath), "魂珠图标输出");
            }

            if (fileList.Items.Count > 0 && fileList.SelectedItems.Count == 0)
            {
                fileList.Items[0].Selected = true;
                fileList.Items[0].EnsureVisible();
            }

            statusLabel.Text = added > 0
                ? string.Format("已加入 {0} 个文件，共 {1} 个待处理。", added, items.Count)
                : "没有加入新文件；请确认拖入的是 PNG。";
        }

        private void ConvertAll(object sender, EventArgs e)
        {
            if (items.Count == 0)
            {
                MessageBox.Show(this, "请先选择或拖入装备图标 PNG。", Text,
                    MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            string directory = outputDirectoryText.Text.Trim();
            if (string.IsNullOrEmpty(directory))
            {
                MessageBox.Show(this, "请设置输出目录。", Text,
                    MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            convertButton.Enabled = false;
            int success = 0;
            int failed = 0;
            try
            {
                Directory.CreateDirectory(directory);
                foreach (IconWorkItem item in items)
                {
                    item.Status = "转换中…";
                    UpdateRow(item);
                    statusLabel.Text = "正在转换：" + Path.GetFileName(item.InputPath);
                    Application.DoEvents();

                    try
                    {
                        string outputPath = GetSafeOutputPath(directory, item.InputPath);
                        SoulTransformer.ConvertFile(item.InputPath, outputPath);
                        item.OutputPath = outputPath;
                        item.Status = "完成";
                        success++;
                    }
                    catch (Exception exception)
                    {
                        item.OutputPath = string.Empty;
                        item.Status = "失败：" + ShortMessage(exception.Message);
                        failed++;
                    }

                    UpdateRow(item);
                }
            }
            finally
            {
                convertButton.Enabled = true;
            }

            ShowSelectedPreview();
            statusLabel.Text = string.Format("转换结束：成功 {0}，失败 {1}。", success, failed);
            MessageBox.Show(this,
                string.Format("处理完成。\r\n\r\n成功：{0}\r\n失败：{1}\r\n输出目录：{2}",
                    success, failed, directory),
                Text,
                MessageBoxButtons.OK,
                failed == 0 ? MessageBoxIcon.Information : MessageBoxIcon.Warning);
        }

        private static string GetSafeOutputPath(string directory, string inputPath)
        {
            string baseName = Path.GetFileNameWithoutExtension(inputPath) + "_魂珠";
            string candidate = Path.Combine(directory, baseName + ".png");
            int suffix = 2;
            while (File.Exists(candidate))
            {
                candidate = Path.Combine(directory,
                    string.Format("{0}_{1}.png", baseName, suffix));
                suffix++;
            }
            return candidate;
        }

        private void ClearItems(object sender, EventArgs e)
        {
            items.Clear();
            fileList.Items.Clear();
            sourcePreview.PreviewImage = null;
            soulPreview.PreviewImage = null;
            gamePreview.SetImages(null, null);
            sourcePathLabel.Text = "尚未选择";
            soulPathLabel.Text = "尚未生成";
            gamePreviewLabel.Text = "五星装备格 + 五星魂珠格";
            statusLabel.Text = "已清空。";
        }

        private void SelectedFileChanged(object sender, EventArgs e)
        {
            ShowSelectedPreview();
        }

        private void ShowSelectedPreview()
        {
            if (fileList.SelectedItems.Count == 0)
            {
                gamePreview.SetImages(null, null);
                return;
            }

            IconWorkItem item = fileList.SelectedItems[0].Tag as IconWorkItem;
            if (item == null)
            {
                return;
            }

            Bitmap sourceForGame = null;
            Bitmap soulForGame = null;
            Bitmap loadedSource = null;
            try
            {
                loadedSource = SoulTransformer.LoadBitmapUnlocked(item.InputPath);
                sourcePreview.PreviewImage = loadedSource;
                loadedSource = null;
                sourcePathLabel.Text = item.InputPath;
                sourceForGame = new Bitmap(sourcePreview.PreviewImage);
            }
            catch
            {
                if (loadedSource != null)
                {
                    loadedSource.Dispose();
                }
                sourcePreview.PreviewImage = null;
                sourcePathLabel.Text = "源图片无法读取";
            }

            if (sourcePreview.PreviewImage != null
                && sourcePreview.PreviewImage.Width == SoulTransformer.RequiredWidth
                && sourcePreview.PreviewImage.Height == SoulTransformer.RequiredHeight)
            {
                try
                {
                    Bitmap result;
                    if (!string.IsNullOrEmpty(item.OutputPath) && File.Exists(item.OutputPath))
                    {
                        result = SoulTransformer.LoadBitmapUnlocked(item.OutputPath);
                        soulPathLabel.Text = item.OutputPath;
                    }
                    else
                    {
                        result = SoulTransformer.Convert(sourcePreview.PreviewImage);
                        soulPathLabel.Text = "实时预览（尚未保存）";
                    }

                    soulPreview.PreviewImage = result;
                    soulForGame = new Bitmap(soulPreview.PreviewImage);
                }
                catch
                {
                    soulPreview.PreviewImage = null;
                    soulPathLabel.Text = "魂珠预览生成失败";
                }
            }
            else
            {
                soulPreview.PreviewImage = null;
                soulPathLabel.Text = "需要 20×20 PNG";
            }

            bool validPreview = sourceForGame != null && soulForGame != null;
            if (!validPreview && sourceForGame != null)
            {
                sourceForGame.Dispose();
                sourceForGame = null;
            }

            gamePreview.SetImages(sourceForGame, soulForGame);
            gamePreviewLabel.Text = validPreview
                ? "客户端五星框 · 6× 最近邻"
                : "需要有效的 20×20 PNG";
        }

        private static void UpdateRow(IconWorkItem item)
        {
            item.Row.SubItems[1].Text = item.SizeText;
            item.Row.SubItems[2].Text = item.Status;
            item.Row.SubItems[3].Text = item.OutputPath ?? string.Empty;
        }

        private static string ShortMessage(string message)
        {
            if (string.IsNullOrWhiteSpace(message))
            {
                return "未知错误";
            }

            string firstLine = message.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries)[0];
            return firstLine.Length > 80 ? firstLine.Substring(0, 80) + "…" : firstLine;
        }

        private sealed class IconWorkItem
        {
            internal string InputPath;
            internal string OutputPath;
            internal string SizeText;
            internal string Status;
            internal ListViewItem Row;
        }
    }
}
