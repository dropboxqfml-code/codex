using System;
using System.Windows.Input;

namespace ATIVBatteryGuard.ViewModels
{
	public sealed class RelayCommand : ICommand
	{
		private readonly Action execute;

		private readonly Func<bool> canExecute;

		public event EventHandler CanExecuteChanged;

		public RelayCommand(Action execute, Func<bool> canExecute = null)
		{
			this.execute = execute;
			this.canExecute = canExecute;
		}

		public bool CanExecute(object parameter)
		{
			if (canExecute != null)
			{
				return canExecute();
			}
			return true;
		}

		public void Execute(object parameter)
		{
			if (CanExecute(parameter))
			{
				execute();
			}
		}

		public void Refresh()
		{
			this.CanExecuteChanged?.Invoke(this, EventArgs.Empty);
		}
	}
}
