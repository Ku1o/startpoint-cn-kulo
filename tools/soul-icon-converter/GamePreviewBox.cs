using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Windows.Forms;

namespace SoulIconConverter
{
    internal sealed class GamePreviewBox : Control
    {
        private readonly Bitmap equipmentBackground;
        private readonly Bitmap soulBackground;
        private Bitmap sourceImage;
        private Bitmap soulImage;

        internal GamePreviewBox()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint, true);
            SetStyle(ControlStyles.OptimizedDoubleBuffer, true);
            SetStyle(ControlStyles.ResizeRedraw, true);
            SetStyle(ControlStyles.UserPaint, true);
            BackColor = Color.FromArgb(28, 31, 39);

            using (Bitmap outer = LoadEmbeddedPng(GamePreviewAssets.OuterFramePngBase64))
            using (Bitmap rarity = LoadEmbeddedPng(GamePreviewAssets.RarityFivePngBase64))
            using (Bitmap soulInner = LoadEmbeddedPng(GamePreviewAssets.SoulInnerFramePngBase64))
            {
                equipmentBackground = BuildBackground(outer, rarity, null);
                soulBackground = BuildBackground(outer, rarity, soulInner);
            }
        }

        internal void SetImages(Bitmap source, Bitmap soul)
        {
            if (sourceImage != null)
            {
                sourceImage.Dispose();
            }

            if (soulImage != null)
            {
                soulImage.Dispose();
            }

            sourceImage = source;
            soulImage = soul;
            Invalidate();
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                if (sourceImage != null)
                {
                    sourceImage.Dispose();
                    sourceImage = null;
                }

                if (soulImage != null)
                {
                    soulImage.Dispose();
                    soulImage = null;
                }

                equipmentBackground.Dispose();
                soulBackground.Dispose();
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

            DrawBackdrop(e.Graphics, area);
            if (sourceImage == null)
            {
                DrawCenteredMessage(e.Graphics, area,
                    "选择 20×20 PNG 后显示\r\n五星装备格与五星魂珠格");
                return;
            }

            float dpiScale = Math.Max(1.0f, e.Graphics.DpiX / 96.0f);
            int gap = (int)Math.Round(8.0f * dpiScale);
            int labelHeight = (int)Math.Round(22.0f * dpiScale);
            int footerHeight = (int)Math.Round(24.0f * dpiScale);
            int desiredSide = (int)Math.Round(168.0f * dpiScale);
            int sideByWidth = (area.Width - gap * 3) / 2;
            int sideByHeight = area.Height - labelHeight - footerHeight - gap * 2;
            int side = Math.Min(desiredSide, Math.Min(sideByWidth, sideByHeight));
            if (side < 72)
            {
                DrawCenteredMessage(e.Graphics, area, "请适当放大窗口以显示游戏预览");
                return;
            }

            int contentWidth = side * 2 + gap;
            int contentHeight = labelHeight + side + footerHeight + gap * 2;
            int startX = area.Left + (area.Width - contentWidth) / 2;
            int startY = area.Top + Math.Max(gap, (area.Height - contentHeight) / 2);
            Rectangle sourceTile = new Rectangle(startX, startY + labelHeight, side, side);
            Rectangle soulTile = new Rectangle(startX + side + gap, startY + labelHeight, side, side);

            using (Font labelFont = new Font("Microsoft YaHei UI", 8.5f, FontStyle.Bold))
            using (Font noteFont = new Font("Microsoft YaHei UI", 8.0f, FontStyle.Regular))
            using (SolidBrush labelBrush = new SolidBrush(Color.FromArgb(226, 234, 244)))
            using (SolidBrush noteBrush = new SolidBrush(Color.FromArgb(151, 169, 193)))
            {
                DrawCenteredText(e.Graphics, "原装备", labelFont, labelBrush,
                    new Rectangle(sourceTile.X, startY, side, labelHeight));
                DrawCenteredText(e.Graphics, "魂珠结果", labelFont, labelBrush,
                    new Rectangle(soulTile.X, startY, side, labelHeight));

                DrawTile(e.Graphics, sourceTile, equipmentBackground, sourceImage);
                DrawTile(e.Graphics, soulTile, soulBackground, soulImage);

                Rectangle footer = new Rectangle(
                    startX,
                    sourceTile.Bottom + gap,
                    contentWidth,
                    footerHeight);
                DrawCenteredText(e.Graphics, "客户端五星框 · 图标 6× 最近邻", noteFont, noteBrush, footer);
            }
        }

        private static Bitmap LoadEmbeddedPng(string base64)
        {
            byte[] bytes = Convert.FromBase64String(base64);
            using (MemoryStream stream = new MemoryStream(bytes, false))
            using (Image image = Image.FromStream(stream, true, true))
            {
                return new Bitmap(image);
            }
        }

        private static Bitmap BuildBackground(Bitmap outer, Bitmap rarity, Bitmap soulInner)
        {
            Bitmap result = new Bitmap(168, 168, System.Drawing.Imaging.PixelFormat.Format32bppArgb);
            using (Graphics graphics = Graphics.FromImage(result))
            {
                graphics.Clear(Color.Transparent);
                graphics.CompositingMode = CompositingMode.SourceOver;
                graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
                graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;

                DrawNineSlice(graphics, outer, new Rectangle(0, 0, 168, 168),
                    new[] { 0, 16, 25, 40 }, new[] { 0, 15, 26, 40 });
                graphics.DrawImage(rarity, new Rectangle(12, 12, 144, 144),
                    0, 0, rarity.Width, rarity.Height, GraphicsUnit.Pixel);

                if (soulInner != null)
                {
                    DrawNineSlice(graphics, soulInner, new Rectangle(12, 12, 144, 144),
                        new[] { 0, 19, 22, 40 }, new[] { 0, 20, 22, 40 });
                }
            }

            return result;
        }

        private static void DrawNineSlice(
            Graphics graphics,
            Image image,
            Rectangle destination,
            int[] cutsX,
            int[] cutsY)
        {
            int[] destinationX =
            {
                destination.Left,
                destination.Left + cutsX[1],
                destination.Right - (cutsX[3] - cutsX[2]),
                destination.Right,
            };
            int[] destinationY =
            {
                destination.Top,
                destination.Top + cutsY[1],
                destination.Bottom - (cutsY[3] - cutsY[2]),
                destination.Bottom,
            };

            for (int row = 0; row < 3; row++)
            {
                for (int column = 0; column < 3; column++)
                {
                    Rectangle source = Rectangle.FromLTRB(
                        cutsX[column], cutsY[row], cutsX[column + 1], cutsY[row + 1]);
                    Rectangle target = Rectangle.FromLTRB(
                        destinationX[column], destinationY[row],
                        destinationX[column + 1], destinationY[row + 1]);
                    graphics.DrawImage(image, target, source, GraphicsUnit.Pixel);
                }
            }
        }

        private static void DrawTile(Graphics graphics, Rectangle tile, Bitmap background, Bitmap icon)
        {
            graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
            graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;
            graphics.DrawImage(background, tile, 0, 0, 168, 168, GraphicsUnit.Pixel);

            if (icon != null)
            {
                int offset = (int)Math.Round(tile.Width * 24.0 / 168.0);
                int iconSide = (int)Math.Round(tile.Width * 120.0 / 168.0);
                Rectangle iconDestination = new Rectangle(
                    tile.X + offset,
                    tile.Y + offset,
                    iconSide,
                    iconSide);
                graphics.InterpolationMode = InterpolationMode.NearestNeighbor;
                graphics.PixelOffsetMode = PixelOffsetMode.Half;
                graphics.DrawImage(icon, iconDestination,
                    0, 0, icon.Width, icon.Height, GraphicsUnit.Pixel);
            }

            using (Pen border = new Pen(Color.FromArgb(88, 112, 139), 1.0f))
            {
                graphics.DrawRectangle(border, tile.X, tile.Y, tile.Width - 1, tile.Height - 1);
            }
        }

        private static void DrawBackdrop(Graphics graphics, Rectangle area)
        {
            graphics.Clear(Color.FromArgb(24, 28, 36));
            const int cell = 18;
            using (SolidBrush brush = new SolidBrush(Color.FromArgb(8, 255, 255, 255)))
            {
                for (int y = -area.Height; y < area.Height * 2; y += cell * 2)
                {
                    graphics.FillRectangle(brush, 0, y, area.Width, 1);
                }
            }
        }

        private static void DrawCenteredMessage(Graphics graphics, Rectangle area, string message)
        {
            using (Font font = new Font("Microsoft YaHei UI", 11.0f, FontStyle.Regular))
            using (SolidBrush brush = new SolidBrush(Color.FromArgb(202, 214, 230)))
            {
                StringFormat format = new StringFormat();
                format.Alignment = StringAlignment.Center;
                format.LineAlignment = StringAlignment.Center;
                graphics.DrawString(message, font, brush, area, format);
                format.Dispose();
            }
        }

        private static void DrawCenteredText(
            Graphics graphics,
            string text,
            Font font,
            Brush brush,
            Rectangle area)
        {
            using (StringFormat format = new StringFormat())
            {
                format.Alignment = StringAlignment.Center;
                format.LineAlignment = StringAlignment.Center;
                format.Trimming = StringTrimming.EllipsisCharacter;
                format.FormatFlags = StringFormatFlags.NoWrap;
                graphics.DrawString(text, font, brush, area, format);
            }
        }
    }
}
