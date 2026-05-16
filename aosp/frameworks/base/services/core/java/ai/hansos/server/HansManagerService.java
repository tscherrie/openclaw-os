package ai.hansos.server;

import android.content.Context;
import android.os.IBinder;
import android.os.RemoteException;
import android.util.Slog;
import android.os.SystemClock;

import com.android.internal.util.DumpUtils;
import com.android.server.SystemService;

import java.io.FileDescriptor;
import java.io.PrintWriter;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.json.JSONException;
import org.json.JSONObject;

import ai.hansos.agent.HansAgentStates;
import ai.hansos.agent.HansEventTypes;
import ai.hansos.agent.IHansManager;
import ai.hansos.agent.IHansRuntime;
import ai.hansos.agent.IHansStreamCallback;

public final class HansManagerService extends SystemService {
    public static final String SERVICE_NAME = "hans";
    private static final String TAG = "HansManagerService";
    private static final String VOICE_SESSION_BYTES_PREFIX = "voice_session bytes=";

    private final Object mLock = new Object();
    private final List<String> mAuditEvents = new ArrayList<>();
    private int mAgentState = HansAgentStates.STARTING;
    private IHansRuntime mRuntime;
    private IBinder mRuntimeBinder;
    private int mLastInputKeyCode = -1;
    private int mLastInputAction = -1;
    private boolean mLastInputPttCandidate;
    private long mLastInputUptimeMillis;
    private String mLastVoiceSessionId = "";
    private String mVoiceSessionState = "idle";
    private int mLastVoiceBytes;
    private String mLastTranscriptionStatus = "idle";
    private String mLastVoiceEventType = "";
    private long mLastVoiceEventUptimeMillis;

    private final IBinder.DeathRecipient mRuntimeDeathRecipient = () -> {
        synchronized (mLock) {
            mRuntime = null;
            mRuntimeBinder = null;
            mAgentState = HansAgentStates.ERROR;
        }
        audit("runtime_died", "binder death", false);
        Slog.w(TAG, "Hans runtime died");
    };

    private final IHansManager.Stub mBinder = new IHansManager.Stub() {
        @Override
        public String submitIntent(String text, IHansStreamCallback callback) {
            return HansManagerService.this.submitIntent(text, callback);
        }

        @Override
        public String startVoiceSession(IHansStreamCallback callback) {
            return HansManagerService.this.startVoiceSession(callback);
        }

        @Override
        public void appendVoiceAudio(String sessionId, byte[] pcm16MonoChunk) {
            HansManagerService.this.appendVoiceAudio(sessionId, pcm16MonoChunk);
        }

        @Override
        public void finishVoiceSession(String sessionId) {
            HansManagerService.this.finishVoiceSession(sessionId);
        }

        @Override
        public void cancelVoiceSession(String sessionId) {
            HansManagerService.this.cancelVoiceSession(sessionId);
        }

        @Override
        public void reportInputEvent(int keyCode, int action, boolean pttCandidate) {
            HansManagerService.this.reportInputEvent(keyCode, action, pttCandidate);
        }

        @Override
        public void registerRuntime(IHansRuntime runtime) {
            if (runtime == null) {
                Slog.w(TAG, "Ignoring null runtime registration");
                return;
            }
            IBinder runtimeBinder = runtime.asBinder();
            synchronized (mLock) {
                if (mRuntimeBinder != runtimeBinder) {
                    if (mRuntimeBinder != null) {
                        mRuntimeBinder.unlinkToDeath(mRuntimeDeathRecipient, 0);
                    }
                    try {
                        runtimeBinder.linkToDeath(mRuntimeDeathRecipient, 0);
                    } catch (RemoteException e) {
                        mRuntime = null;
                        mRuntimeBinder = null;
                        mAgentState = HansAgentStates.ERROR;
                        audit("runtime_register_failed", "binder already dead", false);
                        Slog.w(TAG, "Runtime died during registration", e);
                        return;
                    }
                }
                mRuntime = runtime;
                mRuntimeBinder = runtimeBinder;
                mAgentState = HansAgentStates.IDLE;
            }
            Slog.i(TAG, "Hans runtime registered");
        }

        @Override
        public void unregisterRuntime(IHansRuntime runtime) {
            if (runtime == null) {
                return;
            }
            synchronized (mLock) {
                if (mRuntime != null && mRuntime.asBinder() == runtime.asBinder()) {
                    if (mRuntimeBinder != null) {
                        mRuntimeBinder.unlinkToDeath(mRuntimeDeathRecipient, 0);
                    }
                    mRuntime = null;
                    mRuntimeBinder = null;
                    mAgentState = HansAgentStates.ERROR;
                }
            }
            Slog.w(TAG, "Hans runtime unregistered");
        }

        @Override
        public void emergencyStop() {
            HansManagerService.this.emergencyStop();
        }

        @Override
        public int getAgentState() {
            synchronized (mLock) {
                return mAgentState;
            }
        }

        @Override
        public String getMemorySnapshotJson() {
            return HansManagerService.this.getMemorySnapshotJson();
        }

        @Override
        protected void dump(FileDescriptor fd, PrintWriter pw, String[] args) {
            if (!DumpUtils.checkDumpPermission(getContext(), TAG, pw)) {
                return;
            }
            HansManagerService.this.dump(pw, args);
        }
    };

    public HansManagerService(Context context) {
        super(context);
    }

    @Override
    public void onStart() {
        publishBinderService(SERVICE_NAME, mBinder);
        synchronized (mLock) {
            mAgentState = HansAgentStates.IDLE;
        }
        Slog.i(TAG, "Hans Manager published as '" + SERVICE_NAME + "'");
    }

    private String submitIntent(String text, IHansStreamCallback callback) {
        String requestId = UUID.randomUUID().toString();
        IHansRuntime runtime;
        synchronized (mLock) {
            runtime = mRuntime;
            mAgentState = HansAgentStates.THINKING;
        }

        if (runtime == null) {
            emitLocalDegradedFlow(requestId, text, callback);
            return requestId;
        }

        try {
            String runtimeRequestId = runtime.submitIntent(text,
                    new ManagerStreamCallback(callback, text));
            audit("runtime_submit", safe(text), true);
            return runtimeRequestId;
        } catch (RemoteException e) {
            Slog.e(TAG, "Runtime submit failed", e);
            emit(requestId, callback, HansEventTypes.ERROR, "Hans runtime is unavailable");
            emit(requestId, callback, HansEventTypes.REPAIR_SUGGESTION, "Restart HansRuntimeService over ADB");
            audit("runtime_submit_failed", e.toString(), false);
            synchronized (mLock) {
                mAgentState = HansAgentStates.ERROR;
            }
            return requestId;
        }
    }

    private String startVoiceSession(IHansStreamCallback callback) {
        String requestId = UUID.randomUUID().toString();
        IHansRuntime runtime;
        synchronized (mLock) {
            runtime = mRuntime;
            mAgentState = HansAgentStates.LISTENING;
            mLastVoiceSessionId = requestId;
            mVoiceSessionState = "starting";
            mLastVoiceBytes = 0;
            mLastTranscriptionStatus = "idle";
        }

        if (runtime == null) {
            emit(requestId, callback, HansEventTypes.ERROR, "Hans runtime is unavailable for voice");
            emit(requestId, callback, HansEventTypes.REPAIR_SUGGESTION, "Use setup or restart HansRuntimeService");
            audit("voice_start_failed", "runtime missing", false);
            synchronized (mLock) {
                mAgentState = HansAgentStates.ERROR;
                mVoiceSessionState = "runtime_missing";
            }
            return requestId;
        }

        try {
            String runtimeSessionId = runtime.startVoiceSession(new ManagerStreamCallback(callback, "voice"));
            synchronized (mLock) {
                mLastVoiceSessionId = runtimeSessionId;
                mVoiceSessionState = "recording";
            }
            audit("voice_start", runtimeSessionId, true);
            return runtimeSessionId;
        } catch (RemoteException e) {
            emit(requestId, callback, HansEventTypes.ERROR, "Voice session failed: " + e.getMessage());
            audit("voice_start_failed", e.toString(), false);
            synchronized (mLock) {
                mAgentState = HansAgentStates.ERROR;
                mVoiceSessionState = "start_failed";
            }
            return requestId;
        }
    }

    private void appendVoiceAudio(String sessionId, byte[] pcm16MonoChunk) {
        IHansRuntime runtime;
        synchronized (mLock) {
            runtime = mRuntime;
            if (pcm16MonoChunk != null) {
                mLastVoiceSessionId = sessionId == null ? "" : sessionId;
                mLastVoiceBytes += pcm16MonoChunk.length;
                mVoiceSessionState = "recording";
            }
        }
        if (runtime == null) {
            audit("voice_audio_dropped", "runtime missing", false);
            return;
        }
        try {
            runtime.appendVoiceAudio(sessionId, pcm16MonoChunk);
        } catch (RemoteException e) {
            audit("voice_audio_failed", e.toString(), false);
            setState(HansAgentStates.ERROR);
        }
    }

    private void finishVoiceSession(String sessionId) {
        IHansRuntime runtime;
        synchronized (mLock) {
            runtime = mRuntime;
            mAgentState = HansAgentStates.TRANSCRIBING;
            mLastVoiceSessionId = sessionId == null ? "" : sessionId;
            mVoiceSessionState = "finishing";
            mLastTranscriptionStatus = "started";
        }
        if (runtime == null) {
            audit("voice_finish_failed", "runtime missing", false);
            setState(HansAgentStates.ERROR);
            synchronized (mLock) {
                mVoiceSessionState = "runtime_missing";
            }
            return;
        }
        try {
            runtime.finishVoiceSession(sessionId);
            synchronized (mLock) {
                mVoiceSessionState = "transcribing";
            }
            audit("voice_finish", sessionId, true);
        } catch (RemoteException e) {
            audit("voice_finish_failed", e.toString(), false);
            setState(HansAgentStates.ERROR);
            synchronized (mLock) {
                mVoiceSessionState = "finish_failed";
            }
        }
    }

    private void cancelVoiceSession(String sessionId) {
        IHansRuntime runtime;
        synchronized (mLock) {
            runtime = mRuntime;
            mAgentState = HansAgentStates.STOPPED;
            mLastVoiceSessionId = sessionId == null ? "" : sessionId;
            mVoiceSessionState = "cancelled";
        }
        if (runtime == null) {
            audit("voice_cancel", "runtime missing", false);
            return;
        }
        try {
            runtime.cancelVoiceSession(sessionId);
            audit("voice_cancel", sessionId, true);
        } catch (RemoteException e) {
            audit("voice_cancel_failed", e.toString(), false);
        }
    }

    private void reportInputEvent(int keyCode, int action, boolean pttCandidate) {
        synchronized (mLock) {
            mLastInputKeyCode = keyCode;
            mLastInputAction = action;
            mLastInputPttCandidate = pttCandidate;
            mLastInputUptimeMillis = SystemClock.uptimeMillis();
        }
        if (pttCandidate) {
            audit("ptt_input", "keyCode=" + keyCode + ", action=" + action, true);
        }
    }

    private void emitLocalDegradedFlow(String requestId, String text, IHansStreamCallback callback) {
        emit(requestId, callback, HansEventTypes.THINKING, "Hans is running without runtime");
        emit(requestId, callback, HansEventTypes.PLAN, "Use degraded local fake response for: " + safe(text));
        emit(requestId, callback, HansEventTypes.DONE, "Runtime missing. Core Binder path is alive.");
        audit("degraded_submit", safe(text), true);
        synchronized (mLock) {
            mAgentState = HansAgentStates.IDLE;
        }
    }

    private void emit(String requestId, IHansStreamCallback callback, String type, String message) {
        if (callback == null) {
            return;
        }
        String json = "{\"type\":\"" + type + "\",\"message\":\"" + safe(message) + "\"}";
        try {
            callback.onEvent(requestId, json);
        } catch (RemoteException e) {
            Slog.w(TAG, "Callback failed for event " + type, e);
        }
    }

    private void audit(String action, String result, boolean success) {
        String event = "{\"timestamp\":\"" + Instant.now().toString()
                + "\",\"action\":\"" + safe(action)
                + "\",\"result\":\"" + safe(result)
                + "\",\"success\":" + success + "}";
        synchronized (mLock) {
            mAuditEvents.add(event);
        }
    }

    private void dump(PrintWriter pw, String[] args) {
        if (args != null && args.length > 0) {
            if ("submit".equals(args[0])) {
                String text = joinArgs(args, 1);
                CapturingCallback callback = new CapturingCallback();
                String requestId = submitIntent(text, callback);
                callback.awaitDone();
                pw.println("requestId=" + requestId);
                for (String event : callback.events) {
                    pw.println(event);
                }
                return;
            }
            if ("stop".equals(args[0])) {
                emergencyStop();
                pw.println("stopped");
                return;
            }
            if ("memory".equals(args[0])) {
                pw.println(getMemorySnapshotJson());
                return;
            }
            if ("voice".equals(args[0])) {
                CapturingCallback callback = new CapturingCallback();
                printVoiceState(pw);
                String sessionId = startVoiceSession(callback);
                finishVoiceSession(sessionId);
                callback.awaitDone();
                pw.println("sessionId=" + sessionId);
                for (String event : callback.events) {
                    pw.println(event);
                }
                printVoiceState(pw);
                return;
            }
            if ("input".equals(args[0])) {
                int keyCode = args.length > 1 ? parseInt(args[1], -1) : -1;
                int action = args.length > 2 ? parseInt(args[2], -1) : -1;
                boolean pttCandidate = args.length > 3 && Boolean.parseBoolean(args[3]);
                reportInputEvent(keyCode, action, pttCandidate);
                pw.println("input_reported");
                printVoiceState(pw);
                return;
            }
        }

        synchronized (mLock) {
            pw.println("HansManagerService");
            pw.println("  state=" + mAgentState);
            pw.println("  runtime=" + (mRuntime != null));
            pw.println("  auditEvents=" + mAuditEvents.size());
        }
        pw.println("Commands:");
        pw.println("  dumpsys hans submit <text>");
        pw.println("  dumpsys hans voice");
        pw.println("  dumpsys hans input <keyCode> <action> <pttCandidate>");
        pw.println("  dumpsys hans stop");
        pw.println("  dumpsys hans memory");
    }

    private void printVoiceState(PrintWriter pw) {
        synchronized (mLock) {
            pw.println("voiceDiagnostics");
            pw.println("  last_input_keycode=" + mLastInputKeyCode);
            pw.println("  last_input_action=" + mLastInputAction);
            pw.println("  last_input_ptt_candidate=" + mLastInputPttCandidate);
            pw.println("  last_input_uptime_ms=" + mLastInputUptimeMillis);
            pw.println("  session_id=" + safe(mLastVoiceSessionId));
            pw.println("  session_state=" + safe(mVoiceSessionState));
            pw.println("  audio_bytes=" + mLastVoiceBytes);
            pw.println("  transcription_status=" + safe(mLastTranscriptionStatus));
            pw.println("  last_voice_event=" + safe(mLastVoiceEventType));
            pw.println("  last_voice_event_uptime_ms=" + mLastVoiceEventUptimeMillis);
        }
    }

    private void emergencyStop() {
        IHansRuntime runtime;
        synchronized (mLock) {
            runtime = mRuntime;
            mAgentState = HansAgentStates.STOPPED;
        }
        if (runtime != null) {
            try {
                runtime.emergencyStop();
            } catch (RemoteException e) {
                Slog.w(TAG, "Runtime failed during emergency stop", e);
            }
        }
        audit("emergency_stop", "ok", true);
    }

    private String getMemorySnapshotJson() {
        synchronized (mLock) {
            return "{\"audit\":" + mAuditEvents.toString() + "}";
        }
    }

    private static String joinArgs(String[] args, int start) {
        if (args == null || args.length <= start) {
            return "";
        }
        StringBuilder builder = new StringBuilder();
        for (int i = start; i < args.length; i++) {
            if (builder.length() > 0) {
                builder.append(' ');
            }
            builder.append(args[i]);
        }
        return builder.toString();
    }

    private static String safe(String value) {
        if (value == null) {
            return "";
        }
        return value.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }

    private static int parseInt(String value, int fallback) {
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException e) {
            return fallback;
        }
    }

    private void handleRuntimeEvent(String eventJson) {
        try {
            JSONObject event = new JSONObject(eventJson);
            String type = event.optString("type", "");
            String message = event.optString("message", "");
            synchronized (mLock) {
                mLastVoiceEventType = type;
                mLastVoiceEventUptimeMillis = SystemClock.uptimeMillis();
            }

            if (HansEventTypes.LISTENING_STARTED.equals(type)) {
                setState(HansAgentStates.LISTENING);
                updateVoiceState("recording", "idle");
            } else if (HansEventTypes.LISTENING_FINISHED.equals(type)
                    || HansEventTypes.TRANSCRIPT_PARTIAL.equals(type)) {
                setState(HansAgentStates.TRANSCRIBING);
                updateVoiceState("transcribing", HansEventTypes.TRANSCRIPT_PARTIAL.equals(type)
                        ? "partial" : "started");
            } else if (HansEventTypes.TRANSCRIPT_FINAL.equals(type)) {
                setState(HansAgentStates.TRANSCRIBING);
                updateVoiceState("transcribed", message.isEmpty() ? "final_empty" : "final_text");
            } else if (HansEventTypes.THINKING.equals(type) || HansEventTypes.PLAN.equals(type)) {
                setState(HansAgentStates.THINKING);
            } else if (HansEventTypes.SPEAKING_STARTED.equals(type) || HansEventTypes.SPEECH.equals(type)) {
                setState(HansAgentStates.SPEAKING);
                updateVoiceState("responding", mLastTranscriptionStatus);
            } else if (HansEventTypes.SPEAKING_FINISHED.equals(type)) {
                setState(HansAgentStates.IDLE);
                updateVoiceState("idle", mLastTranscriptionStatus);
            } else if (HansEventTypes.ACTION_STARTED.equals(type)
                    || HansEventTypes.APP_CONTROL_STARTED.equals(type)) {
                setState(HansAgentStates.ACTING);
            } else if (HansEventTypes.DONE.equals(type)) {
                setState(HansAgentStates.IDLE);
                audit("runtime_done", message, true);
            } else if (HansEventTypes.ERROR.equals(type)) {
                setState(HansAgentStates.ERROR);
                updateVoiceState("error", "error");
                audit("runtime_error", message, false);
            } else if (HansEventTypes.AUDIT.equals(type)) {
                maybeRecordVoiceBytes(message);
                audit("runtime_audit", message, true);
            }
        } catch (JSONException e) {
            audit("runtime_event_parse_failed", eventJson, false);
        }
    }

    private void updateVoiceState(String sessionState, String transcriptionStatus) {
        synchronized (mLock) {
            mVoiceSessionState = sessionState;
            mLastTranscriptionStatus = transcriptionStatus;
        }
    }

    private void maybeRecordVoiceBytes(String message) {
        if (message == null || !message.startsWith(VOICE_SESSION_BYTES_PREFIX)) {
            return;
        }
        int bytes = parseInt(message.substring(VOICE_SESSION_BYTES_PREFIX.length()).trim(), -1);
        if (bytes >= 0) {
            synchronized (mLock) {
                mLastVoiceBytes = bytes;
            }
        }
    }

    private void setState(int state) {
        synchronized (mLock) {
            mAgentState = state;
        }
    }

    private final class ManagerStreamCallback extends IHansStreamCallback.Stub {
        private final IHansStreamCallback mDownstream;
        private final String mOriginalText;

        ManagerStreamCallback(IHansStreamCallback downstream, String originalText) {
            mDownstream = downstream;
            mOriginalText = originalText;
        }

        @Override
        public void onEvent(String requestId, String eventJson) {
            handleRuntimeEvent(eventJson);
            if (mDownstream != null) {
                try {
                    mDownstream.onEvent(requestId, eventJson);
                } catch (RemoteException e) {
                    audit("downstream_callback_failed", e.toString(), false);
                }
            }
            if (eventJson != null && eventJson.contains("\"type\":\"" + HansEventTypes.DONE + "\"")) {
                audit("runtime_flow_completed", safe(mOriginalText), true);
            }
        }
    }

    private static final class CapturingCallback extends IHansStreamCallback.Stub {
        private static final long DUMP_TIMEOUT_SECONDS = 8;

        final List<String> events = new ArrayList<>();
        final CountDownLatch done = new CountDownLatch(1);

        @Override
        public void onEvent(String requestId, String eventJson) {
            events.add(requestId + " " + eventJson);
            if (eventJson != null
                    && (eventJson.contains("\"type\":\"" + HansEventTypes.DONE + "\"")
                    || eventJson.contains("\"type\":\"" + HansEventTypes.ERROR + "\""))) {
                done.countDown();
            }
        }

        void awaitDone() {
            try {
                done.await(DUMP_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
