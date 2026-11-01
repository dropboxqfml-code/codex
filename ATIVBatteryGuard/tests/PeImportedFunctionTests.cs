using System;
using System.Linq;
using System.Text;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterPeImportedFunctionTests()
    {
        Add("PE32 and PE32+ resolve actual named import thunks without loading modules", () =>
        {
            foreach (bool x64 in new[] { false, true })
            {
                byte[] bytes = FunctionPe(x64, new[] { "CreateFileW", "DeviceIoControl", "LoadLibraryW", "GetProcAddress" });
                var result = PeModuleReader.Read(bytes);
                Check(result.IsValid, result.Error);
                Equal(x64 ? "x64" : "x86", result.Architecture);
                Equal("KERNEL32.dll", result.ImportedModules[0]);
                Equal(4, result.ImportedFunctions.Length);
                Equal("KERNEL32.dll!DeviceIoControl", result.ImportedFunctions[1].DisplayName);
                Check(result.ImportedFunctions.All(f => !f.Ordinal.HasValue), "name interpreted as ordinal");
                Equal(0, result.ExportedNames.Length);
            }
        });
        Add("PE functions preserve module association across import descriptors", () =>
        {
            byte[] bytes = FunctionPe(false, new[] { "CreateFileW" });
            SecondFunctionDescriptor(bytes, false, "ADVAPI32.dll", "CreateServiceW");
            var result = PeModuleReader.Read(bytes);
            Check(result.IsValid, result.Error); Equal(2, result.ImportedModules.Length);
            Equal("ADVAPI32.dll!CreateServiceW", result.ImportedFunctions[1].DisplayName);
        });
        Add("PE ordinal imports preserve zero and maximum ordinal on both architectures", () =>
        {
            foreach (bool x64 in new[] { false, true }) foreach (ushort ordinal in new ushort[] { 0, 65535 })
            {
                var bytes = FunctionPe(x64, new[] { "ignored" });
                FunctionPut64Or32(bytes, 0x1200, (x64 ? 0x8000000000000000UL : 0x80000000UL) | ordinal, x64);
                var result = PeModuleReader.Read(bytes);
                Check(result.IsValid, result.Error); Equal(1, result.ImportedFunctions.Length);
                Equal<int?>(ordinal, result.ImportedFunctions[0].Ordinal);
                Equal(string.Empty, result.ImportedFunctions[0].FunctionName);
                Equal("KERNEL32.dll!#" + ordinal, result.ImportedFunctions[0].DisplayName);
            }
        });
        Add("PE rejects reserved ordinal bits and non RVA 64 bit import pointers", () =>
        {
            foreach (bool x64 in new[] { false, true })
            {
                var bytes = FunctionPe(x64, new[] { "CreateFileW" });
                FunctionPut64Or32(bytes, 0x1200, (x64 ? 0x8000000000000000UL : 0x80000000UL) | 0x10000UL, x64);
                AssertInvalidFunctionPe(bytes);
            }
            var wide = FunctionPe(true, new[] { "CreateFileW" });
            FunctionPut64Or32(wide, 0x1200, 0x100000001UL, true); AssertInvalidFunctionPe(wide);
            FunctionPut64Or32(wide, 0x1200, uint.MaxValue, true); AssertInvalidFunctionPe(wide);
        });
        Add("PE fallback unbound IAT reads names while bound IAT stays explicitly limited", () =>
        {
            foreach (bool x64 in new[] { false, true })
            {
                var bytes = FunctionPe(x64, new[] { "CreateFileW" });
                FunctionPut32(bytes, 0x200, 0); // no OriginalFirstThunk
                var unbound = PeModuleReader.Read(bytes);
                Check(unbound.IsValid, unbound.Error); Equal("CreateFileW", unbound.ImportedFunctions[0].FunctionName);
                FunctionPut32(bytes, 0x204, uint.MaxValue); // binding timestamp
                FunctionPut64Or32(bytes, 0x1200, x64 ? 0x00007ffeff112233UL : 0x77112233UL, x64);
                var bound = PeModuleReader.Read(bytes);
                Check(bound.IsValid, bound.Error); Equal(0, bound.ImportedFunctions.Length);
                Equal("KERNEL32.dll", bound.ImportedModules[0]); Check(bound.Error.Length > 0, "bound table limitation hidden");
            }
        });
        Add("PE malformed thunk or function name discards earlier import observations", () =>
        {
            foreach (bool x64 in new[] { false, true })
            {
                var bytes = FunctionPe(x64, new[] { "CreateFileW", "DeviceIoControl" });
                FunctionPut64Or32(bytes, 0x1200 + (x64 ? 8 : 4), 0x70000000, x64);
                AssertInvalidFunctionPe(bytes);
                bytes = FunctionPe(x64, new[] { "CreateFileW", @"C:\Users\PrivateName\secret" });
                AssertInvalidFunctionPe(bytes);
                bytes = FunctionPe(x64, new[] { new string('a',129) });
                AssertInvalidFunctionPe(bytes);
                bytes = FunctionPe(x64, new[] { "CreateFileW" });
                FunctionPut32(bytes, 0x200, uint.MaxValue - 1); AssertInvalidFunctionPe(bytes);
            }
        });
        Add("PE import function list truncates output but validates remaining thunk rows", () =>
        {
            var bytes = FunctionPe(true, Enumerable.Range(0,300).Select(i => "f" + i.ToString("D3")).ToArray());
            var result = PeModuleReader.Read(bytes);
            Check(result.IsValid, result.Error); Equal(PeModuleInfo.MaximumImportedFunctions, result.ImportedFunctions.Length);
            Check(result.Error.Length > 0, "display limit hidden");
            FunctionPut64Or32(bytes, 0x1200 + 299 * 8, 0x70000000, true);
            AssertInvalidFunctionPe(bytes);
        });
        Add("PE unterminated import thunks stop at bounded work quota", () =>
        {
            foreach (bool x64 in new[] { false,true })
            {
                var bytes = FunctionPe(x64, new string[0]);
                for (int i=0; i<4096; i++) FunctionPut64Or32(bytes, 0x1200+i*(x64?8:4), (x64?0x8000000000000000UL:0x80000000UL)|1, x64);
                AssertInvalidFunctionPe(bytes);
            }
        });
        Add("PE import deduplication respects module casing and function case sensitivity", () =>
        {
            var bytes = FunctionPe(false, new[] { "CreateFileW", "CreateFileW", "createfilew" });
            SecondFunctionDescriptor(bytes, false, "kernel32.dll", "CreateFileW");
            var result = PeModuleReader.Read(bytes);
            Check(result.IsValid, result.Error); Equal(1, result.ImportedModules.Length); Equal(2, result.ImportedFunctions.Length);
            Equal("CreateFileW",result.ImportedFunctions[0].FunctionName); Equal("createfilew",result.ImportedFunctions[1].FunctionName);
        });
        Add("PE import models reject paths and snapshot caller arrays", () =>
        {
            foreach (Action action in new Action[] {
                () => new PeImportedFunction(@"C:\Users\Private\module.dll","Open"),
                () => new PeImportedFunction("kernel32.dll", @"C:\private"),
                () => new PeImportedFunction("kernel32.dll", "x\ny"),
                () => new PeImportedFunction("kernel32.dll", null),
                () => new PeImportedFunction("kernel32.dll", "name", 1),
                () => new PeImportedFunction("kernel32.dll", null, -1),
                () => new PeImportedFunction("kernel32.dll", null, 65536) })
                FunctionThrowsArgument(action);
            var import = new PeImportedFunction("kernel32.dll","CreateFileW");
            var items = new[] { import, import, new PeImportedFunction("KERNEL32.DLL","CreateFileW") };
            var info = new PeModuleInfo(true,false,"x64", importedFunctions:items);
            items[0] = null; info.ImportedFunctions[0] = null;
            Equal(1,info.ImportedFunctions.Length); Equal(import,info.ImportedFunctions[0]);
            Equal(0,new PeModuleInfo(false,false,"x64", importedFunctions:items).ImportedFunctions.Length);
        });
    }

    // Minimal PE structure: one raw section maps file0x200 to RVA0x1000.
    // The ILT is at file0x1200, names at0x400; no executable code is needed.
    private static byte[] FunctionPe(bool x64, string[] names)
    {
        var bytes = new byte[65536];
        FunctionPut16(bytes,0,0x5a4d); FunctionPut32(bytes,0x3c,0x80); FunctionPut32(bytes,0x80,0x4550);
        FunctionPut16(bytes,0x84,x64?(ushort)0x8664:(ushort)0x14c); FunctionPut16(bytes,0x86,1);
        int optionalSize=x64?0xf0:0xe0;
        FunctionPut16(bytes,0x94,(ushort)optionalSize); FunctionPut16(bytes,0x96,0x2102);
        FunctionPut16(bytes,0x98,x64?(ushort)0x20b:(ushort)0x10b); FunctionPut32(bytes,0x98+60,0x200);
        int directories=0x98+(x64?112:96);
        FunctionPut32(bytes,directories-4,16); FunctionPut32(bytes,directories+8,0x1000); FunctionPut32(bytes,directories+12,40);
        int section=0x98+optionalSize;
        FunctionPut32(bytes,section+8,0xfe00); FunctionPut32(bytes,section+12,0x1000);
        FunctionPut32(bytes,section+16,0xfe00); FunctionPut32(bytes,section+20,0x200);
        FunctionPut32(bytes,0x200,0x2000); FunctionPut32(bytes,0x20c,0x1140); FunctionPut32(bytes,0x210,0x2000);
        FunctionWriteName(bytes,0x340,"KERNEL32.dll");
        int cursor=0x400;
        for (int i=0; i<names.Length; i++)
        {
            FunctionPut64Or32(bytes,0x1200+i*(x64?8:4),(ulong)(cursor+0xe00),x64);
            FunctionPut16(bytes,cursor,0); FunctionWriteName(bytes,cursor+2,names[i]); cursor+=names[i].Length+3;
        }
        return bytes;
    }

    private static void SecondFunctionDescriptor(byte[] bytes,bool x64,string module,string function)
    {
        int directories=0x98+(x64?112:96); FunctionPut32(bytes,directories+12,60);
        FunctionPut32(bytes,0x214,0x1400); FunctionPut32(bytes,0x220,0x1300); FunctionPut32(bytes,0x224,0x1400);
        FunctionWriteName(bytes,0x500,module); FunctionPut64Or32(bytes,0x600,0x1500,x64);
        FunctionPut16(bytes,0x700,0); FunctionWriteName(bytes,0x702,function);
    }

    private static void AssertInvalidFunctionPe(byte[] bytes)
    {
        var result = PeModuleReader.Read(bytes);
        Check(!result.IsValid,"malformed PE import accepted"); Equal(0,result.ImportedFunctions.Length);
        Equal(0,result.ImportedModules.Length);
        Check(!result.Error.Contains("PrivateName"),"private import path leaked");
    }

    private static void FunctionPut16(byte[] bytes,int offset,ushort value) { bytes[offset]=(byte)value;bytes[offset+1]=(byte)(value>>8); }
    private static void FunctionPut32(byte[] bytes,int offset,uint value) { for(int i=0;i<4;i++) bytes[offset+i]=(byte)(value>>(8*i)); }
    private static void FunctionPut64Or32(byte[] bytes,int offset,ulong value,bool x64) { for(int i=0;i<(x64?8:4);i++) bytes[offset+i]=(byte)(value>>(8*i)); }
    private static void FunctionWriteName(byte[] bytes,int offset,string value) { var encoded=Encoding.ASCII.GetBytes(value+'\0');Array.Copy(encoded,0,bytes,offset,encoded.Length); }
    private static void FunctionThrowsArgument(Action action)
    {
        try { action(); } catch(ArgumentException) { return; }
        throw new Exception("invalid import model accepted");
    }
}
