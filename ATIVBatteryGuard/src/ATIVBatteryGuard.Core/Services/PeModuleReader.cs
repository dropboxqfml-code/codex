using System;
using System.Collections.Generic;
using System.Text;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
	public static class PeModuleReader
	{
		private sealed class InvalidPeException : Exception
		{
			public InvalidPeException(string message)
				: base(message)
			{
			}
		}

		private sealed class Section
		{
			public uint Address;

			public uint VirtualSize;

			public uint RawOffset;

			public uint RawSize;

			public ulong Span => Math.Max((ulong)VirtualSize, (ulong)RawSize);
		}

		private sealed class DirectoryEntry
		{
			public uint Address;

			public uint Size;
		}

		private sealed class Reader
		{
			private readonly byte[] data;

			private readonly List<Section> sections = new List<Section>();

			private readonly DirectoryEntry[] directories = new DirectoryEntry[16];

			private uint headersSize;

			private bool is64;

			private bool limited;

			public Reader(byte[] bytes)
			{
				data = bytes;
			}

			public PeModuleInfo Read()
			{
				if (U16(0L) != 23117)
				{
					Fail("지원하는 분석 범위의 x86/x64 PE 파일이 아닙니다.");
				}
				long num = U32(60L);
				if (num < 64 || num > 1048576)
				{
					Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				}
				Range(num, 24L);
				if (U32(num) != 17744)
				{
					Fail("지원하는 분석 범위의 x86/x64 PE 파일이 아닙니다.");
				}
				long num2 = num + 4;
				ushort num3 = U16(num2);
				int num4 = U16(num2 + 2);
				int num5 = U16(num2 + 16);
				if ((U16(num2 + 18) & 2) == 0)
				{
					Fail("지원하는 분석 범위의 x86/x64 PE 파일이 아닙니다.");
				}
				if (num3 != 332 && num3 != 34404)
				{
					Fail("지원하는 분석 범위의 x86/x64 PE 파일이 아닙니다.");
				}
				if (num4 < 1 || num4 > 96)
				{
					Fail("지원하는 PE 메타데이터 분석 한도를 초과했습니다.");
				}
				long num6 = num2 + 20;
				Range(num6, num5);
				ushort num7 = U16(num6);
				is64 = num3 == 34404;
				if (num7 != (is64 ? 523 : 267))
				{
					Fail("지원하는 분석 범위의 x86/x64 PE 파일이 아닙니다.");
				}
				int num8 = (is64 ? 112 : 96);
				if (num5 < num8)
				{
					Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				}
				headersSize = U32(num6 + 60);
				uint num9 = U32(num6 + num8 - 4);
				if (num9 > 16 || (long)num9 * 8L > num5 - num8)
				{
					Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				}
				long num10 = num6 + num5;
				Range(num10, (long)num4 * 40L);
				if (headersSize < num10 + (long)num4 * 40L || headersSize > data.Length)
				{
					Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				}
				for (int i = 0; i < num4; i++)
				{
					long num11 = num10 + (long)i * 40L;
					Section section = new Section
					{
						VirtualSize = U32(num11 + 8),
						Address = U32(num11 + 12),
						RawSize = U32(num11 + 16),
						RawOffset = U32(num11 + 20)
					};
					if (section.Address == 0 || section.Address + section.Span > 4294967296L)
					{
						Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
					}
					if (section.RawSize != 0)
					{
						if (section.RawOffset < headersSize)
						{
							Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
						}
						Range(section.RawOffset, section.RawSize);
					}
					foreach (Section section2 in sections)
					{
						if (Overlaps(section.Address, section.Span, section2.Address, section2.Span) || Overlaps(section.RawOffset, section.RawSize, section2.RawOffset, section2.RawSize))
						{
							Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
						}
					}
					sections.Add(section);
				}
				for (int j = 0; j < directories.Length; j++)
				{
					DirectoryEntry directoryEntry = new DirectoryEntry();
					if (j < num9)
					{
						directoryEntry.Address = U32(num6 + num8 + (long)j * 8L);
						directoryEntry.Size = U32(num6 + num8 + (long)j * 8L + 4);
					}
					directories[j] = directoryEntry;
					if (directoryEntry.Address == 0)
					{
						if (directoryEntry.Size != 0)
						{
							Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
						}
					}
					else if (j == 4)
					{
						Range(directoryEntry.Address, directoryEntry.Size);
					}
					else
					{
						Rva(directoryEntry.Address, (directoryEntry.Size == 0) ? 1 : directoryEntry.Size);
					}
				}
				string[] importedModules = ReadImports();
				string[] exportedNames = ReadExports();
				bool isManaged = ReadManaged();
				return new PeModuleInfo(isValid: true, isManaged, is64 ? "x64" : "x86", importedModules, exportedNames, limited ? "표시 한도에 따라 일부 이름만 포함했습니다." : string.Empty);
			}

			private string[] ReadImports()
			{
				DirectoryEntry directoryEntry = directories[1];
				List<string> list = new List<string>();
				HashSet<string> hashSet = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
				if (directoryEntry.Address == 0)
				{
					return list.ToArray();
				}
				if (directoryEntry.Size < 20)
				{
					Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				}
				long num = Rva(directoryEntry.Address, directoryEntry.Size);
				for (int i = 0; i < 1024; i++)
				{
					long num2 = (long)i * 20L;
					if (num2 + 20 > directoryEntry.Size)
					{
						Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
					}
					long num3 = num + num2;
					uint num4 = U32(num3);
					uint num5 = U32(num3 + 4);
					uint num6 = U32(num3 + 8);
					uint num7 = U32(num3 + 12);
					uint num8 = U32(num3 + 16);
					if ((num4 | num5 | num6 | num7 | num8) == 0)
					{
						return list.ToArray();
					}
					if (num7 == 0 || num8 == 0)
					{
						Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
					}
					Rva(num8, (ulong)(is64 ? 8 : 4));
					if (num4 != 0)
					{
						Rva(num4, (ulong)(is64 ? 8 : 4));
					}
					string item = Name(num7, module: true);
					if (hashSet.Add(item))
					{
						if (list.Count < 64)
						{
							list.Add(item);
						}
						else
						{
							limited = true;
						}
					}
				}
				Fail("지원하는 PE 메타데이터 분석 한도를 초과했습니다.");
				return list.ToArray();
			}

			private string[] ReadExports()
			{
				DirectoryEntry directoryEntry = directories[0];
				List<string> list = new List<string>();
				HashSet<string> hashSet = new HashSet<string>(StringComparer.Ordinal);
				if (directoryEntry.Address == 0)
				{
					return list.ToArray();
				}
				if (directoryEntry.Size < 40)
				{
					Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				}
				long num = Rva(directoryEntry.Address, directoryEntry.Size);
				uint num2 = U32(num + 20);
				uint num3 = U32(num + 24);
				if (num3 > 4096 || num2 > 65536)
				{
					Fail("지원하는 PE 메타데이터 분석 한도를 초과했습니다.");
				}
				uint num4 = U32(num + 28);
				uint num5 = U32(num + 32);
				uint num6 = U32(num + 36);
				if (num2 != 0)
				{
					if (num4 == 0)
					{
						Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
					}
					Rva(num4, (ulong)num2 * 4uL);
				}
				if (num3 == 0)
				{
					return list.ToArray();
				}
				if (num5 == 0 || num6 == 0 || num2 == 0)
				{
					Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				}
				long num7 = Rva(num5, (ulong)num3 * 4uL);
				long num8 = Rva(num6, (ulong)num3 * 2uL);
				for (uint num9 = 0u; num9 < num3; num9++)
				{
					if (U16(num8 + (long)num9 * 2L) >= num2)
					{
						Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
					}
					uint num10 = U32(num7 + (long)num9 * 4L);
					if (num10 == 0)
					{
						Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
					}
					string item = Name(num10, module: false);
					if (hashSet.Add(item))
					{
						if (list.Count < 128)
						{
							list.Add(item);
						}
						else
						{
							limited = true;
						}
					}
				}
				return list.ToArray();
			}

			private bool ReadManaged()
			{
				DirectoryEntry directoryEntry = directories[14];
				if (directoryEntry.Address == 0)
				{
					return false;
				}
				if (directoryEntry.Size < 72)
				{
					Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				}
				long num = Rva(directoryEntry.Address, directoryEntry.Size);
				uint num2 = U32(num);
				if (num2 < 72 || num2 > directoryEntry.Size)
				{
					Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				}
				uint num3 = U32(num + 8);
				uint num4 = U32(num + 12);
				if (num3 == 0 || num4 < 4)
				{
					Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				}
				long offset = Rva(num3, num4);
				if (U32(offset) != 1112167234)
				{
					Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				}
				return true;
			}

			private string Name(uint address, bool module)
			{
				StringBuilder stringBuilder = new StringBuilder(128);
				for (uint num = 0u; num <= 128; num++)
				{
					if ((ulong)((long)address + (long)num) > 4294967295uL)
					{
						Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
					}
					byte b = data[(int)Rva(address + num, 1uL)];
					if (b == 0)
					{
						string text = stringBuilder.ToString();
						if (!PeModuleInfo.IsSafeName(text, module))
						{
							Fail("PE 이름에 경로 또는 지원하지 않는 문자가 포함되어 있습니다.");
						}
						return text;
					}
					if (num == 128 || b > 127)
					{
						Fail("PE 이름에 경로 또는 지원하지 않는 문자가 포함되어 있습니다.");
					}
					stringBuilder.Append((char)b);
				}
				Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				return string.Empty;
			}

			private long Rva(uint address, ulong count)
			{
				ulong num = address + count;
				if (num > 4294967296L || count == 0L)
				{
					Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				}
				if (address < headersSize)
				{
					if (num > headersSize)
					{
						Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
					}
					Range(address, (long)count);
					return address;
				}
				foreach (Section section in sections)
				{
					if (address >= section.Address && num <= section.Address + section.Span)
					{
						ulong num2 = (ulong)address - (ulong)section.Address;
						if (num2 + count > section.RawSize)
						{
							Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
						}
						long num3 = (long)(section.RawOffset + num2);
						Range(num3, (long)count);
						return num3;
					}
				}
				Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				return 0L;
			}

			private ushort U16(long offset)
			{
				Range(offset, 2L);
				int num = (int)offset;
				return (ushort)(data[num] | (data[num + 1] << 8));
			}

			private uint U32(long offset)
			{
				Range(offset, 4L);
				int num = (int)offset;
				return (uint)(data[num] | (data[num + 1] << 8) | (data[num + 2] << 16) | (data[num + 3] << 24));
			}

			private void Range(long offset, long count)
			{
				if (offset < 0 || count < 0 || count > data.Length || offset > data.Length - count)
				{
					Fail("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
				}
			}

			private static bool Overlaps(ulong first, ulong firstSize, ulong second, ulong secondSize)
			{
				if (firstSize != 0L && secondSize != 0L && first < second + secondSize)
				{
					return second < first + firstSize;
				}
				return false;
			}

			private static void Fail(string reason)
			{
				throw new InvalidPeException(reason);
			}
		}

		private const int MaximumFileBytes = 16777216;

		private const string Malformed = "PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.";

		private const string Unsupported = "지원하는 분석 범위의 x86/x64 PE 파일이 아닙니다.";

		private const string LimitExceeded = "지원하는 PE 메타데이터 분석 한도를 초과했습니다.";

		private const string UnsafeName = "PE 이름에 경로 또는 지원하지 않는 문자가 포함되어 있습니다.";

		public static PeModuleInfo Read(byte[] bytes)
		{
			if (bytes == null || bytes.Length < 64)
			{
				return Invalid("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
			}
			if (bytes.Length > 16777216)
			{
				return Invalid("지원하는 PE 메타데이터 분석 한도를 초과했습니다.");
			}
			try
			{
				return new Reader(bytes).Read();
			}
			catch (InvalidPeException ex)
			{
				return Invalid(ex.Message);
			}
			catch (OverflowException)
			{
				return Invalid("PE 헤더 또는 이름 표의 범위가 올바르지 않습니다.");
			}
		}

		private static PeModuleInfo Invalid(string message)
		{
			return new PeModuleInfo(isValid: false, isManaged: false, "Unknown", null, null, message);
		}
	}
}
