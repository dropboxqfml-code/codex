using System;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.ManualProtectionHelper
{
    // An enum and two bounded correlation tokens only. Never a path, address,
    // threshold, raw command, alternate executable, worker mode or old purpose.
    internal static class ManualHelperAdmission
    {
        internal const string Argument = "--manual-v1";
        internal const string PipePrefix = "ATIVBatteryGuard-Manual-v1-";

        internal static bool TryParse(string[] args, out ManualProtectionContext context)
        {
            context = null;
            if (args == null || args.Length != 4 || args[0] != Argument) return false;
            ManualProtectionOperation operation;
            if (!Enum.TryParse(args[2], false, out operation) || !Enum.IsDefined(typeof(ManualProtectionOperation), operation) ||
                operation.ToString() != args[2]) return false;
            try { context = new ManualProtectionContext(args[1], args[3], operation); return true; }
            catch { return false; }
        }

        internal static string Confirmation(ManualProtectionOperation operation)
        {
            switch (operation)
            {
                case ManualProtectionOperation.ReadState:
                    return "보호 모드·상한·하한을 최대3회 고정 조회합니다. 설정은 변경하지 않습니다.\n\n" + Common;
                case ManualProtectionOperation.Enable80:
                    return "80% 보호를 켭니다. 이번 사전 모드가0일 때만 설정1을 한 번 요청하며, 상한80·하한75로 바뀔 수 있습니다. 전후 읽기 포함 최대7회입니다.\n\n" +
                        "실패 뒤 자동으로 끄거나 이전 임계값으로 복원하지 않습니다.\n\n" + Common;
                case ManualProtectionOperation.DisableProtection:
                    return "보호를 해제합니다. 이번 사전 모드가1일 때만 설정0을 한 번 요청합니다. 전후 읽기 포함 최대3회입니다.\n\n" +
                        "충전이 재개될 수 있습니다. 자동으로 다시 켜거나 이전 임계값을 복원하지 않으며 100% 충전을 보장하지 않습니다.\n\n" + Common;
                default: throw new ArgumentOutOfRangeException(nameof(operation));
            }
        }

        private const string Common = "대상은 검증된940X3G/930X3G·P05ACJ profile이며 불일치에서는 호출하지 않습니다.\n" +
            "초기화·재시도·임의 명령·드라이버/서비스/보안 변경은 없습니다.\n" +
            "표시 시간 초과는 실제 종료가 아닙니다. 작업·정리 중 창이나 helper를 강제 종료하지 마세요.\n\n" +
            "이 동작을 지금 한 번 수행하시겠습니까?";
    }
}
