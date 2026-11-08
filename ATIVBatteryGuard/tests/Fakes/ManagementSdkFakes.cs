using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Threading;

// Test-only stand-ins. The portable project compiles the production reader and
// binding against these shapes; this is not execution of System.Management.
namespace System.Management
{
    public enum CimType { SInt32 = 3, String = 8, Object = 13, UInt8 = 17 }
    public enum ManagementStatus
    {
        NoError = 0,
        NotFound = unchecked((int)0x80041002),
        AccessDenied = unchecked((int)0x80041003),
        CallCanceled = unchecked((int)0x80041032)
    }

    public sealed class PropertyData
    {
        private object value;
        private int valueReads, valueWrites;
        public CimType Type { get; set; }
        public bool IsArray { get; set; }
        public Func<object> OnGetValue;
        public Action<object> BeforeSetValue;
        public Action<object> AfterSetValue;
        public int ValueReads => Volatile.Read(ref valueReads);
        public int ValueWrites => Volatile.Read(ref valueWrites);
        public object Value
        {
            get
            {
                Interlocked.Increment(ref valueReads);
                return OnGetValue == null ? value : OnGetValue();
            }
            set
            {
                Interlocked.Increment(ref valueWrites);
                BeforeSetValue?.Invoke(value);
                this.value = value;
                AfterSetValue?.Invoke(value);
            }
        }

        public PropertyData(CimType type, bool isArray, object value)
        {
            Type = type; IsArray = isArray; this.value = value;
        }
    }

    public sealed class PropertyDataCollection
    {
        private readonly Dictionary<string, PropertyData> values =
            new Dictionary<string, PropertyData>(StringComparer.Ordinal);
        private int reads;
        public Func<string, PropertyData> OnRead;
        public int Reads => Volatile.Read(ref reads);
        public int Count => values.Count;
        public PropertyData this[string name]
        {
            get
            {
                Interlocked.Increment(ref reads);
                if (OnRead != null) return OnRead(name);
                PropertyData value;
                return values.TryGetValue(name, out value) ? value : null;
            }
        }

        public void Add(string name, PropertyData property) { values.Add(name, property); }
        public PropertyData Add(string name, CimType type, bool isArray, object value)
        {
            var property = new PropertyData(type, isArray, value);
            Add(name, property); return property;
        }
    }

    public sealed class ManagementPath
    {
        private string className;
        private string server = ".", namespacePath = @"root\WMI";
        private bool isInstance = true;
        private int classNameReads;
        public Func<string> OnGetClassName;
        public Func<string> OnGetServer, OnGetNamespacePath;
        public Func<bool> OnGetIsInstance;
        public string Server { get => OnGetServer == null ? server : OnGetServer(); set => server = value; }
        public string NamespacePath { get => OnGetNamespacePath == null ? namespacePath : OnGetNamespacePath(); set => namespacePath = value; }
        public bool IsInstance { get => OnGetIsInstance == null ? isInstance : OnGetIsInstance(); set => isInstance = value; }
        public int ClassNameReads => Volatile.Read(ref classNameReads);
        public string ClassName
        {
            get
            {
                Interlocked.Increment(ref classNameReads);
                return OnGetClassName == null ? className : OnGetClassName();
            }
            set { className = value; }
        }

        public ManagementPath(string className = null) { this.className = className; }
    }

    public sealed class ManagementScope
    {
        private ManagementPath path = new ManagementPath();
        private bool connected = true;
        public Func<ManagementPath> OnGetPath;
        public Func<bool> OnGetIsConnected;
        public ManagementPath Path { get => OnGetPath == null ? path : OnGetPath(); set => path = value; }
        public bool IsConnected { get => OnGetIsConnected == null ? connected : OnGetIsConnected(); set => connected = value; }
    }

    public sealed class InvokeMethodOptions { }

    public class ManagementObject : ManagementBaseObject
    {
        private ManagementScope scope = new ManagementScope();
        private ManagementPath path = new ManagementPath("WmiAcpiMethod");
        private int invokeCalls;
        public Func<ManagementScope> OnGetScope;
        public Func<ManagementPath> OnGetPath;
        public Action<ManagementOperationObserver, string, ManagementBaseObject, InvokeMethodOptions> OnInvoke;
        public int InvokeCalls => Volatile.Read(ref invokeCalls);
        public ManagementScope Scope { get => OnGetScope == null ? scope : OnGetScope(); set => scope = value; }
        public virtual ManagementPath Path { get => OnGetPath == null ? path : OnGetPath(); set => path = value; }
        public void InvokeMethod(ManagementOperationObserver observer, string method,
            ManagementBaseObject input, InvokeMethodOptions options)
        {
            Interlocked.Increment(ref invokeCalls); OnInvoke?.Invoke(observer, method, input, options);
        }
    }

    public class ManagementBaseObject : Component
    {
        private PropertyDataCollection properties = new PropertyDataCollection();
        private ManagementPath classPath = new ManagementPath();
        private int concreteDisposeCalls, componentDisposeCalls;
        public Func<PropertyDataCollection> OnGetProperties;
        public Func<ManagementPath> OnGetClassPath;
        public Action OnDispose;
        public Action OnComponentDispose;
        public int ConcreteDisposeCalls => Volatile.Read(ref concreteDisposeCalls);
        public int ComponentDisposeCalls => Volatile.Read(ref componentDisposeCalls);
        public PropertyDataCollection Properties
        {
            get { return OnGetProperties == null ? properties : OnGetProperties(); }
            set { properties = value; }
        }
        public ManagementPath ClassPath
        {
            get { return OnGetClassPath == null ? classPath : OnGetClassPath(); }
            set { classPath = value; }
        }

        // Deliberately reproduces the relevant Component/new-Dispose shape:
        // an IDisposable-constrained call is not this concrete method.
        public new void Dispose()
        {
            Interlocked.Increment(ref concreteDisposeCalls); OnDispose?.Invoke();
        }
        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                Interlocked.Increment(ref componentDisposeCalls); OnComponentDispose?.Invoke();
            }
            base.Dispose(disposing);
        }
    }

    public delegate void ObjectReadyEventHandler(object sender, ObjectReadyEventArgs args);
    public delegate void CompletedEventHandler(object sender, CompletedEventArgs args);

    public sealed class ObjectReadyEventArgs : EventArgs
    {
        private readonly ManagementBaseObject value;
        private int newObjectReads, contextReads;
        public Func<ManagementBaseObject> OnGetNewObject;
        public Func<object> OnGetContext;
        public int NewObjectReads => Volatile.Read(ref newObjectReads);
        public int ContextReads => Volatile.Read(ref contextReads);
        public ManagementBaseObject NewObject
        {
            get
            {
                Interlocked.Increment(ref newObjectReads);
                return OnGetNewObject == null ? value : OnGetNewObject();
            }
        }
        public object Context
        {
            get { Interlocked.Increment(ref contextReads); return OnGetContext?.Invoke(); }
        }
        public ObjectReadyEventArgs(ManagementBaseObject value) { this.value = value; }
    }

    public sealed class CompletedEventArgs : EventArgs
    {
        private readonly ManagementStatus status;
        private int statusReads, contextReads, statusObjectReads;
        public Func<ManagementStatus> OnGetStatus;
        public Func<object> OnGetContext;
        public Func<ManagementBaseObject> OnGetStatusObject;
        public int StatusReads => Volatile.Read(ref statusReads);
        public int ContextReads => Volatile.Read(ref contextReads);
        public int StatusObjectReads => Volatile.Read(ref statusObjectReads);
        public ManagementStatus Status
        {
            get { Interlocked.Increment(ref statusReads); return OnGetStatus == null ? status : OnGetStatus(); }
        }
        public object Context
        {
            get { Interlocked.Increment(ref contextReads); return OnGetContext?.Invoke(); }
        }
        public ManagementBaseObject StatusObject
        {
            get { Interlocked.Increment(ref statusObjectReads); return OnGetStatusObject?.Invoke(); }
        }
        public CompletedEventArgs(ManagementStatus status) { this.status = status; }
    }

    public class ManagementOperationObserver
    {
        private readonly object gate = new object();
        private ObjectReadyEventHandler objectReady;
        private CompletedEventHandler completed;
        public Action<string> BeforeAdd;
        public Action<string> AfterAdd;
        public Action<string> BeforeRemove;

        public event ObjectReadyEventHandler ObjectReady
        {
            add { BeforeAdd?.Invoke(nameof(ObjectReady)); lock (gate) objectReady += value; AfterAdd?.Invoke(nameof(ObjectReady)); }
            remove { BeforeRemove?.Invoke(nameof(ObjectReady)); lock (gate) objectReady -= value; }
        }
        public event CompletedEventHandler Completed
        {
            add { BeforeAdd?.Invoke(nameof(Completed)); lock (gate) completed += value; AfterAdd?.Invoke(nameof(Completed)); }
            remove { BeforeRemove?.Invoke(nameof(Completed)); lock (gate) completed -= value; }
        }
        public int ObjectReadySubscriberCount
        {
            get { lock (gate) return objectReady == null ? 0 : objectReady.GetInvocationList().Length; }
        }
        public int CompletedSubscriberCount
        {
            get { lock (gate) return completed == null ? 0 : completed.GetInvocationList().Length; }
        }
        public ObjectReadyEventHandler ObjectReadySnapshot { get { lock (gate) return objectReady; } }
        public CompletedEventHandler CompletedSnapshot { get { lock (gate) return completed; } }
        public void EmitObjectReady(ManagementBaseObject value) => EmitObjectReady(new ObjectReadyEventArgs(value));
        public void EmitObjectReady(ObjectReadyEventArgs args) => ObjectReadySnapshot?.Invoke(this, args);
        public void EmitCompleted(ManagementStatus status) => EmitCompleted(new CompletedEventArgs(status));
        public void EmitCompleted(CompletedEventArgs args) => CompletedSnapshot?.Invoke(this, args);
    }
}
