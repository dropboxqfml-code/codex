using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Management;
using System.Runtime.InteropServices;
using System.Security;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using Microsoft.Win32;

namespace ATIVBatteryGuard.Diagnostics
{
	public enum SamsungAnalysisScope
	{
		ServiceModules,
		SettingsApplication
	}

	public sealed class SamsungAnalysisBundleService : ISamsungAnalysisBundleService
	{
		private sealed class ModuleData
		{
			public string Name;

			public string Company;

			public string Product;

			public string Version;

			public string ProductVersion;

			public string Hash;

			public string Architecture;

			public string CollectionBasis;

			public bool DetailedMetadataAvailable;

			public byte[] Bytes;

			public PeModuleInfo Pe;
		}

		private sealed class SkippedModule
		{
			public string Name;

			public string Reason;
		}

		private sealed class TargetedCollection
		{
			public string ReferenceStatus = "REFERENCE_UNCONFIRMED";

			public string TargetStatus = "REFERENCE_UNCONFIRMED";

			public string PolicyReason = string.Empty;
		}

		private const int MaximumFileBytes = 16777216;

		private const int MaximumTotalBytes = 25165824;

		private const int MaximumZipBytes = 33554432;

		private const int MaximumModules = 16;

		private const int MaximumSkippedRecords = 64;

		private const string ServiceKey = "SYSTEM\\CurrentControlSet\\Services\\SamsungSystemConfiguration";

		private readonly string localOutputDirectory;

		private readonly SamsungAnalysisScope scope;

		public SamsungAnalysisBundleService(string localOutputDirectory, SamsungAnalysisScope scope = SamsungAnalysisScope.ServiceModules)
		{
			if (!Enum.IsDefined(typeof(SamsungAnalysisScope), scope)) throw new ArgumentOutOfRangeException(nameof(scope));
			this.localOutputDirectory = localOutputDirectory;
			this.scope = scope;
		}

		public SamsungBundleResult Create()
		{
			if (Environment.OSVersion.Platform != PlatformID.Win32NT)
			{
				return Failure("삼성 분석 파일은 Windows에서만 만들 수 있습니다.");
			}
			string text = null;
			bool flag = false;
			try
			{
				string text2 = LocalPathPolicy.NormalizeDirectory(localOutputDirectory);
				List<string> notes = new List<string>();
				SamsungServiceLocation samsungServiceLocation = scope == SamsungAnalysisScope.SettingsApplication
					? SamsungSettingsLocator.Locate(notes) : LocateServiceModule(notes);
				List<ModuleData> list = new List<ModuleData>();
				string reason = samsungServiceLocation.ReasonCode;
				int totalBytes = 0;
				int count = 0;
				List<SkippedModule> excluded = new List<SkippedModule>();
				TargetedCollection targetedCollection = new TargetedCollection();
				bool limited = false;
				if (samsungServiceLocation.Found)
				{
					ModuleData moduleData = TryReadModule(samsungServiceLocation.Path, 16777216, out reason);
					if (moduleData != null)
					{
						list.Add(moduleData);
						totalBytes = moduleData.Bytes.Length;
						string directoryName = Path.GetDirectoryName(samsungServiceLocation.Path);
						if (scope == SamsungAnalysisScope.SettingsApplication)
						{
							var policy = new SamsungSettingsPathPolicy(
								Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
								Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
								Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData));
							var root = policy.ResolveInstallDirectory(samsungServiceLocation.CollectionDirectory);
							if (!root.Accepted || !SamsungSettingsPathPolicy.IsInsideDirectory(samsungServiceLocation.Path, root.Path)
								|| !IsSafeSourcePath(root.Path)) throw new IOException("Settings collection root rejected.");
							directoryName = root.Path;
						}
						HashSet<string> hashSet = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { moduleData.Name };
						HashSet<string> hashSet2 = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { moduleData.Name };
						if (scope == SamsungAnalysisScope.ServiceModules)
							CollectReferencedModule(samsungServiceLocation, directoryName, moduleData, list, hashSet, hashSet2, excluded, targetedCollection, ref count, ref totalBytes);
						foreach (string item in CandidateFiles(samsungServiceLocation, directoryName, moduleData, notes, out limited))
						{
							string fileName = Path.GetFileName(item);
							if (!hashSet2.Add(fileName))
							{
								continue;
							}
							if (list.Count >= 16 || totalBytes >= 25165824)
							{
								limited = true;
								if (IsReferencedTargetName(fileName))
								{
									targetedCollection.TargetStatus = "COLLECTION_LIMIT";
								}
								AddSkipped(excluded, ref count, fileName, "COLLECTION_LIMIT");
								continue;
							}
							string reason2;
							ModuleData moduleData2 = TryReadModule(item, 25165824 - totalBytes, out reason2);
							if (moduleData2 == null || hashSet.Contains(moduleData2.Name))
							{
								if (IsReferencedTargetName(fileName))
								{
									targetedCollection.TargetStatus = ((moduleData2 == null) ? reason2 : "ALREADY_INCLUDED");
								}
								AddSkipped(excluded, ref count, fileName, (moduleData2 == null) ? reason2 : "DUPLICATE_NAME");
								continue;
							}
							list.Add(moduleData2);
							hashSet.Add(moduleData2.Name);
							totalBytes += moduleData2.Bytes.Length;
							if (IsReferencedTargetName(moduleData2.Name))
							{
								targetedCollection.TargetStatus = "COPIED_STRICT_METADATA";
								targetedCollection.PolicyReason = "ORDINARY_SAMSUNG_METADATA_AND_PE";
							}
						}
						reason = "MODULES_COPIED";
					}
					else
					{
						AddSkipped(excluded, ref count, samsungServiceLocation.FileName, reason);
					}
				}
				Directory.CreateDirectory(text2);
				string text3 = "samsung-analysis-" + DateTime.UtcNow.ToString("yyyyMMddTHHmmss", CultureInfo.InvariantCulture) + "-" + Guid.NewGuid().ToString("N") + ".zip";
				string text4 = Path.Combine(text2, text3);
				LocalPathPolicy.EnsureNoReparsePoints(text4);
				text = Path.Combine(text2, ".samsung-analysis-" + Guid.NewGuid().ToString("N") + ".tmp");
				using (FileStream fileStream = new FileStream(text, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None))
				{
					flag = true;
					using (ZipArchive zipArchive = new ZipArchive(fileStream, ZipArchiveMode.Create, leaveOpen: true, Encoding.UTF8))
					{
						foreach (ModuleData item2 in list)
						{
							using (Stream stream = zipArchive.CreateEntry("modules/" + item2.Name, CompressionLevel.Optimal).Open())
							{
								stream.Write(item2.Bytes, 0, item2.Bytes.Length);
							}
						}
						using (StreamWriter streamWriter = new StreamWriter(zipArchive.CreateEntry("module-report.txt", CompressionLevel.Optimal).Open(), new UTF8Encoding(encoderShouldEmitUTF8Identifier: true)))
						{
							streamWriter.Write(BuildReport(samsungServiceLocation, reason, notes, list, totalBytes, count, limited, excluded, targetedCollection));
						}
					}
					fileStream.Flush(flushToDisk: true);
					if (fileStream.Length <= 0 || fileStream.Length >= 33554432)
					{
						throw new IOException("분석 파일 용량 제한");
					}
				}
				LocalPathPolicy.EnsureNoReparsePoints(text2);
				File.Move(text, text4);
				flag = false;
				text = null;
				bool flag2 = false;
				foreach (ModuleData item3 in list)
				{
					if (string.Equals(item3.Name, "wsabi.dll", StringComparison.OrdinalIgnoreCase))
					{
						flag2 = true;
					}
				}
				if (scope == SamsungAnalysisScope.SettingsApplication)
					return new SamsungBundleResult(true, list.Count == 0
						? "Samsung Settings 앱 파일을 복사하지 못해 위치 점검 보고서만 만들었습니다. 이 ZIP으로 원인을 확인할 수 있습니다."
						: "Samsung Settings 앱 분석 ZIP을 만들었습니다. 프로그램 파일은 실행하지 않았으며 충전 설정도 변경하지 않았습니다.", text3, list.Count != 0);
				return (list.Count == 0) ? new SamsungBundleResult(success: true, "삼성 파일을 복사하지 못해 점검 보고서만 생성했습니다. wsabi.dll 상태는 보고서에 기록했습니다.", text3, containsModules: false) : new SamsungBundleResult(success: true, flag2 ? "삼성 분석 ZIP을 만들었습니다. wsabi.dll을 분석 데이터로 확보했습니다. 파일은 실행하지 않았습니다." : "삼성 분석 ZIP을 만들었습니다. wsabi.dll은 확보하지 못해 이유를 보고서에 기록했습니다. 원본은 변경하지 않았습니다.", text3);
			}
			catch (Exception exception) when (ReadFailure(exception))
			{
				return Failure("삼성 분석 파일을 만들지 못했습니다. 읽기 권한과 저장 위치를 확인하세요. 원본 파일은 변경하지 않았습니다.");
			}
			finally
			{
				if (flag && text != null)
				{
					try
					{
						File.Delete(text);
					}
					catch (Exception exception2) when (ReadFailure(exception2))
					{
					}
				}
			}
		}

		private static SamsungServiceLocation LocateServiceModule(IList<string> notes)
		{
			string text = null;
			string text2 = null;
			string text3 = null;
			try
			{
				using (ManagementObjectSearcher managementObjectSearcher = new ManagementObjectSearcher(new ManagementScope("\\\\.\\root\\cimv2", new ConnectionOptions
				{
					Timeout = TimeSpan.FromSeconds(3.0)
				}), options: new EnumerationOptions
				{
					ReturnImmediately = true,
					Rewindable = false,
					Timeout = TimeSpan.FromSeconds(3.0)
				}, query: new ObjectQuery("SELECT PathName FROM Win32_Service WHERE Name='SamsungSystemConfiguration'")))
				{
					using (ManagementObjectCollection managementObjectCollection = managementObjectSearcher.Get())
					{
						using (ManagementObjectCollection.ManagementObjectEnumerator managementObjectEnumerator = managementObjectCollection.GetEnumerator())
						{
							if (managementObjectEnumerator.MoveNext())
							{
								ManagementBaseObject current = managementObjectEnumerator.Current;
								using (current)
								{
									text = Convert.ToString(current["PathName"], CultureInfo.InvariantCulture);
								}
							}
						}
					}
				}
				notes.Add(string.IsNullOrWhiteSpace(text) ? "WMI_PATH_MISSING" : "WMI_PATH_PRESENT");
			}
			catch (Exception exception) when (ReadFailure(exception))
			{
				notes.Add("WMI_PATH_READ_FAILED");
			}
			try
			{
				using (RegistryKey registryKey = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64))
				{
					using (RegistryKey registryKey2 = registryKey.OpenSubKey("SYSTEM\\CurrentControlSet\\Services\\SamsungSystemConfiguration", writable: false))
					{
						if (registryKey2 != null)
						{
							text2 = Convert.ToString(registryKey2.GetValue("ImagePath", null, RegistryValueOptions.DoNotExpandEnvironmentNames), CultureInfo.InvariantCulture);
							using (RegistryKey registryKey3 = registryKey2.OpenSubKey("Parameters", writable: false))
							{
								if (registryKey3 != null)
								{
									text3 = Convert.ToString(registryKey3.GetValue("ServiceDll", null, RegistryValueOptions.DoNotExpandEnvironmentNames), CultureInfo.InvariantCulture);
								}
							}
						}
					}
				}
				notes.Add(string.IsNullOrWhiteSpace(text2) ? "REGISTRY_IMAGE_MISSING" : "REGISTRY_IMAGE_PRESENT");
				notes.Add(string.IsNullOrWhiteSpace(text3) ? "REGISTRY_DLL_MISSING" : "REGISTRY_DLL_PRESENT");
			}
			catch (Exception exception2) when (ReadFailure(exception2))
			{
				notes.Add("REGISTRY_PATH_READ_FAILED");
			}
			try
			{
				return SamsungServicePathResolver.Resolve(text, text2, text3, Environment.GetFolderPath(Environment.SpecialFolder.Windows), Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), File.Exists, IsSafeSourcePath);
			}
			catch (Exception exception3) when (ReadFailure(exception3))
			{
				return new SamsungServiceLocation(found: false, string.Empty, string.Empty, "None", "Invalid", "RESOLUTION_READ_FAILED");
			}
		}

		private static bool IsSafeSourcePath(string file)
		{
			try
			{
				LocalPathPolicy.NormalizeDirectory(Path.GetDirectoryName(file));
				LocalPathPolicy.EnsureNoReparsePoints(file);
				return true;
			}
			catch (Exception exception) when (ReadFailure(exception))
			{
				return false;
			}
		}

		private List<string> CandidateFiles(SamsungServiceLocation location, string directory, ModuleData serviceModule, IList<string> notes, out bool limited)
		{
			if (scope == SamsungAnalysisScope.SettingsApplication)
				return SettingsCandidateFiles(directory, notes, out limited);
			List<string> list = new List<string>();
			HashSet<string> hashSet = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { serviceModule.Name };
			limited = false;
			if (location.CanEnumerateDirectory)
			{
				try
				{
					int num = 0;
					foreach (string item in Directory.EnumerateFiles(directory, "*", SearchOption.TopDirectoryOnly))
					{
						if (++num > 128)
						{
							limited = true;
							break;
						}
						if (IsModuleFile(item) && hashSet.Add(Path.GetFileName(item)))
						{
							list.Add(item);
						}
					}
					notes.Add("DEDICATED_FOLDER_CANDIDATES");
				}
				catch (Exception exception) when (ReadFailure(exception))
				{
					notes.Add("CANDIDATE_DIRECTORY_READ_FAILED");
				}
			}
			else
			{
				string[] importedModules = serviceModule.Pe.ImportedModules;
				foreach (string text in importedModules)
				{
					if (IsModuleFile(text) && Path.GetFileName(text) == text && hashSet.Add(text))
					{
						list.Add(Path.Combine(directory, text));
					}
				}
				notes.Add("SHARED_FOLDER_DIRECT_IMPORTS_ONLY");
			}
			list.Sort(delegate(string left, string right)
			{
				int num2 = Priority(left).CompareTo(Priority(right));
				return (num2 == 0) ? StringComparer.OrdinalIgnoreCase.Compare(Path.GetFileName(left), Path.GetFileName(right)) : num2;
			});
			return list;
		}

		private static List<string> SettingsCandidateFiles(string root, IList<string> notes, out bool limited)
		{
			// Search only the already-approved Settings installation subtree. Never
			// follow reparse points or search user folders, PATH, or sibling apps.
			const int maxEntries = 512, maxDirectories = 16, maxCandidates = 128, maxDepth = 2;
			limited = false;
			var files = new List<string>();
			var pending = new Queue<Tuple<string, int>>();
			pending.Enqueue(Tuple.Create(root, 0));
			int visitedEntries = 0, visitedDirectories = 0;
			string prefix = root.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
			var pathPolicy = new SamsungSettingsPathPolicy(
				Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
				Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
				Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData));
			while (pending.Count > 0)
			{
				if (++visitedDirectories > maxDirectories) { limited = true; break; }
				var current = pending.Dequeue();
				if (!IsSafeSourcePath(current.Item1)) { notes.Add("SETTINGS_UNSAFE_DIRECTORY_SKIPPED"); continue; }
				try
				{
					var children = new List<string>();
					foreach (string entry in Directory.EnumerateFileSystemEntries(current.Item1, "*", SearchOption.TopDirectoryOnly))
					{
						if (++visitedEntries > maxEntries) { limited = true; break; }
						// Apply the same lexical/device-name rules to every descendant
						// before any filesystem probe, including directory candidates.
						if (!entry.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)
							|| !pathPolicy.ResolveInstallDirectory(entry).Accepted || !IsSafeSourcePath(entry)) continue;
						FileAttributes attributes = File.GetAttributes(entry);
						if ((attributes & FileAttributes.ReparsePoint) != 0) continue;
						if ((attributes & FileAttributes.Directory) != 0)
						{
							if (current.Item2 < maxDepth) children.Add(entry);
							else limited = true;
							}
						else if (IsModuleFile(entry))
						{
							if (files.Count == maxCandidates) { limited = true; break; }
							files.Add(entry);
						}
					}
					children.Sort(CompareSettingsCandidates);
					foreach (string child in children) pending.Enqueue(Tuple.Create(child, current.Item2 + 1));
				}
				catch (Exception exception) when (ReadFailure(exception))
				{
					if (!notes.Contains("SETTINGS_CANDIDATE_READ_FAILED")) notes.Add("SETTINGS_CANDIDATE_READ_FAILED");
				}
				if (visitedEntries > maxEntries || files.Count == maxCandidates) { limited = true; break; }
			}
			files.Sort(CompareSettingsCandidates);
			notes.Add("SETTINGS_SUBTREE_DEPTH2_BOUNDED");
			return files;
		}

		private static int CompareSettingsCandidates(string left, string right)
		{
			int priority = SettingsPriority(left).CompareTo(SettingsPriority(right));
			return priority != 0 ? priority : StringComparer.OrdinalIgnoreCase.Compare(left, right);
		}

		private static int SettingsPriority(string path)
		{
			string name = Path.GetFileName(path);
			foreach (string word in new[] { "battery", "extender", "charge", "power" })
				if (name.IndexOf(word, StringComparison.OrdinalIgnoreCase) >= 0) return 0;
			if (name.IndexOf("settings", StringComparison.OrdinalIgnoreCase) >= 0) return 1;
			return 2;
		}

		private static void CollectReferencedModule(SamsungServiceLocation location, string directory, ModuleData serviceModule, IList<ModuleData> modules, ISet<string> names, ISet<string> processed, IList<SkippedModule> excluded, TargetedCollection targeted, ref int skipped, ref int totalBytes)
		{
			if (IsReferencedTargetName(serviceModule.Name))
			{
				targeted.ReferenceStatus = "STRICT_ROOT_MODULE";
				targeted.TargetStatus = "ALREADY_INCLUDED";
				targeted.PolicyReason = "ORDINARY_SAMSUNG_METADATA_AND_PE";
				return;
			}
			ModuleData moduleData = (SamsungReferencedModulePolicy.IsConfirmedParent(serviceModule.Name, serviceModule.Hash) ? serviceModule : null);
			if (moduleData == null && !location.CanEnumerateDirectory)
			{
				targeted.ReferenceStatus = "SHARED_FOLDER_REFERENCE_UNAVAILABLE";
				targeted.TargetStatus = "REFERENCE_UNCONFIRMED";
				return;
			}
			if (moduleData == null)
			{
				string text = "SamsungConfigurationMonitor.exe";
				processed.Add(text);
				string reason;
				ModuleData moduleData2 = TryReadModule(Path.Combine(directory, text), 25165824 - totalBytes, out reason);
				if (moduleData2 != null && !names.Contains(moduleData2.Name))
				{
					modules.Add(moduleData2);
					names.Add(moduleData2.Name);
					totalBytes += moduleData2.Bytes.Length;
					moduleData = moduleData2;
				}
				else if (moduleData2 == null)
				{
					AddSkipped(excluded, ref skipped, text, reason);
				}
			}
			string text2 = "wsabi.dll";
			if (moduleData == null || !SamsungReferencedModulePolicy.IsConfirmedParent(moduleData.Name, moduleData.Hash))
			{
				targeted.ReferenceStatus = "REFERENCE_UNCONFIRMED";
				targeted.TargetStatus = "REFERENCE_UNCONFIRMED";
				return;
			}
			processed.Add(text2);
			targeted.ReferenceStatus = "CONFIRMED_PARENT_SHA256";
			if (names.Contains(text2))
			{
				targeted.TargetStatus = "ALREADY_INCLUDED";
				return;
			}
			if (modules.Count >= 16 || totalBytes >= 25165824)
			{
				targeted.TargetStatus = "TOO_LARGE";
				AddSkipped(excluded, ref skipped, text2, targeted.TargetStatus);
				return;
			}
			string reason2;
			ModuleData moduleData3 = TryReadReferencedModule(Path.Combine(directory, text2), moduleData, 25165824 - totalBytes, out reason2, out targeted.PolicyReason);
			targeted.TargetStatus = reason2;
			if (moduleData3 == null)
			{
				AddSkipped(excluded, ref skipped, text2, reason2);
				return;
			}
			modules.Add(moduleData3);
			names.Add(moduleData3.Name);
			totalBytes += moduleData3.Bytes.Length;
		}

		private static bool IsReferencedTargetName(string name)
		{
			return string.Equals(name, "wsabi.dll", StringComparison.OrdinalIgnoreCase);
		}

		private static ModuleData TryReadReferencedModule(string file, ModuleData parent, int availableBytes, out string reason, out string policyReason)
		{
			reason = "READ_FAILED";
			policyReason = string.Empty;
			try
			{
				if (!SamsungReferencedModulePolicy.IsConfirmedParent(parent.Name, parent.Hash))
				{
					reason = "REFERENCE_UNCONFIRMED";
					return null;
				}
				if (!IsModuleFile(file) || !string.Equals(Path.GetFileName(file), "wsabi.dll", StringComparison.OrdinalIgnoreCase))
				{
					reason = "POLICY_REJECTED";
					return null;
				}
				if (!IsSafeSourcePath(file))
				{
					reason = "PATH_UNSAFE";
					return null;
				}
				if (!File.Exists(file))
				{
					reason = "NOT_FOUND";
					return null;
				}
				using (FileStream fileStream = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read))
				{
					if (fileStream.Length > 16777216 || fileStream.Length > availableBytes)
					{
						reason = "TOO_LARGE";
						return null;
					}
					if (fileStream.Length <= 0)
					{
						reason = "POLICY_REJECTED";
						return null;
					}
					byte[] array = new byte[(int)fileStream.Length];
					int num;
					for (int i = 0; i < array.Length; i += num)
					{
						num = fileStream.Read(array, i, array.Length - i);
						if (num == 0)
						{
							throw new EndOfStreamException();
						}
					}
					ReferencedModuleDecision referencedModuleDecision = SamsungReferencedModulePolicy.Evaluate(parent.Name, parent.Hash, Path.GetFileName(file), array);
					policyReason = referencedModuleDecision.ReasonCode;
					if (!referencedModuleDecision.Allowed)
					{
						reason = "POLICY_REJECTED";
						return null;
					}
					FileVersionInfo fileVersionInfo = null;
					try
					{
						fileVersionInfo = FileVersionInfo.GetVersionInfo(file);
					}
					catch (Exception exception) when (ReadFailure(exception))
					{
					}
					string hash;
					using (SHA256 sHA = SHA256.Create())
					{
						hash = BitConverter.ToString(sHA.ComputeHash(array)).Replace("-", string.Empty).ToLowerInvariant();
					}
					reason = "COPIED_DATA_ONLY";
					return new ModuleData
					{
						Name = Path.GetFileName(file),
						Bytes = array,
						Company = SafeMetadata(fileVersionInfo?.CompanyName),
						Product = SafeMetadata(fileVersionInfo?.ProductName),
						Version = SafeMetadata(fileVersionInfo?.FileVersion),
						ProductVersion = SafeMetadata(fileVersionInfo?.ProductVersion),
						Hash = hash,
						Pe = referencedModuleDecision.Metadata,
						Architecture = referencedModuleDecision.Architecture,
						DetailedMetadataAvailable = referencedModuleDecision.DetailedMetadataAvailable,
						CollectionBasis = "STATIC_REFERENCE_DATA_ONLY"
					};
				}
			}
			catch (FileNotFoundException)
			{
				reason = "NOT_FOUND";
				return null;
			}
			catch (DirectoryNotFoundException)
			{
				reason = "NOT_FOUND";
				return null;
			}
			catch (Exception exception2) when (ReadFailure(exception2))
			{
				reason = "READ_FAILED";
				return null;
			}
		}

		private static void AddSkipped(IList<SkippedModule> excluded, ref int count, string name, string reason)
		{
			count++;
			if (excluded.Count < 64)
			{
				string fileName = Path.GetFileName(name);
				if (IsModuleFile(fileName) && fileName.IndexOf('\\') < 0 && fileName.IndexOf('/') < 0)
				{
					excluded.Add(new SkippedModule
					{
						Name = fileName,
						Reason = SafeToken(reason)
					});
				}
			}
		}

		private static ModuleData TryReadModule(string file, int availableBytes, out string reason)
		{
			try
			{
				return ReadModule(file, availableBytes, out reason);
			}
			catch (Exception exception) when (ReadFailure(exception))
			{
				reason = "MODULE_READ_FAILED";
				return null;
			}
		}

		private static ModuleData ReadModule(string file, int availableBytes, out string reason)
		{
			reason = "MODULE_NAME_REJECTED";
			if (!IsModuleFile(file))
			{
				return null;
			}
			reason = "MODULE_PATH_UNSAFE";
			if (!IsSafeSourcePath(file))
			{
				return null;
			}
			LocalPathPolicy.EnsureNoReparsePoints(file);
			using (FileStream fileStream = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read))
			{
				reason = "MODULE_SIZE_REJECTED";
				if (fileStream.Length <= 0 || fileStream.Length > 16777216 || fileStream.Length > availableBytes)
				{
					return null;
				}
				FileVersionInfo versionInfo = FileVersionInfo.GetVersionInfo(file);
				reason = "COMPANY_NOT_SAMSUNG";
				if (string.IsNullOrWhiteSpace(versionInfo.CompanyName) || (versionInfo.CompanyName.IndexOf("Samsung", StringComparison.OrdinalIgnoreCase) < 0 && versionInfo.CompanyName.IndexOf("삼성", StringComparison.OrdinalIgnoreCase) < 0))
				{
					return null;
				}
				byte[] array = new byte[(int)fileStream.Length];
				int num;
				for (int i = 0; i < array.Length; i += num)
				{
					num = fileStream.Read(array, i, array.Length - i);
					if (num == 0)
					{
						throw new EndOfStreamException();
					}
				}
				PeModuleInfo peModuleInfo = PeModuleReader.Read(array);
				reason = "PE_METADATA_REJECTED";
				if (!peModuleInfo.IsValid)
				{
					return null;
				}
				string hash;
				using (SHA256 sHA = SHA256.Create())
				{
					hash = BitConverter.ToString(sHA.ComputeHash(array)).Replace("-", string.Empty).ToLowerInvariant();
				}
				reason = "MODULE_READ_OK";
				return new ModuleData
				{
					Name = Path.GetFileName(file),
					Bytes = array,
					Company = SafeMetadata(versionInfo.CompanyName),
					Product = SafeMetadata(versionInfo.ProductName),
					Version = SafeMetadata(versionInfo.FileVersion),
					ProductVersion = SafeMetadata(versionInfo.ProductVersion),
					Hash = hash,
					Pe = peModuleInfo,
					Architecture = peModuleInfo.Architecture,
					DetailedMetadataAvailable = true,
					CollectionBasis = "SAMSUNG_METADATA_AND_PE"
				};
			}
		}

		private static bool IsModuleFile(string path)
		{
			if (string.IsNullOrWhiteSpace(path))
			{
				return false;
			}
			string extension = Path.GetExtension(path);
			string fileName = Path.GetFileName(path);
			if (fileName.Length == 0 || fileName.Length > 160 || fileName != fileName.Trim())
			{
				return false;
			}
			string text = fileName;
			foreach (char c in text)
			{
				if (!char.IsLetterOrDigit(c) && c != '.' && c != '_' && c != '-' && c != ' ' && c != '(' && c != ')')
				{
					return false;
				}
			}
			if (!string.Equals(extension, ".exe", StringComparison.OrdinalIgnoreCase))
			{
				return string.Equals(extension, ".dll", StringComparison.OrdinalIgnoreCase);
			}
			return true;
		}

		private static int Priority(string path)
		{
			string fileName = Path.GetFileName(path);
			string[] array = new string[7] { "sabi", "battery", "control", "system", "config", "service", "settings" };
			foreach (string value in array)
			{
				if (fileName.IndexOf(value, StringComparison.OrdinalIgnoreCase) >= 0)
				{
					return 0;
				}
			}
			return 1;
		}

		private string BuildReport(SamsungServiceLocation location, string reason, IList<string> notes, IList<ModuleData> modules, int bytes, int skipped, bool limited, IList<SkippedModule> excluded, TargetedCollection targeted)
		{
			StringBuilder stringBuilder = new StringBuilder();
			bool settingsApp = scope == SamsungAnalysisScope.SettingsApplication;
			stringBuilder.AppendLine(settingsApp ? "ATIV Battery Guard — Samsung Settings 앱 정적 분석 자료" : "ATIV Battery Guard — 삼성 모듈 오프라인 분석 자료");
			stringBuilder.AppendLine((modules.Count == 0) ? "삼성 모듈을 복사하지 못했습니다. 이 ZIP은 위치 점검 보고서만 포함합니다." : settingsApp
				? "사용자가 확인한 뒤 설치된 Samsung Settings 전용 폴더의 EXE/DLL만 분석 데이터로 복사했습니다."
				: "사용자가 확인한 뒤 알려진 서비스 관련 모듈과 정적 참조 근거로 허용한 분석 데이터만 복사했습니다.");
			stringBuilder.AppendLine("결과 코드: " + SafeToken(reason));
			stringBuilder.AppendLine("위치 확인 출처: " + SafeToken(location.Source));
			stringBuilder.AppendLine("설치 위치 유형: " + SafeToken(location.Category));
			stringBuilder.AppendLine("대상 파일 이름: " + ((IsModuleFile(location.FileName) && Path.GetFileName(location.FileName) == location.FileName && location.FileName.IndexOf('\\') < 0 && location.FileName.IndexOf('/') < 0) ? location.FileName : "알 수 없음"));
			stringBuilder.AppendLine("후보 폴더 열거: " + ((location.Found && location.CanEnumerateDirectory) ? "승인된 전용 설치 폴더만" : "없음; 공유 폴더는 직접 가져오기 이름만 확인"));
			foreach (string note in notes)
			{
				stringBuilder.AppendLine("확인 단계: " + SafeToken(note));
			}
			stringBuilder.AppendLine();
			if (settingsApp)
			{
				stringBuilder.AppendLine("[Settings 앱 수집 범위]");
				stringBuilder.AppendLine("HKLM 32/64비트의 정확한 Samsung Settings 등록과 전용 설치 경로만 확인했습니다. 제거 명령은 읽거나 실행하지 않습니다.");
				stringBuilder.AppendLine("폴더 깊이 최대 2, 디렉터리 최대 16, 항목 최대 512, 후보 파일 최대 128, 복사 모듈 최대 16개입니다.");
				stringBuilder.AppendLine("파일당 최대 16MiB, 총 최대 24MiB, ZIP은 32MiB 미만입니다. 링크 경로를 따라가지 않습니다.");
				stringBuilder.AppendLine("충전 관련 이름을 우선하지만 이름과 회사 표시 정보만으로 배터리 기능이나 전자서명 신뢰를 입증할 수 없습니다.");
				stringBuilder.AppendLine("하위 폴더에 같은 이름의 파일이 여러 개 있으면 이름별 한 파일만 포함합니다. 이 자료는 전체 설치 파일의 완전한 복사본이 아닙니다.");
				stringBuilder.AppendLine("설정·로그·개인 문서·서비스 폴더·드라이버·ACPI 원본 테이블은 이 수집에 포함하지 않습니다.");
			}
			else
			{
			stringBuilder.AppendLine("[같은 폴더 wsabi.dll 대상 수집]");
			stringBuilder.AppendLine("정적 참조 부모: SamsungConfigurationMonitor.exe");
			stringBuilder.AppendLine("확인된 부모 SHA-256: 8a0d87b214623f424b7f493034bca3271e35fc4376bbfa3f72a1491d33b72281");
			stringBuilder.AppendLine("부모 참조 확인: " + SafeToken(targeted.ReferenceStatus));
			stringBuilder.AppendLine("대상 파일: wsabi.dll");
			stringBuilder.AppendLine("대상 결과: " + SafeToken(targeted.TargetStatus));
			if (!string.IsNullOrEmpty(targeted.PolicyReason))
			{
				stringBuilder.AppendLine("대상 데이터 검사: " + SafeToken(targeted.PolicyReason));
			}
			stringBuilder.AppendLine("확인된 모니터 SHA-256과 같은 폴더의 wsabi.dll 한 파일만 정적 참조 예외 대상으로 허용합니다.");
			stringBuilder.AppendLine("이 예외는 회사 표시 정보가 없거나 상세 PE 분석이 불완전해도 기본 PE 형식이 확인된 파일을 데이터로 복사하기 위한 것입니다.");
			stringBuilder.AppendLine("참조 근거와 기본 PE 형식은 전자서명 신뢰·실행 가능성·호출 규약·충전 제어 지원의 증거가 아닙니다.");
			stringBuilder.AppendLine("부모 모니터에서 확인된 동작은 팬·정숙 모드 관련이며 충전 제한 명령은 확인되지 않았습니다.");
			stringBuilder.AppendLine("다른 폴더나 PATH를 검색하지 않고 파일을 로드·실행하거나 DLL 함수를 호출하지 않았습니다.");
			}
			stringBuilder.AppendLine();
			stringBuilder.AppendLine("이름·버전·SHA-256·PE 가져오기 모듈/내보내기 이름만 읽었으며 파일을 로드하거나 실행하지 않았습니다.");
			stringBuilder.AppendLine("회사 정보는 파일의 표시 정보일 뿐 신뢰 증명이 아닙니다. 전자서명 신뢰 검증 미실행; 파일은 분석 데이터일 뿐 실행 안함.");
			stringBuilder.AppendLine("펌웨어·레지스트리·서비스·드라이버 변경 및 자동 전송은 하지 않았습니다. 실제 충전 제어는 미지원입니다.");
			stringBuilder.AppendLine("기록하지 않는 정보: 전체 파일 경로·서비스 명령행·사용자 이름·설정 파일·로그.");
			stringBuilder.AppendLine("복사 모듈 수: " + modules.Count.ToString(CultureInfo.InvariantCulture));
			stringBuilder.AppendLine("복사 바이트 수: " + bytes.ToString(CultureInfo.InvariantCulture));
			stringBuilder.AppendLine("제외하거나 확보하지 못한 후보 수: " + skipped.ToString(CultureInfo.InvariantCulture));
			if (limited)
			{
				stringBuilder.AppendLine("조회 또는 모듈 수 한도에 도달해 전체 설치 파일을 포함하지 않았습니다.");
			}
			stringBuilder.AppendLine();
			stringBuilder.AppendLine("[제외 또는 미확보 후보 이름 / 이유]");
			if (excluded.Count == 0)
			{
				stringBuilder.AppendLine("기록된 제외 후보가 없습니다.");
			}
			foreach (SkippedModule item in excluded)
			{
				stringBuilder.AppendLine("- " + item.Name + " | " + SafeToken(item.Reason));
			}
			if (skipped > excluded.Count)
			{
				stringBuilder.AppendLine("표시 한도에 따라 일부 제외 이유만 기록했습니다.");
			}
			stringBuilder.AppendLine();
			foreach (ModuleData module in modules)
			{
				stringBuilder.AppendLine("[" + module.Name + "]");
				stringBuilder.AppendLine("회사: " + module.Company);
				stringBuilder.AppendLine("제품: " + module.Product);
				stringBuilder.AppendLine("파일 버전: " + module.Version);
				stringBuilder.AppendLine("제품 버전: " + module.ProductVersion);
				stringBuilder.AppendLine("파일 크기: " + module.Bytes.Length.ToString(CultureInfo.InvariantCulture));
				stringBuilder.AppendLine("SHA-256: " + module.Hash);
				stringBuilder.AppendLine("수집 근거: " + SafeToken(module.CollectionBasis));
				stringBuilder.AppendLine("형식: " + module.Architecture + ((!module.DetailedMetadataAvailable) ? " / 상세 PE 메타데이터 미확인 — 분석 데이터 전용" : (module.Pe.IsManaged ? " / 관리형 .NET" : " / 네이티브")));
				stringBuilder.AppendLine("가져오기 모듈: " + string.Join(", ", module.Pe.ImportedModules));
				stringBuilder.AppendLine("내보내기 이름: " + string.Join(", ", module.Pe.ExportedNames));
				if (!string.IsNullOrEmpty(module.Pe.Error))
				{
					stringBuilder.AppendLine("PE 표시 제한: " + SafeMetadata(module.Pe.Error));
				}
				stringBuilder.AppendLine();
			}
			return stringBuilder.ToString();
		}

		private static string SafeMetadata(string value)
		{
			if (string.IsNullOrWhiteSpace(value))
			{
				return "알 수 없음";
			}
			if (Regex.IsMatch(value, "[A-Za-z]:[\\\\/]") || value.Contains("\\\\") || value.IndexOf("/home/", StringComparison.OrdinalIgnoreCase) >= 0 || value.IndexOf("/Users/", StringComparison.OrdinalIgnoreCase) >= 0)
			{
				return "경로가 포함된 표시 정보는 기록하지 않았습니다.";
			}
			StringBuilder stringBuilder = new StringBuilder(160);
			foreach (char c in value)
			{
				stringBuilder.Append((char.IsControl(c) || c == '\u2028' || c == '\u2029' || (c >= '\u202a' && c <= '\u202e') || (c >= '\u2066' && c <= '\u2069')) ? ' ' : c);
				if (stringBuilder.Length == 160)
				{
					break;
				}
			}
			return stringBuilder.ToString().Trim();
		}

		private static string SafeToken(string value)
		{
			if (string.IsNullOrEmpty(value) || !Regex.IsMatch(value, "\\A[A-Za-z0-9_]{1,80}\\z"))
			{
				return "UNKNOWN";
			}
			return value;
		}

		private static SamsungBundleResult Failure(string message)
		{
			return new SamsungBundleResult(success: false, message);
		}

		private static bool ReadFailure(Exception exception)
		{
			if (!(exception is IOException) && !(exception is UnauthorizedAccessException) && !(exception is SecurityException) && !(exception is ManagementException) && !(exception is COMException) && !(exception is Win32Exception) && !(exception is InvalidOperationException) && !(exception is TimeoutException) && !(exception is ArgumentException) && !(exception is NotSupportedException))
			{
				return exception is OverflowException;
			}
			return true;
		}
	}
}
