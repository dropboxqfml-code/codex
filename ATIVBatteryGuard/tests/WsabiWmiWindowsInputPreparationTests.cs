using System;
using System.Collections.Generic;
using System.Linq;
using System.Management;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.WmiInterop;

internal static partial class Program
{
    // Production input preparation with stand-in SDK objects and the existing
    // synthetic 0x34 envelope. No target, invocation or actual read is present.
    private static void RegisterWsabiWmiWindowsInputPreparationTests()
    {
        Add("Windows input preparation rejects missing plan and malformed requests before SDK access or object claims", () =>
        {
            var plan = InputPreparationPlan();
            var valid = InputPreparationRequest();
            byte[] badHeader = BoundChannelRequest(); badHeader[0] ^= 0xff;
            byte[] badCommand = BoundChannelRequest(); badCommand[2] ^= 1;
            var requests = new[]
            {
                valid, null, new WsabiWmiMethodRequest(2, 0x34, BoundChannelRequest()),
                new WsabiWmiMethodRequest(1, 0x34, badHeader), new WsabiWmiMethodRequest(1, 0x34, badCommand)
            };
            for (int index = 0; index < requests.Length; index++)
            {
                var pair = InputPreparationPair.Create();
                int sdkTouches = 0;
                InputPreparationPoisonSdk(pair, () => sdkTouches++);
                var status = WsabiWmiWindowsInputPreparation.Populate(index == 0 ? null : plan,
                    requests[index], pair.Parameters, pair.Buffer);
                Equal(index == 0 ? WsabiWmiWindowsInputPreparationStatus.PlanMissing
                    : WsabiWmiWindowsInputPreparationStatus.RequestMismatch, status);
                Equal(0, sdkTouches); InputPreparationAssertUntouched(pair);
                InputPreparationResetSdk(pair);
                Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                    WsabiWmiWindowsInputPreparation.Populate(plan, valid, pair.Parameters, pair.Buffer));
                InputPreparationAssertBorrowed(pair);
            }
        });

        Add("Windows input preparation rejects missing or aliased roots before SDK access without consuming valid pairs", () =>
        {
            var plan = InputPreparationPlan(); var request = InputPreparationRequest();
            for (int variant = 0; variant < 4; variant++)
            {
                var pair = InputPreparationPair.Create();
                int sdkTouches = 0;
                InputPreparationPoisonSdk(pair, () => sdkTouches++);
                ManagementBaseObject parameters = variant == 0 || variant == 3 ? null : pair.Parameters;
                ManagementBaseObject buffer = variant == 1 || variant == 3 ? null : variant == 2 ? pair.Parameters : pair.Buffer;
                Equal(WsabiWmiWindowsInputPreparationStatus.ObjectsMissingOrAliased,
                    WsabiWmiWindowsInputPreparation.Populate(plan, request, parameters, buffer));
                Equal(0, sdkTouches); InputPreparationAssertUntouched(pair);
                InputPreparationResetSdk(pair);
                Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                    WsabiWmiWindowsInputPreparation.Populate(plan, request, pair.Parameters, pair.Buffer));
                InputPreparationAssertBorrowed(pair);
            }
        });

        Add("Windows input preparation validates all metadata before ordered detached writes without reading property values", () =>
        {
            var plan = InputPreparationPlan(); var request = InputPreparationRequest();
            var pair = InputPreparationPair.Create();
            var order = new List<string>();
            bool inputSeen = false, bytesSeen = false, classSeen = false;
            byte[] assignedBytes = null; object assignedBuffer = null;
            var parameterProperties = pair.Parameters.Properties;
            var bufferProperties = pair.Buffer.Properties;
            pair.Parameters.OnGetClassPath = () => throw new InvalidOperationException("PRIVATE-SDK parameter class is not required");
            pair.Buffer.ClassPath = new ManagementPath("dAtAbUfFeR") { OnGetClassName = () => { classSeen = true; return "dAtAbUfFeR"; } };
            parameterProperties.OnRead = name => { Equal("inData", name); inputSeen = true; return pair.Input; };
            bufferProperties.OnRead = name => { Equal("Bytes", name); bytesSeen = true; return pair.Bytes; };
            pair.Input.OnGetValue = () => throw new InvalidOperationException("PRIVATE-SDK input Value must remain unread");
            pair.Bytes.OnGetValue = () => throw new InvalidOperationException("PRIVATE-SDK Bytes Value must remain unread");
            pair.Bytes.BeforeSetValue = value =>
            {
                Check(inputSeen && bytesSeen && classSeen, "a value write preceded complete metadata validation");
                Check(value != null && value.GetType() == typeof(byte[]), "byte property did not receive an exact byte array");
                order.Add("Bytes"); assignedBytes = (byte[])value;
            };
            pair.Input.BeforeSetValue = value =>
            {
                Equal(1, order.Count); Equal("Bytes", order[0]);
                order.Add("inData"); assignedBuffer = value;
            };
            Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                WsabiWmiWindowsInputPreparation.Populate(plan, request, pair.Parameters, pair.Buffer));
            Check(order.SequenceEqual(new[] { "Bytes", "inData" }) && ReferenceEquals(assignedBuffer, pair.Buffer),
                "input object assignment did not follow the detached bytes assignment");
            Check(assignedBytes.SequenceEqual(BoundChannelRequest()), "input preparation changed the existing synthetic envelope");
            assignedBytes[5] ^= 0xff;
            Check(request.Frame.SequenceEqual(BoundChannelRequest()), "assigned SDK byte array aliases the request envelope");
            byte[] externalRequest = request.Frame; externalRequest[6] ^= 0xff;
            Check(assignedBytes[6] != externalRequest[6], "external request view aliases assigned bytes");
            Equal(1, pair.Input.ValueWrites); Equal(1, pair.Bytes.ValueWrites);
            Equal(0, pair.Input.ValueReads); Equal(0, pair.Bytes.ValueReads);
            Check(!plan.IsHardwareObservation && !plan.CanInvokeMethods && !plan.CanReadHardware && !plan.CanWriteHardware,
                "populated in-memory objects became hardware authority");
            InputPreparationAssertBorrowed(pair);
        });

        Add("Windows input preparation rejects class names missing fields and extra properties before either value write", () =>
        {
            var changes = new Action<InputPreparationPair>[]
            {
                pair => pair.Buffer.ClassPath = null,
                pair => pair.Buffer.ClassPath = new ManagementPath(null),
                pair => pair.Buffer.ClassPath = new ManagementPath("OtherClass"),
                pair => pair.Buffer.ClassPath = new ManagementPath("DataBufferExtra"),
                pair => pair.Parameters.Properties = null,
                pair => pair.Buffer.Properties = null,
                pair => pair.Parameters.Properties = new PropertyDataCollection(),
                pair => pair.Buffer.Properties = new PropertyDataCollection(),
                pair => pair.Parameters.Properties.Add("extra", CimType.String, false, null),
                pair => pair.Buffer.Properties.Add("extra", CimType.String, false, null),
                pair => { pair.Parameters.Properties = new PropertyDataCollection(); pair.Parameters.Properties.Add("other", pair.Input); },
                pair => { pair.Buffer.Properties = new PropertyDataCollection(); pair.Buffer.Properties.Add("other", pair.Bytes); }
            };
            foreach (var change in changes)
            {
                var pair = InputPreparationPair.Create(); change(pair);
                Equal(WsabiWmiWindowsInputPreparationStatus.ShapeMismatch,
                    WsabiWmiWindowsInputPreparation.Populate(InputPreparationPlan(), InputPreparationRequest(), pair.Parameters, pair.Buffer));
                InputPreparationAssertUntouched(pair); InputPreparationAssertBorrowed(pair);
                Equal(WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed,
                    WsabiWmiWindowsInputPreparation.Populate(InputPreparationPlan(), InputPreparationRequest(), pair.Parameters, pair.Buffer));
            }
        });

        Add("Windows input preparation requires scalar Object inData and UInt8 array Bytes metadata before either write", () =>
        {
            var changes = new Action<InputPreparationPair>[]
            {
                pair => pair.Input.Type = CimType.String,
                pair => pair.Input.Type = CimType.UInt8,
                pair => pair.Input.IsArray = true,
                pair => pair.Bytes.Type = CimType.String,
                pair => pair.Bytes.Type = CimType.Object,
                pair => pair.Bytes.Type = CimType.SInt32,
                pair => pair.Bytes.IsArray = false
            };
            foreach (var change in changes)
            {
                var pair = InputPreparationPair.Create(); change(pair);
                pair.Input.OnGetValue = () => throw new InvalidOperationException("PRIVATE-SDK malformed input Value");
                pair.Bytes.OnGetValue = () => throw new InvalidOperationException("PRIVATE-SDK malformed Bytes Value");
                Equal(WsabiWmiWindowsInputPreparationStatus.ShapeMismatch,
                    WsabiWmiWindowsInputPreparation.Populate(InputPreparationPlan(), InputPreparationRequest(), pair.Parameters, pair.Buffer));
                InputPreparationAssertUntouched(pair); InputPreparationAssertBorrowed(pair);
                Equal(WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed,
                    WsabiWmiWindowsInputPreparation.Populate(InputPreparationPlan(), InputPreparationRequest(), pair.Parameters, pair.Buffer));
            }
        });

        Add("Windows input preparation converts SDK metadata getter failures to fixed status and retains both object claims", () =>
        {
            var changes = new Action<InputPreparationPair>[]
            {
                pair => pair.Parameters.OnGetProperties = () => throw new InvalidOperationException("PRIVATE-SDK parameter properties"),
                pair => pair.Buffer.OnGetClassPath = () => throw new InvalidOperationException("PRIVATE-SDK class path"),
                pair => pair.Buffer.ClassPath.OnGetClassName = () => throw new InvalidOperationException("PRIVATE-SDK class name"),
                pair => pair.Buffer.OnGetProperties = () => throw new InvalidOperationException("PRIVATE-SDK buffer properties"),
                pair => pair.Parameters.Properties.OnRead = name => throw new InvalidOperationException("PRIVATE-SDK input lookup"),
                pair => pair.Buffer.Properties.OnRead = name => throw new InvalidOperationException("PRIVATE-SDK Bytes lookup")
            };
            foreach (var change in changes)
            {
                var pair = InputPreparationPair.Create(); change(pair);
                Equal(WsabiWmiWindowsInputPreparationStatus.PropertyAccessFailed,
                    WsabiWmiWindowsInputPreparation.Populate(InputPreparationPlan(), InputPreparationRequest(), pair.Parameters, pair.Buffer));
                InputPreparationAssertUntouched(pair); InputPreparationAssertBorrowed(pair);
                Equal(WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed,
                    WsabiWmiWindowsInputPreparation.Populate(InputPreparationPlan(), InputPreparationRequest(), pair.Parameters, pair.Buffer));
            }
        });

        Add("Windows input preparation setter failure preserves write order without rollback or implicit value reads", () =>
        {
            foreach (bool firstSetter in new[] { true, false })
            {
                var pair = InputPreparationPair.Create();
                var committed = new List<string>();
                pair.Bytes.AfterSetValue = value => committed.Add("Bytes");
                pair.Input.AfterSetValue = value => committed.Add("inData");
                if (firstSetter) pair.Bytes.BeforeSetValue = value => throw new InvalidOperationException("PRIVATE-SDK byte setter");
                else pair.Input.BeforeSetValue = value => throw new InvalidOperationException("PRIVATE-SDK input setter");
                Equal(WsabiWmiWindowsInputPreparationStatus.PropertyAccessFailed,
                    WsabiWmiWindowsInputPreparation.Populate(InputPreparationPlan(), InputPreparationRequest(), pair.Parameters, pair.Buffer));
                Equal(1, pair.Bytes.ValueWrites); Equal(firstSetter ? 0 : 1, pair.Input.ValueWrites);
                Check(committed.SequenceEqual(firstSetter ? new string[0] : new[] { "Bytes" }), "setter failure triggered later writes or rollback");
                Equal(0, pair.Input.ValueReads); Equal(0, pair.Bytes.ValueReads);
                Equal(WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed,
                    WsabiWmiWindowsInputPreparation.Populate(InputPreparationPlan(), InputPreparationRequest(), pair.Parameters, pair.Buffer));
                Equal(1, pair.Bytes.ValueWrites); Equal(firstSetter ? 0 : 1, pair.Input.ValueWrites);
                InputPreparationAssertBorrowed(pair);
            }
        });

        Add("Windows input preparation treats mutating setter throws as used objects without retry or rollback", () =>
        {
            foreach (bool firstSetter in new[] { true, false })
            {
                var pair = InputPreparationPair.Create();
                byte[] committedBytes = null; object committedInput = null;
                pair.Bytes.AfterSetValue = value =>
                {
                    committedBytes = (byte[])value;
                    if (firstSetter) throw new InvalidOperationException("PRIVATE-SDK byte setter after mutation");
                };
                pair.Input.AfterSetValue = value =>
                {
                    committedInput = value;
                    throw new InvalidOperationException("PRIVATE-SDK input setter after mutation");
                };
                Equal(WsabiWmiWindowsInputPreparationStatus.PropertyAccessFailed,
                    WsabiWmiWindowsInputPreparation.Populate(InputPreparationPlan(), InputPreparationRequest(), pair.Parameters, pair.Buffer));
                Check(committedBytes != null && committedBytes.SequenceEqual(BoundChannelRequest()), "partial byte mutation was hidden or overwritten");
                Check(firstSetter ? committedInput == null : ReferenceEquals(committedInput, pair.Buffer), "input mutation did not follow the failed write position");
                Equal(1, pair.Bytes.ValueWrites); Equal(firstSetter ? 0 : 1, pair.Input.ValueWrites);
                Equal(WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed,
                    WsabiWmiWindowsInputPreparation.Populate(InputPreparationPlan(), InputPreparationRequest(), pair.Parameters, pair.Buffer));
                Equal(1, pair.Bytes.ValueWrites); Equal(firstSetter ? 0 : 1, pair.Input.ValueWrites);
                Equal(0, pair.Input.ValueReads); Equal(0, pair.Bytes.ValueReads);
                InputPreparationAssertBorrowed(pair);
            }
        });

        AddAsync("Windows input preparation claims both root identities atomically before SDK access under concurrent callers", async () =>
        {
            using (var releaseMetadata = new ManualResetEventSlim())
            {
                var pair = InputPreparationPair.Create(new InputPreparationPoisonObject(), new InputPreparationPoisonObject());
                var plan = InputPreparationPlan(); var request = InputPreparationRequest();
                var metadataEntered = CooperativeCompletion();
                var path = pair.Buffer.ClassPath;
                pair.Buffer.OnGetClassPath = () =>
                {
                    metadataEntered.TrySetResult(true); InputPreparationWait(releaseMetadata); return path;
                };
                var first = Task.Run(() => WsabiWmiWindowsInputPreparation.Populate(plan, request, pair.Parameters, pair.Buffer));
                Task<WsabiWmiWindowsInputPreparationStatus> second = null;
                try
                {
                    await CooperativeAwait(metadataEntered.Task);
                    second = Task.Run(() => WsabiWmiWindowsInputPreparation.Populate(plan, request, pair.Parameters, pair.Buffer));
                    await CooperativeAwait(second);
                    Equal(WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed, await second);
                    Check(!first.IsCompleted, "metadata getter gate did not keep the first preparation active");
                    InputPreparationAssertUntouched(pair);
                    releaseMetadata.Set(); await CooperativeAwait(first);
                    Equal(WsabiWmiWindowsInputPreparationStatus.Populated, await first);
                    Equal(1, pair.Input.ValueWrites); Equal(1, pair.Bytes.ValueWrites);
                    InputPreparationAssertBorrowed(pair);
                }
                finally
                {
                    releaseMetadata.Set(); await CooperativeAwait(first);
                    if (second != null) await CooperativeAwait(second);
                }
            }
        });

        Add("Windows input preparation overlap rejection never claims the other fresh root or inspects reused metadata", () =>
        {
            var plan = InputPreparationPlan(); var request = InputPreparationRequest();
            foreach (bool reuseParameters in new[] { true, false })
            {
                var used = InputPreparationPair.Create();
                Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                    WsabiWmiWindowsInputPreparation.Populate(plan, request, used.Parameters, used.Buffer));
                var fresh = InputPreparationPair.Create();
                int sdkTouches = 0;
                InputPreparationPoisonSdk(used, () => sdkTouches++);
                InputPreparationPoisonSdk(fresh, () => sdkTouches++);
                Equal(WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed,
                    WsabiWmiWindowsInputPreparation.Populate(plan, request,
                        reuseParameters ? used.Parameters : fresh.Parameters, reuseParameters ? fresh.Buffer : used.Buffer));
                Equal(0, sdkTouches); InputPreparationAssertUntouched(fresh);
                InputPreparationResetSdk(fresh);
                Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                    WsabiWmiWindowsInputPreparation.Populate(plan, request, fresh.Parameters, fresh.Buffer));
                Equal(1, fresh.Input.ValueWrites); Equal(1, fresh.Bytes.ValueWrites);
                InputPreparationAssertBorrowed(used); InputPreparationAssertBorrowed(fresh);
            }
        });
    }

    private static WsabiWmiSingleReadPlan InputPreparationPlan()
        => SingleReadPlanCreate(SingleReadTarget(new object()));

    private static WsabiWmiMethodRequest InputPreparationRequest()
    {
        WsabiWmiMethodRequest request;
        Check(BinderCreate().TryWrapFrame(BoundChannelRequest(), out request), "existing synthetic input fixture was rejected");
        return request;
    }

    private static void InputPreparationAssertUntouched(InputPreparationPair pair)
    {
        Equal(0, pair.Input.ValueReads); Equal(0, pair.Bytes.ValueReads);
        Equal(0, pair.Input.ValueWrites); Equal(0, pair.Bytes.ValueWrites);
    }

    private static void InputPreparationAssertBorrowed(InputPreparationPair pair)
    {
        Equal(0, pair.Parameters.ConcreteDisposeCalls); Equal(0, pair.Parameters.ComponentDisposeCalls);
        Equal(0, pair.Buffer.ConcreteDisposeCalls); Equal(0, pair.Buffer.ComponentDisposeCalls);
    }

    private static void InputPreparationPoisonSdk(InputPreparationPair pair, Action touched)
    {
        pair.Parameters.OnGetProperties = () => { touched(); throw new InvalidOperationException("PRIVATE-SDK unexpected parameter properties"); };
        pair.Parameters.OnGetClassPath = () => { touched(); throw new InvalidOperationException("PRIVATE-SDK unexpected parameter class"); };
        pair.Buffer.OnGetProperties = () => { touched(); throw new InvalidOperationException("PRIVATE-SDK unexpected buffer properties"); };
        pair.Buffer.OnGetClassPath = () => { touched(); throw new InvalidOperationException("PRIVATE-SDK unexpected buffer class"); };
    }

    private static void InputPreparationResetSdk(InputPreparationPair pair)
    {
        pair.Parameters.OnGetProperties = null; pair.Parameters.OnGetClassPath = null;
        pair.Buffer.OnGetProperties = null; pair.Buffer.OnGetClassPath = null;
    }

    private static void InputPreparationWait(ManualResetEventSlim release)
    {
        if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("Stand-in metadata gate was not released.");
    }

    private sealed class InputPreparationPair
    {
        internal ManagementBaseObject Parameters, Buffer;
        internal PropertyData Input, Bytes;

        internal static InputPreparationPair Create(ManagementBaseObject parameters = null, ManagementBaseObject buffer = null)
        {
            var pair = new InputPreparationPair
            {
                Parameters = parameters ?? new ManagementBaseObject(),
                Buffer = buffer ?? new ManagementBaseObject { ClassPath = new ManagementPath("DataBuffer") }
            };
            // Explicitly supplied poison objects have the same fixed shape.
            pair.Buffer.ClassPath = new ManagementPath("DataBuffer");
            pair.Input = pair.Parameters.Properties.Add("inData", CimType.Object, false, null);
            pair.Bytes = pair.Buffer.Properties.Add("Bytes", CimType.UInt8, true, null);
            return pair;
        }
    }

    private sealed class InputPreparationPoisonObject : ManagementBaseObject
    {
        public override bool Equals(object value) => throw new InvalidOperationException("Input preparation must not call provider equality.");
        public override int GetHashCode() => throw new InvalidOperationException("Input preparation must not call provider hashing.");
        public override string ToString() => throw new InvalidOperationException("Input preparation must not call provider text conversion.");
    }
}
