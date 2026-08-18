using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;

namespace SoulIconConverter
{
    internal static class SoulTransformer
    {
        internal const int RequiredWidth = 20;
        internal const int RequiredHeight = 20;

        internal static Bitmap Convert(Bitmap source)
        {
            if (source == null)
            {
                throw new ArgumentNullException("source");
            }

            if (source.Width != RequiredWidth || source.Height != RequiredHeight)
            {
                throw new InvalidDataException(
                    string.Format("图片必须是 20×20 像素，当前为 {0}×{1}。", source.Width, source.Height));
            }

            Bitmap result = new Bitmap(RequiredWidth, RequiredHeight, PixelFormat.Format32bppArgb);
            for (int y = 0; y < RequiredHeight; y++)
            {
                for (int x = 0; x < RequiredWidth; x++)
                {
                    Color input = source.GetPixel(x, y);
                    if (input.A == 0)
                    {
                        result.SetPixel(x, y, Color.FromArgb(0, 0, 0, 0));
                        continue;
                    }

                    int coordinate = y * RequiredWidth + x;
                    int red = Predict(coordinate, 0, input);
                    int green = Predict(coordinate, 1, input);
                    int blue = Predict(coordinate, 2, input);
                    result.SetPixel(x, y, Color.FromArgb(input.A, red, green, blue));
                }
            }

            return result;
        }

        internal static string ConvertFile(string inputPath, string outputPath)
        {
            if (string.IsNullOrWhiteSpace(inputPath))
            {
                throw new ArgumentException("没有提供输入图片。", "inputPath");
            }

            if (!File.Exists(inputPath))
            {
                throw new FileNotFoundException("找不到输入图片。", inputPath);
            }

            string extension = Path.GetExtension(inputPath);
            if (!string.Equals(extension, ".png", StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException("只支持 PNG 图片。");
            }

            string outputDirectory = Path.GetDirectoryName(outputPath);
            if (!string.IsNullOrEmpty(outputDirectory))
            {
                Directory.CreateDirectory(outputDirectory);
            }

            using (Bitmap source = LoadBitmapUnlocked(inputPath))
            using (Bitmap result = Convert(source))
            {
                result.Save(outputPath, ImageFormat.Png);
            }

            return outputPath;
        }

        internal static Bitmap LoadBitmapUnlocked(string path)
        {
            using (FileStream stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (Image image = Image.FromStream(stream, true, true))
            {
                return new Bitmap(image);
            }
        }

        private static int Predict(int coordinate, int channel, Color input)
        {
            double value =
                SoulColorModel.Coordinate[coordinate, channel, 0] * input.R
                + SoulColorModel.Coordinate[coordinate, channel, 1] * input.G
                + SoulColorModel.Coordinate[coordinate, channel, 2] * input.B
                + SoulColorModel.Coordinate[coordinate, channel, 3];

            int rounded = (int)Math.Floor(value + 0.5d);
            if (rounded < 0)
            {
                return 0;
            }

            return rounded > 255 ? 255 : rounded;
        }
    }
}
