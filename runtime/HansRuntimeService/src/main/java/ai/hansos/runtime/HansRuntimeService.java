package ai.hansos.runtime;

import android.app.Service;
import android.content.Intent;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.RemoteException;
import android.os.ServiceManager;
import android.os.SystemProperties;
import android.provider.Settings;
import android.util.Slog;

import java.util.Locale;
import java.util.UUID;

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

    private HandlerThread mThread;
    private Handler mHandler;
    private volatile boolean mStopped;
    private final FakeDailyPhoneProvider mDailyPhone = new FakeDailyPhoneProvider();
    private final FakeAppControlProvider mAppControl = new FakeAppControlProvider();
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
        public void emergencyStop() {
            mStopped = true;
            mHandler.removeCallbacksAndMessages(null);
            Slog.w(TAG, "Emergency stop received");
        }

        @Override
        public int getRuntimeState() {
            return mStopped ? HansAgentStates.STOPPED : HansAgentStates.IDLE;
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        mOpenAi = new OpenAiResponsesProvider(this);
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
        if (isMorningIntent(normalized)) {
            runMorningFlow(requestId, callback);
        } else if (isAppControlIntent(normalized)) {
            runAppControlFlow(requestId, callback);
        } else if (isFocusIntent(normalized)) {
            runCommandActionFlow(requestId, prompt, callback);
        } else if (explicitOpenAi || isOpenAiProviderActive()) {
            runOpenAiFlow(requestId, stripOpenAiPrefix(prompt, explicitOpenAi), callback);
        } else {
            runCommandActionFlow(requestId, prompt, callback);
        }
    }

    private boolean isMorningIntent(String normalized) {
        return normalized.contains("morning") || normalized.contains("morgen");
    }

    private boolean isAppControlIntent(String normalized) {
        return normalized.contains("settings")
                || normalized.contains("network")
                || normalized.contains("app")
                || normalized.contains("einstellung");
    }

    private boolean isFocusIntent(String normalized) {
        return normalized.contains("focus") || normalized.contains("fokus");
    }

    private boolean isOpenAiProviderActive() {
        String provider = SystemProperties.get(PROVIDER_PROP, "").trim();
        if (provider.isEmpty()) {
            provider = Settings.Global.getString(getContentResolver(), PROVIDER_SETTING);
            provider = provider == null ? "" : provider.trim();
        }
        return PROVIDER_OPENAI.equals(provider.isEmpty() ? PROVIDER_FAKE : provider);
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
        String result = mDailyPhone.setFocusMode(true);
        emit(requestId, callback, HansEventTypes.ACTION_COMPLETED, result);
        emit(requestId, callback, HansEventTypes.AUDIT, "focus_mode enabled; undo available");
        emit(requestId, callback, HansEventTypes.DONE, "Erledigt. Ich habe den Fokusmodus simuliert aktiviert.");
    }

    private void runMorningFlow(String requestId, IHansStreamCallback callback) {
        emit(requestId, callback, HansEventTypes.THINKING, "Ich sammle deinen Morgenkontext.");
        emit(requestId, callback, HansEventTypes.SPEECH, mDailyPhone.buildMorningBrief());
        emit(requestId, callback, HansEventTypes.ACTION_STARTED, "notification_triage");
        emit(requestId, callback, HansEventTypes.ACTION_COMPLETED, mDailyPhone.triageNotifications());
        emit(requestId, callback, HansEventTypes.AUDIT, "morning brief generated from fake providers");
        emit(requestId, callback, HansEventTypes.DONE, "Morgen bereit. Ich bleibe im Hintergrund wach.");
    }

    private void runAppControlFlow(String requestId, IHansStreamCallback callback) {
        emit(requestId, callback, HansEventTypes.APP_CONTROL_STARTED, "settings");
        emit(requestId, callback, HansEventTypes.PLAN, "Ich oeffne die Zieloberflaeche nur temporaer und kehre zur Canvas zurueck.");
        emit(requestId, callback, HansEventTypes.APP_CONTROL_COMPLETED, mAppControl.inspectNetworkSettings());
        emit(requestId, callback, HansEventTypes.AUDIT, "app_control settings fixture inspected");
        emit(requestId, callback, HansEventTypes.DONE, "Netzwerkstatus gelesen. Zurueck zur Canvas.");
    }

    private void runOpenAiFlow(String requestId, String text, IHansStreamCallback callback) {
        emit(requestId, callback, HansEventTypes.THINKING, "OpenAI Provider aktiv.");
        emit(requestId, callback, HansEventTypes.PLAN,
                "Ich sende diesen Prompt ueber deinen BYOK-Key an " + mOpenAi.getModel() + ".");
        try {
            mOpenAi.streamResponse(text,
                    (type, message) -> emit(requestId, callback, type, message));
        } catch (OpenAiResponsesProvider.OpenAiException e) {
            emit(requestId, callback, HansEventTypes.ERROR, e.getMessage());
            emit(requestId, callback, HansEventTypes.REPAIR_SUGGESTION, e.getRepairSuggestion());
        } catch (Exception e) {
            emit(requestId, callback, HansEventTypes.ERROR, "OpenAI request failed: " + e.getMessage());
            emit(requestId, callback, HansEventTypes.REPAIR_SUGGESTION,
                    "Pruefe Netzwerk, DNS und persist.hansos.openai_model; Fake-Provider bleibt verfuegbar.");
        }
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
}
