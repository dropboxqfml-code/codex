using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;

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
                string relative = fullPath.Substring(Path.GetPathRoot(fullPath).Length);
                if (relative.Split(new[] { '\\', '/' }, StringSplitOptions.RemoveEmptyEntries).Any(part => !IsSafeFileName(part)))
                    throw new IOException("로컬 폴더 이름을 확인하세요.");
				DriveType driveType = new DriveInfo(Path.GetPathRoot(fullPath)).DriveType;
				if (driveType != DriveType.Fixed && driveType != DriveType.Removable && driveType != DriveType.Ram)
				{
					throw new IOException("로컬 저장 드라이브를 확인할 수 없습니다.");
				}
			}
			EnsureNoReparsePoints(fullPath);
			return fullPath;
		}

        public static bool IsSafeFileName(string name)
        {
            if (string.IsNullOrWhiteSpace(name) || name.Length > 255 || name.EndsWith(".", StringComparison.Ordinal)
                || name.EndsWith(" ", StringComparison.Ordinal)
                || name.Any(c => char.IsControl(c) || "<>:\"/\\|?*".IndexOf(c) >= 0)) return false;
            try { new UTF8Encoding(false, true).GetByteCount(name); } catch (EncoderFallbackException) { return false; }
            string stem = name.Split('.')[0].TrimEnd(' ');
            return !new[] { "CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$" }
                .Concat("123456789¹²³".SelectMany(c => new[] { "COM" + c, "LPT" + c }))
                .Any(reserved => string.Equals(reserved, stem, StringComparison.OrdinalIgnoreCase));
        }

        public static string NormalizeFile(string path)
        {
            if (string.IsNullOrWhiteSpace(path) || !Path.IsPathRooted(path)
                || path.StartsWith(@"\\", StringComparison.Ordinal) || path.StartsWith("//", StringComparison.Ordinal)
                || path.IndexOf("://", StringComparison.Ordinal) >= 0) throw new IOException("로컬 파일 위치를 확인하세요.");
            NormalizeDirectory(Path.GetDirectoryName(path));
            if (!IsSafeFileName(Path.GetFileName(path))) throw new IOException("파일 이름과 확장자를 확인하세요.");
            string full = Path.GetFullPath(path);
            EnsureNoReparsePoints(full);
            return full;
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
