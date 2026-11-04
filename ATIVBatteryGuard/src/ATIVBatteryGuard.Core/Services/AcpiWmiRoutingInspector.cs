using System;
using System.Collections.Generic;
using System.Text;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // A deliberately restricted AML syntax reader. It never evaluates AML,
    // follows operation regions, loads tables, or executes named methods.
    // Unsupported syntax closes the current container, never byte-resyncs.
    public static class AcpiWmiRoutingInspector
    {
        public const int MaximumTableBytes = 4 * 1024 * 1024;
        public const int MaximumHelperDepth = 2;
        public const int MaximumHelperDefinitions = 8;
        public const int MaximumHelperCallSites = 32;
        public const int MaximumNamespaceObjects = 8192;
        public const int MaximumObjectRelationNames = 64;
        private static readonly byte[] KnownGuid = new Guid("C16C47BA-50E3-444A-AF3A-B1C348380001").ToByteArray();

        public static AcpiWmiRoutingReport Inspect(byte[] table)
        {
            if (table == null || table.Length < 36) return Invalid();
            if (table.Length > MaximumTableBytes) return new AcpiWmiRoutingReport(AcpiRoutingStatus.LimitExceeded);
            // Own a stable bounded snapshot; callers may immediately clear theirs.
            var copy = (byte[])table.Clone();
            try
            {
                if (!Signature(copy, "DSDT") && !Signature(copy, "SSDT")) return Invalid();
                uint length = (uint)(copy[4] | copy[5] << 8 | copy[6] << 16 | copy[7] << 24);
                if (length != copy.Length) return Invalid();
                int sum = 0; foreach (byte value in copy) sum = (sum + value) & 255;
                if (sum != 0) return Invalid();
                return new Reader(copy).Read();
            }
            catch (LimitException) { return new AcpiWmiRoutingReport(AcpiRoutingStatus.LimitExceeded); }
            catch { return Invalid(); }
            finally { Array.Clear(copy, 0, copy.Length); }
        }

        private static bool Signature(byte[] data, string expected)
        {
            for (int i = 0; i < 4; i++) if (data[i] != expected[i]) return false;
            return true;
        }
        private static AcpiWmiRoutingReport Invalid() => new AcpiWmiRoutingReport(AcpiRoutingStatus.InvalidTable);
        private sealed class ParseException : Exception
        {
            internal readonly AcpiSyntaxFailureKind Kind;
            internal readonly AcpiSyntaxOperation Operation;
            internal ParseException(AcpiSyntaxFailureKind kind = AcpiSyntaxFailureKind.InvalidEncoding,
                AcpiSyntaxOperation operation = AcpiSyntaxOperation.None)
            { Kind = kind; Operation = operation; }
            internal ParseException At(AcpiSyntaxOperation operation) => new ParseException(Kind, Operation | operation);
        }
        private sealed class LimitException : Exception { }
        private sealed class Method { internal string Path; internal int Arguments, Start, End; }
        private sealed class Descriptor { internal string Scope, Suffix; }
        private sealed class NameReference
        {
            internal string Path, Scope;
            internal bool ParentSearch;
        }
        private sealed class NamedDefinition
        {
            internal AcpiNamedObjectKinds Kind;
            internal AcpiAddressSpaceKinds Space;
            internal NameReference Region;
            internal bool Ambiguous;
        }
        private sealed class NamedUse
        {
            internal NameReference Reference;
            internal int Count;
            internal bool Returned, Arg2StoreTarget, StoreTarget;
        }
        private sealed class ClassifiedName
        {
            internal object Identity;
            internal AcpiNamedObjectKinds Kind;
            internal AcpiAddressSpaceKinds Space;
        }
        private sealed class ReferenceSummary
        {
            internal int References, Classified;
            internal bool Unknown, ReturnUnknown, Arg2Unknown, StoreUnknown;
            internal AcpiNamedObjectKinds Kinds, ReturnKinds, Arg2Kinds, StoreKinds;
            internal AcpiAddressSpaceKinds FieldStoreSpaces;
            internal readonly HashSet<object> All = new HashSet<object>();
            internal readonly HashSet<object> Returns = new HashSet<object>();
            internal readonly HashSet<object> Arg2Targets = new HashSet<object>();
        }
        private struct Value
        {
            internal int Kind; // 1: integer, 2: Arg1, 3: Arg2, 4: SizeOf(Arg2), 5: known call, 6: unresolved name
            internal ulong Integer;
            internal int BufferStart, BufferLength;
            internal AcpiNamedObjectKinds DeclarationKind;
            internal NamedUse NamedUse;
        }
        private sealed class BodyEvidence
        {
            internal bool IdOne, Input21, Ff, Complete = true;
            internal int CallSites, Arg2CallArguments, ReturnStatements, UnresolvedNames;
            internal AcpiReturnSyntax Returns;
            internal AcpiSyntaxOperation ExtendedSyntax;
            internal readonly List<Method> Calls = new List<Method>();
            internal int NamedReferenceCount;
            internal bool ObjectRelationLimit;
            internal readonly Dictionary<string, NamedUse> NamedUses = new Dictionary<string, NamedUse>();
            internal readonly HashSet<string> CreatedNames = new HashSet<string>();
        }
        private sealed class FlowEvidence
        {
            internal bool Partial, Limited, Cycle, Ff;
            internal int Inspected, Parsed, Unsupported, Unresolved, CallSites;
            internal int ParsedReturnStatements;
            internal AcpiReturnSyntax ParsedReturns;
            internal AcpiSyntaxOperation ParsedExtendedSyntax, FailureOperations;
            internal AcpiSyntaxFailureKind Failures;
            internal readonly HashSet<Method> Visited = new HashSet<Method>();
            internal readonly HashSet<Method> Active = new HashSet<Method>();
            internal readonly List<BodyEvidence> ParsedBodies = new List<BodyEvidence>();
        }

        private sealed class Reader
        {
            private readonly byte[] bytes;
            private readonly List<Method> methods = new List<Method>();
            private readonly List<Descriptor> descriptors = new List<Descriptor>();
            private readonly HashSet<string> objects = new HashSet<string>();
            private readonly Dictionary<string, NamedDefinition> objectDefinitions = new Dictionary<string, NamedDefinition>();
            private readonly HashSet<string> opaqueObjectScopes = new HashSet<string>();
            private bool complete = true;
            private int nodes;
            internal Reader(byte[] data) { bytes = data; }

            internal AcpiWmiRoutingReport Read()
            {
                Walk(36, bytes.Length, "", 0);
                var matches = new List<Method>();
                foreach (var descriptor in descriptors)
                    foreach (var method in methods)
                        if (method.Path == Join(descriptor.Scope, "WM" + descriptor.Suffix)) matches.Add(method);
                int? args = null; bool? id = null, size = null, ff = null;
                AcpiMethodFlowReport flow = null;
                AcpiObjectReferenceReport objectReferences = null;
                AcpiMethodSyntaxStatus syntax = descriptors.Count > 1 || matches.Count > 1
                    ? AcpiMethodSyntaxStatus.Ambiguous : AcpiMethodSyntaxStatus.NotObserved;
                if (descriptors.Count == 1 && matches.Count == 1)
                {
                    var method = matches[0]; args = method.Arguments;
                    var evidence = new BodyEvidence { Complete = method.Arguments == 3 };
                    syntax = method.Arguments == 3 ? AcpiMethodSyntaxStatus.UnsupportedSyntax : AcpiMethodSyntaxStatus.WrongArgumentCount;
                    if (evidence.Complete)
                    {
                        try { ScanBody(method.Start, method.End, Parent(method.Path), evidence, 0); }
                        catch (ParseException ex)
                        {
                            evidence.Complete = false;
                            flow = new AcpiMethodFlowReport(rootSyntaxFailure: ex.Kind, rootFailureOperations: ex.Operation);
                        }
                    }
                    if (evidence.Complete)
                    {
                        syntax = AcpiMethodSyntaxStatus.Parsed; id = evidence.IdOne; size = evidence.Input21; ff = evidence.Ff;
                        List<BodyEvidence> helpers;
                        flow = InspectFlow(method, evidence, out helpers);
                        objectReferences = InspectObjectReferences(evidence, helpers, flow);
                    }
                }
                return new AcpiWmiRoutingReport(complete ? AcpiRoutingStatus.Complete : AcpiRoutingStatus.Partial,
                    descriptors.Count, matches.Count, args, id, size, ff, syntax, flow, objectReferences);
            }

            private AcpiMethodFlowReport InspectFlow(Method root, BodyEvidence body, out List<BodyEvidence> helpers)
            {
                var flow = new FlowEvidence();
                flow.Visited.Add(root); flow.Active.Add(root);
                VisitFlow(body, 0, flow);
                helpers = flow.ParsedBodies;
                AcpiMethodFlowStatus status = flow.Limited ? AcpiMethodFlowStatus.LimitExceeded :
                    flow.Partial ? AcpiMethodFlowStatus.Partial : AcpiMethodFlowStatus.ParsedObservedDefinitions;
                bool? ff = status == AcpiMethodFlowStatus.ParsedObservedDefinitions && flow.Parsed > 0 ? (bool?)flow.Ff : null;
                return new AcpiMethodFlowReport(status, body.CallSites, body.Arg2CallArguments, body.ReturnStatements,
                    body.Returns, flow.Inspected, flow.Parsed, flow.Unsupported, flow.Unresolved, flow.Cycle, ff,
                    helperSyntaxFailures: flow.Failures, helperFailureOperations: flow.FailureOperations,
                    rootExtendedSyntax: body.ExtendedSyntax,
                    parsedHelperExtendedSyntax: flow.Parsed > 0 ? (AcpiSyntaxOperation?)flow.ParsedExtendedSyntax : null,
                    parsedHelperReturnStatements: flow.Parsed > 0 ? (int?)flow.ParsedReturnStatements : null,
                    parsedHelperReturnSyntax: flow.Parsed > 0 ? (AcpiReturnSyntax?)flow.ParsedReturns : null,
                    parsedHelperLiteralFfReturn: flow.Parsed > 0 ? (bool?)flow.Ff : null);
            }

            private void VisitFlow(BodyEvidence body, int depth, FlowEvidence flow)
            {
                flow.Unresolved += body.UnresolvedNames;
                if (body.UnresolvedNames != 0) flow.Partial = true;
                flow.CallSites += body.CallSites;
                if (flow.CallSites > MaximumHelperCallSites) { flow.Limited = true; return; }
                foreach (Method method in body.Calls)
                {
                    if (flow.Limited) return;
                    if (flow.Active.Contains(method)) { flow.Cycle = true; flow.Partial = true; continue; }
                    if (flow.Visited.Contains(method)) continue;
                    if (depth >= MaximumHelperDepth || flow.Inspected >= MaximumHelperDefinitions)
                    { flow.Limited = true; return; }
                    flow.Visited.Add(method); flow.Inspected++;
                    var child = new BodyEvidence();
                    try { ScanBody(method.Start, method.End, Parent(method.Path), child, 0); }
                    catch (ParseException ex)
                    {
                        flow.Unsupported++; flow.Partial = true;
                        flow.Failures |= ex.Kind; flow.FailureOperations |= ex.Operation;
                        continue;
                    }
                    catch (LimitException) { flow.Limited = true; return; }
                    flow.Parsed++; flow.Ff |= child.Ff;
                    flow.ParsedBodies.Add(child);
                    flow.ParsedReturnStatements += child.ReturnStatements;
                    flow.ParsedReturns |= child.Returns; flow.ParsedExtendedSyntax |= child.ExtendedSyntax;
                    flow.Active.Add(method);
                    VisitFlow(child, depth + 1, flow);
                    flow.Active.Remove(method);
                }
            }

            private void Walk(int start, int end, string scope, int depth)
            {
                CheckDepth(depth);
                int p = start;
                try
                {
                    while (p < end)
                    {
                        Tick(); byte op = Get(ref p, end);
                        if (op == 0x08)
                        {
                            string name = Name(ref p, end, scope);
                            NamedDefinition definition = ObjectName(name);
                            Value value = Arg(ref p, end, scope, null, depth + 1);
                            CommitDefinition(definition, value.DeclarationKind);
                            if (Last(name) == "_WDG")
                            {
                                if (value.BufferStart == 0) { complete = false; continue; }
                                Wdg(value, Parent(name));
                            }
                        }
                        else if (op == 0x10 || op == 0x14 || op == 0x5b)
                        {
                            byte ext = op == 0x5b ? Get(ref p, end) : (byte)0;
                            if (op == 0x5b && (ext == 1 || ext == 2))
                            {
                                NamedDefinition definition = ObjectName(Name(ref p, end, scope));
                                if (ext == 1) Get(ref p, end);
                                CommitDefinition(definition, ext == 1 ? AcpiNamedObjectKinds.Mutex : AcpiNamedObjectKinds.Event);
                                continue;
                            }
                            if (op == 0x5b && ext == 0x80)
                            {
                                NamedDefinition definition = ObjectName(Name(ref p, end, scope));
                                AcpiAddressSpaceKinds space = AddressSpace(Get(ref p, end));
                                Arg(ref p, end, scope, null, depth + 1); Arg(ref p, end, scope, null, depth + 1);
                                CommitDefinition(definition, AcpiNamedObjectKinds.OperationRegion, space);
                                continue;
                            }
                            if (op == 0x5b && ext == 0x88)
                            {
                                NamedDefinition definition = ObjectName(Name(ref p, end, scope));
                                for (int i = 0; i < 3; i++) Arg(ref p, end, scope, null, depth + 1);
                                CommitDefinition(definition, AcpiNamedObjectKinds.Other);
                                continue;
                            }
                            if (op == 0x5b && ext != 0x81 && ext != 0x82 && ext != 0x83 && ext != 0x84 && ext != 0x85 && ext != 0x86 && ext != 0x87)
                                throw new ParseException();
                            int finish = Package(ref p, end);
                            if (op == 0x5b && ext == 0x81)
                            {
                                try { ReadFieldList(p, finish, scope); }
                                catch (ParseException) { complete = false; OpaqueObjectScope(scope); }
                                p = finish; continue;
                            }
                            if (op == 0x5b && (ext == 0x86 || ext == 0x87))
                            { complete = false; OpaqueObjectScope(scope); p = finish; continue; }
                            string name = Name(ref p, finish, scope);
                            if (op == 0x14)
                            {
                                int flags = Get(ref p, finish);
                                if (methods.Count >= 4096) throw new LimitException();
                                methods.Add(new Method { Path = name, Arguments = flags & 7, Start = p, End = finish });
                            }
                            else
                            {
                                NamedDefinition definition = op == 0x5b ? ObjectName(name) : null;
                                if (ext == 0x83) Advance(ref p, finish, 6);
                                if (ext == 0x84) Advance(ref p, finish, 3);
                                if (definition != null) CommitDefinition(definition, AcpiNamedObjectKinds.Other);
                                Walk(p, finish, name, depth + 1);
                            }
                            p = finish;
                        }
                        else if (op == 0x15) { ObjectName(Name(ref p, end, scope)); Advance(ref p, end, 2); }
                        else if (op == 0x06) { Name(ref p, end, scope); ObjectName(Name(ref p, end, scope)); complete = false; }
                        else if (op == 0xa0 || op == 0xa1 || op == 0xa2)
                        { p = Package(ref p, end); complete = false; OpaqueObjectScope(scope); }
                        else if (op != 0xa3) throw new ParseException();
                    }
                }
                catch (ParseException) { complete = false; OpaqueObjectScope(scope); }
            }

            private void ReadFieldList(int start, int end, string scope)
            {
                int p = start;
                NameReference region = ReadNameReference(ref p, end, scope);
                byte flags = Get(ref p, end);
                if ((flags & 0x80) != 0 || (flags & 15) > 5 || ((flags >> 5) & 3) == 3) throw new ParseException();
                var fields = new List<NamedDefinition>();
                while (p < end)
                {
                    Tick(); byte op = bytes[p];
                    if (op == 0) { p++; FieldBitLength(ref p, end); }
                    else if (op == 1) { p++; Advance(ref p, end, 2); }
                    else if (op == 3) { p++; Advance(ref p, end, 3); }
                    else if (NameCharacter(op, true))
                    {
                        var segment = new StringBuilder(4);
                        for (int i = 0; i < 4; i++)
                        {
                            byte value = Get(ref p, end);
                            if (!NameCharacter(value, i == 0)) throw new ParseException();
                            segment.Append((char)value);
                        }
                        NamedDefinition definition = ObjectName(Join(scope, segment.ToString()));
                        FieldBitLength(ref p, end);
                        if (fields.Count >= MaximumNamespaceObjects) throw new LimitException();
                        fields.Add(definition);
                    }
                    else throw new ParseException(); // Includes opaque ConnectField; never resynchronize.
                }
                // A failed FieldList leaves only opaque name barriers. No prefix
                // becomes a typed Field before the entire bounded list parses.
                foreach (NamedDefinition definition in fields)
                {
                    CommitDefinition(definition, AcpiNamedObjectKinds.Field);
                    if (!definition.Ambiguous) definition.Region = region;
                }
            }

            private void FieldBitLength(ref int p, int end)
            {
                byte lead = Get(ref p, end); int following = lead >> 6;
                if (following != 0 && (lead & 0x30) != 0) throw new ParseException();
                // FieldLength uses PkgLength encoding but describes a bit count,
                // not a package extent. It may greatly exceed remaining bytes.
                Advance(ref p, end, following);
            }

            private static AcpiAddressSpaceKinds AddressSpace(byte value)
            {
                switch (value)
                {
                    case 0: return AcpiAddressSpaceKinds.SystemMemory;
                    case 1: return AcpiAddressSpaceKinds.SystemIo;
                    case 2: return AcpiAddressSpaceKinds.PciConfiguration;
                    case 3: return AcpiAddressSpaceKinds.EmbeddedControl;
                    case 4: return AcpiAddressSpaceKinds.SmBus;
                    default: return AcpiAddressSpaceKinds.Other;
                }
            }

            private NameReference ReadNameReference(ref int p, int end, string scope)
            {
                if (p >= end) throw new ParseException();
                bool parentSearch = NameCharacter(bytes[p], true);
                return new NameReference { Path = Name(ref p, end, scope), Scope = scope, ParentSearch = parentSearch };
            }

            private static NamedUse RecordReference(BodyEvidence body, string path, string scope, bool parentSearch)
            {
                if (body == null) return null;
                body.NamedReferenceCount++;
                string key = scope + "|" + path + "|" + (parentSearch ? "1" : "0");
                NamedUse use;
                if (body.NamedUses.TryGetValue(key, out use)) { use.Count++; return use; }
                if (body.NamedUses.Count + body.CreatedNames.Count >= MaximumObjectRelationNames)
                { body.ObjectRelationLimit = true; return null; }
                use = new NamedUse
                {
                    Reference = new NameReference { Path = path, Scope = scope, ParentSearch = parentSearch },
                    Count = 1
                };
                body.NamedUses.Add(key, use);
                return use;
            }

            private AcpiObjectReferenceReport InspectObjectReferences(BodyEvidence root, List<BodyEvidence> helpers,
                AcpiMethodFlowReport flow)
            {
                bool relationLimit = root.ObjectRelationLimit;
                var created = new HashSet<string>(root.CreatedNames);
                foreach (BodyEvidence helper in helpers)
                {
                    relationLimit |= helper.ObjectRelationLimit;
                    foreach (string name in helper.CreatedNames) created.Add(name);
                }
                bool graphLimit = flow.Status == AcpiMethodFlowStatus.LimitExceeded;
                if (relationLimit)
                    return new AcpiObjectReferenceReport(AcpiReferenceAnalysisStatus.LimitExceeded,
                        rootNamedReferences: root.NamedReferenceCount, parsedHelpers: helpers.Count);

                ReferenceSummary rootSummary = SummarizeReferences(root, created);
                var helperSummary = new ReferenceSummary();
                foreach (BodyEvidence helper in helpers) SummarizeReferences(helper, created, helperSummary);
                bool unknown = rootSummary.Unknown || helperSummary.Unknown || !complete ||
                    flow.UnsupportedHelpers != 0 || flow.CycleObserved;
                AcpiReferenceAnalysisStatus status = graphLimit ? AcpiReferenceAnalysisStatus.LimitExceeded :
                    unknown ? AcpiReferenceAnalysisStatus.Partial : AcpiReferenceAnalysisStatus.ClassifiedObservedSyntax;
                bool negative = !unknown && !graphLimit;
                bool? storeReturn = graphLimit ? null : Relation(rootSummary.Arg2Targets, rootSummary.Returns, negative);
                bool? returnHelper = graphLimit || helpers.Count == 0 ? null : Relation(rootSummary.Returns, helperSummary.All, negative);
                bool? storeHelper = graphLimit || helpers.Count == 0 ? null : Relation(rootSummary.Arg2Targets, helperSummary.All, negative);
                AcpiAddressSpaceKinds? helperSpaces = helpers.Count == 0 ? null :
                    helperSummary.StoreUnknown && helperSummary.FieldStoreSpaces == AcpiAddressSpaceKinds.None ? null :
                    (AcpiAddressSpaceKinds?)(helperSummary.FieldStoreSpaces |
                        (helperSummary.StoreUnknown ? AcpiAddressSpaceKinds.Unknown : AcpiAddressSpaceKinds.None));
                return new AcpiObjectReferenceReport(status, rootSummary.References, rootSummary.Classified,
                    Kinds(rootSummary.Kinds, rootSummary.Unknown), Kinds(rootSummary.ReturnKinds, rootSummary.ReturnUnknown),
                    Kinds(rootSummary.Arg2Kinds, rootSummary.Arg2Unknown), helpers.Count,
                    helpers.Count == 0 ? null : (int?)helperSummary.References,
                    helpers.Count == 0 ? null : (int?)helperSummary.Classified,
                    helpers.Count == 0 ? null : Kinds(helperSummary.Kinds, helperSummary.Unknown),
                    helpers.Count == 0 ? null : Kinds(helperSummary.StoreKinds, helperSummary.StoreUnknown),
                    helperSpaces, storeReturn, returnHelper, storeHelper);
            }

            private ReferenceSummary SummarizeReferences(BodyEvidence body, HashSet<string> created,
                ReferenceSummary summary = null)
            {
                if (summary == null) summary = new ReferenceSummary();
                summary.References += body.NamedReferenceCount;
                foreach (NamedUse use in body.NamedUses.Values)
                {
                    ClassifiedName classified = Classify(use.Reference, created);
                    if (classified == null)
                    {
                        summary.Unknown = true;
                        summary.ReturnUnknown |= use.Returned; summary.Arg2Unknown |= use.Arg2StoreTarget;
                        summary.StoreUnknown |= use.StoreTarget;
                        continue;
                    }
                    summary.Classified += use.Count; summary.Kinds |= classified.Kind; summary.All.Add(classified.Identity);
                    if (use.Returned) { summary.ReturnKinds |= classified.Kind; summary.Returns.Add(classified.Identity); }
                    if (use.Arg2StoreTarget) { summary.Arg2Kinds |= classified.Kind; summary.Arg2Targets.Add(classified.Identity); }
                    if (use.StoreTarget)
                    {
                        summary.StoreKinds |= classified.Kind;
                        if (classified.Kind == AcpiNamedObjectKinds.Field) summary.FieldStoreSpaces |= classified.Space;
                    }
                    if (classified.Kind == AcpiNamedObjectKinds.Field && classified.Space == AcpiAddressSpaceKinds.Unknown)
                        summary.Unknown = true;
                }
                return summary;
            }

            private static AcpiNamedObjectKinds? Kinds(AcpiNamedObjectKinds known, bool unknown)
                => known == AcpiNamedObjectKinds.None && unknown ? null : (AcpiNamedObjectKinds?)known;

            private static bool? Relation(HashSet<object> left, HashSet<object> right, bool negative)
            {
                foreach (object identity in left) if (right.Contains(identity)) return true;
                return negative ? (bool?)false : null;
            }

            private ClassifiedName Classify(NameReference reference, HashSet<string> created)
            {
                ClassifiedName value = ResolveReference(reference, created);
                if (value == null || value.Kind != AcpiNamedObjectKinds.Field) return value;
                var field = (NamedDefinition)value.Identity;
                ClassifiedName region = field.Region == null ? null : ResolveReference(field.Region, created);
                value.Space = region != null && region.Kind == AcpiNamedObjectKinds.OperationRegion
                    ? ((NamedDefinition)region.Identity).Space : AcpiAddressSpaceKinds.Unknown;
                return value;
            }

            private ClassifiedName ResolveReference(NameReference reference, HashSet<string> created)
            {
                bool found;
                ClassifiedName value = LookupReference(reference.Path, created, out found);
                if (found) return value;
                if (!reference.ParentSearch || reference.Path != Join(reference.Scope, Last(reference.Path))) return null;
                string scope = reference.Scope;
                while (scope.Length != 0)
                {
                    if (opaqueObjectScopes.Contains(scope)) return null;
                    scope = Parent(scope);
                    value = LookupReference(Join(scope, Last(reference.Path)), created, out found);
                    if (found) return value;
                }
                return null;
            }

            private ClassifiedName LookupReference(string path, HashSet<string> created, out bool found)
            {
                found = created.Contains(path);
                if (found) return null;
                NamedDefinition definition;
                bool hasObject = objectDefinitions.TryGetValue(path, out definition);
                Method match = null; int count = 0;
                foreach (Method method in methods) if (method.Path == path) { match = method; count++; }
                found = hasObject || count != 0;
                if (hasObject)
                {
                    if (count != 0 || definition.Ambiguous || definition.Kind == AcpiNamedObjectKinds.None) return null;
                    return new ClassifiedName { Identity = definition, Kind = definition.Kind, Space = definition.Space };
                }
                return count == 1 ? new ClassifiedName { Identity = match, Kind = AcpiNamedObjectKinds.MethodReference } : null;
            }

            private void Wdg(Value buffer, string scope)
            {
                if (buffer.BufferLength % 20 != 0 || buffer.BufferLength > 65520) { complete = false; return; }
                for (int at = buffer.BufferStart; at < buffer.BufferStart + buffer.BufferLength; at += 20)
                {
                    bool same = true;
                    for (int i = 0; i < 16; i++) if (bytes[at + i] != KnownGuid[i]) same = false;
                    if (!same) continue;
                    if ((bytes[at + 19] & 2) == 0 || (bytes[at + 19] & ~3) != 0 || bytes[at + 18] == 0 ||
                        !NameCharacter(bytes[at + 16], false) || !NameCharacter(bytes[at + 17], false))
                    { complete = false; continue; }
                    if (descriptors.Count >= 32) throw new LimitException();
                    descriptors.Add(new Descriptor { Scope = scope,
                        Suffix = new string(new[] { (char)bytes[at + 16], (char)bytes[at + 17] }) });
                }
            }

            private void ScanBody(int start, int end, string scope, BodyEvidence evidence, int depth)
            {
                CheckDepth(depth); int p = start;
                while (p < end)
                {
                    Tick(); byte op = bytes[p];
                    if (op == 0xa0 || op == 0xa1 || op == 0xa2)
                    {
                        p++; int finish = Package(ref p, end);
                        if (op != 0xa1) Arg(ref p, finish, scope, evidence, depth + 1);
                        ScanBody(p, finish, scope, evidence, depth + 1); p = finish;
                    }
                    else if (op == 0xa4)
                    {
                        p++; Value value = Arg(ref p, end, scope, evidence, depth + 1);
                        evidence.ReturnStatements++;
                        evidence.Returns |= ReturnForm(value);
                        if (value.Kind == 6 && value.NamedUse != null) value.NamedUse.Returned = true;
                        if ((value.Kind == 1 && value.Integer == 255) ||
                            (value.BufferLength == 21 && bytes[value.BufferStart + 4] == 0xaa && bytes[value.BufferStart + 5] == 255))
                            evidence.Ff = true;
                    }
                    else if (op == 0xa3 || op == 0xa5 || op == 0x9f || op == 0xcc) p++;
                    else if (op == 0x5b)
                    {
                        p++;
                        Extended(ref p, end, scope, evidence, depth + 1, true);
                    }
                    else
                    {
                        if (op == 0x06 || op == 0x08 || op == 0x10 || op == 0x14 || op == 0x15)
                            throw UnsupportedPrimary(op);
                        // Integer/local/name references alone are not complete
                        // executable TermObjects; never resync after an unknown call.
                        if (op <= 0x6e || IsNameStart(op))
                        {
                            int probe = p; string path = Name(ref probe, end, scope);
                            if (FindMethod(path, scope, NameCharacter(op, true)) == null)
                                throw new ParseException(AcpiSyntaxFailureKind.UnresolvedStatement);
                        }
                        Arg(ref p, end, scope, evidence, depth + 1);
                    }
                }
            }

            private Value Arg(ref int p, int end, string scope, BodyEvidence evidence, int depth)
            {
                CheckDepth(depth); Tick(); int original = p; byte op = Get(ref p, end);
                if (op == 0x5b) return Extended(ref p, end, scope, evidence, depth + 1, false);
                if (op == 0 || op == 1 || op == 255)
                    return new Value { Kind = 1, Integer = op == 255 ? ulong.MaxValue : op, DeclarationKind = AcpiNamedObjectKinds.Integer };
                if (op == 0x0a || op == 0x0b || op == 0x0c || op == 0x0e)
                {
                    int count = op == 0x0a ? 1 : op == 0x0b ? 2 : op == 0x0c ? 4 : 8;
                    ulong value = 0; for (int i = 0; i < count; i++) value |= (ulong)Get(ref p, end) << (8 * i);
                    return new Value { Kind = 1, Integer = value, DeclarationKind = AcpiNamedObjectKinds.Integer };
                }
                if (op == 0x0d)
                { while (Get(ref p, end) != 0) { } return new Value { DeclarationKind = AcpiNamedObjectKinds.String }; }
                if (op == 0x11 || op == 0x12 || op == 0x13)
                {
                    int finish = Package(ref p, end);
                    Value result = new Value { DeclarationKind = op == 0x11 ? AcpiNamedObjectKinds.Buffer : AcpiNamedObjectKinds.Package };
                    if (op == 0x11)
                    {
                        Value size = Arg(ref p, finish, scope, null, depth + 1);
                        if (size.Kind == 1 && size.Integer == (ulong)(finish - p))
                            result = new Value { BufferStart = p, BufferLength = finish - p, DeclarationKind = AcpiNamedObjectKinds.Buffer };
                        else if (evidence != null) throw new ParseException(AcpiSyntaxFailureKind.DynamicBuffer);
                    }
                    p = finish; return result;
                }
                if (op >= 0x60 && op <= 0x6e)
                    return new Value { Kind = op == 0x69 ? 2 : op == 0x6a ? 3 : 0 };
                if (IsNameStart(op))
                {
                    p = original; string path = Name(ref p, end, scope);
                    Method method = FindMethod(path, scope, NameCharacter(op, true));
                    if (method == null)
                    {
                        if (evidence != null) evidence.UnresolvedNames++;
                        return new Value { Kind = 6, NamedUse = RecordReference(evidence, path, scope, NameCharacter(op, true)) };
                    }
                    int arg2 = 0;
                    for (int i = 0; i < method.Arguments; i++)
                        if (Arg(ref p, end, scope, evidence, depth + 1).Kind == 3) arg2++;
                    if (evidence != null)
                    {
                        evidence.CallSites++; evidence.Arg2CallArguments += arg2;
                        if (evidence.Calls.Count < MaximumHelperCallSites) evidence.Calls.Add(method);
                    }
                    return new Value { Kind = 5 };
                }
                if (op == 0x93 || op == 0x94 || op == 0x95)
                {
                    Value left = Arg(ref p, end, scope, evidence, depth + 1);
                    Value right = Arg(ref p, end, scope, evidence, depth + 1);
                    if (evidence != null && op == 0x93)
                    {
                        if (Pair(left, right, 2, 1)) evidence.IdOne = true;
                        if (Pair(left, right, 4, 21)) evidence.Input21 = true;
                    }
                    return default(Value);
                }
                if (op == 0x87)
                {
                    Value value = Reference(ref p, end, scope, evidence, depth + 1, false);
                    return new Value { Kind = value.Kind == 3 ? 4 : 0 };
                }
                if (op == 0x70)
                {
                    Value source = Arg(ref p, end, scope, evidence, depth + 1);
                    Value target = Reference(ref p, end, scope, evidence, depth + 1, false);
                    if (target.NamedUse != null)
                    {
                        target.NamedUse.StoreTarget = true;
                        if (source.Kind == 3) target.NamedUse.Arg2StoreTarget = true;
                    }
                    return default(Value);
                }
                int arity = Arity(op);
                if (arity >= 0)
                {
                    for (int i = 0; i < arity; i++)
                    {
                        int reference = ReferenceOperand(op, i);
                        if (reference != 0) Reference(ref p, end, scope, evidence, depth + 1, reference == 2, reference != 3);
                        else Arg(ref p, end, scope, evidence, depth + 1);
                    }
                    return default(Value);
                }
                if (op == 0x8a || op == 0x8b || op == 0x8c || op == 0x8d || op == 0x8f)
                {
                    try
                    {
                        Arg(ref p, end, scope, evidence, depth + 1); Arg(ref p, end, scope, evidence, depth + 1);
                        CreatedFieldName(ref p, end, scope, evidence);
                    }
                    catch (ParseException ex) { throw ex.At(AcpiSyntaxOperation.CreateField); }
                    return default(Value);
                }
                throw UnsupportedPrimary(op);
            }

            private Value Extended(ref int p, int end, string scope, BodyEvidence evidence, int depth, bool statement)
            {
                CheckDepth(depth);
                byte ext;
                try { ext = Get(ref p, end); }
                catch (ParseException ex) { throw ex.At(AcpiSyntaxOperation.UnrecognizedExtended); }
                AcpiSyntaxOperation operation = ExtendedOperation(ext);
                try
                {
                    if (statement && (ext == 0x30 || ext == 0x31 || ext == 0x33))
                        throw new ParseException(AcpiSyntaxFailureKind.UnresolvedStatement);
                    switch (ext)
                    {
                        case 0x12:
                            Reference(ref p, end, scope, evidence, depth + 1, false, false);
                            Reference(ref p, end, scope, evidence, depth + 1, true);
                            break;
                        case 0x13:
                            if (!statement) throw new ParseException(AcpiSyntaxFailureKind.UnsupportedExtendedOpcode);
                            for (int i = 0; i < 3; i++) Arg(ref p, end, scope, evidence, depth + 1);
                            CreatedFieldName(ref p, end, scope, evidence);
                            break;
                        case 0x21: case 0x22:
                            if (!statement) throw new ParseException(AcpiSyntaxFailureKind.UnsupportedExtendedOpcode);
                            Arg(ref p, end, scope, evidence, depth + 1);
                            break;
                        case 0x23:
                            Reference(ref p, end, scope, evidence, depth + 1, false);
                            // Acquire's timeout is a raw WORD, not an AML term.
                            Advance(ref p, end, 2);
                            break;
                        case 0x24: case 0x26: case 0x27:
                            if (!statement) throw new ParseException(AcpiSyntaxFailureKind.UnsupportedExtendedOpcode);
                            Reference(ref p, end, scope, evidence, depth + 1, false);
                            break;
                        case 0x25:
                            Reference(ref p, end, scope, evidence, depth + 1, false);
                            Arg(ref p, end, scope, evidence, depth + 1);
                            break;
                        case 0x28: case 0x29:
                            Arg(ref p, end, scope, evidence, depth + 1);
                            Reference(ref p, end, scope, evidence, depth + 1, true);
                            break;
                        case 0x30: case 0x33:
                            // Only a syntax kind is observed; do not synthesize a value.
                            break;
                        case 0x31:
                            throw new ParseException(AcpiSyntaxFailureKind.UnsupportedReference);
                        case 0x32:
                            if (!statement) throw new ParseException(AcpiSyntaxFailureKind.UnsupportedExtendedOpcode);
                            // Fatal contains raw BYTE+DWORD data before its TermArg.
                            Advance(ref p, end, 5);
                            Arg(ref p, end, scope, evidence, depth + 1);
                            break;
                        case 0x1f: case 0x20: case 0x2a:
                            throw new ParseException(AcpiSyntaxFailureKind.UnsupportedExtendedOpcode);
                        case 0x01: case 0x02: case 0x80: case 0x81: case 0x82: case 0x83:
                        case 0x84: case 0x85: case 0x86: case 0x87: case 0x88:
                            throw new ParseException(AcpiSyntaxFailureKind.DynamicNamespace);
                        default:
                            throw new ParseException(AcpiSyntaxFailureKind.UnsupportedExtendedOpcode);
                    }
                    if (evidence != null) evidence.ExtendedSyntax |= operation;
                    return default(Value);
                }
                catch (ParseException ex) { throw ex.At(operation); }
            }

            private void CreatedFieldName(ref int p, int end, string scope, BodyEvidence evidence)
            {
                string created = Name(ref p, end, scope);
                // Creating a field could hide an observed method. This is a
                // conservative syntax rejection, never a namespace mutation.
                if (evidence != null && FindMethod(created, Parent(created), true) != null)
                    throw new ParseException(AcpiSyntaxFailureKind.MethodNameCollision, AcpiSyntaxOperation.CreateField);
                if (evidence != null && !evidence.CreatedNames.Contains(created))
                {
                    if (evidence.CreatedNames.Count + evidence.NamedUses.Count >= MaximumObjectRelationNames)
                        evidence.ObjectRelationLimit = true;
                    else evidence.CreatedNames.Add(created);
                }
            }

            private static AcpiSyntaxOperation ExtendedOperation(byte ext)
            {
                switch (ext)
                {
                    case 0x12: return AcpiSyntaxOperation.CondRefOf;
                    case 0x13: return AcpiSyntaxOperation.CreateField;
                    case 0x1f: return AcpiSyntaxOperation.LoadTable;
                    case 0x20: return AcpiSyntaxOperation.Load;
                    case 0x21: return AcpiSyntaxOperation.Stall;
                    case 0x22: return AcpiSyntaxOperation.Sleep;
                    case 0x23: return AcpiSyntaxOperation.Acquire;
                    case 0x24: return AcpiSyntaxOperation.Signal;
                    case 0x25: return AcpiSyntaxOperation.Wait;
                    case 0x26: return AcpiSyntaxOperation.Reset;
                    case 0x27: return AcpiSyntaxOperation.Release;
                    case 0x28: return AcpiSyntaxOperation.FromBcd;
                    case 0x29: return AcpiSyntaxOperation.ToBcd;
                    case 0x2a: return AcpiSyntaxOperation.Unload;
                    case 0x30: return AcpiSyntaxOperation.Revision;
                    case 0x31: return AcpiSyntaxOperation.Debug;
                    case 0x32: return AcpiSyntaxOperation.Fatal;
                    case 0x33: return AcpiSyntaxOperation.Timer;
                    case 0x01: case 0x02: case 0x80: case 0x81: case 0x82: case 0x83:
                    case 0x84: case 0x85: case 0x86: case 0x87: case 0x88:
                        return AcpiSyntaxOperation.OtherNamespaceDefinition;
                    default: return AcpiSyntaxOperation.UnrecognizedExtended;
                }
            }

            private static ParseException UnsupportedPrimary(byte op)
            {
                if (op == 0x08) return new ParseException(AcpiSyntaxFailureKind.DynamicNamespace, AcpiSyntaxOperation.NameDefinition);
                if (op == 0x06 || op == 0x10 || op == 0x14 || op == 0x15)
                    return new ParseException(AcpiSyntaxFailureKind.DynamicNamespace, AcpiSyntaxOperation.OtherNamespaceDefinition);
                return new ParseException(AcpiSyntaxFailureKind.UnsupportedOpcode,
                    op == 0x89 ? AcpiSyntaxOperation.Match : AcpiSyntaxOperation.UnrecognizedPrimary);
            }

            private Value Reference(ref int p, int end, string scope, BodyEvidence evidence, int depth, bool allowNull,
                bool allowType6 = true)
            {
                CheckDepth(depth); Tick(); int original = p; byte op = Get(ref p, end);
                if (allowNull && op == 0) return default(Value);
                if (op >= 0x60 && op <= 0x6e)
                    return new Value { Kind = op == 0x69 ? 2 : op == 0x6a ? 3 : 0 };
                if (IsNameStart(op))
                {
                    p = original; string path = Name(ref p, end, scope);
                    if (evidence != null) evidence.UnresolvedNames++;
                    // SuperName/Target names denote references, including when
                    // their spelling also belongs to a known method. No method
                    // arguments are consumed and no call site is recorded.
                    return new Value { Kind = 6, NamedUse = RecordReference(evidence, path, scope, NameCharacter(op, true)) };
                }
                if (op == 0x5b)
                {
                    byte ext;
                    try { ext = Get(ref p, end); }
                    catch (ParseException ex) { throw ex.At(AcpiSyntaxOperation.UnrecognizedExtended); }
                    if (allowType6 && ext == 0x31)
                    {
                        if (evidence != null) evidence.ExtendedSyntax |= AcpiSyntaxOperation.Debug;
                        return default(Value);
                    }
                    throw new ParseException(AcpiSyntaxFailureKind.UnsupportedReference, ExtendedOperation(ext));
                }
                if (allowType6 && (op == 0x71 || op == 0x83 || op == 0x88))
                {
                    // Supported Type6 syntax. Its own TermArg operands may
                    // contain real call expressions; the outer reference does
                    // not itself become a call or a direct Arg2 expression.
                    p = original; Arg(ref p, end, scope, evidence, depth + 1);
                    return default(Value);
                }
                throw new ParseException(AcpiSyntaxFailureKind.UnsupportedReference, UnsupportedPrimary(op).Operation);
            }

            private static int ReferenceOperand(byte op, int index)
            {
                // 0: TermArg, 1: SuperName, 2: Target (also accepts NullName), 3: SimpleName.
                switch (op)
                {
                    case 0x70: return index == 1 ? 1 : 0;
                    case 0x9d: return index == 1 ? 3 : 0;
                    case 0x71: case 0x8e: return index == 0 ? 3 : 0;
                    case 0x80: case 0x81: case 0x82:
                    case 0x96: case 0x97: case 0x98: case 0x99: return index == 1 ? 2 : 0;
                    case 0x86: case 0x75: case 0x76: case 0x83: return index == 0 ? 1 : 0;
                    case 0x72: case 0x73: case 0x74: case 0x77: case 0x79: case 0x7a: case 0x7b:
                    case 0x7c: case 0x7d: case 0x7e: case 0x7f: case 0x84: case 0x85: case 0x88:
                    case 0x9c: return index == 2 ? 2 : 0;
                    case 0x78: return index >= 2 ? 2 : 0;
                    case 0x9e: return index == 3 ? 2 : 0;
                    default: return 0;
                }
            }

            private static int Arity(byte op)
            {
                switch (op)
                {
                    case 0x70: case 0x80: case 0x81: case 0x82: case 0x86:
                    case 0x90: case 0x91: case 0x96: case 0x97: case 0x98: case 0x99: case 0x9d: return 2;
                    case 0x71: case 0x75: case 0x76: case 0x83: case 0x8e: case 0x92: return 1;
                    case 0x72: case 0x73: case 0x74: case 0x77: case 0x79: case 0x7a: case 0x7b:
                    case 0x7c: case 0x7d: case 0x7e: case 0x7f: case 0x84: case 0x85: case 0x88: case 0x9c: return 3;
                    case 0x78: case 0x9e: return 4;
                    default: return -1;
                }
            }
            private static bool Pair(Value a, Value b, int kind, ulong value)
                => (a.Kind == kind && b.Kind == 1 && b.Integer == value) ||
                   (b.Kind == kind && a.Kind == 1 && a.Integer == value);

            private static AcpiReturnSyntax ReturnForm(Value value)
            {
                if (value.Kind == 1) return AcpiReturnSyntax.IntegerLiteral;
                if (value.BufferStart != 0) return AcpiReturnSyntax.BufferLiteral;
                if (value.Kind == 3) return AcpiReturnSyntax.Argument2;
                if (value.Kind == 5) return AcpiReturnSyntax.KnownMethodCall;
                if (value.Kind == 6) return AcpiReturnSyntax.UnresolvedName;
                return AcpiReturnSyntax.Other;
            }

            private Method FindMethod(string path, string scope, bool parentSearch)
            {
                Method match = UniqueMethod(path);
                if (match != null || objects.Contains(path)) return match;
                // Only an originally unprefixed single NameSeg may search up.
                // Explicit root/parent prefixes and dual/multi names stay exact.
                if (!parentSearch || path != Join(scope, Last(path))) return null;
                while (scope.Length != 0)
                {
                    scope = Parent(scope); string candidate = Join(scope, Last(path));
                    match = UniqueMethod(candidate);
                    if (match != null || objects.Contains(candidate)) return match;
                }
                return null;
            }
            private Method UniqueMethod(string path)
            {
                Method found = null;
                foreach (Method method in methods)
                {
                    if (method.Path != path) continue;
                    if (found != null) throw new ParseException(AcpiSyntaxFailureKind.AmbiguousName);
                    if (objects.Contains(path)) throw new ParseException(AcpiSyntaxFailureKind.MethodNameCollision);
                    found = method;
                }
                return found;
            }
            private NamedDefinition ObjectName(string name)
            {
                if (objects.Count >= MaximumNamespaceObjects && !objects.Contains(name)) throw new LimitException();
                objects.Add(name);
                NamedDefinition definition;
                if (objectDefinitions.TryGetValue(name, out definition))
                {
                    definition.Ambiguous = true; definition.Kind = AcpiNamedObjectKinds.None;
                    definition.Region = null; definition.Space = AcpiAddressSpaceKinds.Unknown;
                }
                else
                {
                    definition = new NamedDefinition();
                    objectDefinitions.Add(name, definition);
                }
                return definition;
            }
            private static void CommitDefinition(NamedDefinition definition, AcpiNamedObjectKinds kind,
                AcpiAddressSpaceKinds space = AcpiAddressSpaceKinds.None)
            {
                if (definition.Ambiguous) return;
                definition.Kind = kind; definition.Space = space;
            }
            private void OpaqueObjectScope(string scope)
            {
                if (opaqueObjectScopes.Count >= MaximumNamespaceObjects && !opaqueObjectScopes.Contains(scope)) throw new LimitException();
                opaqueObjectScopes.Add(scope);
            }
            private int Package(ref int p, int end)
            {
                int start = p; byte lead = Get(ref p, end); int following = lead >> 6;
                if (following != 0 && (lead & 0x30) != 0) throw new ParseException();
                int size = lead & (following == 0 ? 0x3f : 0x0f);
                for (int i = 0; i < following; i++) size |= Get(ref p, end) << (4 + 8 * i);
                if (size < p - start || size > end - start) throw new ParseException();
                return start + size;
            }
            private string Name(ref int p, int end, string scope)
            {
                if (p >= end) throw new ParseException();
                if (bytes[p] == 0x5c) { scope = ""; p++; }
                else while (p < end && bytes[p] == 0x5e)
                { if (scope.Length == 0) throw new ParseException(); scope = Parent(scope); p++; }
                byte first = Get(ref p, end);
                if (first == 0) return scope;
                int segments = first == 0x2e ? 2 : first == 0x2f ? Get(ref p, end) : 1;
                if (segments == 0 || segments > 32) throw new ParseException();
                if (first != 0x2e && first != 0x2f) p--;
                for (int segment = 0; segment < segments; segment++)
                {
                    var name = new StringBuilder(4);
                    for (int i = 0; i < 4; i++)
                    { byte value = Get(ref p, end); if (!NameCharacter(value, i == 0)) throw new ParseException(); name.Append((char)value); }
                    scope = Join(scope, name.ToString());
                }
                if (scope.Length > 512) throw new LimitException();
                return scope;
            }
            private byte Get(ref int p, int end) { if (p >= end) throw new ParseException(); return bytes[p++]; }
            private static void Advance(ref int p, int end, int count)
            { if (count < 0 || count > end - p) throw new ParseException(); p += count; }
            private void Tick() { if (++nodes > 100000) throw new LimitException(); }
            private static void CheckDepth(int depth) { if (depth > 32) throw new LimitException(); }
        }
        private static bool IsNameStart(byte value) => value == 0x5c || value == 0x5e || value == 0x2e || value == 0x2f || NameCharacter(value, true);
        private static bool NameCharacter(byte value, bool first)
            => value == '_' || (value >= 'A' && value <= 'Z') || (!first && value >= '0' && value <= '9');
        private static string Join(string scope, string name) => scope.Length == 0 ? name : scope + "." + name;
        private static string Parent(string path) { int at = path.LastIndexOf('.'); return at < 0 ? "" : path.Substring(0, at); }
        private static string Last(string path) { int at = path.LastIndexOf('.'); return path.Substring(at + 1); }
    }
}
