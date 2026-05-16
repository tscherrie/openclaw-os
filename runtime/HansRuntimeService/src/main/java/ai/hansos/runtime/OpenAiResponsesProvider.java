package ai.hansos.runtime;

import android.content.ContentResolver;
import android.content.Context;
import android.os.SystemProperties;
import android.provider.Settings;
import android.util.Slog;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.MalformedURLException;
import java.net.URL;
import java.nio.charset.StandardCharsets;

import ai.hansos.agent.HansEventTypes;

final class OpenAiResponsesProvider {
    interface EventSink {
        void emit(String type, String message);
    }

    private static final String TAG = "HansOpenAI";
    private static final String DEFAULT_API_BASE_URL = "https://api.openai.com/v1";
    private static final String RESPONSES_ENDPOINT = "responses";
    private static final String AUDIO_TRANSCRIPTIONS_ENDPOINT = "audio/transcriptions";
    private static final String AUDIO_SPEECH_ENDPOINT = "audio/speech";
    private static final String KEY_PROP = "persist.hansos.openai_key";
    private static final String KEY_PART_COUNT_PROP = "persist.hansos.openai_key_parts";
    private static final String KEY_PART_PROP_PREFIX = "persist.hansos.openai_key_part";
    private static final String KEY_FILE_PROP = "persist.hansos.openai_key_file";
    private static final String MODEL_PROP = "persist.hansos.openai_model";
    private static final String TRANSCRIPTION_MODEL_PROP = "persist.hansos.openai_transcription_model";
    private static final String SPEECH_MODEL_PROP = "persist.hansos.openai_speech_model";
    private static final String SPEECH_VOICE_PROP = "persist.hansos.openai_speech_voice";
    private static final String SPEECH_SPEED_PROP = "persist.hansos.openai_speech_speed";
    private static final String SPEECH_INSTRUCTIONS_PROP = "persist.hansos.openai_speech_instructions";
    private static final String BASE_URL_PROP = "persist.hansos.openai_base_url";
    private static final String KEY_SETTING = "hansos_openai_key";
    private static final String KEY_PART_COUNT_SETTING = "hansos_openai_key_parts";
    private static final String KEY_PART_SETTING_PREFIX = "hansos_openai_key_part";
    private static final String KEY_FILE_SETTING = "hansos_openai_key_file";
    private static final String MODEL_SETTING = "hansos_openai_model";
    private static final String TRANSCRIPTION_MODEL_SETTING = "hansos_openai_transcription_model";
    private static final String SPEECH_MODEL_SETTING = "hansos_openai_speech_model";
    private static final String SPEECH_VOICE_SETTING = "hansos_openai_speech_voice";
    private static final String SPEECH_SPEED_SETTING = "hansos_openai_speech_speed";
    private static final String SPEECH_INSTRUCTIONS_SETTING = "hansos_openai_speech_instructions";
    private static final String BASE_URL_SETTING = "hansos_openai_base_url";
    private static final String DEFAULT_MODEL = "gpt-5.4-mini";
    private static final String DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe";
    private static final String DEFAULT_SPEECH_MODEL = "gpt-4o-mini-tts";
    private static final String DEFAULT_SPEECH_VOICE = "alloy";
    private static final String DEFAULT_SPEECH_INSTRUCTIONS =
            "Speak warmly, clearly, and concisely like a helpful handheld voice agent. Use a calm natural pace.";
    private static final int MAX_SPEECH_AUDIO_BYTES = 6 * 1024 * 1024;
    private static final int MAX_KEY_PARTS = 8;
    private final ContentResolver mResolver;

    OpenAiResponsesProvider(Context context) {
        mResolver = context.getContentResolver();
    }

    static final class OpenAiException extends IOException {
        private final String mRepairSuggestion;

        OpenAiException(String message, String repairSuggestion) {
            super(message);
            mRepairSuggestion = repairSuggestion;
        }

        String getRepairSuggestion() {
            return mRepairSuggestion;
        }
    }

    boolean isConfigured() {
        return !getApiKey().isEmpty();
    }

    String getModel() {
        String model = SystemProperties.get(MODEL_PROP, "").trim();
        if (!model.isEmpty()) {
            return model;
        }
        model = getGlobalString(MODEL_SETTING);
        return model.isEmpty() ? DEFAULT_MODEL : model;
    }

    String getTranscriptionModel() {
        String model = SystemProperties.get(TRANSCRIPTION_MODEL_PROP, "").trim();
        if (!model.isEmpty()) {
            return model;
        }
        model = getGlobalString(TRANSCRIPTION_MODEL_SETTING);
        return model.isEmpty() ? DEFAULT_TRANSCRIPTION_MODEL : model;
    }

    String getSpeechModel() {
        String model = SystemProperties.get(SPEECH_MODEL_PROP, "").trim();
        if (!model.isEmpty()) {
            return model;
        }
        model = getGlobalString(SPEECH_MODEL_SETTING);
        return model.isEmpty() ? DEFAULT_SPEECH_MODEL : model;
    }

    String getSpeechVoice() {
        String voice = SystemProperties.get(SPEECH_VOICE_PROP, "").trim();
        if (!voice.isEmpty()) {
            return voice;
        }
        voice = getGlobalString(SPEECH_VOICE_SETTING);
        return voice.isEmpty() ? DEFAULT_SPEECH_VOICE : voice;
    }

    float getSpeechSpeed() {
        String speed = SystemProperties.get(SPEECH_SPEED_PROP, "").trim();
        if (speed.isEmpty()) {
            speed = getGlobalString(SPEECH_SPEED_SETTING);
        }
        return parseBoundedFloat(speed, 1.03f, 0.75f, 1.25f);
    }

    String getSpeechInstructions() {
        String instructions = SystemProperties.get(SPEECH_INSTRUCTIONS_PROP, "").trim();
        if (!instructions.isEmpty()) {
            return instructions;
        }
        instructions = getGlobalString(SPEECH_INSTRUCTIONS_SETTING);
        return instructions.isEmpty() ? DEFAULT_SPEECH_INSTRUCTIONS : instructions;
    }

    String transcribePcm16Mono(byte[] pcm16Mono, int sampleRate)
            throws OpenAiException, IOException {
        if (pcm16Mono == null || pcm16Mono.length == 0) {
            return "";
        }
        String key = getApiKey();
        if (key.isEmpty()) {
            throw new OpenAiException("OpenAI BYOK key fehlt fuer Voice-Transkription.",
                    "Setze persist.hansos.openai_key(_parts), hansos_openai_key(_parts) oder eine BYOK-Key-Datei.");
        }

        String boundary = "HansOSBoundary" + System.currentTimeMillis();
        HttpURLConnection connection = (HttpURLConnection)
                buildEndpointUrl(AUDIO_TRANSCRIPTIONS_ENDPOINT).openConnection();
        connection.setConnectTimeout(15_000);
        connection.setReadTimeout(90_000);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setRequestProperty("Authorization", "Bearer " + key);
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);

        byte[] wav = buildPcm16Wav(pcm16Mono, sampleRate);
        try (OutputStream output = connection.getOutputStream()) {
            writeFormField(output, boundary, "model", getTranscriptionModel());
            writeFormField(output, boundary, "response_format", "json");
            writeFileField(output, boundary, "file", "hans-voice.wav", "audio/wav", wav);
            output.write(("--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
        }

        int code = connection.getResponseCode();
        if (code < 200 || code >= 300) {
            throw new OpenAiException(buildHttpError(code, connection),
                    repairSuggestionForHttp(code));
        }
        String body = readBody(connection.getInputStream(), 2048);
        connection.disconnect();
        try {
            return new JSONObject(body).optString("text", "").trim();
        } catch (JSONException e) {
            throw new IOException("Could not parse OpenAI transcription response", e);
        }
    }

    void streamResponse(String userText, EventSink sink) throws OpenAiException, IOException {
        String key = getApiKey();
        if (key.isEmpty()) {
            throw new OpenAiException("OpenAI BYOK key fehlt.",
                    "Setze persist.hansos.openai_key(_parts), hansos_openai_key(_parts) oder eine BYOK-Key-Datei und starte HansRuntimeService neu.");
        }

        HttpURLConnection connection = (HttpURLConnection)
                buildEndpointUrl(RESPONSES_ENDPOINT).openConnection();
        connection.setConnectTimeout(15_000);
        connection.setReadTimeout(60_000);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setRequestProperty("Authorization", "Bearer " + key);
        connection.setRequestProperty("Content-Type", "application/json");
        connection.setRequestProperty("Accept", "text/event-stream");

        byte[] payload = buildPayload(userText).toString().getBytes(StandardCharsets.UTF_8);
        try (OutputStream output = connection.getOutputStream()) {
            output.write(payload);
        }

        int code = connection.getResponseCode();
        if (code < 200 || code >= 300) {
            throw new OpenAiException(buildHttpError(code, connection),
                    repairSuggestionForHttp(code));
        }

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (!line.startsWith("data:")) {
                    continue;
                }
                handleSseData(line.substring("data:".length()).trim(), sink);
            }
        } finally {
            connection.disconnect();
        }
    }

    byte[] synthesizeSpeechMp3(String text) throws OpenAiException, IOException {
        String input = text == null ? "" : text.trim();
        if (input.isEmpty()) {
            return new byte[0];
        }
        String key = getApiKey();
        if (key.isEmpty()) {
            throw new OpenAiException("OpenAI BYOK key fehlt fuer Tonausgabe.",
                    "Setze persist.hansos.openai_key(_parts), hansos_openai_key(_parts) oder eine BYOK-Key-Datei.");
        }

        HttpURLConnection connection = (HttpURLConnection)
                buildEndpointUrl(AUDIO_SPEECH_ENDPOINT).openConnection();
        connection.setConnectTimeout(15_000);
        connection.setReadTimeout(90_000);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setRequestProperty("Authorization", "Bearer " + key);
        connection.setRequestProperty("Content-Type", "application/json");
        connection.setRequestProperty("Accept", "audio/mpeg");

        byte[] payload = buildSpeechPayload(input).toString().getBytes(StandardCharsets.UTF_8);
        try (OutputStream output = connection.getOutputStream()) {
            output.write(payload);
        }

        int code = connection.getResponseCode();
        if (code < 200 || code >= 300) {
            throw new OpenAiException(buildHttpError(code, connection),
                    repairSuggestionForHttp(code));
        }
        try {
            return readBytes(connection.getInputStream(), MAX_SPEECH_AUDIO_BYTES);
        } finally {
            connection.disconnect();
        }
    }

    private JSONObject buildPayload(String userText) throws IOException {
        try {
            JSONObject payload = new JSONObject();
            payload.put("model", getModel());
            payload.put("stream", true);
            payload.put("input", new JSONArray()
                    .put(new JSONObject()
                            .put("role", "system")
                            .put("content", "You are Hans, the playful autonomous phone agent in HansOS. This is a voice-first phone: default to one or two short spoken sentences, avoid lists unless asked, be action-oriented, and be honest about system limits."))
                    .put(new JSONObject()
                            .put("role", "user")
                            .put("content", userText == null ? "" : userText)));
            return payload;
        } catch (JSONException e) {
            throw new IOException("Could not build OpenAI payload", e);
        }
    }

    private JSONObject buildSpeechPayload(String text) throws IOException {
        try {
            JSONObject payload = new JSONObject();
            payload.put("model", getSpeechModel());
            payload.put("voice", getSpeechVoice());
            payload.put("input", text);
            payload.put("response_format", "mp3");
            payload.put("speed", getSpeechSpeed());
            payload.put("instructions", getSpeechInstructions());
            return payload;
        } catch (JSONException e) {
            throw new IOException("Could not build OpenAI speech payload", e);
        }
    }

    private URL buildEndpointUrl(String endpoint) throws OpenAiException {
        String baseUrl = SystemProperties.get(BASE_URL_PROP, "").trim();
        if (baseUrl.isEmpty()) {
            baseUrl = getGlobalString(BASE_URL_SETTING);
        }
        if (baseUrl.isEmpty()) {
            baseUrl = DEFAULT_API_BASE_URL;
        }
        while (baseUrl.endsWith("/")) {
            baseUrl = baseUrl.substring(0, baseUrl.length() - 1);
        }
        String path = endpoint.startsWith("/") ? endpoint : "/" + endpoint;
        try {
            URL url = new URL(baseUrl + path);
            enforceCleartextLoopbackOnly(url);
            return url;
        } catch (MalformedURLException e) {
            throw new OpenAiException("OpenAI base URL ist ungueltig: " + baseUrl,
                    "Pruefe persist.hansos.openai_base_url oder hansos_openai_base_url.");
        }
    }

    private void enforceCleartextLoopbackOnly(URL url) throws OpenAiException {
        if (!"http".equalsIgnoreCase(url.getProtocol())) {
            return;
        }
        String host = url.getHost();
        if ("localhost".equalsIgnoreCase(host) || "127.0.0.1".equals(host)
                || "::1".equals(host) || host.startsWith("127.")) {
            return;
        }
        throw new OpenAiException("OpenAI base URL darf HTTP nur fuer Loopback nutzen: " + host,
                "Nutze https://... oder den lokalen adb-reverse Proxy auf 127.0.0.1.");
    }

    private void handleSseData(String data, EventSink sink) {
        if (data.isEmpty() || "[DONE]".equals(data)) {
            return;
        }
        try {
            JSONObject event = new JSONObject(data);
            String type = event.optString("type", "");
            if ("response.output_text.delta".equals(type)) {
                sink.emit(HansEventTypes.SPEECH, event.optString("delta", ""));
            } else if ("response.completed".equals(type)) {
                sink.emit(HansEventTypes.DONE, "OpenAI response completed");
            } else if ("response.failed".equals(type)) {
                sink.emit(HansEventTypes.ERROR, event.toString());
            }
        } catch (Exception e) {
            Slog.v(TAG, "Skipping malformed OpenAI SSE event", e);
        }
    }

    private String buildHttpError(int code, HttpURLConnection connection) {
        String detail = readErrorBody(connection);
        if (code == 401 || code == 403) {
            return "OpenAI BYOK key wurde abgelehnt (HTTP " + code + ").";
        }
        if (detail.isEmpty()) {
            return "OpenAI request failed with HTTP " + code + ".";
        }
        return "OpenAI request failed with HTTP " + code + ": " + detail;
    }

    private String repairSuggestionForHttp(int code) {
        if (code == 401 || code == 403) {
            return "Pruefe persist.hansos.openai_key und ob der Key fuer die Responses API freigeschaltet ist.";
        }
        if (code == 429) {
            return "Warte kurz oder pruefe OpenAI Rate Limits/Billing fuer den BYOK-Key.";
        }
        return "Pruefe Netzwerk, Modellnamen und OpenAI API-Status; Fake-Provider bleibt als Fallback verfuegbar.";
    }

    private String readErrorBody(HttpURLConnection connection) {
        InputStream stream = connection.getErrorStream();
        if (stream == null) {
            return "";
        }
        return readBody(stream, 500);
    }

    private String readBody(InputStream stream, int maxChars) {
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            StringBuilder builder = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null && builder.length() < maxChars) {
                if (builder.length() > 0) {
                    builder.append(' ');
                }
                builder.append(line.trim());
            }
            return builder.toString();
        } catch (IOException e) {
            return "";
        }
    }

    private byte[] readBytes(InputStream stream, int maxBytes) throws IOException {
        try (InputStream input = stream;
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int read;
            while ((read = input.read(buffer)) != -1) {
                if (output.size() + read > maxBytes) {
                    throw new IOException("OpenAI speech response exceeded local safety limit");
                }
                output.write(buffer, 0, read);
            }
            return output.toByteArray();
        }
    }

    private static byte[] buildPcm16Wav(byte[] pcm16, int sampleRate) throws IOException {
        int byteRate = sampleRate * 2;
        int dataSize = pcm16.length;
        ByteArrayOutputStream out = new ByteArrayOutputStream(44 + dataSize);
        writeAscii(out, "RIFF");
        writeIntLe(out, 36 + dataSize);
        writeAscii(out, "WAVE");
        writeAscii(out, "fmt ");
        writeIntLe(out, 16);
        writeShortLe(out, 1);
        writeShortLe(out, 1);
        writeIntLe(out, sampleRate);
        writeIntLe(out, byteRate);
        writeShortLe(out, 2);
        writeShortLe(out, 16);
        writeAscii(out, "data");
        writeIntLe(out, dataSize);
        out.write(pcm16);
        return out.toByteArray();
    }

    private static void writeFormField(OutputStream output, String boundary, String name, String value)
            throws IOException {
        output.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
        output.write(("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n")
                .getBytes(StandardCharsets.UTF_8));
        output.write((value == null ? "" : value).getBytes(StandardCharsets.UTF_8));
        output.write("\r\n".getBytes(StandardCharsets.UTF_8));
    }

    private static void writeFileField(OutputStream output, String boundary, String name,
            String filename, String contentType, byte[] content) throws IOException {
        output.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
        output.write(("Content-Disposition: form-data; name=\"" + name
                + "\"; filename=\"" + filename + "\"\r\n").getBytes(StandardCharsets.UTF_8));
        output.write(("Content-Type: " + contentType + "\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        output.write(content);
        output.write("\r\n".getBytes(StandardCharsets.UTF_8));
    }

    private static void writeAscii(ByteArrayOutputStream out, String value) {
        byte[] bytes = value.getBytes(StandardCharsets.US_ASCII);
        out.write(bytes, 0, bytes.length);
    }

    private static void writeIntLe(ByteArrayOutputStream out, int value) {
        out.write(value & 0xff);
        out.write((value >> 8) & 0xff);
        out.write((value >> 16) & 0xff);
        out.write((value >> 24) & 0xff);
    }

    private static void writeShortLe(ByteArrayOutputStream out, int value) {
        out.write(value & 0xff);
        out.write((value >> 8) & 0xff);
    }

    private String getApiKey() {
        String key = SystemProperties.get(KEY_PROP, "").trim();
        if (!key.isEmpty()) {
            return key;
        }
        key = getChunkedApiKey();
        if (!key.isEmpty()) {
            return key;
        }
        key = getGlobalString(KEY_SETTING);
        if (!key.isEmpty()) {
            return key;
        }
        key = getChunkedGlobalApiKey();
        if (!key.isEmpty()) {
            return key;
        }
        String keyFile = SystemProperties.get(KEY_FILE_PROP, "").trim();
        if (keyFile.isEmpty()) {
            keyFile = getGlobalString(KEY_FILE_SETTING);
        }
        if (keyFile.isEmpty()) {
            return "";
        }
        return readFirstLine(keyFile);
    }

    private String getChunkedApiKey() {
        int partCount = SystemProperties.getInt(KEY_PART_COUNT_PROP, 0);
        if (partCount <= 0 || partCount > MAX_KEY_PARTS) {
            return "";
        }
        StringBuilder builder = new StringBuilder();
        for (int index = 1; index <= partCount; index++) {
            String part = SystemProperties.get(KEY_PART_PROP_PREFIX + index, "");
            if (part.isEmpty()) {
                Slog.w(TAG, "OpenAI BYOK key part " + index + " missing");
                return "";
            }
            builder.append(part.trim());
        }
        return builder.toString();
    }

    private String getChunkedGlobalApiKey() {
        int partCount = getGlobalInt(KEY_PART_COUNT_SETTING, 0);
        if (partCount <= 0 || partCount > MAX_KEY_PARTS) {
            return "";
        }
        StringBuilder builder = new StringBuilder();
        for (int index = 1; index <= partCount; index++) {
            String part = getGlobalString(KEY_PART_SETTING_PREFIX + index);
            if (part.isEmpty()) {
                Slog.w(TAG, "OpenAI BYOK settings key part " + index + " missing");
                return "";
            }
            builder.append(part.trim());
        }
        return builder.toString();
    }

    private String getGlobalString(String name) {
        String value = Settings.Global.getString(mResolver, name);
        return value == null ? "" : value.trim();
    }

    private int getGlobalInt(String name, int defaultValue) {
        return Settings.Global.getInt(mResolver, name, defaultValue);
    }

    private static float parseBoundedFloat(String value, float fallback, float min, float max) {
        if (value == null || value.trim().isEmpty()) {
            return fallback;
        }
        try {
            float parsed = Float.parseFloat(value.trim());
            if (parsed < min) {
                return min;
            }
            if (parsed > max) {
                return max;
            }
            return parsed;
        } catch (NumberFormatException e) {
            return fallback;
        }
    }

    private String readFirstLine(String path) {
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                new FileInputStream(path), StandardCharsets.UTF_8))) {
            String line = reader.readLine();
            return line == null ? "" : line.trim();
        } catch (IOException e) {
            Slog.w(TAG, "Could not read OpenAI BYOK key file", e);
            return "";
        }
    }
}
