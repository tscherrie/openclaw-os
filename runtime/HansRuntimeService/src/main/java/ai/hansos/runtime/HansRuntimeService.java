package ai.hansos.runtime;

import android.app.Service;
import android.os.Build;
import android.content.Intent;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.RemoteException;
import android.os.ServiceManager;
import android.os.SystemProperties;
import android.provider.Settings;
import android.util.Slog;

import java.io.ByteArrayOutputStream;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import ai.hansos.agent.HansAgentStates;
import ai.hansos.agent.HansEventTypes;
import ai.hansos.agent.IHansManager;
import ai.hansos.agent.IHansRuntime;
import ai.hansos.agent.IHansStreamCallback;
import ai.hansos.fakes.FakeAppControlProvider;
import ai.hansos.fakes.FakeDailyPhoneProvider;

public final class HansRuntimeService extends Service {
    private static final String TAG = "HansRuntimeService";
    private static final String PROVIDER_PROP = "persist.hansos.provider";
    private static final String PROVIDER_SETTING = "hansos_provider";
    private static final String PROVIDER_FAKE = "fake";
    private static final String PROVIDER_OPENAI = "openai";
    private static final String CONTEXT_PROVIDER_PROP = "persist.hansos.context_provider";
    private static final String CONTEXT_PROVIDER_SETTING = "hansos_context_provider";
    private static final String CONTEXT_PROVIDER_AUTO = "auto";
    private static final String CONTEXT_PROVIDER_FAKE = "fake";
    private static final String CONTEXT_PROVIDER_REAL = "real";
    private static final int VOICE_SAMPLE_RATE = 16000;
    private static final int MAX_VOICE_AUDIO_BYTES = VOICE_SAMPLE_RATE * 2 * 90;
    private static final int VOICE_PARTIAL_TRANSCRIPT_BYTES = VOICE_SAMPLE_RATE * 2 * 4;
    private static final String VOICE_PARTIALS_PROP = "persist.hansos.voice_partial_transcripts";
    private static final int APP_PILOT_MAX_STEPS = 8;
    private static final long APP_PILOT_TIMEOUT_MS = 12_000L;

    private HandlerThread mThread;
    private Handler mHandler;
    private volatile boolean mStopped;
    private final Map<String, VoiceSession> mVoiceSessions = new ConcurrentHashMap<>();
    private final FakeDailyPhoneProvider mDailyPhone = new FakeDailyPhoneProvider();
    private final FakeAppControlProvider mAppControl = new FakeAppControlProvider();
    private SystemPhoneProvider mSystemPhone;
    private OpenAiResponsesProvider mOpenAi;

    private final IHansRuntime.Stub mBinder = new IHansRuntime.Stub() {
        @Override
        public String submitIntent(String text, IHansStreamCallback callback) {
            String requestId = UUID.randomUUID().toString();
            mStopped = false;
            mHandler.post(() -> runFlow(requestId, text, callback));
            return requestId;
        }

        @Override
        public String startVoiceSession(IHansStreamCallback callback) {
            String sessionId = UUID.randomUUID().toString();
            mStopped = false;
            VoiceSession session = new VoiceSession(sessionId, callback);
            mVoiceSessions.put(sessionId, session);
            mHandler.post(() -> {
                emit(sessionId, callback, HansEventTypes.LISTENING_STARTED, "Zuhoeren.");
                emit(sessionId, callback, HansEventTypes.TRANSCRIPT_PARTIAL, "");
            });
            return sessionId;
        }

        @Override
        public void appendVoiceAudio(String sessionId, byte[] pcm16MonoChunk) {
            VoiceSession session = mVoiceSessions.get(sessionId);
            if (session == null || pcm16MonoChunk == null) {
                return;
            }
            session.append(pcm16MonoChunk);
            maybeStartPartialVoiceTranscription(session);
        }

        @Override
        public void finishVoiceSession(String sessionId) {
            VoiceSession session = mVoiceSessions.remove(sessionId);
            if (session == null) {
                return;
            }
            session.markFinished();
            mHandler.post(() -> finishVoiceSessionOnRuntimeThread(session));
        }

        @Override
        public void cancelVoiceSession(String sessionId) {
            VoiceSession session = mVoiceSessions.remove(sessionId);
            if (session == null) {
                return;
            }
            mHandler.post(() -> {
                emit(sessionId, session.callback, HansEventTypes.LISTENING_FINISHED, "Abgebrochen.");
                emit(sessionId, session.callback, HansEventTypes.DONE, "Voice turn abgebrochen.");
            });
        }

        @Override
        public void emergencyStop() {
            mStopped = true;
            mVoiceSessions.clear();
            mHandler.removeCallbacksAndMessages(null);
            Slog.w(TAG, "Emergency stop received");
        }

        @Override
        public int getRuntimeState() {
            if (!mVoiceSessions.isEmpty()) {
                return HansAgentStates.LISTENING;
            }
            return mStopped ? HansAgentStates.STOPPED : HansAgentStates.IDLE;
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        mOpenAi = new OpenAiResponsesProvider(this);
        mSystemPhone = new SystemPhoneProvider(this);
        HansNotificationListenerService.ensureEnabled(this);
        HansAppPilotAccessibilityService.ensureEnabled(this);
        mThread = new HandlerThread("HansRuntime");
        mThread.start();
        mHandler = new Handler(mThread.getLooper());
        registerWithManager();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        registerWithManager();
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return mBinder;
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        unregisterFromManager();
        if (mThread != null) {
            mThread.quitSafely();
        }
    }

    private void registerWithManager() {
        IBinder binder = ServiceManager.getService("hans");
        IHansManager manager = IHansManager.Stub.asInterface(binder);
        if (manager == null) {
            Slog.w(TAG, "Hans manager not available yet");
            return;
        }
        try {
            manager.registerRuntime(mBinder);
            Slog.i(TAG, "Registered with Hans manager");
        } catch (RemoteException e) {
            Slog.e(TAG, "Could not register runtime", e);
        }
    }

    private void unregisterFromManager() {
        IBinder binder = ServiceManager.getService("hans");
        IHansManager manager = IHansManager.Stub.asInterface(binder);
        if (manager == null) {
            return;
        }
        try {
            manager.unregisterRuntime(mBinder);
            Slog.i(TAG, "Unregistered from Hans manager");
        } catch (RemoteException e) {
            Slog.w(TAG, "Could not unregister runtime", e);
        }
    }

    private void runFlow(String requestId, String text, IHansStreamCallback callback) {
        String prompt = text == null ? "" : text.trim();
        String normalized = prompt.toLowerCase(Locale.ROOT);
        boolean explicitOpenAi = normalized.startsWith("ask openai");
        if (requiresManualMode(normalized)) {
            runManualModeRequiredFlow(requestId, prompt, callback);
        } else if (explicitOpenAi) {
            runOpenAiFlow(requestId, stripOpenAiPrefix(prompt, true), callback);
        } else if (isMorningIntent(normalized)) {
            runMorningFlow(requestId, callback);
        } else if (isAppControlIntent(normalized)) {
            runAppControlFlow(requestId, callback);
        } else if (isFocusIntent(normalized)) {
            runCommandActionFlow(requestId, prompt, callback);
        } else if (isOpenAiProviderActive()) {
            runOpenAiFlow(requestId, prompt, callback);
        } else {
            runCommandActionFlow(requestId, prompt, callback);
        }
    }

    private boolean isMorningIntent(String normalized) {
        return normalized.contains("morning") || normalized.contains("morgen");
    }

    private boolean isAppControlIntent(String normalized) {
        return normalized.contains("open settings")
                || normalized.contains("settings")
                || normalized.contains("network")
                || normalized.contains("wifi")
                || normalized.contains("wlan")
                || normalized.contains("einstellung");
    }

    private boolean isFocusIntent(String normalized) {
        return normalized.contains("focus mode")
                || normalized.contains("fokus mode")
                || normalized.contains("fokusmodus")
                || normalized.contains("konzentrationsmodus")
                || normalized.contains("do not disturb")
                || normalized.contains("nicht stoeren")
                || normalized.contains("turn on focus")
                || normalized.contains("enable focus")
                || normalized.contains("activate focus")
                || normalized.contains("fokus aktiv")
                || normalized.contains("fokus einschalten")
                || normalized.contains("fokus starten");
    }

    private boolean requiresManualMode(String normalized) {
        return normalized.contains("call ")
                || normalized.contains("anrufen")
                || normalized.contains("sms")
                || normalized.contains("send message")
                || normalized.contains("nachricht senden")
                || normalized.contains("delete")
                || normalized.contains("loeschen")
                || normalized.contains("password")
                || normalized.contains("passwort")
                || normalized.contains("pin ")
                || normalized.contains("flash ")
                || normalized.contains("unlock bootloader");
    }

    private boolean isOpenAiProviderActive() {
        String provider = SystemProperties.get(PROVIDER_PROP, "").trim();
        if (provider.isEmpty()) {
            provider = Settings.Global.getString(getContentResolver(), PROVIDER_SETTING);
            provider = provider == null ? "" : provider.trim();
        }
        return PROVIDER_OPENAI.equals(provider.isEmpty() ? PROVIDER_FAKE : provider);
    }

    private boolean shouldUseFakeContextProvider() {
        String provider = SystemProperties.get(CONTEXT_PROVIDER_PROP, "").trim();
        if (provider.isEmpty()) {
            provider = Settings.Global.getString(getContentResolver(), CONTEXT_PROVIDER_SETTING);
            provider = provider == null ? "" : provider.trim();
        }
        provider = provider.isEmpty() ? CONTEXT_PROVIDER_AUTO : provider;
        if (CONTEXT_PROVIDER_FAKE.equals(provider)) {
            return true;
        }
        if (CONTEXT_PROVIDER_REAL.equals(provider)) {
            return false;
        }
        return isEmulatorOrCuttlefish();
    }

    private boolean isEmulatorOrCuttlefish() {
        String hardware = SystemProperties.get("ro.hardware", "").toLowerCase(Locale.ROOT);
        String bootHardware = SystemProperties.get("ro.boot.hardware", "").toLowerCase(Locale.ROOT);
        String product = Build.PRODUCT == null ? "" : Build.PRODUCT.toLowerCase(Locale.ROOT);
        String device = Build.DEVICE == null ? "" : Build.DEVICE.toLowerCase(Locale.ROOT);
        return hardware.contains("ranchu")
                || hardware.contains("goldfish")
                || hardware.contains("cutf")
                || bootHardware.contains("ranchu")
                || bootHardware.contains("goldfish")
                || bootHardware.contains("cutf")
                || product.contains("cf_")
                || product.contains("cuttlefish")
                || device.contains("cuttlefish");
    }

    private String stripOpenAiPrefix(String text, boolean explicitOpenAi) {
        if (!explicitOpenAi) {
            return text;
        }
        return text.replaceFirst("(?i)^ask openai", "").trim();
    }

    private void runCommandActionFlow(String requestId, String text, IHansStreamCallback callback) {
        emit(requestId, callback, HansEventTypes.THINKING, "Ich schaue mir das kurz an.");
        emit(requestId, callback, HansEventTypes.PLAN, "Ich setze eine sichere lokale Aktion um und protokolliere sie.");
        emit(requestId, callback, HansEventTypes.ACTION_STARTED, "focus_mode");
        String result = shouldUseFakeContextProvider()
                ? mDailyPhone.setFocusMode(true)
                : mSystemPhone.setFocusMode(true);
        emit(requestId, callback, HansEventTypes.ACTION_COMPLETED, result);
        emit(requestId, callback, HansEventTypes.AUDIT, "focus_mode enabled; undo available");
        speak(requestId, callback, shouldUseFakeContextProvider()
                ? "Erledigt. Ich habe den Fokusmodus simuliert aktiviert."
                : "Erledigt. Ich habe den Fokusmodus auf dem Telefon aktiviert.");
        emit(requestId, callback, HansEventTypes.DONE, "Fokusmodus bereit.");
    }

    private void runMorningFlow(String requestId, IHansStreamCallback callback) {
        emit(requestId, callback, HansEventTypes.THINKING, "Ich sammle deinen Morgenkontext.");
        speak(requestId, callback, shouldUseFakeContextProvider()
                ? mDailyPhone.buildMorningBrief()
                : mSystemPhone.buildMorningBrief());
        emit(requestId, callback, HansEventTypes.ACTION_STARTED, "notification_triage");
        emit(requestId, callback, HansEventTypes.ACTION_COMPLETED, shouldUseFakeContextProvider()
                ? mDailyPhone.triageNotifications()
                : mSystemPhone.triageNotifications());
        emit(requestId, callback, HansEventTypes.AUDIT, shouldUseFakeContextProvider()
                ? "morning brief generated from fake providers"
                : "morning brief generated from system providers");
        emit(requestId, callback, HansEventTypes.DONE, "Morgen bereit. Ich bleibe im Hintergrund wach.");
    }

    private void runAppControlFlow(String requestId, IHansStreamCallback callback) {
        emit(requestId, callback, HansEventTypes.APP_CONTROL_STARTED, "settings");
        emit(requestId, callback, HansEventTypes.PLAN, "Ich oeffne die Zieloberflaeche nur temporaer und kehre zur Canvas zurueck.");
        boolean fake = shouldUseFakeContextProvider();
        if (fake) {
            emit(requestId, callback, HansEventTypes.VISUAL_STARTED,
                    "app_pilot fake fixture");
            emit(requestId, callback, HansEventTypes.APP_CONTROL_COMPLETED,
                    mAppControl.inspectNetworkSettings());
            emit(requestId, callback, HansEventTypes.AUDIT,
                    "app_control settings fixture inspected");
        } else {
            emit(requestId, callback, HansEventTypes.VISUAL_STARTED,
                    "app_pilot settings allowlist active");
            String result = HansAppPilotAccessibilityService.openSettingsAndInspectNetwork(
                    this, mSystemPhone);
            emit(requestId, callback, HansEventTypes.VISUAL_UPDATED, result);
            emit(requestId, callback, HansEventTypes.APP_CONTROL_COMPLETED, result);
            emit(requestId, callback, HansEventTypes.AUDIT,
                    "app_pilot settings inspected; allowlist=com.android.settings; max_steps="
                            + APP_PILOT_MAX_STEPS + "; timeout_ms=" + APP_PILOT_TIMEOUT_MS);
        }
        speak(requestId, callback, "Netzwerkstatus gelesen. Zurueck zur Canvas.");
        emit(requestId, callback, HansEventTypes.DONE, "App-Control abgeschlossen.");
    }

    private void runManualModeRequiredFlow(String requestId, String text, IHansStreamCallback callback) {
        emit(requestId, callback, HansEventTypes.CONFIRMATION_REQUIRED,
                "Dieser Wunsch braucht bewusste manuelle Bestaetigung.");
        emit(requestId, callback, HansEventTypes.MANUAL_MODE_REQUIRED,
                "Ich fuehre keine sensiblen Aktionen blind aus: " + text);
        emit(requestId, callback, HansEventTypes.AUDIT, "manual_mode_required for sensitive intent");
        emit(requestId, callback, HansEventTypes.DONE, "Manueller Modus erforderlich.");
    }

    private void runOpenAiFlow(String requestId, String text, IHansStreamCallback callback) {
        emit(requestId, callback, HansEventTypes.THINKING, "OpenAI Provider aktiv.");
        emit(requestId, callback, HansEventTypes.PLAN,
                "Ich sende diesen Prompt ueber deinen BYOK-Key an " + mOpenAi.getModel() + ".");
        try {
            emit(requestId, callback, HansEventTypes.SPEAKING_STARTED, "OpenAI Antwort startet.");
            mOpenAi.streamResponse(text,
                    (type, message) -> emit(requestId, callback, type, message));
            emit(requestId, callback, HansEventTypes.SPEAKING_FINISHED, "OpenAI Antwort beendet.");
        } catch (OpenAiResponsesProvider.OpenAiException e) {
            emit(requestId, callback, HansEventTypes.ERROR, e.getMessage());
            emit(requestId, callback, HansEventTypes.REPAIR_SUGGESTION, e.getRepairSuggestion());
            emit(requestId, callback, HansEventTypes.SPEAKING_FINISHED, "OpenAI Antwort abgebrochen.");
        } catch (Exception e) {
            emit(requestId, callback, HansEventTypes.ERROR, "OpenAI request failed: " + e.getMessage());
            emit(requestId, callback, HansEventTypes.REPAIR_SUGGESTION,
                    "Pruefe Netzwerk, DNS und persist.hansos.openai_model; Fake-Provider bleibt verfuegbar.");
            emit(requestId, callback, HansEventTypes.SPEAKING_FINISHED, "OpenAI Antwort abgebrochen.");
        }
    }

    private void finishVoiceSessionOnRuntimeThread(VoiceSession session) {
        if (mStopped) {
            return;
        }
        emit(session.sessionId, session.callback, HansEventTypes.LISTENING_FINISHED, "Aufnahme beendet.");
        String transcript = transcribeVoiceSession(session);
        emit(session.sessionId, session.callback, HansEventTypes.TRANSCRIPT_FINAL, transcript);
        if (!transcript.isEmpty()) {
            runFlow(session.sessionId, transcript, session.callback);
            return;
        }
        emit(session.sessionId, session.callback, HansEventTypes.THINKING, "Voice turn empfangen.");
        emit(session.sessionId, session.callback, HansEventTypes.PLAN,
                "Ich halte die Audio-Strecke stabil und nutze bis zur Transkription den lokalen Voice-Fallback.");
        emit(session.sessionId, session.callback, HansEventTypes.SPEAKING_STARTED, "Antwort startet.");
        emit(session.sessionId, session.callback, HansEventTypes.SPEECH,
                "Ich habe dich gehoert. Die Push-to-talk Strecke ist bereit; echte Transkription wird als Provider-Schritt angebunden.");
        emit(session.sessionId, session.callback, HansEventTypes.SPEAKING_FINISHED, "Antwort beendet.");
        emit(session.sessionId, session.callback, HansEventTypes.AUDIT,
                "voice_session bytes=" + session.bytesReceived);
        emit(session.sessionId, session.callback, HansEventTypes.DONE, "Voice turn abgeschlossen.");
    }

    private void maybeStartPartialVoiceTranscription(VoiceSession session) {
        if (mOpenAi == null || !mOpenAi.isConfigured()) {
            return;
        }
        if (!SystemProperties.getBoolean(VOICE_PARTIALS_PROP, true)) {
            return;
        }
        byte[] snapshot = session.startPartialTranscriptionSnapshot();
        if (snapshot.length == 0) {
            return;
        }
        Thread partialThread = new Thread(() -> {
            try {
                String transcript = mOpenAi.transcribePcm16Mono(snapshot, VOICE_SAMPLE_RATE);
                if (!transcript.isEmpty()
                        && mVoiceSessions.get(session.sessionId) == session
                        && !session.isFinished()) {
                    emit(session.sessionId, session.callback,
                            HansEventTypes.TRANSCRIPT_PARTIAL, transcript);
                }
            } catch (Exception e) {
                Slog.v(TAG, "Partial voice transcription failed", e);
            } finally {
                session.finishPartialTranscription();
            }
        }, "HansVoicePartialTranscript");
        partialThread.start();
    }

    private String transcribeVoiceSession(VoiceSession session) {
        byte[] audio = session.audio();
        if (audio.length == 0) {
            return "";
        }
        if (mOpenAi != null && mOpenAi.isConfigured()) {
            try {
                String transcript = mOpenAi.transcribePcm16Mono(audio, VOICE_SAMPLE_RATE);
                if (!transcript.isEmpty()) {
                    return transcript;
                }
            } catch (OpenAiResponsesProvider.OpenAiException e) {
                emit(session.sessionId, session.callback, HansEventTypes.ERROR, e.getMessage());
                emit(session.sessionId, session.callback, HansEventTypes.REPAIR_SUGGESTION,
                        e.getRepairSuggestion());
            } catch (Exception e) {
                emit(session.sessionId, session.callback, HansEventTypes.ERROR,
                        "Voice transcription failed: " + e.getMessage());
                emit(session.sessionId, session.callback, HansEventTypes.REPAIR_SUGGESTION,
                        "Pruefe OpenAI BYOK, Netzwerk und persist.hansos.openai_transcription_model.");
            }
        }
        return "";
    }

    private void speak(String requestId, IHansStreamCallback callback, String message) {
        emit(requestId, callback, HansEventTypes.SPEAKING_STARTED, "Antwort startet.");
        emit(requestId, callback, HansEventTypes.SPEECH, message);
        emit(requestId, callback, HansEventTypes.SPEAKING_FINISHED, "Antwort beendet.");
    }

    private void emit(String requestId, IHansStreamCallback callback, String type, String message) {
        if (mStopped || callback == null) {
            return;
        }
        String json = "{\"type\":\"" + escape(type) + "\",\"message\":\"" + escape(message) + "\"}";
        try {
            callback.onEvent(requestId, json);
        } catch (RemoteException e) {
            Slog.w(TAG, "Callback failed", e);
        }
    }

    private static String escape(String value) {
        if (value == null) {
            return "";
        }
        return value.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }

    private static final class VoiceSession {
        final String sessionId;
        final IHansStreamCallback callback;
        final ByteArrayOutputStream audio = new ByteArrayOutputStream();
        int bytesReceived;
        int lastPartialBytes;
        boolean partialTranscriptionInFlight;
        boolean finished;

        VoiceSession(String sessionId, IHansStreamCallback callback) {
            this.sessionId = sessionId;
            this.callback = callback;
        }

        synchronized void append(byte[] pcm16MonoChunk) {
            bytesReceived += pcm16MonoChunk.length;
            int remaining = MAX_VOICE_AUDIO_BYTES - audio.size();
            if (remaining <= 0) {
                return;
            }
            int count = Math.min(remaining, pcm16MonoChunk.length);
            audio.write(pcm16MonoChunk, 0, count);
        }

        synchronized byte[] audio() {
            return audio.toByteArray();
        }

        synchronized byte[] startPartialTranscriptionSnapshot() {
            if (finished || partialTranscriptionInFlight) {
                return new byte[0];
            }
            if (audio.size() - lastPartialBytes < VOICE_PARTIAL_TRANSCRIPT_BYTES) {
                return new byte[0];
            }
            partialTranscriptionInFlight = true;
            lastPartialBytes = audio.size();
            return audio.toByteArray();
        }

        synchronized void finishPartialTranscription() {
            partialTranscriptionInFlight = false;
        }

        synchronized void markFinished() {
            finished = true;
        }

        synchronized boolean isFinished() {
            return finished;
        }
    }
}
