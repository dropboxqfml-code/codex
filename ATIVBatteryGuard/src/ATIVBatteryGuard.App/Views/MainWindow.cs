using System.ComponentModel;
using System.Windows;
using ATIVBatteryGuard.ViewModels;

namespace ATIVBatteryGuard.Views
{
    public partial class MainWindow : Window
    {
        public MainWindow()
        {
            InitializeComponent();
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
    }
}
