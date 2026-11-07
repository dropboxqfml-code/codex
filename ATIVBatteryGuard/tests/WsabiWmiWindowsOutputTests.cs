using System;
using System.Linq;
using System.Management;
using ATIVBatteryGuard.WmiInterop;

internal static partial class Program
{
    // The exact production reader is linked against test-only SDK stand-ins.
    // These tests establish our shape/ownership logic, not real SDK behavior.
    private static void RegisterWsabiWmiWindowsOutputTests()
    {
        Add("Windows output reader copies scalar DataBuffer bytes and leaves the root owned by its caller", () =>
        {
            byte[] original = BoundChannelReply();
            ManagementBaseObject embedded;
            var root = WindowsOutputFixture(original, out embedded);
            root.OnGetClassPath = () => throw new InvalidOperationException("PRIVATE-SDK root class must remain unread");
            byte[] result = WsabiWmiWindowsOutputReader.Read(root);
            Check(result.SequenceEqual(original) && !ReferenceEquals(result, original), "reader did not detach its byte view");
            original[0] ^= 0xff;
            Check(result[0] != original[0], "reader result aliases SDK property bytes");
            Equal(1, root.Properties["outData"].ValueReads);
            Equal(1, embedded.Properties["Bytes"].ValueReads);
            Equal(1, embedded.ConcreteDisposeCalls); Equal(0, embedded.ComponentDisposeCalls);
            WindowsOutputAssertRootOwned(root);
        });

        Add("Windows output reader rejects missing or non scalar object metadata without reading its Value", () =>
        {
            WindowsOutputReject(null);
            var missing = new ManagementBaseObject();
            WindowsOutputReject(missing); WindowsOutputAssertRootOwned(missing);
            foreach (var shape in new[]
            {
                new { Type = CimType.String, Array = false },
                new { Type = CimType.UInt8, Array = true },
                new { Type = CimType.Object, Array = true }
            })
            {
                var property = new PropertyData(shape.Type, shape.Array, null)
                {
                    OnGetValue = () => throw new InvalidOperationException("PRIVATE-SDK outer Value must remain unread")
                };
                var root = new ManagementBaseObject(); root.Properties.Add("outData", property);
                WindowsOutputReject(root);
                Equal(0, property.ValueReads); WindowsOutputAssertRootOwned(root);
            }
        });

        Add("Windows output reader requires an actual embedded object and rejects a root self reference without disposing it", () =>
        {
            foreach (object value in new object[]
            {
                null, DBNull.Value, "DataBuffer", new object(), new ManagementBaseObject[0], new byte[0]
            })
            {
                var root = WindowsOutputRoot(value);
                WindowsOutputReject(root);
                Equal(1, root.Properties["outData"].ValueReads); WindowsOutputAssertRootOwned(root);
            }
            var self = new ManagementBaseObject();
            self.Properties.Add("outData", CimType.Object, false, self);
            self.OnGetClassPath = () => throw new InvalidOperationException("PRIVATE-SDK self class must remain unread");
            WindowsOutputReject(self);
            WindowsOutputAssertRootOwned(self);
        });

        Add("Windows output reader validates embedded DataBuffer class before touching Bytes", () =>
        {
            foreach (string className in new[] { null, "", "OtherClass", "__PARAMETERS", "DataBufferExtra" })
            {
                var embedded = new ManagementBaseObject { ClassPath = new ManagementPath(className) };
                embedded.OnGetProperties = () => throw new InvalidOperationException("PRIVATE-SDK wrong class Bytes must remain unread");
                var root = WindowsOutputRoot(embedded);
                WindowsOutputReject(root);
                Equal(1, embedded.ClassPath.ClassNameReads);
                Equal(1, embedded.ConcreteDisposeCalls); Equal(0, embedded.ComponentDisposeCalls);
                WindowsOutputAssertRootOwned(root);
            }
        });

        Add("Windows output reader requires UInt8 array metadata before reading Bytes Value", () =>
        {
            foreach (var shape in new[]
            {
                new { Type = CimType.UInt8, Array = false },
                new { Type = CimType.String, Array = true },
                new { Type = CimType.Object, Array = true },
                new { Type = CimType.SInt32, Array = true }
            })
            {
                var property = new PropertyData(shape.Type, shape.Array, null)
                {
                    OnGetValue = () => throw new InvalidOperationException("PRIVATE-SDK Bytes Value must remain unread")
                };
                var embedded = new ManagementBaseObject { ClassPath = new ManagementPath("DataBuffer") };
                embedded.Properties.Add("Bytes", property);
                var root = WindowsOutputRoot(embedded);
                WindowsOutputReject(root);
                Equal(0, property.ValueReads);
                Equal(1, embedded.ConcreteDisposeCalls); Equal(0, embedded.ComponentDisposeCalls);
                WindowsOutputAssertRootOwned(root);
            }
            var missing = new ManagementBaseObject { ClassPath = new ManagementPath("DataBuffer") };
            WindowsOutputReject(WindowsOutputRoot(missing));
            Equal(1, missing.ConcreteDisposeCalls); Equal(0, missing.ComponentDisposeCalls);
        });

        Add("Windows output reader rejects coercible and differently shaped arrays despite UInt8 array metadata", () =>
        {
            foreach (object value in new object[]
            {
                null, DBNull.Value, "0102", new object(), new int[] { 1, 2 }, new sbyte[] { 1, 2 },
                new object[] { (byte)1, (byte)2 }, new byte[1, 2], new byte[][] { new byte[] { 1, 2 } },
                Array.CreateInstance(typeof(byte), new[] { 21 }, new[] { 1 })
            })
            {
                var embedded = new ManagementBaseObject { ClassPath = new ManagementPath("DataBuffer") };
                var property = embedded.Properties.Add("Bytes", CimType.UInt8, true, value);
                var root = WindowsOutputRoot(embedded);
                WindowsOutputReject(root);
                Equal(1, property.ValueReads);
                Equal(1, embedded.ConcreteDisposeCalls); Equal(0, embedded.ComponentDisposeCalls);
                WindowsOutputAssertRootOwned(root);
            }
        });

        Add("Windows output reader keeps its 4096 byte retention cap separate from frame acceptance", () =>
        {
            foreach (int length in new[] { 0, 1, 16, 21, 4096 })
            {
                byte[] original = Enumerable.Range(0, length).Select(index => (byte)index).ToArray();
                ManagementBaseObject embedded;
                var root = WindowsOutputFixture(original, out embedded);
                byte[] result = WsabiWmiWindowsOutputReader.Read(root);
                Equal(length, result.Length);
                Check(result.SequenceEqual(original) && !ReferenceEquals(result, original), "reader padded truncated or retained the byte view");
                Equal(1, embedded.ConcreteDisposeCalls); Equal(0, embedded.ComponentDisposeCalls);
                WindowsOutputAssertRootOwned(root);
            }
            ManagementBaseObject oversized;
            var oversizedRoot = WindowsOutputFixture(new byte[4097], out oversized);
            WindowsOutputReject(oversizedRoot);
            Equal(1, oversized.ConcreteDisposeCalls); Equal(0, oversized.ComponentDisposeCalls);
            WindowsOutputAssertRootOwned(oversizedRoot);
        });

        Add("Windows output reader copies before concrete embedded Dispose and rejects a Dispose failure", () =>
        {
            byte[] original = BoundChannelReply();
            byte[] expected = (byte[])original.Clone();
            ManagementBaseObject embedded;
            var root = WindowsOutputFixture(original, out embedded);
            embedded.OnDispose = () => Array.Clear(original, 0, original.Length);
            byte[] result = WsabiWmiWindowsOutputReader.Read(root);
            Check(result.SequenceEqual(expected) && original.All(value => value == 0), "embedded Dispose ran before the detached copy");
            Equal(1, embedded.ConcreteDisposeCalls); Equal(0, embedded.ComponentDisposeCalls);
            WindowsOutputAssertRootOwned(root);

            ManagementBaseObject throwing;
            var throwingRoot = WindowsOutputFixture(BoundChannelReply(), out throwing);
            throwing.OnDispose = () => throw new InvalidOperationException("PRIVATE-SDK embedded dispose detail");
            WindowsOutputReject(throwingRoot);
            Equal(1, throwing.ConcreteDisposeCalls); Equal(0, throwing.ComponentDisposeCalls);
            WindowsOutputAssertRootOwned(throwingRoot);

            var boundary = new ManagementBaseObject();
            ((IDisposable)boundary).Dispose();
            Equal(0, boundary.ConcreteDisposeCalls); Equal(1, boundary.ComponentDisposeCalls);
        });

        Add("Windows output reader hides property class and value getter errors while disposing only acquired embedded objects", () =>
        {
            string fixedMessage = null;
            var rootFailure = new ManagementBaseObject
            {
                OnGetProperties = () => throw new InvalidOperationException("PRIVATE-SDK root property detail")
            };
            fixedMessage = WindowsOutputReject(rootFailure).Message;
            WindowsOutputAssertRootOwned(rootFailure);

            var valueFailure = WindowsOutputRoot(null);
            valueFailure.Properties["outData"].OnGetValue = () => throw new InvalidOperationException("PRIVATE-SDK outer getter detail");
            Equal(fixedMessage, WindowsOutputReject(valueFailure).Message);
            WindowsOutputAssertRootOwned(valueFailure);

            for (int failure = 0; failure < 4; failure++)
            {
                ManagementBaseObject embedded;
                var root = WindowsOutputFixture(BoundChannelReply(), out embedded);
                switch (failure)
                {
                    case 0:
                        embedded.OnGetClassPath = () => throw new InvalidOperationException("PRIVATE-SDK class path detail");
                        break;
                    case 1:
                        embedded.ClassPath.OnGetClassName = () => throw new InvalidOperationException("PRIVATE-SDK class name detail");
                        break;
                    case 2:
                        embedded.OnGetProperties = () => throw new InvalidOperationException("PRIVATE-SDK embedded property detail");
                        break;
                    default:
                        embedded.Properties["Bytes"].OnGetValue = () => throw new InvalidOperationException("PRIVATE-SDK bytes getter detail");
                        break;
                }
                Equal(fixedMessage, WindowsOutputReject(root).Message);
                Equal(1, embedded.ConcreteDisposeCalls); Equal(0, embedded.ComponentDisposeCalls);
                WindowsOutputAssertRootOwned(root);
            }
        });
    }

    private static ManagementBaseObject WindowsOutputFixture(byte[] bytes, out ManagementBaseObject embedded)
    {
        embedded = new ManagementBaseObject { ClassPath = new ManagementPath("DataBuffer") };
        embedded.Properties.Add("Bytes", CimType.UInt8, true, bytes);
        return WindowsOutputRoot(embedded);
    }

    private static ManagementBaseObject WindowsOutputRoot(object embedded)
    {
        var root = new ManagementBaseObject();
        root.Properties.Add("outData", CimType.Object, false, embedded);
        return root;
    }

    private static InvalidOperationException WindowsOutputReject(ManagementBaseObject root)
    {
        try { WsabiWmiWindowsOutputReader.Read(root); }
        catch (InvalidOperationException error)
        {
            Check(error.InnerException == null && !error.Message.Contains("PRIVATE-SDK"), "reader leaked an SDK getter or disposal exception");
            return error;
        }
        throw new InvalidOperationException("Expected a fixed Windows WMI output failure.");
    }

    private static void WindowsOutputAssertRootOwned(ManagementBaseObject root)
    {
        Equal(0, root.ConcreteDisposeCalls); Equal(0, root.ComponentDisposeCalls);
    }
}
