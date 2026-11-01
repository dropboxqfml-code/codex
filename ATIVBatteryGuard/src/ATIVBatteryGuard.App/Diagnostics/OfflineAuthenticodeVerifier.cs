using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Diagnostics
{
    // Embedded Authenticode verification only. No vendor module is loaded.
    // CACHE_ONLY_URL_RETRIEVAL and REVOCATION_CHECK_NONE prohibit online retrieval.
    internal static class OfflineAuthenticodeVerifier
    {
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct FileInfo
        {
            internal uint Size;
            [MarshalAs(UnmanagedType.LPWStr)] internal string Path;
            internal IntPtr Handle;
            internal IntPtr KnownSubject;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct TrustData
        {
            internal uint Size;
            internal IntPtr PolicyCallback;
            internal IntPtr SipClient;
            internal uint UiChoice;
            internal uint RevocationChecks;
            internal uint UnionChoice;
            internal IntPtr File;
            internal uint StateAction;
            internal IntPtr State;
            internal IntPtr UrlReference;
            internal uint ProviderFlags;
            internal uint UiContext;
            internal IntPtr SignatureSettings;
        }

        internal static OfflineSignatureStatus Verify(string path, SafeFileHandle handle)
        {
            IntPtr memory = IntPtr.Zero;
            bool pinned = false;
            bool marshaled = false;
            bool attempted = false;
            var action = new Guid("00AAC56B-CD44-11D0-8CC2-00C04FC295EE");
            var data = new TrustData();
            try
            {
                handle.DangerousAddRef(ref pinned);
                var file = new FileInfo
                {
                    Size = (uint)Marshal.SizeOf(typeof(FileInfo)),
                    Path = path,
                    Handle = handle.DangerousGetHandle()
                };
                memory = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(FileInfo)));
                Marshal.StructureToPtr(file, memory, false);
                marshaled = true;
                data = new TrustData
                {
                    Size = (uint)Marshal.SizeOf(typeof(TrustData)),
                    UiChoice = 2, // WTD_UI_NONE
                    RevocationChecks = 0, // WTD_REVOKE_NONE
                    UnionChoice = 1, // WTD_CHOICE_FILE
                    File = memory,
                    StateAction = 1, // WTD_STATEACTION_VERIFY
                    ProviderFlags = 0x1010 // CACHE_ONLY_URL_RETRIEVAL | REVOCATION_CHECK_NONE
                };
                attempted = true;
                uint result = unchecked((uint)WinVerifyTrust(new IntPtr(-1), ref action, ref data));
                switch (result)
                {
                    case 0: return OfflineSignatureStatus.ValidOffline;
                    case 0x800B0100: return OfflineSignatureStatus.Unsigned; // TRUST_E_NOSIGNATURE
                    case 0x80096010: // TRUST_E_BAD_DIGEST
                    case 0x800B0111: // TRUST_E_EXPLICIT_DISTRUST
                    case 0x800B010C: // CERT_E_REVOKED (only available local evidence)
                        return OfflineSignatureStatus.Invalid;
                    default: return OfflineSignatureStatus.Inconclusive;
                }
            }
            catch { return OfflineSignatureStatus.Inconclusive; }
            finally
            {
                if (attempted)
                {
                    try
                    {
                        data.StateAction = 2; // WTD_STATEACTION_CLOSE
                        WinVerifyTrust(new IntPtr(-1), ref action, ref data);
                    }
                    catch { }
                }
                if (marshaled) Marshal.DestroyStructure(memory, typeof(FileInfo));
                if (memory != IntPtr.Zero) Marshal.FreeHGlobal(memory);
                if (pinned) handle.DangerousRelease();
            }
        }

        [DllImport("wintrust.dll", ExactSpelling = true, CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern int WinVerifyTrust(IntPtr window, ref Guid action, ref TrustData data);
    }
}
