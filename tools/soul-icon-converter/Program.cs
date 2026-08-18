using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Windows.Forms;

namespace SoulIconConverter
{
    internal static class Program
    {
        [STAThread]
        private static int Main(string[] args)
        {
            if (args.Length == 3 && string.Equals(args[0], "--convert", StringComparison.OrdinalIgnoreCase))
            {
                try
                {
                    SoulTransformer.ConvertFile(args[1], args[2]);
                    return 0;
                }
                catch (Exception exception)
                {
                    try
                    {
                        File.WriteAllText(args[2] + ".error.txt", exception.ToString());
                    }
                    catch
                    {
                    }
                    return 1;
                }
            }

            if ((args.Length == 2 || args.Length == 3)
                && string.Equals(args[0], "--screenshot", StringComparison.OrdinalIgnoreCase))
            {
                try
                {
                    Application.EnableVisualStyles();
                    Application.SetCompatibleTextRenderingDefault(false);
                    string[] startupPaths = args.Length == 3
                        ? new[] { args[2] }
                        : new string[0];
                    using (MainForm form = new MainForm(startupPaths))
                    {
                        form.StartPosition = FormStartPosition.Manual;
                        form.Location = new Point(-32000, -32000);
                        form.ShowInTaskbar = false;
                        form.Show();
                        Application.DoEvents();
                        using (Bitmap screenshot = new Bitmap(form.Width, form.Height, PixelFormat.Format32bppArgb))
                        {
                            form.DrawToBitmap(screenshot, new Rectangle(0, 0, screenshot.Width, screenshot.Height));
                            string directory = Path.GetDirectoryName(args[1]);
                            if (!string.IsNullOrEmpty(directory))
                            {
                                Directory.CreateDirectory(directory);
                            }
                            screenshot.Save(args[1], ImageFormat.Png);
                        }
                        form.Close();
                    }
                    return 0;
                }
                catch (Exception exception)
                {
                    try
                    {
                        File.WriteAllText(args[1] + ".error.txt", exception.ToString());
                    }
                    catch
                    {
                    }
                    return 1;
                }
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm(args));
            return 0;
        }
    }
}
