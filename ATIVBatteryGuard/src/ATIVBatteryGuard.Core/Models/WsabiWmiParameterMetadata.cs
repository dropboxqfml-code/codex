namespace ATIVBatteryGuard.Core.Models
{
    public enum WsabiWmiParameterShape { NotChecked, Missing, ScalarObject, Other }
    public enum WsabiWmiQualifierMatch { Missing, MatchesDataBuffer, Other, UnspecifiedObject, Invalid }
    public enum WsabiWmiParameterBinding
    {
        Unknown, MatchesDataBuffer, OtherDefinition, ConflictingQualifiers, InvalidMetadata
    }

    // A fixed parameter definition only. Raw qualifier strings, values and
    // provider errors are never retained in this object.
    public sealed class WsabiWmiParameterMetadata
    {
        public WsabiWmiParameterShape Shape { get; }
        public WsabiWmiQualifierMatch EmbeddedInstanceMatch { get; }
        public WsabiWmiQualifierMatch CimTypeMatch { get; }
        public WsabiWmiParameterBinding Binding { get; }
        public bool? IsDataBuffer => Binding == WsabiWmiParameterBinding.MatchesDataBuffer ? true
            : Binding == WsabiWmiParameterBinding.OtherDefinition ? false : (bool?)null;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        public WsabiWmiParameterMetadata()
            : this(WsabiWmiParameterShape.NotChecked, WsabiWmiQualifierMatch.Missing, WsabiWmiQualifierMatch.Missing) { }

        internal WsabiWmiParameterMetadata(WsabiWmiParameterShape shape,
            WsabiWmiQualifierMatch embeddedInstance, WsabiWmiQualifierMatch cimType)
        {
            if (!System.Enum.IsDefined(typeof(WsabiWmiParameterShape), shape))
            {
                Shape = WsabiWmiParameterShape.NotChecked;
                Binding = WsabiWmiParameterBinding.InvalidMetadata;
                return;
            }
            Shape = shape;
            if (shape != WsabiWmiParameterShape.ScalarObject)
            {
                // Type/shape mismatch is already an observation. Qualifiers on
                // a different shape do not establish an embedded class.
                Binding = shape == WsabiWmiParameterShape.NotChecked
                    ? WsabiWmiParameterBinding.Unknown : WsabiWmiParameterBinding.OtherDefinition;
                return;
            }
            EmbeddedInstanceMatch = !System.Enum.IsDefined(typeof(WsabiWmiQualifierMatch), embeddedInstance) ||
                embeddedInstance == WsabiWmiQualifierMatch.UnspecifiedObject
                ? WsabiWmiQualifierMatch.Invalid : embeddedInstance;
            CimTypeMatch = System.Enum.IsDefined(typeof(WsabiWmiQualifierMatch), cimType)
                ? cimType : WsabiWmiQualifierMatch.Invalid;
            if (EmbeddedInstanceMatch == WsabiWmiQualifierMatch.Invalid || CimTypeMatch == WsabiWmiQualifierMatch.Invalid)
            {
                Binding = WsabiWmiParameterBinding.InvalidMetadata;
                return;
            }
            bool match = EmbeddedInstanceMatch == WsabiWmiQualifierMatch.MatchesDataBuffer ||
                CimTypeMatch == WsabiWmiQualifierMatch.MatchesDataBuffer;
            bool other = EmbeddedInstanceMatch == WsabiWmiQualifierMatch.Other ||
                CimTypeMatch == WsabiWmiQualifierMatch.Other;
            Binding = match && other ? WsabiWmiParameterBinding.ConflictingQualifiers
                : match ? WsabiWmiParameterBinding.MatchesDataBuffer
                : other ? WsabiWmiParameterBinding.OtherDefinition : WsabiWmiParameterBinding.Unknown;
        }
    }
}
