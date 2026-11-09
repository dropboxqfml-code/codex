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
            WsabiWmiWindowsOwnedInputPair ignored;
            return PopulateCore(plan, request, parameters, buffer, false, out ignored);
        }

        internal static WsabiWmiWindowsInputPreparationStatus PopulateOwned(WsabiWmiSingleReadPlan plan,
            WsabiWmiMethodRequest request, ManagementBaseObject parameters, ManagementBaseObject buffer,
            out WsabiWmiWindowsOwnedInputPair owned, ManagementBaseObject borrowedTarget = null)
            => PopulateCore(plan, request, parameters, buffer, true, out owned, borrowedTarget);

        private static WsabiWmiWindowsInputPreparationStatus PopulateCore(WsabiWmiSingleReadPlan plan,
            WsabiWmiMethodRequest request, ManagementBaseObject parameters, ManagementBaseObject buffer,
            bool takeOwnership, out WsabiWmiWindowsOwnedInputPair owned, ManagementBaseObject borrowedTarget = null)
        {
            owned = null;
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
                if (takeOwnership) owned = new WsabiWmiWindowsOwnedInputPair(parameters, buffer, borrowedTarget);
            }
            return PopulateFrozen(plan.Binder, frozen, parameters, buffer);
        }

        // New fixed-purpose lazy leaves claim each allocated wrapper before
        // another allocation can fail. The same registry also protects A.
        internal static bool TryClaimProtectionObject(ManagementBaseObject value, object owner,
            ManagementBaseObject borrowedTarget)
        {
            if (value == null || owner == null || ReferenceEquals(value, borrowedTarget)) return false;
            lock (ClaimGate)
            {
                Used ignored;
                if (Objects.TryGetValue(value, out ignored)) return false;
                Objects.Add(value, new Used(owner));
                return true;
            }
        }

        internal static WsabiWmiWindowsInputPreparationStatus PopulateProtectionOwned(
            WsabiWmiProtectionLeafRequest request, WsabiWmiMethodBinder binder,
            ManagementBaseObject parameters, ManagementBaseObject buffer, object owner,
            out WsabiWmiWindowsOwnedInputPair owned, ManagementBaseObject borrowedTarget)
        {
            owned = null;
            if (request == null || binder == null || !request.Matches(request.Request))
                return WsabiWmiWindowsInputPreparationStatus.RequestMismatch;
            if (parameters == null || buffer == null || ReferenceEquals(parameters, buffer) ||
                ReferenceEquals(parameters, borrowedTarget) || ReferenceEquals(buffer, borrowedTarget))
                return WsabiWmiWindowsInputPreparationStatus.ObjectsMissingOrAliased;
            lock (ClaimGate)
            {
                Used first, second;
                if (owner == null || !Objects.TryGetValue(parameters, out first) || !Objects.TryGetValue(buffer, out second) ||
                    !ReferenceEquals(first.Owner, owner) || !ReferenceEquals(second.Owner, owner))
                    return WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed;
                owned = new WsabiWmiWindowsOwnedInputPair(parameters, buffer, borrowedTarget);
            }
            return PopulateFrozen(binder, request.Request, parameters, buffer);
        }

        // Separately approved fixed disable request only. The shared registry
        // and private frozen-population helper do not admit arbitrary requests.
        internal static WsabiWmiWindowsInputPreparationStatus PopulateProtectionDisableOwned(
            WsabiWmiProtectionDisableLeafRequest request, WsabiWmiMethodBinder binder,
            ManagementBaseObject parameters, ManagementBaseObject buffer, object owner,
            out WsabiWmiWindowsOwnedInputPair owned, ManagementBaseObject borrowedTarget)
        {
            owned = null;
            if (request == null || binder == null || !request.Matches(request.Request))
                return WsabiWmiWindowsInputPreparationStatus.RequestMismatch;
            if (parameters == null || buffer == null || ReferenceEquals(parameters, buffer) ||
                ReferenceEquals(parameters, borrowedTarget) || ReferenceEquals(buffer, borrowedTarget))
                return WsabiWmiWindowsInputPreparationStatus.ObjectsMissingOrAliased;
            lock (ClaimGate)
            {
                Used first, second;
                if (owner == null || !Objects.TryGetValue(parameters, out first) || !Objects.TryGetValue(buffer, out second) ||
                    !ReferenceEquals(first.Owner, owner) || !ReferenceEquals(second.Owner, owner))
                    return WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed;
                owned = new WsabiWmiWindowsOwnedInputPair(parameters, buffer, borrowedTarget);
            }
            return PopulateFrozen(binder, request.Request, parameters, buffer);
        }

        private static WsabiWmiWindowsInputPreparationStatus PopulateFrozen(WsabiWmiMethodBinder binder,
            WsabiWmiMethodRequest frozen, ManagementBaseObject parameters, ManagementBaseObject buffer)
        {
            try
            {
                ManagementPath classPath = buffer.ClassPath;
                if (classPath == null || !string.Equals(classPath.ClassName, binder.BufferClass,
                    StringComparison.OrdinalIgnoreCase)) return WsabiWmiWindowsInputPreparationStatus.ShapeMismatch;
                PropertyDataCollection inputProperties = parameters.Properties;
                PropertyDataCollection bufferProperties = buffer.Properties;
                if (inputProperties == null || bufferProperties == null ||
                    inputProperties.Count != 1 || bufferProperties.Count != 1)
                    return WsabiWmiWindowsInputPreparationStatus.ShapeMismatch;
                PropertyData inputProperty = inputProperties[binder.InputName];
                PropertyData byteProperty = bufferProperties[binder.BytesName];
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

        private sealed class Used
        {
            internal readonly object Owner;
            internal Used(object owner = null) { Owner = owner; }
        }
    }
}
