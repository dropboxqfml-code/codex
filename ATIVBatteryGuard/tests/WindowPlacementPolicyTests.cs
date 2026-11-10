using System;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWindowPlacementPolicyTests()
    {
        Add("compact startup fits the 1280 by 688 logical work area", () =>
        {
            WindowPixelBounds bounds;
            Check(WindowPlacementPolicy.TryCreateInitialBounds(new WindowPixelBounds(0, 0, 1280, 688),
                1, 1, out bounds), "logical-equivalent placement rejected");
            EqualWindowBounds(265, 61, 750, 565, bounds);
        });
        Add("250 percent startup keeps the complete outer window inside 3200 by 1720 pixels", () =>
        {
            var workArea = new WindowPixelBounds(0, 0, 3200, 1720);
            WindowPixelBounds bounds;
            Check(WindowPlacementPolicy.TryCreateInitialBounds(workArea, 2.5, 2.5, out bounds),
                "actual high-DPI work area rejected");
            EqualWindowBounds(662, 153, 1875, 1413, bounds);
            CheckWindowContained(bounds, workArea);
            Check(bounds.Width / 2.5 / 1120 > 0.66 && bounds.Width / 2.5 / 1120 < 0.68,
                "startup width is not about two thirds of the previous window");
            Check(bounds.Height / 2.5 / 850 > 0.66 && bounds.Height / 2.5 / 850 < 0.68,
                "startup height is not about two thirds of the previous window");
        });
        Add("startup preserves negative monitor origins while scaling sizes", () =>
        {
            var workArea = new WindowPixelBounds(-1920, -1080, 1920, 1040);
            WindowPixelBounds bounds;
            Check(WindowPlacementPolicy.TryCreateInitialBounds(workArea, 1.25, 1.25, out bounds),
                "negative-origin monitor rejected");
            EqualWindowBounds(-1429, -913, 938, 706, bounds);
            CheckWindowContained(bounds, workArea);
        });
        Add("startup centers inside taskbar-adjusted work area instead of desktop origin", () =>
        {
            var workArea = new WindowPixelBounds(48, 72, 1552, 828);
            WindowPixelBounds bounds;
            Check(WindowPlacementPolicy.TryCreateInitialBounds(workArea, 1, 1, out bounds),
                "offset work area rejected");
            EqualWindowBounds(449, 203, 750, 565, bounds);
            CheckWindowContained(bounds, workArea);
        });
        Add("tiny work areas override preferred startup size and nominal minimum", () =>
        {
            var workArea = new WindowPixelBounds(12, 34, 280, 190);
            WindowPixelBounds bounds;
            double minimumWidth, minimumHeight;
            Check(WindowPlacementPolicy.TryCreateInitialBounds(workArea, 2.5, 2.5, out bounds),
                "tiny work area rejected");
            EqualWindowBounds(12, 34, 280, 190, bounds);
            Check(WindowPlacementPolicy.TryGetMinimumSizeDip(workArea, 2.5, 2.5,
                out minimumWidth, out minimumHeight), "tiny minimum rejected");
            Equal(112.0, minimumWidth);
            Equal(76.0, minimumHeight);
        });
        Add("minimum sizes adapt independently to monitor dimensions and scale", () =>
        {
            double width, height;
            Check(WindowPlacementPolicy.TryGetMinimumSizeDip(new WindowPixelBounds(0, 0, 1200, 900),
                2.5, 2.5, out width, out height), "normal minimum rejected");
            Equal(480.0, width);
            Equal(320.0, height);
            Check(WindowPlacementPolicy.TryGetMinimumSizeDip(new WindowPixelBounds(0, 0, 900, 600),
                2.5, 2.5, out width, out height), "small minimum rejected");
            Equal(360.0, width);
            Equal(240.0, height);
            Check(WindowPlacementPolicy.TryGetMinimumSizeDip(new WindowPixelBounds(0, 0, 900, 600),
                1.25, 2.5, out width, out height), "independent scales rejected");
            Equal(480.0, width);
            Equal(240.0, height);
        });
        Add("a DPI or display change shrinks oversized old bounds to the current work area", () =>
        {
            var workArea = new WindowPixelBounds(0, 0, 1280, 688);
            WindowPixelBounds bounds;
            Check(WindowPlacementPolicy.TryFitBounds(new WindowPixelBounds(-100, -200, 2800, 2125),
                workArea, out bounds), "oversized old window rejected");
            EqualWindowBounds(0, 0, 1280, 688, bounds);
            CheckWindowContained(bounds, workArea);
        });
        Add("fitting onto a negative-origin monitor keeps all native caption edges reachable", () =>
        {
            var workArea = new WindowPixelBounds(-1920, 0, 1920, 1040);
            WindowPixelBounds bounds;
            Check(WindowPlacementPolicy.TryFitBounds(new WindowPixelBounds(2300, 80, 1875, 1413),
                workArea, out bounds), "cross-monitor bounds rejected");
            EqualWindowBounds(-1875, 0, 1875, 1040, bounds);
            CheckWindowContained(bounds, workArea);
        });
        Add("offscreen bottom and right edges are moved without changing fitting dimensions", () =>
        {
            var workArea = new WindowPixelBounds(0, 0, 1920, 1040);
            WindowPixelBounds bounds;
            Check(WindowPlacementPolicy.TryFitBounds(new WindowPixelBounds(1800, 1000, 750, 565),
                workArea, out bounds), "offscreen bounds rejected");
            EqualWindowBounds(1170, 475, 750, 565, bounds);
            CheckWindowContained(bounds, workArea);
        });
        Add("an offscreen title bar is moved below the work-area top", () =>
        {
            WindowPixelBounds bounds;
            Check(WindowPlacementPolicy.TryFitBounds(new WindowPixelBounds(500, -100, 750, 565),
                new WindowPixelBounds(0, 40, 1920, 1000), out bounds), "title-bar recovery rejected");
            EqualWindowBounds(500, 40, 750, 565, bounds);
        });
        Add("fitting preserves a valid manually positioned and resized window", () =>
        {
            WindowPixelBounds bounds;
            Check(WindowPlacementPolicy.TryFitBounds(new WindowPixelBounds(840, 360, 510, 335),
                new WindowPixelBounds(0, 0, 1920, 1040), out bounds), "user-sized window rejected");
            EqualWindowBounds(840, 360, 510, 335, bounds);
        });
        Add("fitting is idempotent for ordinary negative and tiny monitor work areas", () =>
        {
            foreach (var workArea in new[] {
                new WindowPixelBounds(0, 0, 3200, 1720),
                new WindowPixelBounds(-1920, -1080, 1920, 1040),
                new WindowPixelBounds(12, 34, 280, 190) })
            {
                WindowPixelBounds once, twice;
                Check(WindowPlacementPolicy.TryFitBounds(new WindowPixelBounds(-400, -500, 2800, 2125),
                    workArea, out once), "first fit rejected");
                Check(WindowPlacementPolicy.TryFitBounds(once, workArea, out twice), "second fit rejected");
                EqualWindowBounds(once.Left, once.Top, once.Width, once.Height, twice);
                CheckWindowContained(twice, workArea);
            }
        });
        Add("invalid DPI scales are rejected with empty outputs", () =>
        {
            var workArea = new WindowPixelBounds(0, 0, 3200, 1720);
            foreach (double scale in new[] { 0.0, -1.0, double.NaN, double.PositiveInfinity, double.NegativeInfinity })
            {
                WindowPixelBounds bounds;
                double width, height;
                Check(!WindowPlacementPolicy.TryCreateInitialBounds(workArea, scale, 2.5, out bounds),
                    "invalid horizontal scale accepted");
                EqualWindowBounds(0, 0, 0, 0, bounds);
                Check(!WindowPlacementPolicy.TryCreateInitialBounds(workArea, 2.5, scale, out bounds),
                    "invalid vertical scale accepted");
                EqualWindowBounds(0, 0, 0, 0, bounds);
                Check(!WindowPlacementPolicy.TryGetMinimumSizeDip(workArea, scale, 2.5, out width, out height),
                    "invalid horizontal minimum scale accepted");
                Equal(0.0, width); Equal(0.0, height);
                Check(!WindowPlacementPolicy.TryGetMinimumSizeDip(workArea, 2.5, scale, out width, out height),
                    "invalid vertical minimum scale accepted");
                Equal(0.0, width); Equal(0.0, height);
            }
        });
        Add("empty negative and overflowing rectangles are rejected with empty outputs", () =>
        {
            var valid = new WindowPixelBounds(0, 0, 1280, 688);
            foreach (var invalid in new[] {
                default(WindowPixelBounds), new WindowPixelBounds(0, 0, 0, 100),
                new WindowPixelBounds(0, 0, 100, 0), new WindowPixelBounds(0, 0, -1, 100),
                new WindowPixelBounds(0, 0, 100, -1), new WindowPixelBounds(int.MaxValue, 0, 1, 100),
                new WindowPixelBounds(0, int.MaxValue, 100, 1) })
            {
                WindowPixelBounds bounds;
                double width, height;
                Check(!WindowPlacementPolicy.TryCreateInitialBounds(invalid, 1, 1, out bounds),
                    "invalid initial work area accepted");
                EqualWindowBounds(0, 0, 0, 0, bounds);
                Check(!WindowPlacementPolicy.TryFitBounds(valid, invalid, out bounds),
                    "invalid fit work area accepted");
                EqualWindowBounds(0, 0, 0, 0, bounds);
                Check(!WindowPlacementPolicy.TryFitBounds(invalid, valid, out bounds),
                    "invalid current bounds accepted");
                EqualWindowBounds(0, 0, 0, 0, bounds);
                Check(!WindowPlacementPolicy.TryGetMinimumSizeDip(invalid, 1, 1, out width, out height),
                    "invalid minimum work area accepted");
                Equal(0.0, width); Equal(0.0, height);
            }
        });
        Add("extreme valid desktop coordinates do not overflow centering or fitting", () =>
        {
            foreach (var workArea in new[] {
                new WindowPixelBounds(int.MinValue, int.MinValue, int.MaxValue, int.MaxValue),
                new WindowPixelBounds(int.MaxValue - 1280, int.MaxValue - 688, 1280, 688) })
            {
                WindowPixelBounds initial, fitted;
                Check(WindowPlacementPolicy.TryCreateInitialBounds(workArea, 2.5, 2.5, out initial),
                    "valid extreme work area rejected");
                CheckWindowContained(initial, workArea);
                Check(WindowPlacementPolicy.TryFitBounds(new WindowPixelBounds(0, 0, 1875, 1413),
                    workArea, out fitted), "extreme coordinate fit rejected");
                CheckWindowContained(fitted, workArea);
            }
        });
        Add("extreme finite scales clip safely and one-pixel work areas remain valid", () =>
        {
            WindowPixelBounds bounds;
            Check(WindowPlacementPolicy.TryCreateInitialBounds(new WindowPixelBounds(-1, -1, 1, 1),
                double.MaxValue, double.MaxValue, out bounds), "finite huge scale overflowed");
            EqualWindowBounds(-1, -1, 1, 1, bounds);
            Check(WindowPlacementPolicy.TryCreateInitialBounds(new WindowPixelBounds(0, 0, 1280, 688),
                double.Epsilon, double.Epsilon, out bounds), "positive tiny scale rejected");
            EqualWindowBounds(639, 343, 1, 1, bounds);
        });
    }

    private static void EqualWindowBounds(int left, int top, int width, int height, WindowPixelBounds actual)
    {
        Equal(left, actual.Left); Equal(top, actual.Top);
        Equal(width, actual.Width); Equal(height, actual.Height);
    }

    private static void CheckWindowContained(WindowPixelBounds window, WindowPixelBounds workArea)
    {
        Check(window.Width > 0 && window.Height > 0, "window dimensions are not positive");
        Check(window.Left >= workArea.Left && window.Top >= workArea.Top,
            "window starts above or to the left of the work area");
        Check((long)window.Left + window.Width <= (long)workArea.Left + workArea.Width,
            "window right edge is outside the work area");
        Check((long)window.Top + window.Height <= (long)workArea.Top + workArea.Height,
            "window bottom edge is outside the work area");
    }
}
