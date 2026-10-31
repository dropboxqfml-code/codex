using System;
using System.Collections.Generic;
using System.IO;

namespace ATIVBatteryGuard.Core.Storage
{
	public static class LocalPathPolicy
	{
		public static string NormalizeDirectory(string directory)
		{
			if (string.IsNullOrWhiteSpace(directory) || directory.StartsWith("\\\\", StringComparison.Ordinal) || directory.StartsWith("//", StringComparison.Ordinal) || directory.IndexOf("://", StringComparison.Ordinal) >= 0)
			{
				throw new IOException("로컬 저장 폴더만 사용할 수 있습니다.");
			}
			string fullPath = Path.GetFullPath(directory);
			if (fullPath.StartsWith("\\\\", StringComparison.Ordinal) || fullPath.StartsWith("//", StringComparison.Ordinal))
			{
				throw new IOException("로컬 저장 폴더만 사용할 수 있습니다.");
			}
			if (Environment.OSVersion.Platform == PlatformID.Win32NT)
			{
				DriveType driveType = new DriveInfo(Path.GetPathRoot(fullPath)).DriveType;
				if (driveType != DriveType.Fixed && driveType != DriveType.Removable && driveType != DriveType.Ram)
				{
					throw new IOException("로컬 저장 드라이브를 확인할 수 없습니다.");
				}
			}
			EnsureNoReparsePoints(fullPath);
			return fullPath;
		}

		public static void EnsureNoReparsePoints(string path)
		{
			string text = Path.GetFullPath(path);
			Stack<string> stack = new Stack<string>();
			while (!string.IsNullOrEmpty(text))
			{
				stack.Push(text);
				string directoryName = Path.GetDirectoryName(text);
				if (directoryName == text)
				{
					break;
				}
				text = directoryName;
			}
			foreach (string item in stack)
			{
				try
				{
					if ((File.GetAttributes(item) & FileAttributes.ReparsePoint) != 0)
					{
						throw new IOException("링크 경로에는 데이터를 저장하지 않습니다.");
					}
				}
				catch (FileNotFoundException)
				{
				}
				catch (DirectoryNotFoundException)
				{
				}
			}
		}
	}
}
