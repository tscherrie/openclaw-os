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
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

import ai.hansos.agent.HansEventTypes;

final class OpenAiResponsesProvider {
    interface EventSink {
        void emit(String type, String message);
    }

    private static final String TAG = "HansOpenAI";
    private static final String API_URL = "https://api.openai.com/v1/responses";
    private static final String KEY_PROP = "persist.hansos.openai_key";
    private static final String KEY_PART_COUNT_PROP = "persist.hansos.openai_key_parts";
    private static final String KEY_PART_PROP_PREFIX = "persist.hansos.openai_key_part";
    private static final String KEY_FILE_PROP = "persist.hansos.openai_key_file";
    private static final String MODEL_PROP = "persist.hansos.openai_model";
    private static final String KEY_SETTING = "hansos_openai_key";
    private static final String KEY_PART_COUNT_SETTING = "hansos_openai_key_parts";
    private static final String KEY_PART_SETTING_PREFIX = "hansos_openai_key_part";
    private static final String KEY_FILE_SETTING = "hansos_openai_key_file";
    private static final String MODEL_SETTING = "hansos_openai_model";
    private static final String DEFAULT_MODEL = "gpt-5.4-mini";
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

    void streamResponse(String userText, EventSink sink) throws OpenAiException, IOException {
        String key = getApiKey();
        if (key.isEmpty()) {
            throw new OpenAiException("OpenAI BYOK key fehlt.",
                    "Setze persist.hansos.openai_key(_parts), hansos_openai_key(_parts) oder eine BYOK-Key-Datei und starte HansRuntimeService neu.");
        }

        HttpURLConnection connection = (HttpURLConnection) new URL(API_URL).openConnection();
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

    private JSONObject buildPayload(String userText) throws IOException {
        try {
            JSONObject payload = new JSONObject();
            payload.put("model", getModel());
            payload.put("stream", true);
            payload.put("input", new JSONArray()
                    .put(new JSONObject()
                            .put("role", "system")
                            .put("content", "You are Hans, the playful autonomous phone agent in HansOS. Be concise, action-oriented, and honest about system limits."))
                    .put(new JSONObject()
                            .put("role", "user")
                            .put("content", userText == null ? "" : userText)));
            return payload;
        } catch (JSONException e) {
            throw new IOException("Could not build OpenAI payload", e);
        }
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
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            StringBuilder builder = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null && builder.length() < 500) {
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
