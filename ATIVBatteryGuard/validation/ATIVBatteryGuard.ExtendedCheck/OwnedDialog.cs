using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Threading;
using ATIVBatteryGuard.Services;

namespace ATIVBatteryGuard.ExtendedValidation
{
    internal static class OwnedDialog
    {
        private delegate bool EnumWindow(IntPtr handle, IntPtr unused);
        [DllImport("user32.dll")] private static extern bool EnumThreadWindows(uint thread, EnumWindow callback, IntPtr unused);
        [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
        [DllImport("user32.dll")] private static extern IntPtr GetWindow(IntPtr window, uint command);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassName(IntPtr window, StringBuilder name, int size);
        [DllImport("user32.dll")] private static extern IntPtr GetDlgItem(IntPtr dialog, int id);
        [DllImport("user32.dll")] private static extern IntPtr SendMessage(IntPtr window, uint message, IntPtr wparam, IntPtr lparam);
        [DllImport("user32.dll")] private static extern bool IsWindowEnabled(IntPtr window);
        [DllImport("user32.dll")] private static extern IntPtr SetActiveWindow(IntPtr window);

        public static ObservationLossChoice Choose(Func<ObservationLossChoice> show, ObservationLossChoice choice)
        {
            var owner = new WindowInteropHelper(Application.Current.MainWindow).Handle;
            if (owner == IntPtr.Zero) throw new InvalidOperationException();
            uint thread = GetCurrentThreadId();
            var watch = Stopwatch.StartNew(); bool clicked = false;
            int id = choice == ObservationLossChoice.Save ? 6 : choice == ObservationLossChoice.Discard ? 7 : 2;
            var timer = new DispatcherTimer(DispatcherPriority.Send) { Interval = TimeSpan.FromMilliseconds(75) };
            timer.Tick += (sender, args) => {
                EnumThreadWindows(thread, (handle, ignored) => {
                    var name = new StringBuilder(32);
                    GetClassName(handle, name, name.Capacity);
                    if (name.ToString() != "#32770" || GetWindow(handle, 4) != owner) return true;
                    // Fail safely if the requested button was unavailable: cancel only our
                    // own modal dialog after five seconds, never accept another dialog.
                    int buttonId = watch.Elapsed.TotalSeconds > 5 ? 2 : id;
                    IntPtr button = GetDlgItem(handle, buttonId);
                    if (button == IntPtr.Zero || !IsWindowEnabled(button)) return true;
                    clicked = buttonId == id;
                    SetActiveWindow(handle);
                    SendMessage(button, 0x00F5, IntPtr.Zero, IntPtr.Zero); // BM_CLICK
                    return false;
                }, IntPtr.Zero);
            };
            timer.Start();
            try
            {
                var result = show();
                if (!clicked || result != choice) throw new InvalidOperationException();
                return result;
            }
            finally { timer.Stop(); }
        }
    }
}
