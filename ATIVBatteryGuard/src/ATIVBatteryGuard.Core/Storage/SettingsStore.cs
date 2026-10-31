using System;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Security;
using System.Xml;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Storage
{
	public sealed class SettingsStore
	{
		[DataContract]
		private sealed class SchemaHeader
		{
			[DataMember(Name = "schemaVersion")]
			public int SchemaVersion { get; set; }
		}

		private const int MaximumBytes = 65536;

		private readonly object sync = new object();

		private readonly string initializationError;

		private bool loaded;

		private bool canSave;

		public string DirectoryPath { get; private set; }

		public string FilePath { get; private set; }

		public SettingsStore(string directory)
		{
			try
			{
				DirectoryPath = LocalPathPolicy.NormalizeDirectory(directory);
				FilePath = Path.Combine(DirectoryPath, "settings.json");
			}
			catch (Exception ex) when (IsStorageError(ex))
			{
				DirectoryPath = string.Empty;
				FilePath = string.Empty;
				initializationError = "안전한 로컬 저장 위치를 확인할 수 없습니다.";
			}
		}

		public SettingsLoadResult Load()
		{
			lock (sync)
			{
				loaded = true;
				canSave = false;
				if (initializationError != null)
				{
					return Defaults("안전한 로컬 저장 위치를 확인할 수 없습니다.", allowSave: false);
				}
				try
				{
					LocalPathPolicy.EnsureNoReparsePoints(FilePath);
					if (!File.Exists(FilePath))
					{
						canSave = true;
						return Defaults(string.Empty, allowSave: true);
					}
					byte[] bytes = ReadBounded();
					if (ReadSchema(bytes) > 1)
					{
						return Defaults("더 최신 버전의 설정 파일입니다. 원본을 보존하며 저장을 차단합니다.", allowSave: false);
					}
					AppSettings appSettings = Deserialize<AppSettings>(bytes);
					if (appSettings == null || !appSettings.IsValid(out var _))
					{
						return RecoverCorrupt();
					}
					canSave = true;
					return new SettingsLoadResult(appSettings, string.Empty, canSave: true);
				}
				catch (SerializationException)
				{
					return RecoverCorrupt();
				}
				catch (XmlException)
				{
					return RecoverCorrupt();
				}
				catch (Exception ex3) when (IsStorageError(ex3))
				{
					return Defaults("설정을 읽을 수 없습니다. 원본을 보존하며 저장을 차단합니다.", allowSave: false);
				}
			}
		}

		public OperationResult Save(AppSettings settings)
		{
			lock (sync)
			{
				if (settings == null || !settings.IsValid(out var reason))
				{
					return new OperationResult(success: false, "저장할 설정 값이 올바르지 않습니다.");
				}
				if (!loaded)
				{
					Load();
				}
				if (!canSave)
				{
					return new OperationResult(success: false, "설정 파일 보호를 위해 저장이 차단되었습니다. 저장 위치와 형식을 확인하세요.");
				}
				string text = null;
				try
				{
					LocalPathPolicy.EnsureNoReparsePoints(FilePath);
					Directory.CreateDirectory(DirectoryPath);
					string text2 = FilePath + ".bak";
					LocalPathPolicy.EnsureNoReparsePoints(text2);
					if (File.Exists(FilePath))
					{
						byte[] bytes = ReadBounded();
						if (ReadSchema(bytes) > 1)
						{
							canSave = false;
							return new OperationResult(success: false, "더 최신 버전의 설정 파일을 덮어쓰지 않습니다.");
						}
						AppSettings appSettings = Deserialize<AppSettings>(bytes);
						if (appSettings == null || !appSettings.IsValid(out reason))
						{
							canSave = false;
							return new OperationResult(success: false, "설정 파일이 변경되었습니다. 앱을 다시 열어 파일 상태를 확인하세요.");
						}
					}
					text = Path.Combine(DirectoryPath, ".settings-" + Guid.NewGuid().ToString("N") + ".tmp");
					using (FileStream fileStream = new FileStream(text, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough))
					{
						new DataContractJsonSerializer(typeof(AppSettings)).WriteObject(fileStream, settings);
						fileStream.Flush(flushToDisk: true);
					}
					if (File.Exists(FilePath))
					{
						File.Replace(text, FilePath, text2, ignoreMetadataErrors: true);
					}
					else
					{
						File.Move(text, FilePath);
					}
					text = null;
					return new OperationResult(success: true, "사용자 희망 설정을 저장했습니다. 실제 하드웨어 적용을 의미하지 않습니다.");
				}
				catch (Exception ex) when (IsStorageError(ex) || ex is SerializationException || ex is XmlException)
				{
					return new OperationResult(success: false, "설정을 저장하지 못했습니다. 기존 설정 파일은 삭제하지 않았습니다.");
				}
				finally
				{
					if (text != null)
					{
						try
						{
							File.Delete(text);
						}
						catch (Exception ex2) when (IsStorageError(ex2))
						{
						}
					}
				}
			}
		}

		private SettingsLoadResult RecoverCorrupt()
		{
			try
			{
				LocalPathPolicy.EnsureNoReparsePoints(FilePath);
				string destFileName = Path.Combine(DirectoryPath, "settings.corrupt-" + DateTime.UtcNow.ToString("yyyyMMddTHHmmss") + "-" + Guid.NewGuid().ToString("N") + ".json");
				File.Move(FilePath, destFileName);
				canSave = true;
				return Defaults("손상된 설정 원본을 별도 파일로 보존했습니다. 기본 사용자 설정으로 시작합니다.", allowSave: true);
			}
			catch (Exception ex) when (IsStorageError(ex))
			{
				canSave = false;
				return Defaults("손상된 설정 원본을 보존할 수 없어 저장을 차단했습니다.", allowSave: false);
			}
		}

		private byte[] ReadBounded()
		{
			using (FileStream fileStream = new FileStream(FilePath, FileMode.Open, FileAccess.Read, FileShare.Read))
			{
				if (fileStream.Length > 65536)
				{
					throw new IOException("설정 파일 크기 제한을 초과했습니다.");
				}
				using (MemoryStream memoryStream = new MemoryStream())
				{
					byte[] array = new byte[4096];
					int num;
					while ((num = fileStream.Read(array, 0, array.Length)) > 0)
					{
						if (memoryStream.Length + num > 65536)
						{
							throw new IOException("설정 파일 크기 제한을 초과했습니다.");
						}
						memoryStream.Write(array, 0, num);
					}
					return memoryStream.ToArray();
				}
			}
		}

		private static T Deserialize<T>(byte[] bytes)
		{
			using (MemoryStream stream = new MemoryStream(bytes, writable: false))
			{
				return (T)new DataContractJsonSerializer(typeof(T)).ReadObject(stream);
			}
		}

		private static int ReadSchema(byte[] bytes)
		{
			return Deserialize<SchemaHeader>(bytes)?.SchemaVersion ?? 0;
		}

		private static SettingsLoadResult Defaults(string warning, bool allowSave)
		{
			return new SettingsLoadResult(new AppSettings(), warning, allowSave);
		}

		private static bool IsStorageError(Exception ex)
		{
			if (!(ex is IOException) && !(ex is UnauthorizedAccessException) && !(ex is ArgumentException) && !(ex is NotSupportedException))
			{
				return ex is SecurityException;
			}
			return true;
		}
	}
}
