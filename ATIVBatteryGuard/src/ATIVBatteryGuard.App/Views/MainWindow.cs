using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Threading;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.ViewModels;

namespace ATIVBatteryGuard.Views
{
    public partial class MainWindow : Window
    {
        private const uint MonitorDefaultToNearest = 2;
        private const uint SwpNoZOrder = 0x0004;
        private const uint SwpNoActivate = 0x0010;
        private const int WmSettingChange = 0x001A;
        private const int WmDisplayChange = 0x007E;
        private const int WmEnterSizeMove = 0x0231;
        private const int WmExitSizeMove = 0x0232;
        private const int WmDpiChanged = 0x02E0;

        private HwndSource _windowSource;
        private IntPtr _windowHandle;
        private IntPtr _startupMonitor;
        private IntPtr _moveSizeMonitor;
        private bool _loaded;
        private bool _closed;
        private bool _fitQueued;
        private bool _inMoveSize;
        private bool _fitAfterMoveSize;

        public MainWindow()
        {
            InitializeComponent();
            Loaded += OnWindowLoaded;
        }

        protected override void OnSourceInitialized(EventArgs e)
        {
            base.OnSourceInitialized(e);
            _windowHandle = new WindowInteropHelper(this).Handle;
            _windowSource = HwndSource.FromHwnd(_windowHandle);
            if (_windowSource != null) _windowSource.AddHook(WindowMessageHook);

            NativePoint cursor;
            if (GetCursorPos(out cursor))
                _startupMonitor = MonitorFromPoint(cursor, MonitorDefaultToNearest);
            if (_startupMonitor == IntPtr.Zero)
                _startupMonitor = MonitorFromWindow(_windowHandle, MonitorDefaultToNearest);
            PlaceInitialWindow();
        }

        private void OnWindowLoaded(object sender, RoutedEventArgs e)
        {
            // WPF can finish applying its initial size after SourceInitialized. Place once
            // more after layout, with the actual DPI of the selected monitor.
            if (_loaded) return;
            _loaded = true;
            PlaceInitialWindow();
            _startupMonitor = IntPtr.Zero;
        }

        protected override void OnStateChanged(EventArgs e)
        {
            base.OnStateChanged(e);
            if (_loaded && WindowState == WindowState.Normal) QueueFitToCurrentMonitor();
        }

        protected override void OnClosed(EventArgs e)
        {
            _closed = true;
            if (_windowSource != null) _windowSource.RemoveHook(WindowMessageHook);
            Loaded -= OnWindowLoaded;
            base.OnClosed(e);
        }

        private void PlaceInitialWindow()
        {
            if (_windowHandle == IntPtr.Zero || WindowState != WindowState.Normal) return;
            IntPtr monitor = _startupMonitor != IntPtr.Zero ? _startupMonitor
                : MonitorFromWindow(_windowHandle, MonitorDefaultToNearest);
            WindowPixelBounds workArea;
            if (!TryGetWorkArea(monitor, out workArea)) return;

            if (MonitorFromWindow(_windowHandle, MonitorDefaultToNearest) != monitor)
            {
                // Move the still-opening HWND onto the selected monitor before asking for
                // its DPI. Global desktop origins must stay in physical pixels.
                MinWidth = MinHeight = 0;
                SetWindowPos(_windowHandle, IntPtr.Zero, workArea.Left, workArea.Top,
                    workArea.Width, workArea.Height, SwpNoZOrder | SwpNoActivate);
            }

            double scaleX, scaleY;
            GetCurrentDpiScale(out scaleX, out scaleY);
            UpdateMinimumSize(workArea, scaleX, scaleY);
            WindowPixelBounds bounds;
            if (WindowPlacementPolicy.TryCreateInitialBounds(workArea, scaleX, scaleY, out bounds))
                ApplyNativeBounds(bounds);
        }

        private IntPtr WindowMessageHook(IntPtr hwnd, int message, IntPtr wParam,
            IntPtr lParam, ref bool handled)
        {
            switch (message)
            {
                case WmEnterSizeMove:
                    _inMoveSize = true;
                    _moveSizeMonitor = MonitorFromWindow(hwnd, MonitorDefaultToNearest);
                    break;
                case WmExitSizeMove:
                    _inMoveSize = false;
                    // Equal-DPI monitor moves do not emit WM_DPICHANGED. Fit after an
                    // actual monitor transition, while leaving ordinary user resizing alone.
                    if (_fitAfterMoveSize || (_moveSizeMonitor != IntPtr.Zero
                        && MonitorFromWindow(hwnd, MonitorDefaultToNearest) != _moveSizeMonitor))
                    {
                        _fitAfterMoveSize = false;
                        QueueFitToCurrentMonitor();
                    }
                    _moveSizeMonitor = IntPtr.Zero;
                    break;
                case WmDpiChanged:
                case WmDisplayChange:
                case WmSettingChange:
                    // Let WPF/Windows process DPI suggested bounds and taskbar changes
                    // before fitting. This hook does not replace native message handling.
                    QueueFitToCurrentMonitor();
                    break;
            }
            return IntPtr.Zero;
        }

        private void QueueFitToCurrentMonitor()
        {
            if (_closed || _fitQueued || _windowHandle == IntPtr.Zero
                || Dispatcher.HasShutdownStarted) return;
            _fitQueued = true;
            Dispatcher.BeginInvoke(DispatcherPriority.ContextIdle, new Action(() =>
            {
                _fitQueued = false;
                if (_closed || !_loaded) return;
                if (_inMoveSize)
                {
                    // A DPI transition can arrive during a drag. Finish the user's move
                    // or resize before making a single correction for the new monitor.
                    _fitAfterMoveSize = true;
                    return;
                }
                FitToCurrentMonitor();
            }));
        }

        private void FitToCurrentMonitor()
        {
            // Maximization remains native. Re-fit only after an eventual normal restore;
            // never change WindowState or impose MaxWidth/MaxHeight.
            if (WindowState != WindowState.Normal || IsIconic(_windowHandle)
                || IsZoomed(_windowHandle)) return;
            WindowPixelBounds workArea;
            if (!TryGetWorkArea(MonitorFromWindow(_windowHandle, MonitorDefaultToNearest), out workArea)) return;

            double scaleX, scaleY;
            GetCurrentDpiScale(out scaleX, out scaleY);
            UpdateMinimumSize(workArea, scaleX, scaleY);
            WindowPixelBounds current;
            if (!TryGetWindowBounds(out current)) return;
            WindowPixelBounds fitted;
            if (WindowPlacementPolicy.TryFitBounds(current, workArea, out fitted))
                ApplyNativeBounds(fitted);
        }

        private void UpdateMinimumSize(WindowPixelBounds workArea, double scaleX, double scaleY)
        {
            double minimumWidth, minimumHeight;
            if (WindowPlacementPolicy.TryGetMinimumSizeDip(workArea, scaleX, scaleY,
                out minimumWidth, out minimumHeight))
            {
                MinWidth = minimumWidth;
                MinHeight = minimumHeight;
            }
        }

        private void GetCurrentDpiScale(out double scaleX, out double scaleY)
        {
            // GetDpiForWindow uses this HWND's awareness and current monitor. Early Windows
            // 10 releases do not export it, so retain the WPF device-transform fallback.
            try
            {
                uint dpi = GetDpiForWindow(_windowHandle);
                if (dpi != 0)
                {
                    scaleX = scaleY = dpi / 96.0;
                    return;
                }
            }
            catch (EntryPointNotFoundException) { }

            var target = _windowSource == null ? null : _windowSource.CompositionTarget;
            scaleX = target == null ? 1 : target.TransformToDevice.M11;
            scaleY = target == null ? 1 : target.TransformToDevice.M22;
        }

        private bool TryGetWindowBounds(out WindowPixelBounds bounds)
        {
            NativeRect rect;
            bounds = default(WindowPixelBounds);
            return GetWindowRect(_windowHandle, out rect) && TryConvertBounds(rect, out bounds);
        }

        private static bool TryGetWorkArea(IntPtr monitor, out WindowPixelBounds bounds)
        {
            bounds = default(WindowPixelBounds);
            if (monitor == IntPtr.Zero) return false;
            var info = new MonitorInfo { Size = Marshal.SizeOf(typeof(MonitorInfo)) };
            return GetMonitorInfo(monitor, ref info) && TryConvertBounds(info.WorkArea, out bounds);
        }

        private static bool TryConvertBounds(NativeRect rect, out WindowPixelBounds bounds)
        {
            bounds = default(WindowPixelBounds);
            long width = (long)rect.Right - rect.Left;
            long height = (long)rect.Bottom - rect.Top;
            if (width <= 0 || height <= 0 || width > int.MaxValue || height > int.MaxValue) return false;
            bounds = new WindowPixelBounds(rect.Left, rect.Top, (int)width, (int)height);
            return true;
        }

        private void ApplyNativeBounds(WindowPixelBounds bounds)
        {
            WindowPixelBounds current;
            if (TryGetWindowBounds(out current) && current.Left == bounds.Left
                && current.Top == bounds.Top && current.Width == bounds.Width
                && current.Height == bounds.Height) return;
            SetWindowPos(_windowHandle, IntPtr.Zero, bounds.Left, bounds.Top,
                bounds.Width, bounds.Height, SwpNoZOrder | SwpNoActivate);
        }

        protected override void OnClosing(CancelEventArgs e)
        {
            var viewModel = DataContext as MainViewModel;
            if (viewModel != null && viewModel.ManualProtectionBusy)
            {
                e.Cancel = true;
                viewModel.NotifyManualCloseBlocked();
            }
            base.OnClosing(e);
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct NativePoint
        {
            public int X;
            public int Y;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct NativeRect
        {
            public int Left;
            public int Top;
            public int Right;
            public int Bottom;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct MonitorInfo
        {
            public int Size;
            public NativeRect Monitor;
            public NativeRect WorkArea;
            public uint Flags;
        }

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GetCursorPos(out NativePoint point);

        [DllImport("user32.dll")]
        private static extern IntPtr MonitorFromPoint(NativePoint point, uint flags);

        [DllImport("user32.dll")]
        private static extern IntPtr MonitorFromWindow(IntPtr hwnd, uint flags);

        [DllImport("user32.dll", CharSet = CharSet.Auto)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GetMonitorInfo(IntPtr monitor, ref MonitorInfo info);

        [DllImport("user32.dll")]
        private static extern uint GetDpiForWindow(IntPtr hwnd);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GetWindowRect(IntPtr hwnd, out NativeRect rect);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool SetWindowPos(IntPtr hwnd, IntPtr insertAfter, int x, int y,
            int width, int height, uint flags);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool IsIconic(IntPtr hwnd);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool IsZoomed(IntPtr hwnd);
    }
}
