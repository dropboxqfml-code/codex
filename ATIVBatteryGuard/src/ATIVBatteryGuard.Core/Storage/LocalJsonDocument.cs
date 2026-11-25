using System;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;
using System.Xml;

namespace ATIVBatteryGuard.Core.Storage
{
    // Framework JSON deserialization alone may ignore bytes after the first root.
    internal static class LocalJsonDocument
    {
        private static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);

        public static T Read<T>(byte[] bytes, int maximumBytes, int maximumItems = 1024)
        {
            try
            {
                if (bytes == null || bytes.Length > maximumBytes) throw new SerializationException();
                int offset = bytes.Length >= 3 && bytes[0] == 0xef && bytes[1] == 0xbb && bytes[2] == 0xbf ? 3 : 0;
                string json = Utf8.GetString(bytes, offset, bytes.Length - offset);
                CheckEnvelope(json);
                using (var input = new MemoryStream(bytes, offset, bytes.Length - offset, false))
                using (var reader = JsonReaderWriterFactory.CreateJsonReader(input, new XmlDictionaryReaderQuotas
                { MaxDepth = 8, MaxStringContentLength = maximumBytes, MaxArrayLength = maximumBytes,
                    MaxBytesPerRead = 4096, MaxNameTableCharCount = 4096 }))
                {
                    var result = (T)new DataContractJsonSerializer(typeof(T),
                        new DataContractJsonSerializerSettings { MaxItemsInObjectGraph = maximumItems }).ReadObject(reader);
                    if (reader.Read()) throw new SerializationException();
                    return result;
                }
            }
            catch (Exception ex) when (ex is ArgumentException || ex is XmlException || ex is FormatException)
            { throw new SerializationException("로컬 JSON 파일 형식을 확인하세요."); }
        }

        private static bool Space(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }
        private static void CheckEnvelope(string json)
        {
            int start = 0;
            while (start < json.Length && Space(json[start])) start++;
            if (start == json.Length || json[start] != '{') throw new SerializationException();
            int depth = 0; bool quoted = false, escaped = false;
            for (int i = start; i < json.Length; i++)
            {
                char c = json[i];
                if (quoted)
                {
                    if (escaped) escaped = false;
                    else if (c == '\\') escaped = true;
                    else if (c == '"') quoted = false;
                    continue;
                }
                if (c == '"') quoted = true;
                else if (c == '{' || c == '[') { if (++depth > 8) throw new SerializationException(); }
                else if (c == '}' || c == ']')
                {
                    if (--depth == 0)
                    {
                        for (int j = i + 1; j < json.Length; j++) if (!Space(json[j])) throw new SerializationException();
                        return;
                    }
                }
            }
            throw new SerializationException();
        }
    }
}
