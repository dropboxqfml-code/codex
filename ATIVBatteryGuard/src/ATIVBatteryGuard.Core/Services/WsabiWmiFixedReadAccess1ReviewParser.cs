using System;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // A separate fixed-format historical-text parser. It does not import SDK
    // types, authenticate an execution, recreate a frame or read any file.
    public static class WsabiWmiFixedReadAccess1ReviewParser
    {
        public const int MaximumCharacters = 8192;
        public const int MaximumLines = 64;
        public const int MaximumLineCharacters = 512;
        private const string Title = "ATIV Battery Guard — FixedModeReadA-Access1";
        private const string Scope = "method 최대1 / 저장 byte 샘플0~1 / 초기화·handshake·재시도·설정 변경·fallback 각각0";
        private const string Safety = "실제 충전 제어: Unsupported. 저장 후보는 실제 충전 제한 적용이나 임계값의 증거가 아닙니다.";
        private const string ReadyNotice = "고정 시도 준비 완료: owner 획득 최대2초 / 응답 표시10초 / 실제 종료·정리는 별도 대기.";
        private const string Pending = "관련 종료·소유권 확인 불가: Pending. 관련 참조를 유지하고 추가 해제·새 호출·강제 종료·재시도 없이 기다립니다.";
        private const string Complete = "관련 정리: Complete. 이번 시험 종료. 재시도하지 마세요.";
        private const string RunFailure = "시도 결과 확인 불가. 성공으로 해석하지 않고 관련 정리를 기다립니다.";
        private const string PreStopped = "준비 전 중단: 호출 없음. 예약은 소모됐습니다.";
        private const string PreflightStopped = "호출 없음. 이번 시험은 종료하며 재시도하지 않습니다.";
        private const string CreationStopped = "호출 전 중단. 비교 내용·원문 요청은 기록하지 않습니다. 재시도 없음.";
        private const string SdkStopped = "WMI method 호출 없음. 준비 종료. 이번 시험을 반복하지 마세요.";
        private const string BeforeCallFailed = "호출 전 준비 결과 확인 불가. 원문 오류는 제외하며 재시도하지 않습니다.";
        private const string JournalStopped = "TXT 기록 실패로 호출 전에 종료했습니다. 예약은 소모됐으며 재시도하지 않습니다.";
        private static readonly string[] Prefixes = {
            "현재 토큰:", "새 목적의 영속 1회 예약:", "사전 검증:", "열거 세부 단계:",
            "열거 정리 오류 관측:", "고정 요청 준비:", "SDK 준비:", "대상 연결:",
            "등록:", "입력:", "교환 상태:", "조회 판정:", "저장 모드 후보:" };
        private static readonly string[] Markers = { Title, Scope, Safety, ReadyNotice, Pending, Complete,
            RunFailure, PreStopped, PreflightStopped, CreationStopped, SdkStopped, BeforeCallFailed, JournalStopped };
        private static readonly string[] Notes = {
            "결과 표시는 실제 종료 보장이 아닙니다. 관련 정리 완료를 기다립니다.",
            "실제 보호 조회/충전 제어 지원은 활성화하지 않습니다. 원문 frame·비교 내용·경로·고유 ID는 기록하지 않습니다.",
            "메타데이터 준비 표시 시간 초과: 호출 전 작업의 실제 반환을 기다립니다. 강제 종료·재시도 없음.",
            "SDK 준비 표시 시간 초과: 소유권과 실제 준비 종료를 기다립니다. 강제 종료·재시도 없음." };

        private enum PreflightStatus { Ready, UnsupportedPlatform, DeviceMismatch, MetadataMismatch, TargetMismatch, ClassNotFound, NamespaceNotFound, AccessDenied, TimedOut, Unavailable }
        private enum PreflightStage { Platform, DeviceScope, ModelRead, BiosRead, MethodScope, Metadata, MethodEnumeration, TargetRead, InputParameters, BufferInstance, Ready }
        private enum Substep { None, BudgetCheck, QueryCreate, QueryGet, EnumeratorCreate, MoveNext, Current, ActivePropertyRead, ActiveTypeRead, ActiveArrayRead, ActiveValueRead, InstancePathRead, PathKindRead, PathClassRead, RelativePathObjectRead, RelativePathRead, RowDispose, EnumeratorDispose, CollectionDispose, SearcherDispose }
        private enum Error { None, WmiAccessDenied, WindowsAccessDenied, WmiClassNotFound, WmiNamespaceNotFound, WmiNotFound, WmiTimedOut, WindowsTimedOut, ManagedAccessDenied, ManagedSecurityDenied, ManagedTimedOut, Other }
        private enum SdkPreparation { Ready, PlanMissing, AttemptAlreadyUsed, TargetMismatch, RequestMismatch, PreparationNotReady, InputNotReady, SdkBindingNotReady, ReadSpecificationUnavailable }
        private enum SdkTarget { NotObserved, Ready, IdentityMismatch, BindingAlreadyUsed, UnsupportedTargetType, NotConnected, LocalScopeMismatch, InstanceMismatch, PropertyAccessFailed }
        private enum Registration { NotObserved, Ready, Cancelled, ObserverUnavailable, RegistrationFailed, UnexpectedCallback, CleanupFailed }
        private enum Input { NotObserved, Populated, PlanMissing, RequestMismatch, ObjectsMissingOrAliased, ObjectsAlreadyUsed, ShapeMismatch, PropertyAccessFailed }

        public static WsabiWmiFixedReadAccess1Review Parse(string input)
        {
            if (input == null || input.Length > MaximumCharacters || string.IsNullOrWhiteSpace(input)) return Invalid();
            if (input[0] == '\uFEFF') input = input.Substring(1);
            input = input.Replace("\r\n", "\n");
            if (input.IndexOf('\r') >= 0) return Invalid();
            foreach (char value in input)
                if (char.IsControl(value) && value != '\n' && value != '\t') return Invalid();
            string[] lines = input.Split('\n');
            if (lines.Length > MaximumLines) return Invalid();
            var values = new string[Prefixes.Length];
            var seen = new bool[Markers.Length];
            int lastField = -1;
            foreach (string original in lines)
            {
                if (original.Length > MaximumLineCharacters) return Invalid();
                string line = original.Trim();
                int marker = Array.IndexOf(Markers, line);
                if (marker >= 0)
                {
                    if (seen[marker]) return Invalid();
                    if ((marker == 0 && (lastField != -1 || seen[1] || seen[2])) ||
                        (marker == 1 && (lastField != 1 || !seen[0])) ||
                        (marker == 2 && (lastField != 1 || !seen[1])) ||
                        (marker == 3 && (lastField != 9 || seen[4] || seen[5])))
                        return Result(WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent);
                    seen[marker] = true;
                    continue;
                }
                if (line.StartsWith("ATIV Battery Guard", StringComparison.Ordinal) ||
                    line.StartsWith("method 최대", StringComparison.Ordinal) || line.StartsWith("실제 충전 제어:", StringComparison.Ordinal) ||
                    line.StartsWith("고정 시도 준비 완료:", StringComparison.Ordinal) || line.StartsWith("관련 정리:", StringComparison.Ordinal) ||
                    line.StartsWith("관련 종료·소유권 확인 불가:", StringComparison.Ordinal)) return Invalid();
                bool matched = false;
                for (int index = 0; index < Prefixes.Length; index++)
                {
                    if (!line.StartsWith(Prefixes[index], StringComparison.Ordinal)) continue;
                    if (values[index] != null || index <= lastField) return Invalid();
                    if (seen[4] || seen[5]) return Result(WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent);
                    values[index] = line.Substring(Prefixes[index].Length).Trim();
                    if (values[index].Length == 0) return Invalid();
                    matched = true;
                    lastField = index;
                    break;
                }
                // Only the tool's fixed informational notes are ignored. An
                // unknown line cannot hide a contradictory warning or supply a
                // missing field, and is never retained in the result.
                if (!matched && line.Length != 0 && Array.IndexOf(Notes, line) < 0) return Invalid();
            }
            if (!seen[0] || !seen[1] || !seen[2] || values[0] == null || values[1] == null) return Invalid();
            ProcessElevationState elevation; WsabiWmiOneShotReservationStatus reservation;
            if (!Name(values[0], out elevation) || !Name(values[1], out reservation)) return Invalid();
            if (elevation != ProcessElevationState.Elevated || reservation != WsabiWmiOneShotReservationStatus.Claimed)
                return Result(WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent);
            if (seen[4] && seen[5]) return Result(WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent);
            bool abort = seen[7] || seen[8] || seen[9] || seen[10] || seen[11] || seen[12];

            if (values[2] == null)
                return seen[7] && None(values, 3) && !seen[4] && !seen[5] ? Result(WsabiWmiFixedReadAccess1ReviewStatus.NoReportedCandidate) : Invalid();
            PreflightStatus preflight; PreflightStage stage; Substep substep; Error error;
            if (!Pair(values[2], " / 단계: ", out preflight, out stage) ||
                !Pair(values[3], " / 오류 범주: ", out substep, out error) ||
                (values[4] != "No" && values[4] != "Yes")) return Invalid();
            if (preflight != PreflightStatus.Ready)
                return seen[8] && None(values, 5) && !seen[3] && !seen[4] && !seen[5]
                    ? Result(WsabiWmiFixedReadAccess1ReviewStatus.NoReportedCandidate) : Result(WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent);
            if (stage != PreflightStage.Ready || substep != Substep.None || error != Error.None || values[4] != "No")
                return Result(WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent);
            WsabiWmiFixedReadCreationStatus creation;
            if (!Name(values[5], out creation)) return Invalid();
            if (creation != WsabiWmiFixedReadCreationStatus.Created)
                return seen[9] && None(values, 6) && !seen[3] && !seen[4] && !seen[5]
                    ? Result(WsabiWmiFixedReadAccess1ReviewStatus.NoReportedCandidate) : Result(WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent);
            if (values[6] == null)
            {
                if (!None(values, 7) || seen[3] || seen[5]) return Invalid();
                if (seen[4]) return Result(WsabiWmiFixedReadAccess1ReviewStatus.CompletionPending);
                return seen[9] || seen[11] ? Result(WsabiWmiFixedReadAccess1ReviewStatus.NoReportedCandidate) : Invalid();
            }
            SdkPreparation sdk; SdkTarget target; Registration registration; Input preparedInput;
            if (!Name(values[6], out sdk) || !Name(values[7], out target) ||
                !Name(values[8], out registration) || !Name(values[9], out preparedInput)) return Invalid();
            if (sdk != SdkPreparation.Ready)
            {
                if (!None(values, 10) || seen[3] || seen[5]) return Result(WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent);
                if (seen[4]) return Result(WsabiWmiFixedReadAccess1ReviewStatus.CompletionPending);
                return seen[10] ? Result(WsabiWmiFixedReadAccess1ReviewStatus.NoReportedCandidate) : Invalid();
            }
            if (target != SdkTarget.Ready || registration != Registration.Ready || preparedInput != Input.Populated || !seen[3])
                return Result(WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent);
            if (None(values, 10))
            {
                if (seen[4]) return Result(WsabiWmiFixedReadAccess1ReviewStatus.CompletionPending);
                return (seen[6] && seen[5]) || seen[12] ? Result(WsabiWmiFixedReadAccess1ReviewStatus.NoReportedCandidate) : Invalid();
            }
            WsabiWmiFrameExchangeStatus exchange; WsabiWmiFixedReadStatus verdict;
            if (!Name(values[10], out exchange) || !Name(values[11], out verdict) ||
                (values[12] != "0" && values[12] != "1" && values[12] != "미관측")) return Invalid();
            if (abort || !TupleMatches(exchange, verdict, values[12])) return Result(WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent);
            if (seen[4]) return Result(WsabiWmiFixedReadAccess1ReviewStatus.CompletionPending);
            if (!seen[5]) return Invalid();
            if (seen[6] || verdict != WsabiWmiFixedReadStatus.StoredModeCandidate)
                return Result(WsabiWmiFixedReadAccess1ReviewStatus.NoReportedCandidate);
            return new WsabiWmiFixedReadAccess1Review(WsabiWmiFixedReadAccess1ReviewStatus.ReportedStoredModeCandidate,
                values[12] == "0" ? 0 : 1);
        }

        private static bool TupleMatches(WsabiWmiFrameExchangeStatus exchange, WsabiWmiFixedReadStatus verdict, string candidate)
        {
            if (verdict == WsabiWmiFixedReadStatus.StoredModeCandidate)
                return exchange == WsabiWmiFrameExchangeStatus.ReplyReceived && candidate != "미관측";
            if (candidate != "미관측") return false;
            switch (exchange)
            {
                case WsabiWmiFrameExchangeStatus.InvalidRequest: return verdict == WsabiWmiFixedReadStatus.ExchangeInvalidRequest;
                case WsabiWmiFrameExchangeStatus.Cancelled: return verdict == WsabiWmiFixedReadStatus.ExchangeCancelled;
                case WsabiWmiFrameExchangeStatus.Busy: return verdict == WsabiWmiFixedReadStatus.ExchangeBusy;
                case WsabiWmiFrameExchangeStatus.TimedOut: return verdict == WsabiWmiFixedReadStatus.ExchangeTimedOut;
                case WsabiWmiFrameExchangeStatus.TransportFailure: return verdict == WsabiWmiFixedReadStatus.ExchangeTransportFailure;
                default:
                    switch (verdict)
                    {
                        case WsabiWmiFixedReadStatus.MethodEnvelopeRejected:
                        case WsabiWmiFixedReadStatus.FrameRejected:
                        case WsabiWmiFixedReadStatus.DispatchFailurePrefix:
                        case WsabiWmiFixedReadStatus.UnexpectedControlPrefix:
                        case WsabiWmiFixedReadStatus.UnexpectedClearedTail:
                        case WsabiWmiFixedReadStatus.InputEcho:
                        case WsabiWmiFixedReadStatus.PreservedAddressMismatch:
                        case WsabiWmiFixedReadStatus.PreservedContentMismatch:
                        case WsabiWmiFixedReadStatus.CandidateOutsideDomain: return true;
                        default: return false;
                    }
            }
        }

        private static bool None(string[] values, int start)
        {
            for (int index = start; index < values.Length; index++) if (values[index] != null) return false;
            return true;
        }

        private static bool Pair<T, U>(string text, string separator, out T left, out U right) where T : struct where U : struct
        {
            left = default(T); right = default(U);
            if (text == null) return false;
            int index = text.IndexOf(separator, StringComparison.Ordinal);
            return index > 0 && text.IndexOf(separator, index + separator.Length, StringComparison.Ordinal) < 0 &&
                Name(text.Substring(0, index), out left) && Name(text.Substring(index + separator.Length), out right);
        }

        private static bool Name<T>(string text, out T value) where T : struct
        {
            value = default(T);
            return text != null && Array.IndexOf(Enum.GetNames(typeof(T)), text) >= 0 && Enum.TryParse(text, false, out value);
        }

        private static WsabiWmiFixedReadAccess1Review Result(WsabiWmiFixedReadAccess1ReviewStatus status)
            => new WsabiWmiFixedReadAccess1Review(status);
        private static WsabiWmiFixedReadAccess1Review Invalid() => Result(WsabiWmiFixedReadAccess1ReviewStatus.InvalidInput);
    }
}
