using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;

namespace ATIVBatteryGuard.Services
{
    // The normal GUI remains asInvoker. Only an explicit user operation may
    // launch the fixed helper. No process-kill or trial-marker access exists.
    public sealed class WindowsManualProtectionOperationService : IManualProtectionOperationService, IDisposable
    {
        public const string HelperFileName = "ATIVBatteryGuard.ManualProtectionHelper.exe";
        public const string PipePrefix = "ATIVBatteryGuard-Manual-v1-";
        private readonly object gate = new object();
        private NamedPipeServerStream activePipe;
        private bool running, blocked, disposed;
        public bool IsBlocked { get { lock (gate) return blocked || disposed; } }

        public async Task<ManualProtectionResult> RunAsync(ManualProtectionOperation operation, Action<ManualProtectionPhase> progress)
        {
            // Validate closed operations without doing platform work.
            ManualProtectionLimits.MaximumSdkEntries(operation);
            lock (gate)
            {
                if (disposed || blocked || running)
                    return ManualProtectionResult.Failure(operation, ManualProtectionStatus.Busy, true);
                running = true;
            }
            var synchronization = SynchronizationContext.Current;
            Action<ManualProtectionPhase> report = phase => Report(synchronization, progress, phase);
            ManualProtectionClientSession exchange = null;
            NamedPipeServerStream pipe = null;
            Process helper = null;
            try
            {
                Version version = Environment.OSVersion.Version;
                if (Environment.OSVersion.Platform != PlatformID.Win32NT || !Environment.Is64BitOperatingSystem ||
                    version.Major != 10 || version.Minor != 0 || version.Build < 10240 || version.Build >= 22000)
                    return ManualProtectionResult.Failure(operation, ManualProtectionStatus.Unsupported, true);
                string directory = LocalPathPolicy.NormalizeDirectory(AppDomain.CurrentDomain.BaseDirectory);
                string path = Path.Combine(directory, HelperFileName);
                LocalPathPolicy.EnsureNoReparsePoints(path);
                if (!File.Exists(path)) return ManualProtectionResult.Failure(operation, ManualProtectionStatus.PreflightFailed, true);
                var context = ManualProtectionContext.Create(operation);
                pipe = CreatePrivatePipe(PipePrefix + context.JobId);
                lock (gate) { if (disposed) throw new InvalidOperationException(); activePipe = pipe; }
                var connected = pipe.WaitForConnectionAsync();
                _ = connected.ContinueWith(task => { var ignored = task.Exception; },
                    CancellationToken.None, TaskContinuationOptions.OnlyOnFaulted, TaskScheduler.Default);
                report(ManualProtectionPhase.WaitingAdministrator);
                var start = new ProcessStartInfo
                {
                    FileName = path, WorkingDirectory = directory, UseShellExecute = true, Verb = "runas",
                    Arguments = "--manual-v1 " + context.JobId + " " + operation + " " + context.Nonce
                };
                // Shell elevation may wait for a user response. Never block
                // the WPF dispatcher while that prompt is open.
                helper = await Task.Run(() => Process.Start(start)).ConfigureAwait(false);
                if (await Task.WhenAny(connected, Task.Delay(TimeSpan.FromSeconds(20))).ConfigureAwait(false) != connected)
                {
                    return ManualProtectionResult.Failure(operation, ManualProtectionStatus.PreflightFailed, true);
                }
                await connected.ConfigureAwait(false);
                exchange = new ManualProtectionClientSession(context);
                var result = await exchange.RunAsync(pipe, report).ConfigureAwait(false);
                if (exchange.IsUncertain || !result.CleanupComplete) lock (gate) blocked = true;
                return result;
            }
            catch (Win32Exception error)
            {
                if (exchange != null && exchange.RequestMayHaveBeenSent)
                { lock (gate) blocked = true; return ManualProtectionResult.Failure(operation, ManualProtectionStatus.Unknown, false); }
                return ManualProtectionResult.Failure(operation,
                    error.NativeErrorCode == 1223 ? ManualProtectionStatus.Cancelled : ManualProtectionStatus.PreflightFailed, true);
            }
            catch
            {
                bool uncertain = exchange != null && exchange.RequestMayHaveBeenSent;
                if (uncertain) lock (gate) blocked = true;
                return ManualProtectionResult.Failure(operation,
                    uncertain ? ManualProtectionStatus.Unknown : ManualProtectionStatus.PreflightFailed, !uncertain);
            }
            finally
            {
                // Closing the private pipe affects transport only. An already
                // admitted helper retains its resources and durable marker.
                try { pipe?.Dispose(); } catch { }
                try { helper?.Dispose(); } catch { }
                lock (gate) { activePipe = null; running = false; }
            }
        }

        private static NamedPipeServerStream CreatePrivatePipe(string name)
        {
            var security = new PipeSecurity();
            security.SetAccessRuleProtection(true, false);
            security.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(WellKnownSidType.NetworkSid, null),
                PipeAccessRights.FullControl, AccessControlType.Deny));
            using (var identity = WindowsIdentity.GetCurrent())
            {
                var user = identity.User;
                if (user == null) throw new InvalidOperationException("The local pipe owner is unavailable.");
                security.SetOwner(user);
                security.AddAccessRule(new PipeAccessRule(user, PipeAccessRights.ReadWrite | PipeAccessRights.CreateNewInstance,
                    AccessControlType.Allow));
            }
            return new NamedPipeServerStream(name, PipeDirection.InOut, 1, PipeTransmissionMode.Byte,
                PipeOptions.Asynchronous, 4096, 4096, security);
        }

        private static void Report(SynchronizationContext synchronization, Action<ManualProtectionPhase> progress, ManualProtectionPhase phase)
        {
            if (progress == null) return;
            try
            {
                if (synchronization == null) progress(phase);
                else synchronization.Post(_ => { try { progress(phase); } catch { } }, null);
            }
            catch { }
        }
        public void Dispose()
        {
            NamedPipeServerStream pipe;
            lock (gate) { disposed = true; pipe = activePipe; }
            try { pipe?.Dispose(); } catch { }
        }
    }
}
