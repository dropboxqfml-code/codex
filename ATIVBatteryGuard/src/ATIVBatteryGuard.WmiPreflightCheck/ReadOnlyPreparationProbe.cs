using System;
using System.Diagnostics;
using System.Management;
using System.Runtime.InteropServices;
using System.Security;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Diagnostics;

namespace ATIVBatteryGuard.WmiPreflightCheck
{
    // Frozen read-only reproduction of the experiment's preparation checks.
    // Keep the fixed guards and query options in step with the reviewed source;
    // a failure category is evidence to review, not a reason to bypass a guard.
    internal static class ReadOnlyPreparationProbe
    {
        internal static WsabiWmiPreflightInspectionReport Collect()
            => new Inspection().Collect();

        private sealed class Inspection
        {
            private const string ExpectedModel = "940X3G/930X3G";
            private const string ExpectedBios = "P05ACJ.128.140819.dg";
            private const uint RequiredMethodId = 1;
            private static readonly TimeSpan PreflightBudget = TimeSpan.FromSeconds(6);
            private static readonly TimeSpan QueryTimeout = TimeSpan.FromSeconds(2);
            private readonly Stopwatch elapsed = Stopwatch.StartNew();
            private ProcessElevationState elevation = ProcessElevationState.Unknown;
            private WsabiWmiOneShotPreflightStage stage = WsabiWmiOneShotPreflightStage.Unknown;

            internal WsabiWmiPreflightInspectionReport Collect()
            {
                if (Environment.OSVersion.Platform != PlatformID.Win32NT || !Environment.Is64BitProcess)
                    return Report(WsabiWmiMetadataStatus.UnsupportedPlatform,
                        WsabiWmiPreflightIssue.PlatformUnsupported);
                elevation = ProcessElevationProbe.Read();
                if (elevation != ProcessElevationState.Elevated)
                    return Report(WsabiWmiMetadataStatus.AccessDenied, WsabiWmiPreflightIssue.NotElevated);

                try
                {
                    stage = WsabiWmiOneShotPreflightStage.DeviceScope;
                    var deviceScope = OpenScope(@"root\CIMV2");
                    stage = WsabiWmiOneShotPreflightStage.ModelRead;
                    string model = ReadSingleString(deviceScope,
                        "SELECT Name FROM Win32_ComputerSystemProduct", "Name");
                    if (!MatchesFixedString(model, ExpectedModel))
                        return Report(WsabiWmiMetadataStatus.Complete, WsabiWmiPreflightIssue.DeviceMismatch);
                    stage = WsabiWmiOneShotPreflightStage.BiosRead;
                    string bios = ReadSingleString(deviceScope,
                        "SELECT SMBIOSBIOSVersion FROM Win32_BIOS", "SMBIOSBIOSVersion");
                    if (!MatchesFixedString(bios, ExpectedBios))
                        return Report(WsabiWmiMetadataStatus.Complete, WsabiWmiPreflightIssue.DeviceMismatch);
                    RequirePreflightTime();

                    stage = WsabiWmiOneShotPreflightStage.ContractMetadata;
                    WsabiWmiContractMetadataReport metadata = WsabiWmiContractMetadataProbe.Collect();
                    RequirePreflightTime();
                    WsabiWmiMethodBinder binder;
                    if (!WsabiWmiMethodBinder.TryCreate(metadata, out binder) ||
                        metadata.MethodMetadata.MethodId != RequiredMethodId)
                        return MetadataFailure(metadata);

                    stage = WsabiWmiOneShotPreflightStage.MethodScope;
                    var scope = OpenScope(WsabiWmiContractMetadataPolicy.LocalNamespace);
                    string relativePath = null;
                    bool? active = null;
                    WsabiWmiPreflightIssue activeIssue = WsabiWmiPreflightIssue.None;
                    int count = 0;
                    bool complete;
                    stage = WsabiWmiOneShotPreflightStage.MethodEnumeration;
                    using (var searcher = new ManagementObjectSearcher(scope,
                        new ObjectQuery("SELECT Active FROM WmiAcpiMethod"), CreateEnumerationOptions()))
                    using (var collection = searcher.Get())
                    using (var rows = collection.GetEnumerator())
                    {
                        while (rows.MoveNext())
                        {
                            using (var current = rows.Current)
                            {
                                var row = current as ManagementObject;
                                if (row == null) throw Failure(WsabiWmiPreflightIssue.InactiveOrInvalidTarget);
                                RequirePreflightTime();
                                count++;
                                if (count == 2) break;
                                active = ReadActive(row, out activeIssue);
                                ManagementPath path = row.Path;
                                if (path == null || !path.IsInstance || !string.Equals(path.ClassName,
                                    WsabiWmiContractMetadataPolicy.MethodClass, StringComparison.OrdinalIgnoreCase))
                                    throw Failure(WsabiWmiPreflightIssue.InactiveOrInvalidTarget);
                                relativePath = path.RelativePath;
                                if (string.IsNullOrEmpty(relativePath) || relativePath.Length > 4096)
                                    throw Failure(WsabiWmiPreflightIssue.InactiveOrInvalidTarget);
                            }
                        }
                        complete = count < 2;
                    }
                    RequirePreflightTime();
                    if (!complete || count != 1)
                        return Report(WsabiWmiMetadataStatus.Complete, WsabiWmiPreflightIssue.RowCountMismatch);
                    if (active != true)
                        return Report(WsabiWmiMetadataStatus.Complete,
                            activeIssue == WsabiWmiPreflightIssue.None
                                ? WsabiWmiPreflightIssue.InactiveOrInvalidTarget : activeIssue);

                    // The observed key remains local and is never returned.
                    // Only the original fixed local class and scope are used.
                    stage = WsabiWmiOneShotPreflightStage.TargetRead;
                    using (var target = new ManagementObject(scope, new ManagementPath(relativePath),
                        new ObjectGetOptions { Timeout = RemainingTimeout() }))
                    {
                        target.Get();
                        RequirePreflightTime();
                        if (ReadActive(target, out activeIssue) != true)
                            throw Failure(activeIssue == WsabiWmiPreflightIssue.None
                                ? WsabiWmiPreflightIssue.InactiveOrInvalidTarget : activeIssue);
                        stage = WsabiWmiOneShotPreflightStage.InputParameters;
                        using (var input = target.GetMethodParameters(WsabiWmiContractMetadataPolicy.MethodName))
                        {
                            if (input == null || input.Properties.Count != 1)
                                throw Failure(WsabiWmiPreflightIssue.InputShapeMismatch);
                            PropertyData parameter = ReadProperty(input, "inData");
                            if (parameter == null || parameter.Type != CimType.Object || parameter.IsArray)
                                throw Failure(WsabiWmiPreflightIssue.InputShapeMismatch);
                            RequireInputCimType(parameter);
                            stage = WsabiWmiOneShotPreflightStage.BufferInstance;
                            using (var bufferClass = new ManagementClass(scope,
                                new ManagementPath(WsabiWmiContractMetadataPolicy.BufferClass),
                                new ObjectGetOptions { Timeout = RemainingTimeout() }))
                            {
                                bufferClass.Get();
                                // This SDK factory creates an in-memory object.
                                // It neither saves the object nor sets its fields.
                                using (var dataBuffer = bufferClass.CreateInstance())
                                {
                                    if (dataBuffer == null)
                                        throw Failure(WsabiWmiPreflightIssue.BufferUnavailable);
                                    RequirePreflightTime();
                                }
                            }
                        }
                    }
                    RequirePreflightTime();
                    stage = WsabiWmiOneShotPreflightStage.Ready;
                    return Report(WsabiWmiMetadataStatus.Complete, WsabiWmiPreflightIssue.None);
                }
                catch (InspectionFailure failure)
                {
                    return Report(WsabiWmiMetadataStatus.Complete, failure.Issue);
                }
                catch (Exception exception)
                {
                    WsabiWmiPreflightIssue issue = Classify(exception);
                    return Report(StatusFor(issue), issue);
                }
            }

            private string ReadSingleString(ManagementScope scope, string query, string propertyName)
            {
                string result = null;
                int count = 0;
                using (var searcher = new ManagementObjectSearcher(scope, new ObjectQuery(query), CreateEnumerationOptions()))
                using (var collection = searcher.Get())
                using (var rows = collection.GetEnumerator())
                {
                    while (rows.MoveNext())
                    {
                        using (var row = rows.Current)
                        {
                            RequirePreflightTime();
                            if (++count > 1) throw Failure(WsabiWmiPreflightIssue.RowCountMismatch);
                            PropertyData property = ReadProperty(row, propertyName);
                            if (property == null) throw Failure(WsabiWmiPreflightIssue.FieldUnavailable);
                            if (property.Type != CimType.String || property.IsArray)
                                throw Failure(WsabiWmiPreflightIssue.FieldTypeMismatch);
                            result = property.Value as string;
                            if (result == null || result.Length > 128)
                                throw Failure(WsabiWmiPreflightIssue.InvalidValue);
                        }
                    }
                }
                if (count != 1) throw Failure(WsabiWmiPreflightIssue.RowCountMismatch);
                RequirePreflightTime();
                return result;
            }

            private ManagementScope OpenScope(string name)
            {
                var scope = new ManagementScope(@"\\.\" + name, new ConnectionOptions
                {
                    Timeout = RemainingTimeout(), EnablePrivileges = false,
                    Authentication = AuthenticationLevel.PacketPrivacy,
                    Impersonation = ImpersonationLevel.Impersonate
                });
                scope.Connect();
                RequirePreflightTime();
                return scope;
            }

            private EnumerationOptions CreateEnumerationOptions() => new EnumerationOptions
            {
                Timeout = RemainingTimeout(), BlockSize = 1, Rewindable = false,
                ReturnImmediately = true, DirectRead = true
            };

            private TimeSpan RemainingTimeout()
            {
                TimeSpan remaining = PreflightBudget - elapsed.Elapsed;
                if (remaining <= TimeSpan.Zero) throw new TimeoutException();
                return remaining < QueryTimeout ? remaining : QueryTimeout;
            }

            private void RequirePreflightTime()
            {
                if (elapsed.Elapsed >= PreflightBudget) throw new TimeoutException();
            }

            private WsabiWmiPreflightInspectionReport MetadataFailure(WsabiWmiContractMetadataReport metadata)
            {
                WsabiWmiMetadataStatus status = metadata.MethodMetadata.Status;
                if (IsObserved(status)) status = metadata.BufferMetadata.Status;
                if (IsObserved(status))
                    return Report(WsabiWmiMetadataStatus.Complete, WsabiWmiPreflightIssue.SchemaMismatch);
                switch (status)
                {
                    case WsabiWmiMetadataStatus.AccessDenied:
                        return Report(status, WsabiWmiPreflightIssue.AccessDenied);
                    case WsabiWmiMetadataStatus.TimedOut:
                        return Report(status, WsabiWmiPreflightIssue.TimedOut);
                    case WsabiWmiMetadataStatus.ClassNotFound:
                        return Report(status, WsabiWmiPreflightIssue.ClassNotFound);
                    case WsabiWmiMetadataStatus.NamespaceNotFound:
                        return Report(status, WsabiWmiPreflightIssue.NamespaceNotFound);
                    case WsabiWmiMetadataStatus.UnsupportedPlatform:
                        return Report(status, WsabiWmiPreflightIssue.PlatformUnsupported);
                    default:
                        return Report(WsabiWmiMetadataStatus.Unavailable, WsabiWmiPreflightIssue.OtherError);
                }
            }

            private WsabiWmiPreflightInspectionReport Report(WsabiWmiMetadataStatus status, WsabiWmiPreflightIssue issue)
                => new WsabiWmiPreflightInspectionReport(elevation, status, stage, issue);

            private static bool IsObserved(WsabiWmiMetadataStatus status)
                => status == WsabiWmiMetadataStatus.Complete || status == WsabiWmiMetadataStatus.Partial;

            private static bool MatchesFixedString(string actual, string expected)
                => actual != null && actual.Length <= 128 &&
                    string.Equals(actual.Trim(), expected, StringComparison.OrdinalIgnoreCase);

            private static bool? ReadActive(ManagementBaseObject value, out WsabiWmiPreflightIssue issue)
            {
                PropertyData property = ReadProperty(value, "Active");
                issue = WsabiWmiPreflightIssue.FieldUnavailable;
                if (property == null) return null;
                issue = WsabiWmiPreflightIssue.FieldTypeMismatch;
                if (property.Type != CimType.Boolean || property.IsArray) return null;
                object active = property.Value;
                issue = WsabiWmiPreflightIssue.InvalidValue;
                if (!(active is bool)) return null;
                issue = WsabiWmiPreflightIssue.None;
                return (bool)active;
            }

            private static PropertyData ReadProperty(ManagementBaseObject value, string name)
            {
                try { return value.Properties[name]; }
                catch (ManagementException exception) when (exception.ErrorCode == ManagementStatus.NotFound) { return null; }
            }

            private static void RequireInputCimType(PropertyData parameter)
            {
                object value;
                try
                {
                    QualifierData qualifier = parameter.Qualifiers["CIMTYPE"];
                    value = qualifier == null ? null : qualifier.Value;
                }
                catch (ManagementException exception) when (exception.ErrorCode == ManagementStatus.NotFound)
                {
                    throw Failure(WsabiWmiPreflightIssue.InputCimTypeMissing);
                }
                switch (WsabiWmiContractMetadataPolicy.NormalizeCimType(value))
                {
                    case WsabiWmiQualifierMatch.MatchesDataBuffer: return;
                    case WsabiWmiQualifierMatch.Missing:
                        throw Failure(WsabiWmiPreflightIssue.InputCimTypeMissing);
                    case WsabiWmiQualifierMatch.Invalid:
                        throw Failure(WsabiWmiPreflightIssue.InputCimTypeInvalid);
                    default:
                        throw Failure(WsabiWmiPreflightIssue.InputCimTypeMismatch);
                }
            }

            private static WsabiWmiPreflightIssue Classify(Exception exception)
            {
                if (exception is TimeoutException) return WsabiWmiPreflightIssue.TimedOut;
                if (exception is UnauthorizedAccessException || exception is SecurityException)
                    return WsabiWmiPreflightIssue.AccessDenied;
                if (exception is NotSupportedException) return WsabiWmiPreflightIssue.FrameworkNotSupported;
                var management = exception as ManagementException;
                if (management != null)
                    return WsabiWmiPreflightIssuePolicy.FromHResult((int)management.ErrorCode);
                var com = exception as COMException;
                if (com != null) return WsabiWmiPreflightIssuePolicy.FromHResult(com.ErrorCode);
                return WsabiWmiPreflightIssue.OtherError;
            }

            private static WsabiWmiMetadataStatus StatusFor(WsabiWmiPreflightIssue issue)
            {
                switch (issue)
                {
                    case WsabiWmiPreflightIssue.AccessDenied: return WsabiWmiMetadataStatus.AccessDenied;
                    case WsabiWmiPreflightIssue.TimedOut: return WsabiWmiMetadataStatus.TimedOut;
                    case WsabiWmiPreflightIssue.ClassNotFound: return WsabiWmiMetadataStatus.ClassNotFound;
                    case WsabiWmiPreflightIssue.NamespaceNotFound: return WsabiWmiMetadataStatus.NamespaceNotFound;
                    case WsabiWmiPreflightIssue.PlatformUnsupported: return WsabiWmiMetadataStatus.UnsupportedPlatform;
                    default: return WsabiWmiMetadataStatus.Unavailable;
                }
            }

            private static InspectionFailure Failure(WsabiWmiPreflightIssue issue) => new InspectionFailure(issue);

            private sealed class InspectionFailure : Exception
            {
                internal WsabiWmiPreflightIssue Issue { get; }
                internal InspectionFailure(WsabiWmiPreflightIssue issue) { Issue = issue; }
            }
        }
    }
}
