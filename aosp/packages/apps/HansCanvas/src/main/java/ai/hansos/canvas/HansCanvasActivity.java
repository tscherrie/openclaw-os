package ai.hansos.canvas;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.RemoteException;
import android.os.ServiceManager;
import android.os.SystemClock;
import android.os.SystemProperties;
import android.provider.Settings;
import android.text.Layout;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.Arrays;

import ai.hansos.agent.HansEventTypes;
import ai.hansos.agent.IHansManager;
import ai.hansos.agent.IHansStreamCallback;

public final class HansCanvasActivity extends Activity {
    private static final int BG = Color.BLACK;
    private static final int TEXT = Color.WHITE;
    private static final int MUTED = Color.rgb(145, 149, 160);
    private static final int ACCENT = Color.rgb(110, 231, 183);
    private static final int AMBER = Color.rgb(245, 190, 91);
    private static final int ROSE = Color.rgb(250, 112, 136);
    private static final int BLUE = Color.rgb(125, 184, 255);

    private static final int SAMPLE_RATE = 16000;
    private static final int AUDIO_PERMISSION_REQUEST = 10;
    private static final String PROVIDER_PROP = "persist.hansos.provider";
    private static final String PTT_KEY_PROP = "persist.hansos.ptt_keycode";
    private static final String PTT_KEY_SETTING = "hansos_ptt_keycode";
    private static final String PTT_MIN_HOLD_MS_PROP = "persist.hansos.ptt_min_hold_ms";
    private static final String PTT_MAX_HOLD_MS_PROP = "persist.hansos.ptt_max_hold_ms";
    private static final int KEYCODE_REFRESH = 285;
    private static final int DEFAULT_PTT_MIN_HOLD_MS = 180;
    private static final int DEFAULT_PTT_MAX_HOLD_MS = 45_000;
    private static final String ACTION_SUBMIT = "ai.hansos.canvas.action.SUBMIT";
    private static final String ACTION_QUICK = "ai.hansos.canvas.action.QUICK";
    private static final String ACTION_STOP = "ai.hansos.canvas.action.STOP";
    private static final String ACTION_RETRY = "ai.hansos.canvas.action.RETRY";
    private static final String EXTRA_PROMPT = "ai.hansos.canvas.extra.PROMPT";
    private static final String EXTRA_QUICK = "ai.hansos.canvas.extra.QUICK";

    private TextView mMode;
    private TextView mPhrase;
    private TextView mStatus;
    private TextView mFooter;
    private IHansManager mHans;
    private String mLastPrompt = "";
    private String mVoiceSessionId;
    private AudioRecord mRecorder;
    private Thread mAudioThread;
    private volatile boolean mRecording;
    private long mVoiceStartUptimeMillis;
    private final Handler mUiHandler = new Handler(Looper.getMainLooper());
    private StringBuilder mAgentSpeech = new StringBuilder();
    private String mActivePhraseOwner = "";

    private final IHansStreamCallback.Stub mCallback = new IHansStreamCallback.Stub() {
        @Override
        public void onEvent(String requestId, String eventJson) {
            runOnUiThread(() -> handleHansEvent(eventJson));
        }
    };

    @Override
    protected void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        configureVoiceFirstWindow();
        bindHans();
        setContentView(buildUi());
        showIdle();
        handleDeveloperIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleDeveloperIntent(intent);
    }

    @Override
    protected void onDestroy() {
        stopAudioCapture(false);
        mUiHandler.removeCallbacksAndMessages(null);
        super.onDestroy();
    }

    private void configureVoiceFirstWindow() {
        setShowWhenLocked(true);
        setTurnScreenOn(true);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                | WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        boolean pttKey = isPushToTalkKey(keyCode);
        reportInputEvent(keyCode, KeyEvent.ACTION_DOWN, pttKey);
        if (pttKey) {
            if (event == null || event.getRepeatCount() == 0) {
                startVoiceTurn();
            }
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    public boolean onKeyUp(int keyCode, KeyEvent event) {
        boolean pttKey = isPushToTalkKey(keyCode);
        reportInputEvent(keyCode, KeyEvent.ACTION_UP, pttKey);
        if (pttKey) {
            finishVoiceTurn();
            return true;
        }
        return super.onKeyUp(keyCode, event);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == AUDIO_PERMISSION_REQUEST
                && grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            startVoiceTurn();
        } else if (requestCode == AUDIO_PERMISSION_REQUEST) {
            showManualRequired("Mikrofonzugriff fehlt.");
        }
    }

    private void bindHans() {
        mHans = IHansManager.Stub.asInterface(ServiceManager.getService("hans"));
    }

    private LinearLayout buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18), dp(18), dp(18), dp(18));
        root.setBackgroundColor(BG);

        mMode = new TextView(this);
        mMode.setTextColor(MUTED);
        mMode.setTextSize(12f);
        mMode.setGravity(Gravity.CENTER);
        mMode.setTypeface(Typeface.DEFAULT_BOLD);
        mMode.setSingleLine(true);
        mMode.setContentDescription("Hans voice mode");
        root.addView(mMode, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        mPhrase = new TextView(this);
        mPhrase.setTextColor(TEXT);
        mPhrase.setTextSize(28f);
        mPhrase.setTypeface(Typeface.DEFAULT_BOLD);
        mPhrase.setGravity(Gravity.CENTER);
        mPhrase.setIncludeFontPadding(false);
        mPhrase.setLineSpacing(0f, 1.08f);
        mPhrase.setMaxLines(9);
        mPhrase.setHorizontallyScrolling(false);
        mPhrase.setBreakStrategy(Layout.BREAK_STRATEGY_HIGH_QUALITY);
        mPhrase.setAutoSizeTextTypeUniformWithConfiguration(
                18, 30, 1, TypedValue.COMPLEX_UNIT_SP);
        mPhrase.setText("");
        mPhrase.setContentDescription("Hans live phrase");
        root.addView(mPhrase, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f));

        mStatus = new TextView(this);
        mStatus.setTextColor(MUTED);
        mStatus.setTextSize(13f);
        mStatus.setGravity(Gravity.CENTER);
        mStatus.setContentDescription("Hans voice status");
        root.addView(mStatus, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        mFooter = new TextView(this);
        mFooter.setTextColor(MUTED);
        mFooter.setTextSize(10f);
        mFooter.setGravity(Gravity.CENTER);
        mFooter.setSingleLine(true);
        mFooter.setContentDescription("Hans voice footer");
        LinearLayout.LayoutParams footerLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        footerLp.setMargins(0, dp(10), 0, 0);
        root.addView(mFooter, footerLp);

        return root;
    }

    private void startVoiceTurn() {
        if (mRecording) {
            return;
        }
        if (!ensureAudioPermission()) {
            return;
        }
        if (mHans == null) {
            bindHans();
        }
        if (mHans == null) {
            showManualRequired("Hans Core nicht erreichbar.");
            return;
        }

        try {
            mVoiceSessionId = mHans.startVoiceSession(mCallback);
        } catch (RemoteException e) {
            showError("Voice start fehlgeschlagen.");
            return;
        }
        mVoiceStartUptimeMillis = SystemClock.uptimeMillis();
        mAgentSpeech = new StringBuilder();
        mActivePhraseOwner = "user";
        updatePhrase("", "Listening", ACCENT, "Sprich. Loslassen sendet.");
        startAudioCapture();
        scheduleVoiceTimeout(mVoiceSessionId);
    }

    private void finishVoiceTurn() {
        if (!mRecording && mVoiceSessionId == null) {
            return;
        }
        mUiHandler.removeCallbacksAndMessages(null);
        long heldMs = mVoiceStartUptimeMillis == 0
                ? 0 : SystemClock.uptimeMillis() - mVoiceStartUptimeMillis;
        if (heldMs > 0 && heldMs < configuredPushToTalkMinHoldMs()) {
            cancelVoiceTurn("Zu kurz gehalten.");
            return;
        }
        String sessionId = mVoiceSessionId;
        stopAudioCapture(false);
        if (sessionId == null || mHans == null) {
            return;
        }
        try {
            mHans.finishVoiceSession(sessionId);
        } catch (RemoteException e) {
            showError("Voice finish fehlgeschlagen.");
        }
        mVoiceSessionId = null;
        mVoiceStartUptimeMillis = 0;
    }

    private void scheduleVoiceTimeout(String sessionId) {
        int timeoutMs = configuredPushToTalkMaxHoldMs();
        if (timeoutMs <= 0 || sessionId == null) {
            return;
        }
        mUiHandler.postDelayed(() -> {
            if (mRecording && sessionId.equals(mVoiceSessionId)) {
                finishVoiceTurn();
            }
        }, timeoutMs);
    }

    private void cancelVoiceTurn(String status) {
        String sessionId = mVoiceSessionId;
        stopAudioCapture(true);
        mVoiceSessionId = null;
        mVoiceStartUptimeMillis = 0;
        if (sessionId != null) {
            showManualRequired(status);
        }
    }

    private void startAudioCapture() {
        int min = AudioRecord.getMinBufferSize(SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT);
        int bufferSize = Math.max(min, SAMPLE_RATE / 2);
        try {
            mRecorder = new AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION,
                    SAMPLE_RATE,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
                    bufferSize);
        } catch (IllegalArgumentException e) {
            showError("Mikrofon konnte nicht initialisiert werden.");
            return;
        }
        if (mRecorder.getState() != AudioRecord.STATE_INITIALIZED) {
            showError("Mikrofon ist nicht bereit.");
            return;
        }

        mRecording = true;
        mRecorder.startRecording();
        mAudioThread = new Thread(() -> pumpAudio(bufferSize), "HansCanvasPttAudio");
        mAudioThread.start();
    }

    private void pumpAudio(int bufferSize) {
        byte[] buffer = new byte[bufferSize];
        while (mRecording && mRecorder != null) {
            int read = mRecorder.read(buffer, 0, buffer.length);
            if (read <= 0 || mVoiceSessionId == null || mHans == null) {
                continue;
            }
            byte[] chunk = Arrays.copyOf(buffer, read);
            try {
                mHans.appendVoiceAudio(mVoiceSessionId, chunk);
            } catch (RemoteException e) {
                runOnUiThread(() -> showError("Audio-Stream unterbrochen."));
                mRecording = false;
            }
        }
    }

    private void stopAudioCapture(boolean cancelRemote) {
        mRecording = false;
        if (mRecorder != null) {
            try {
                mRecorder.stop();
            } catch (IllegalStateException ignored) {
            }
            mRecorder.release();
            mRecorder = null;
        }
        if (cancelRemote && mHans != null && mVoiceSessionId != null) {
            try {
                mHans.cancelVoiceSession(mVoiceSessionId);
            } catch (RemoteException ignored) {
            }
        }
        mAudioThread = null;
    }

    private boolean ensureAudioPermission() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            return true;
        }
        requestPermissions(new String[] { Manifest.permission.RECORD_AUDIO }, AUDIO_PERMISSION_REQUEST);
        showManualRequired("Mikrofonzugriff bestaetigen.");
        return false;
    }

    private boolean isPushToTalkKey(int keyCode) {
        int configured = configuredPushToTalkKey();
        return keyCode == configured
                || keyCode == KeyEvent.KEYCODE_ASSIST
                || keyCode == KeyEvent.KEYCODE_VOICE_ASSIST
                || keyCode == KeyEvent.KEYCODE_CAMERA
                || keyCode == KeyEvent.KEYCODE_HEADSETHOOK
                || keyCode == KeyEvent.KEYCODE_BUTTON_1
                || keyCode == KeyEvent.KEYCODE_SYM
                || keyCode == KeyEvent.KEYCODE_PICTSYMBOLS
                || keyCode == KeyEvent.KEYCODE_PERIOD
                || keyCode == KEYCODE_REFRESH;
    }

    private int configuredPushToTalkKey() {
        int fromProp = SystemProperties.getInt(PTT_KEY_PROP, -1);
        if (fromProp >= 0) {
            return fromProp;
        }
        try {
            return Settings.Global.getInt(getContentResolver(),
                    PTT_KEY_SETTING, KeyEvent.KEYCODE_ASSIST);
        } catch (SecurityException e) {
            return KeyEvent.KEYCODE_ASSIST;
        }
    }

    private int configuredPushToTalkMinHoldMs() {
        return Math.max(0, SystemProperties.getInt(
                PTT_MIN_HOLD_MS_PROP, DEFAULT_PTT_MIN_HOLD_MS));
    }

    private int configuredPushToTalkMaxHoldMs() {
        return Math.max(0, SystemProperties.getInt(
                PTT_MAX_HOLD_MS_PROP, DEFAULT_PTT_MAX_HOLD_MS));
    }

    private void reportInputEvent(int keyCode, int action, boolean pttCandidate) {
        if (mHans == null) {
            bindHans();
        }
        if (mHans == null) {
            return;
        }
        try {
            mHans.reportInputEvent(keyCode, action, pttCandidate);
        } catch (RemoteException ignored) {
        }
    }

    private void handleDeveloperIntent(Intent intent) {
        if (intent == null) {
            return;
        }
        String action = intent.getAction();
        if (ACTION_SUBMIT.equals(action)) {
            String prompt = intent.getStringExtra(EXTRA_PROMPT);
            if (prompt != null && !prompt.trim().isEmpty()) {
                submitPrompt(prompt.trim(), true);
            }
        } else if (ACTION_QUICK.equals(action)) {
            String quick = intent.getStringExtra(EXTRA_QUICK);
            String prompt = promptForQuickAction(quick);
            if (prompt != null) {
                submitPrompt(prompt, true);
            } else {
                showManualRequired("Unbekannte Dev-Quick-Action: " + quick);
            }
        } else if (ACTION_STOP.equals(action)) {
            emergencyStop();
        } else if (ACTION_RETRY.equals(action) && !mLastPrompt.isEmpty()) {
            submitPrompt(mLastPrompt, false);
        }
    }

    private String promptForQuickAction(String quick) {
        if ("focus".equals(quick)) {
            return "turn on focus mode";
        }
        if ("morning".equals(quick)) {
            return "morgen briefing";
        }
        if ("settings".equals(quick)) {
            return "open settings network";
        }
        return null;
    }

    private void submitPrompt(String text, boolean remember) {
        if (remember) {
            mLastPrompt = text;
        }
        mActivePhraseOwner = "user";
        updatePhrase(text, "User", BLUE, "Developer input gesendet.");
        if (mHans == null) {
            bindHans();
        }
        if (mHans == null) {
            showManualRequired("Hans Core fehlt.");
            return;
        }
        try {
            mHans.submitIntent(text, mCallback);
        } catch (RemoteException e) {
            showError("Hans Binder-Aufruf fehlgeschlagen.");
        }
    }

    private void emergencyStop() {
        stopAudioCapture(true);
        mUiHandler.removeCallbacksAndMessages(null);
        mVoiceSessionId = null;
        mVoiceStartUptimeMillis = 0;
        if (mHans == null) {
            bindHans();
        }
        if (mHans == null) {
            showError("Stop nicht moeglich, Core fehlt.");
            return;
        }
        try {
            mHans.emergencyStop();
            updatePhrase("Gestoppt.", "Stopped", ROSE, "Emergency Stop aktiv.");
        } catch (RemoteException e) {
            showError("Emergency Stop fehlgeschlagen.");
        }
    }

    private void handleHansEvent(String raw) {
        String type = "event";
        String message = raw == null ? "" : raw;
        try {
            JSONObject event = new JSONObject(message);
            type = event.optString("type", "event");
            message = event.optString("message", "");
        } catch (JSONException ignored) {
        }

        if (HansEventTypes.LISTENING_STARTED.equals(type)) {
            updatePhrase("", "Listening", ACCENT, "Sprich. Loslassen sendet.");
        } else if (HansEventTypes.TRANSCRIPT_PARTIAL.equals(type)
                || HansEventTypes.TRANSCRIPT_FINAL.equals(type)) {
            mActivePhraseOwner = "user";
            updatePhrase(message, "User", BLUE, "Transkript wird aufgebaut.");
        } else if (HansEventTypes.SPEAKING_STARTED.equals(type)) {
            mAgentSpeech = new StringBuilder();
            mActivePhraseOwner = "agent";
            updatePhrase("", "Hans", ACCENT, "Antwort startet.");
        } else if (HansEventTypes.SPEECH.equals(type)) {
            if (!"agent".equals(mActivePhraseOwner)) {
                mAgentSpeech = new StringBuilder();
                mActivePhraseOwner = "agent";
            }
            mAgentSpeech.append(message);
            updatePhrase(mAgentSpeech.toString(), "Hans", ACCENT, "Antwort streamt.");
        } else if (HansEventTypes.SPEAKING_FINISHED.equals(type)) {
            setMode("Hans", ACCENT);
            mStatus.setText("Antwort bereit.");
        } else if (HansEventTypes.ERROR.equals(type)
                || HansEventTypes.REPAIR_SUGGESTION.equals(type)
                || HansEventTypes.MANUAL_MODE_REQUIRED.equals(type)) {
            showManualRequired(message);
        } else if (HansEventTypes.ACTION_STARTED.equals(type)
                || HansEventTypes.APP_CONTROL_STARTED.equals(type)) {
            setMode("Acting", AMBER);
            mStatus.setText("Aktion laeuft: " + message);
        } else if (HansEventTypes.VISUAL_STARTED.equals(type)
                || HansEventTypes.VISUAL_UPDATED.equals(type)) {
            updatePhrase(message, "Visual", BLUE, "Visuelle Darstellung aktiv.");
        } else if (HansEventTypes.DONE.equals(type)) {
            setMode("Ready", ACCENT);
            mStatus.setText("Bereit fuer die Seitentaste.");
        } else if (HansEventTypes.THINKING.equals(type) || HansEventTypes.PLAN.equals(type)) {
            setMode("Thinking", BLUE);
            mStatus.setText(message);
        }
    }

    private void showIdle() {
        setMode("Ready", ACCENT);
        mPhrase.setText("");
        mStatus.setText("Seitentaste halten und sprechen.");
        mFooter.setText("Core " + (mHans == null ? "getrennt" : "verbunden")
                + " - Provider " + providerLabel());
    }

    private void showManualRequired(String message) {
        updatePhrase(message, "Needs attention", AMBER, "Touch/Setup nur falls noetig.");
    }

    private void showError(String message) {
        updatePhrase(message, "Error", ROSE, "Hans braucht Aufmerksamkeit.");
    }

    private void updatePhrase(String phrase, String mode, int color, String status) {
        setMode(mode, color);
        mPhrase.setText(phrase == null ? "" : phrase);
        mStatus.setText(status == null ? "" : status);
        mFooter.setText("Core " + (mHans == null ? "getrennt" : "verbunden")
                + " - Provider " + providerLabel());
    }

    private void setMode(String mode, int color) {
        mMode.setText(mode);
        mMode.setTextColor(color);
    }

    private String providerLabel() {
        String provider = SystemProperties.get(PROVIDER_PROP, "fake");
        if ("openai".equals(provider)) {
            return "OpenAI";
        }
        return "Fake";
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }
}
