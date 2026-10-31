using System;
using System.Collections.Generic;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Models
{
    public enum WmiSchemaStatus
    {
        Found, ClassNotFound, NamespaceNotFound, AccessDenied, TimedOut, UnsupportedPlatform, ReadError
    }

    public sealed class WmiSchemaField
    {
        public string Name { get; }
        public string TypeName { get; }
        public bool IsArray { get; }
        public WmiSchemaField(string name, string typeName, bool isArray = false)
        {
            Name = WmiSchemaPolicy.Identifier(name);
            TypeName = WmiSchemaPolicy.TypeName(typeName);
            IsArray = isArray;
        }
    }

    public sealed class WmiSchemaMethod
    {
        private readonly WmiSchemaField[] inputs;
        private readonly WmiSchemaField[] outputs;
        public string Name { get; }
        public WmiSchemaField[] Inputs => (WmiSchemaField[])inputs.Clone();
        public WmiSchemaField[] Outputs => (WmiSchemaField[])outputs.Clone();
        public bool Truncated { get; }
        public WmiSchemaMethod(string name, IEnumerable<WmiSchemaField> inputs = null, IEnumerable<WmiSchemaField> outputs = null, bool truncated = false)
        {
            Name = WmiSchemaPolicy.Identifier(name);
            bool inputTruncated, outputTruncated;
            this.inputs = WmiSchemaPolicy.CopyBounded(inputs, WmiSchemaPolicy.MaxParameters, out inputTruncated);
            this.outputs = WmiSchemaPolicy.CopyBounded(outputs, WmiSchemaPolicy.MaxParameters, out outputTruncated);
            Truncated = truncated || inputTruncated || outputTruncated;
        }
    }

    public sealed class WmiClassSchema
    {
        private readonly WmiSchemaField[] properties;
        private readonly WmiSchemaMethod[] methods;
        public string ClassName { get; }
        public WmiSchemaStatus Status { get; }
        public WmiSchemaField[] Properties => (WmiSchemaField[])properties.Clone();
        public WmiSchemaMethod[] Methods => (WmiSchemaMethod[])methods.Clone();
        public bool Truncated { get; }
        public bool HardwareWriteAllowed => false;
        public WmiClassSchema(string className, WmiSchemaStatus status, IEnumerable<WmiSchemaField> properties = null, IEnumerable<WmiSchemaMethod> methods = null, bool truncated = false)
        {
            ClassName = WmiSchemaPolicy.IsAllowedClass(className) ? className : "InvalidClass";
            Status = Enum.IsDefined(typeof(WmiSchemaStatus), status) ? status : WmiSchemaStatus.ReadError;
            bool propertiesTruncated, methodsTruncated;
            this.properties = WmiSchemaPolicy.CopyBounded(Status == WmiSchemaStatus.Found ? properties : null, WmiSchemaPolicy.MaxProperties, out propertiesTruncated);
            this.methods = WmiSchemaPolicy.CopyBounded(Status == WmiSchemaStatus.Found ? methods : null, WmiSchemaPolicy.MaxMethods, out methodsTruncated);
            Truncated = truncated || propertiesTruncated || methodsTruncated;
        }
    }
}
