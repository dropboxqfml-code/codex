using System;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Parses bounded historical console text only. No file, clipboard, WMI,
    // reservation, callback, network or hardware dependencies are present.
    public static class WsabiWmiExperimentReviewParser
    {
        public const int MaximumCharacters = 8192;
        public const int MaximumLines = 64;
        public const int MaximumLineCharacters = 512;
        private const string Revision = "수정판: 승인된 단1회 조회 · 경로 정보 확보 보완 (Query65-locator-v2)";
        private const string Title = "ATIV Battery Guard — 승인된 한정 WMI 조회 후보 실험";
        private const string Scope = "범위: 고정 후보 0x65, 최대 1회. 자동 재시도 없음.";
        private static readonly string[] Prefixes = {
            "현재 토큰:", "결과:", "사전 검증:", "사전 검증 단계:", "OEM 호출 요청:",
            "메서드 응답 판정:", "프레임 판정:", "후보 표식:" };

        public static WsabiWmiExperimentReview Parse(string input)
        {
            if (string.IsNullOrWhiteSpace(input) || input.Length > MaximumCharacters)
                return Invalid();
            if (input[0] == '\uFEFF') input = input.Substring(1);
            input = input.Replace("\r\n", "\n");
            if (input.IndexOf('\r') >= 0) return Invalid();
            foreach (char value in input)
                if (char.IsControl(value) && value != '\n' && value != '\t') return Invalid();
            string[] lines = input.Split('\n');
            if (lines.Length > MaximumLines) return Invalid();
            var values = new string[Prefixes.Length];
            bool revision = false, title = false, scope = false;
            foreach (string original in lines)
            {
                if (original.Length > MaximumLineCharacters) return Invalid();
                string line = original.Trim();
                if (line.StartsWith("수정판:", StringComparison.Ordinal))
                {
                    if (revision || line != Revision) return Invalid();
                    revision = true;
                }
                else if (line.StartsWith("ATIV Battery Guard", StringComparison.Ordinal))
                {
                    if (title || line != Title) return Invalid();
                    title = true;
                }
                else if (line.StartsWith("범위:", StringComparison.Ordinal))
                {
                    if (scope || line != Scope) return Invalid();
                    scope = true;
                }
                else
                {
                    for (int index = 0; index < Prefixes.Length; index++)
                    {
                        if (!line.StartsWith(Prefixes[index], StringComparison.Ordinal)) continue;
                        if (values[index] != null) return Invalid();
                        values[index] = line.Substring(Prefixes[index].Length).Trim();
                        break;
                    }
                }
            }
            if (!revision || !title || !scope) return Invalid();
            foreach (string value in values)
                if (string.IsNullOrEmpty(value)) return Invalid();

            ProcessElevationState elevation;
            WsabiWmiOneShotStatus result;
            WsabiWmiMetadataStatus preflight;
            WsabiWmiOneShotPreflightStage stage;
            WsabiWmiMethodReplyStatus? method;
            WsabiWmiReplyStatus? frame;
            WsabiWmiCandidateMarker marker;
            if (!TryEnumName(values[0], out elevation) || !TryEnumSuffix(values[1], out result) ||
                !TryEnumSuffix(values[2], out preflight) || !TryEnumSuffix(values[3], out stage) ||
                !TryOptionalEnum(values[5], out method) || !TryOptionalEnum(values[6], out frame) ||
                !TryMarker(values[7], out marker) || (values[4] != "요청됨" && values[4] != "없음"))
                return Invalid();
            bool requested = values[4] == "요청됨";
            bool hasReply = method.HasValue || frame.HasValue || marker != WsabiWmiCandidateMarker.NotObserved;
            if ((!requested && hasReply) ||
                (requested && (elevation != ProcessElevationState.Elevated ||
                    preflight != WsabiWmiMetadataStatus.Complete || stage != WsabiWmiOneShotPreflightStage.Ready ||
                    (result != WsabiWmiOneShotStatus.ResponseReceived && result != WsabiWmiOneShotStatus.TransportFailure))) ||
                ((result == WsabiWmiOneShotStatus.ResponseReceived || result == WsabiWmiOneShotStatus.TransportFailure) && !requested) ||
                (result != WsabiWmiOneShotStatus.ResponseReceived && hasReply) ||
                !ReplyTupleMatches(method, frame, marker))
                return new WsabiWmiExperimentReview(WsabiWmiExperimentReviewStatus.Inconsistent);
            if (result == WsabiWmiOneShotStatus.ResponseReceived && method == WsabiWmiMethodReplyStatus.FrameChecked &&
                frame == WsabiWmiReplyStatus.ValidFrame && marker != WsabiWmiCandidateMarker.NotObserved)
                return new WsabiWmiExperimentReview(WsabiWmiExperimentReviewStatus.ValidatedFrameMeaningUnknown,
                    true, marker);
            return new WsabiWmiExperimentReview(WsabiWmiExperimentReviewStatus.NoValidatedResponse, requested);
        }

        private static bool ReplyTupleMatches(WsabiWmiMethodReplyStatus? method,
            WsabiWmiReplyStatus? frame, WsabiWmiCandidateMarker marker)
        {
            if (method.HasValue != frame.HasValue) return false;
            if ((frame == WsabiWmiReplyStatus.ValidFrame) != (marker != WsabiWmiCandidateMarker.NotObserved)) return false;
            if (!method.HasValue) return true;
            if (method == WsabiWmiMethodReplyStatus.ApiNotSuccessful)
                return frame == WsabiWmiReplyStatus.ApiNotSuccessful;
            if (method != WsabiWmiMethodReplyStatus.FrameChecked)
                return frame == WsabiWmiReplyStatus.InvalidEnvelope;
            return frame == WsabiWmiReplyStatus.ValidFrame || frame == WsabiWmiReplyStatus.MissingResponse ||
                frame == WsabiWmiReplyStatus.InvalidType || frame == WsabiWmiReplyStatus.InvalidShape ||
                frame == WsabiWmiReplyStatus.UnsupportedLength || frame == WsabiWmiReplyStatus.InvalidAcknowledgement;
        }

        private static bool TryEnumName<T>(string text, out T value) where T : struct
        {
            value = default(T);
            // Enum.TryParse alone accepts numeric and combined enum forms.
            if (Array.IndexOf(Enum.GetNames(typeof(T)), text) < 0) return false;
            return Enum.TryParse(text, false, out value);
        }

        private static bool TryEnumSuffix<T>(string text, out T value) where T : struct
        {
            value = default(T);
            int start = text.LastIndexOf('(');
            return start > 0 && text[start - 1] == ' ' && text.EndsWith(")", StringComparison.Ordinal) &&
                TryEnumName(text.Substring(start + 1, text.Length - start - 2), out value);
        }

        private static bool TryOptionalEnum<T>(string text, out T? value) where T : struct
        {
            value = null;
            if (text == "미관측") return true;
            T parsed;
            if (!TryEnumName(text, out parsed)) return false;
            value = parsed;
            return true;
        }

        private static bool TryMarker(string text, out WsabiWmiCandidateMarker marker)
        {
            marker = WsabiWmiCandidateMarker.NotObserved;
            switch (text)
            {
                case "미관측": return true;
                case "0": marker = WsabiWmiCandidateMarker.Zero; return true;
                case "1": marker = WsabiWmiCandidateMarker.One; return true;
                case "FF": marker = WsabiWmiCandidateMarker.FF; return true;
                case "Other (원문 제외)": marker = WsabiWmiCandidateMarker.Other; return true;
                default: return false;
            }
        }

        private static WsabiWmiExperimentReview Invalid()
            => new WsabiWmiExperimentReview(WsabiWmiExperimentReviewStatus.InvalidInput);
    }
}
