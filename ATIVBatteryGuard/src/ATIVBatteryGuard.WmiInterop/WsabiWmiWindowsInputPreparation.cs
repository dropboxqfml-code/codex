using System;
using System.Management;
using System.Runtime.CompilerServices;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.WmiInterop
{
    public enum WsabiWmiWindowsInputPreparationStatus
    {
        Populated, PlanMissing, RequestMismatch, ObjectsMissingOrAliased,
        ObjectsAlreadyUsed, ShapeMismatch, PropertyAccessFailed
    }

    // Populates supplied, already materialized parameter objects only. Their
    // caller retains ownership and must exclude external mutation/dispatch.
    // SDK property access may enter COM or initialize a lazy supplied object;
    // there is no explicit discovery, construction, Connect/Get/Put or method
    // invocation site here.
    public static class WsabiWmiWindowsInputPreparation
    {
        private static readonly object ClaimGate = new object();
        private static readonly ConditionalWeakTable<ManagementBaseObject, Used> Objects =
            new ConditionalWeakTable<ManagementBaseObject, Used>();

        public static WsabiWmiWindowsInputPreparationStatus Populate(WsabiWmiSingleReadPlan plan,
            WsabiWmiMethodRequest request, ManagementBaseObject parameters, ManagementBaseObject buffer)
        {
            if (plan == null) return WsabiWmiWindowsInputPreparationStatus.PlanMissing;
            WsabiWmiMethodRequest frozen;
            if (!plan.TryFreezeRequest(request, out frozen)) return WsabiWmiWindowsInputPreparationStatus.RequestMismatch;
            if (parameters == null || buffer == null || ReferenceEquals(parameters, buffer))
                return WsabiWmiWindowsInputPreparationStatus.ObjectsMissingOrAliased;
            // Claim both managed wrappers before SDK access. A failed getter or
            // a setter that mutates and then throws cannot rearm either one.
            lock (ClaimGate)
            {
                Used ignored;
                if (Objects.TryGetValue(parameters, out ignored) || Objects.TryGetValue(buffer, out ignored))
                    return WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed;
                Objects.Add(parameters, new Used());
                Objects.Add(buffer, new Used());
            }
            try
            {
                ManagementPath classPath = buffer.ClassPath;
                if (classPath == null || !string.Equals(classPath.ClassName, plan.Binder.BufferClass,
                    StringComparison.OrdinalIgnoreCase)) return WsabiWmiWindowsInputPreparationStatus.ShapeMismatch;
                PropertyDataCollection inputProperties = parameters.Properties;
                PropertyDataCollection bufferProperties = buffer.Properties;
                if (inputProperties == null || bufferProperties == null ||
                    inputProperties.Count != 1 || bufferProperties.Count != 1)
                    return WsabiWmiWindowsInputPreparationStatus.ShapeMismatch;
                PropertyData inputProperty = inputProperties[plan.Binder.InputName];
                PropertyData byteProperty = bufferProperties[plan.Binder.BytesName];
                if (inputProperty == null || inputProperty.Type != CimType.Object || inputProperty.IsArray ||
                    byteProperty == null || byteProperty.Type != CimType.UInt8 || !byteProperty.IsArray)
                    return WsabiWmiWindowsInputPreparationStatus.ShapeMismatch;

                // These are parameter assignments, not a repository Put or a
                // firmware setting write. Do not read old Values or roll back
                // partial assignments. Populated does not authorize dispatch.
                byteProperty.Value = frozen.Frame;
                inputProperty.Value = buffer;
                return WsabiWmiWindowsInputPreparationStatus.Populated;
            }
            catch
            {
                // Return no SDK exception or payload. Partial assignments may
                // remain in borrowed objects; the caller must retire both.
                return WsabiWmiWindowsInputPreparationStatus.PropertyAccessFailed;
            }
        }

        private sealed class Used { }
    }
}
