using System;
using System.Linq;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiFixedReadAdmissionTests()
    {
        Add("fixed read admission accepts only an explicitly elevated token classification", () =>
        {
            Equal(WsabiWmiFixedReadAdmissionStatus.Ready,
                WsabiWmiFixedReadAdmissionPolicy.Evaluate(ProcessElevationState.Elevated));
            Equal(WsabiWmiFixedReadAdmissionStatus.NotElevated,
                WsabiWmiFixedReadAdmissionPolicy.Evaluate(ProcessElevationState.NotElevated));
            foreach (var value in new[] { ProcessElevationState.Unknown, (ProcessElevationState)(-1),
                (ProcessElevationState)3, (ProcessElevationState)int.MinValue, (ProcessElevationState)int.MaxValue })
                Equal(WsabiWmiFixedReadAdmissionStatus.ElevationUnknown,
                    WsabiWmiFixedReadAdmissionPolicy.Evaluate(value));
            Equal(WsabiWmiFixedReadAdmissionStatus.ElevationUnknown, default(WsabiWmiFixedReadAdmissionStatus));
        });

        Add("fixed read admission never retains readiness from an earlier elevated observation", () =>
        {
            var sequence = new[] { ProcessElevationState.Elevated, ProcessElevationState.NotElevated,
                ProcessElevationState.Elevated, ProcessElevationState.Unknown, (ProcessElevationState)999 };
            var expected = new[] { WsabiWmiFixedReadAdmissionStatus.Ready, WsabiWmiFixedReadAdmissionStatus.NotElevated,
                WsabiWmiFixedReadAdmissionStatus.Ready, WsabiWmiFixedReadAdmissionStatus.ElevationUnknown,
                WsabiWmiFixedReadAdmissionStatus.ElevationUnknown };
            for (int index = 0; index < sequence.Length; index++)
                Equal(expected[index], WsabiWmiFixedReadAdmissionPolicy.Evaluate(sequence[index]));
        });

        Add("fixed read admission exposes classification only without hardware authority or callbacks", () =>
        {
            var type = typeof(WsabiWmiFixedReadAdmissionPolicy);
            var methods = type.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly);
            Equal(1, methods.Length); Equal("Evaluate", methods[0].Name);
            Equal(typeof(WsabiWmiFixedReadAdmissionStatus), methods[0].ReturnType);
            var parameters = methods[0].GetParameters();
            Equal(1, parameters.Length); Equal(typeof(ProcessElevationState), parameters[0].ParameterType);
            Equal(0, type.GetProperties(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly).Length);
            Equal(0, type.GetFields(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly).Length);
            Check(Enum.GetNames(typeof(WsabiWmiFixedReadAdmissionStatus)).OrderBy(value => value)
                .SequenceEqual(new[] { "ElevationUnknown", "NotElevated", "Ready" }), "admission gained a device capability state");
        });
    }
}
