using System;
using System.Collections.Generic;
using System.Management;
using System.Runtime.InteropServices;
using System.Security;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Diagnostics
{
    // Deliberately uses ManagementClass.Get for class metadata only.
    // Do not add GetInstances, InvokeMethod, property Value, or qualifiers here.
    public sealed class WindowsWmiSchemaSource : IWmiSchemaSource
    {
        public WmiClassSchema ReadClass(string className)
        {
            if (!WmiSchemaPolicy.IsAllowedClass(className)) throw new ArgumentException("Class is outside the schema allowlist.", nameof(className));
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
                return new WmiClassSchema(className, WmiSchemaStatus.UnsupportedPlatform);
            try
            {
                var scope = new ManagementScope(@"\\.\" + WmiSchemaPolicy.LocalNamespace,
                    new ConnectionOptions { Timeout = TimeSpan.FromSeconds(3), EnablePrivileges = false });
                var options = new ObjectGetOptions { UseAmendedQualifiers = false, Timeout = TimeSpan.FromSeconds(3) };
                using (var schema = new ManagementClass(scope, new ManagementPath(className), options))
                {
                    schema.Get();
                    bool truncated = false;
                    var properties = ReadFields(schema, WmiSchemaPolicy.MaxProperties, ref truncated);
                    var methods = new List<WmiSchemaMethod>();
                    int visited = 0;
                    foreach (MethodData method in schema.Methods)
                    {
                        if (++visited > WmiSchemaPolicy.MaxMethods) { truncated = true; break; }
                        bool methodTruncated = false;
                        WmiSchemaField[] inputs, outputs;
                        using (ManagementBaseObject definition = method.InParameters)
                            inputs = ReadFields(definition, WmiSchemaPolicy.MaxParameters, ref methodTruncated);
                        using (ManagementBaseObject definition = method.OutParameters)
                            outputs = ReadFields(definition, WmiSchemaPolicy.MaxParameters, ref methodTruncated);
                        methods.Add(new WmiSchemaMethod(method.Name, inputs, outputs, methodTruncated));
                    }
                    return new WmiClassSchema(className, WmiSchemaStatus.Found, properties, methods, truncated);
                }
            }
            catch (ManagementException exception)
            {
                return new WmiClassSchema(className, Classify(exception.ErrorCode));
            }
            catch (UnauthorizedAccessException) { return new WmiClassSchema(className, WmiSchemaStatus.AccessDenied); }
            catch (SecurityException) { return new WmiClassSchema(className, WmiSchemaStatus.AccessDenied); }
            catch (TimeoutException) { return new WmiClassSchema(className, WmiSchemaStatus.TimedOut); }
            catch (COMException exception) { return new WmiClassSchema(className, ClassifyHResult(exception.ErrorCode)); }
            catch (InvalidOperationException) { return new WmiClassSchema(className, WmiSchemaStatus.ReadError); }
            catch (ArgumentException) { return new WmiClassSchema(className, WmiSchemaStatus.ReadError); }
            catch (NotSupportedException) { return new WmiClassSchema(className, WmiSchemaStatus.ReadError); }
        }

        private static WmiSchemaField[] ReadFields(ManagementBaseObject definition, int maximum, ref bool truncated)
        {
            var fields = new List<WmiSchemaField>();
            if (definition == null) return fields.ToArray();
            int visited = 0;
            foreach (PropertyData property in definition.Properties)
            {
                if (++visited > maximum) { truncated = true; break; }
                // Metadata only; accessing property.Value would read an unwanted default/instance value.
                fields.Add(new WmiSchemaField(property.Name, property.Type.ToString(), property.IsArray));
            }
            return fields.ToArray();
        }
        private static WmiSchemaStatus Classify(ManagementStatus status)
        {
            switch (status)
            {
                case ManagementStatus.InvalidClass:
                case ManagementStatus.NotFound: return WmiSchemaStatus.ClassNotFound;
                case ManagementStatus.InvalidNamespace: return WmiSchemaStatus.NamespaceNotFound;
                case ManagementStatus.AccessDenied: return WmiSchemaStatus.AccessDenied;
                case ManagementStatus.Timedout: return WmiSchemaStatus.TimedOut;
                default: return WmiSchemaStatus.ReadError;
            }
        }
        private static WmiSchemaStatus ClassifyHResult(int code)
        {
            switch (unchecked((uint)code))
            {
                case 0x80070005: case 0x80041003: return WmiSchemaStatus.AccessDenied;
                case 0x80041002: case 0x80041010: return WmiSchemaStatus.ClassNotFound;
                case 0x8004100E: return WmiSchemaStatus.NamespaceNotFound;
                case 0x80043001: case 0x800705B4: return WmiSchemaStatus.TimedOut;
                default: return WmiSchemaStatus.ReadError;
            }
        }
    }
}
