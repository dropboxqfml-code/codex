using System;

namespace ATIVBatteryGuard.Core.Services
{
    /// <summary>Outer window or monitor work-area bounds, entirely in desktop physical pixels.</summary>
    public struct WindowPixelBounds
    {
        public WindowPixelBounds(int left, int top, int width, int height)
        {
            Left = left;
            Top = top;
            Width = width;
            Height = height;
        }

        public int Left { get; private set; }
        public int Top { get; private set; }
        public int Width { get; private set; }
        public int Height { get; private set; }
    }

    /// <summary>
    /// Pure placement arithmetic. Desktop origins are never scaled: only DIP sizes are
    /// converted with the current window's per-monitor scale before fitting pixel bounds.
    /// </summary>
    public static class WindowPlacementPolicy
    {
        public const double DefaultWidthDip = 750;
        public const double DefaultHeightDip = 565;
        public const double MinimumWidthDip = 480;
        public const double MinimumHeightDip = 320;

        public static bool TryCreateInitialBounds(WindowPixelBounds workArea,
            double dpiScaleX, double dpiScaleY, out WindowPixelBounds bounds)
        {
            bounds = default(WindowPixelBounds);
            if (!IsValid(workArea) || !IsValidScale(dpiScaleX) || !IsValidScale(dpiScaleY))
                return false;

            int width = ToClippedPixels(DefaultWidthDip, dpiScaleX, workArea.Width);
            int height = ToClippedPixels(DefaultHeightDip, dpiScaleY, workArea.Height);
            bounds = new WindowPixelBounds(workArea.Left + (workArea.Width - width) / 2,
                workArea.Top + (workArea.Height - height) / 2, width, height);
            return true;
        }

        public static bool TryFitBounds(WindowPixelBounds windowBounds,
            WindowPixelBounds workArea, out WindowPixelBounds bounds)
        {
            bounds = default(WindowPixelBounds);
            if (!IsValid(windowBounds) || !IsValid(workArea)) return false;

            int width = Math.Min(windowBounds.Width, workArea.Width);
            int height = Math.Min(windowBounds.Height, workArea.Height);
            // Validate rectangle edges with long arithmetic before calculating these limits.
            int rightmostLeft = (int)((long)workArea.Left + workArea.Width - width);
            int bottommostTop = (int)((long)workArea.Top + workArea.Height - height);
            int left = Math.Max(workArea.Left, Math.Min(windowBounds.Left, rightmostLeft));
            int top = Math.Max(workArea.Top, Math.Min(windowBounds.Top, bottommostTop));
            bounds = new WindowPixelBounds(left, top, width, height);
            return true;
        }

        public static bool TryGetMinimumSizeDip(WindowPixelBounds workArea,
            double dpiScaleX, double dpiScaleY, out double width, out double height)
        {
            width = height = 0;
            if (!IsValid(workArea) || !IsValidScale(dpiScaleX) || !IsValidScale(dpiScaleY))
                return false;

            width = Math.Min(MinimumWidthDip, workArea.Width / dpiScaleX);
            height = Math.Min(MinimumHeightDip, workArea.Height / dpiScaleY);
            return true;
        }

        private static int ToClippedPixels(double dip, double scale, int available)
        {
            // Clip before converting to int, including when dip * scale overflows double.
            return Math.Max(1, (int)Math.Round(Math.Min(dip * scale, available),
                MidpointRounding.AwayFromZero));
        }

        private static bool IsValidScale(double scale)
        {
            return scale > 0 && !double.IsNaN(scale) && !double.IsInfinity(scale);
        }

        private static bool IsValid(WindowPixelBounds bounds)
        {
            return bounds.Width > 0 && bounds.Height > 0
                && (long)bounds.Left + bounds.Width <= int.MaxValue
                && (long)bounds.Top + bounds.Height <= int.MaxValue;
        }
    }
}
