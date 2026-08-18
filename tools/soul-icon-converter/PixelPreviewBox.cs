using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace SoulIconConverter
{
    internal sealed class PixelPreviewBox : Control
    {
        private Bitmap previewImage;

        internal PixelPreviewBox()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint, true);
            SetStyle(ControlStyles.OptimizedDoubleBuffer, true);
            SetStyle(ControlStyles.ResizeRedraw, true);
            SetStyle(ControlStyles.UserPaint, true);
            BackColor = Color.FromArgb(28, 31, 39);
        }

        internal Bitmap PreviewImage
        {
            get { return previewImage; }
            set
            {
                if (ReferenceEquals(previewImage, value))
                {
                    return;
                }

                if (previewImage != null)
                {
                    previewImage.Dispose();
                }

                previewImage = value;
                Invalidate();
            }
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing && previewImage != null)
            {
                previewImage.Dispose();
                previewImage = null;
            }

            base.Dispose(disposing);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            Rectangle area = ClientRectangle;
            if (area.Width <= 0 || area.Height <= 0)
            {
                return;
            }

            const int cell = 14;
            Color light = Color.FromArgb(68, 72, 82);
            Color dark = Color.FromArgb(48, 52, 62);
            using (SolidBrush lightBrush = new SolidBrush(light))
            using (SolidBrush darkBrush = new SolidBrush(dark))
            {
                for (int y = 0; y < area.Height; y += cell)
                {
                    for (int x = 0; x < area.Width; x += cell)
                    {
                        Brush brush = (((x / cell) + (y / cell)) & 1) == 0 ? lightBrush : darkBrush;
                        e.Graphics.FillRectangle(brush, x, y, cell, cell);
                    }
                }
            }

            if (previewImage == null)
            {
                const string message = "拖入或选择 20×20 PNG";
                using (Font font = new Font("Microsoft YaHei UI", 12.0f, FontStyle.Regular))
                using (SolidBrush brush = new SolidBrush(Color.FromArgb(210, 220, 232)))
                {
                    SizeF size = e.Graphics.MeasureString(message, font);
                    e.Graphics.DrawString(message, font, brush,
                        (area.Width - size.Width) / 2.0f,
                        (area.Height - size.Height) / 2.0f);
                }
                return;
            }

            int margin = 18;
            int side = Math.Min(area.Width - margin * 2, area.Height - margin * 2);
            if (side <= 0)
            {
                return;
            }

            side -= side % 20;
            Rectangle destination = new Rectangle(
                (area.Width - side) / 2,
                (area.Height - side) / 2,
                side,
                side);

            e.Graphics.InterpolationMode = InterpolationMode.NearestNeighbor;
            e.Graphics.PixelOffsetMode = PixelOffsetMode.Half;
            e.Graphics.CompositingMode = CompositingMode.SourceOver;
            e.Graphics.DrawImage(previewImage, destination, 0, 0,
                previewImage.Width, previewImage.Height, GraphicsUnit.Pixel);

            using (Pen border = new Pen(Color.FromArgb(145, 156, 178), 1.0f))
            {
                e.Graphics.DrawRectangle(border, destination.X, destination.Y,
                    destination.Width - 1, destination.Height - 1);
            }
        }
    }
}
