using System;
using System.Collections.Generic;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // No method invocation, instance enumeration, value or qualifier access is exposed.
    public interface IWmiSchemaSource
    {
        WmiClassSchema ReadClass(string className);
    }

    public static class WmiSchemaInspector
    {
        public static WmiSchemaInspectionReport Inspect(IWmiSchemaSource source)
        {
            if (source == null) throw new ArgumentNullException(nameof(source));
            var results = new List<WmiClassSchema>();
            foreach (string name in WmiSchemaPolicy.AllowedClasses)
            {
                WmiClassSchema result;
                try
                {
                    result = source.ReadClass(name);
                    if (result == null || result.ClassName != name)
                        result = new WmiClassSchema(name, WmiSchemaStatus.ReadError);
                }
                catch (Exception)
                {
                    // Never include exception messages: they may contain local paths or identities.
                    result = new WmiClassSchema(name, WmiSchemaStatus.ReadError);
                }
                results.Add(result);
            }
            return new WmiSchemaInspectionReport(results);
        }
    }
}
