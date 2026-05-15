package ai.hansos.server;

import android.content.Context;
import android.os.IBinder;
import android.os.RemoteException;
import android.util.Slog;

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

    private final Object mLock = new Object();
    private final List<String> mAuditEvents = new ArrayList<>();
    private int mAgentState = HansAgentStates.STARTING;
    private IHansRuntime mRuntime;
    private IBinder mRuntimeBinder;

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
        }

        synchronized (mLock) {
            pw.println("HansManagerService");
            pw.println("  state=" + mAgentState);
            pw.println("  runtime=" + (mRuntime != null));
            pw.println("  auditEvents=" + mAuditEvents.size());
        }
        pw.println("Commands:");
        pw.println("  dumpsys hans submit <text>");
        pw.println("  dumpsys hans stop");
        pw.println("  dumpsys hans memory");
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

    private void handleRuntimeEvent(String eventJson) {
        try {
            JSONObject event = new JSONObject(eventJson);
            String type = event.optString("type", "");
            String message = event.optString("message", "");

            if (HansEventTypes.THINKING.equals(type) || HansEventTypes.PLAN.equals(type)) {
                setState(HansAgentStates.THINKING);
            } else if (HansEventTypes.SPEECH.equals(type)) {
                setState(HansAgentStates.SPEAKING);
            } else if (HansEventTypes.ACTION_STARTED.equals(type)
                    || HansEventTypes.APP_CONTROL_STARTED.equals(type)) {
                setState(HansAgentStates.ACTING);
            } else if (HansEventTypes.DONE.equals(type)) {
                setState(HansAgentStates.IDLE);
                audit("runtime_done", message, true);
            } else if (HansEventTypes.ERROR.equals(type)) {
                setState(HansAgentStates.ERROR);
                audit("runtime_error", message, false);
            } else if (HansEventTypes.AUDIT.equals(type)) {
                audit("runtime_audit", message, true);
            }
        } catch (JSONException e) {
            audit("runtime_event_parse_failed", eventJson, false);
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
