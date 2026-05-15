package ai.hansos.canvas;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.RemoteException;
import android.os.ServiceManager;
import android.os.SystemProperties;
import android.text.InputType;
import android.view.Gravity;
import android.view.inputmethod.EditorInfo;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONException;
import org.json.JSONObject;

import ai.hansos.agent.IHansManager;
import ai.hansos.agent.IHansStreamCallback;

public final class HansCanvasActivity extends Activity {
    private static final int BG = Color.rgb(8, 9, 12);
    private static final int SURFACE = Color.rgb(23, 25, 32);
    private static final int SURFACE_ALT = Color.rgb(31, 34, 43);
    private static final int TEXT = Color.rgb(245, 243, 234);
    private static final int MUTED = Color.rgb(165, 169, 182);
    private static final int ACCENT = Color.rgb(110, 231, 183);
    private static final int BLUE = Color.rgb(125, 184, 255);
    private static final int AMBER = Color.rgb(245, 190, 91);
    private static final int ROSE = Color.rgb(250, 112, 136);
    private static final int LINE = Color.rgb(58, 62, 75);
    private static final String PROVIDER_PROP = "persist.hansos.provider";
    private static final String ACTION_SUBMIT = "ai.hansos.canvas.action.SUBMIT";
    private static final String ACTION_QUICK = "ai.hansos.canvas.action.QUICK";
    private static final String ACTION_STOP = "ai.hansos.canvas.action.STOP";
    private static final String ACTION_RETRY = "ai.hansos.canvas.action.RETRY";
    private static final String EXTRA_PROMPT = "ai.hansos.canvas.extra.PROMPT";
    private static final String EXTRA_QUICK = "ai.hansos.canvas.extra.QUICK";

    private LinearLayout mCards;
    private EditText mInput;
    private ScrollView mScroll;
    private TextView mConnection;
    private TextView mStatePill;
    private TextView mStatusLine;
    private TextView mStreamingSpeechView;
    private StringBuilder mStreamingSpeech;
    private Button mRetry;
    private IHansManager mHans;
    private String mLastPrompt = "";

    private final IHansStreamCallback.Stub mCallback = new IHansStreamCallback.Stub() {
        @Override
        public void onEvent(String requestId, String eventJson) {
            runOnUiThread(() -> addEventCard(eventJson));
        }
    };

    @Override
    protected void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        bindHans();
        setContentView(buildUi());
        addSystemCard("Hans ist wach.");
        handleDeveloperIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleDeveloperIntent(intent);
    }

    private void bindHans() {
        mHans = IHansManager.Stub.asInterface(ServiceManager.getService("hans"));
    }

    private LinearLayout buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(10), dp(8), dp(10), dp(8));
        root.setBackgroundColor(BG);

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);

        LinearLayout titleColumn = new LinearLayout(this);
        titleColumn.setOrientation(LinearLayout.VERTICAL);

        TextView title = new TextView(this);
        title.setText("HansOS");
        title.setTextColor(TEXT);
        title.setTextSize(22f);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setGravity(Gravity.START);
        title.setSingleLine(true);
        titleColumn.addView(title, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        mConnection = new TextView(this);
        mConnection.setTextSize(10f);
        mConnection.setSingleLine(true);
        titleColumn.addView(mConnection);

        header.addView(titleColumn, new LinearLayout.LayoutParams(
                0,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                1f));

        Button stop = makeButton("Stop", SURFACE_ALT, ROSE);
        stop.setContentDescription("Hans stop");
        stop.setOnClickListener(view -> emergencyStop());
        LinearLayout.LayoutParams stopLp = new LinearLayout.LayoutParams(
                dp(52),
                dp(32));
        stopLp.setMargins(dp(6), 0, 0, 0);
        header.addView(stop, stopLp);

        root.addView(header, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        mStatePill = new TextView(this);
        mStatePill.setTextSize(11f);
        mStatePill.setTypeface(Typeface.DEFAULT_BOLD);
        mStatePill.setPadding(dp(9), dp(4), dp(9), dp(4));
        mStatePill.setContentDescription("Hans state");
        LinearLayout.LayoutParams stateLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        stateLp.setMargins(0, dp(6), 0, dp(4));
        root.addView(mStatePill, stateLp);

        mStatusLine = new TextView(this);
        mStatusLine.setTextColor(MUTED);
        mStatusLine.setTextSize(12f);
        mStatusLine.setText("Bereit fuer Agent-Auftraege.");
        mStatusLine.setSingleLine(true);
        LinearLayout.LayoutParams statusLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        statusLp.setMargins(0, 0, 0, dp(6));
        root.addView(mStatusLine, statusLp);
        refreshConnectionStatus();

        LinearLayout quickRow = new LinearLayout(this);
        quickRow.setOrientation(LinearLayout.HORIZONTAL);
        quickRow.setGravity(Gravity.CENTER_VERTICAL);
        quickRow.addView(quickAction("Focus", "turn on focus mode", "Hans quick focus"));
        quickRow.addView(quickAction("Morning", "morgen briefing", "Hans quick morning"));
        quickRow.addView(quickAction("Settings", "open settings network", "Hans quick settings"));
        LinearLayout.LayoutParams quickLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        quickLp.setMargins(0, 0, 0, dp(6));
        root.addView(quickRow, quickLp);

        LinearLayout inputPanel = new LinearLayout(this);
        inputPanel.setOrientation(LinearLayout.VERTICAL);

        mInput = new EditText(this);
        mInput.setTextColor(TEXT);
        mInput.setHintTextColor(MUTED);
        mInput.setHint("Sprich mit Hans...");
        mInput.setSingleLine(true);
        mInput.setMinLines(1);
        mInput.setTextSize(13f);
        mInput.setContentDescription("Hans prompt input");
        mInput.setInputType(InputType.TYPE_CLASS_TEXT);
        mInput.setImeOptions(EditorInfo.IME_ACTION_SEND);
        mInput.setBackground(makeRoundRect(SURFACE, LINE));
        mInput.setMinHeight(0);
        mInput.setMinimumHeight(0);
        mInput.setPadding(dp(12), dp(4), dp(12), dp(4));
        mInput.setOnEditorActionListener((view, actionId, event) -> {
            submitCurrentInput();
            return true;
        });
        inputPanel.addView(mInput, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(38)));

        LinearLayout commandRow = new LinearLayout(this);
        commandRow.setOrientation(LinearLayout.HORIZONTAL);
        commandRow.setGravity(Gravity.CENTER_VERTICAL);

        Button send = makeButton("Send", ACCENT, BG);
        send.setContentDescription("Hans send");
        send.setOnClickListener(view -> submitCurrentInput());
        LinearLayout.LayoutParams sendLp = new LinearLayout.LayoutParams(
                0,
                dp(32),
                1f);
        sendLp.setMargins(0, dp(6), dp(6), 0);
        commandRow.addView(send, sendLp);

        mRetry = makeButton("Retry", SURFACE_ALT, BLUE);
        mRetry.setContentDescription("Hans retry");
        mRetry.setEnabled(false);
        mRetry.setAlpha(0.45f);
        mRetry.setOnClickListener(view -> {
            if (!mLastPrompt.isEmpty()) {
                submitPrompt(mLastPrompt, false);
            }
        });
        LinearLayout.LayoutParams retryLp = new LinearLayout.LayoutParams(
                0,
                dp(32),
                1f);
        retryLp.setMargins(dp(6), dp(6), 0, 0);
        commandRow.addView(mRetry, retryLp);

        inputPanel.addView(commandRow, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        root.addView(inputPanel, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        mScroll = new ScrollView(this);
        mScroll.setFillViewport(false);
        mCards = new LinearLayout(this);
        mCards.setOrientation(LinearLayout.VERTICAL);
        mScroll.addView(mCards, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));
        LinearLayout.LayoutParams scrollLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f);
        scrollLp.setMargins(0, dp(6), 0, 0);
        root.addView(mScroll, scrollLp);

        return root;
    }

    private Button quickAction(String label, String prompt, String description) {
        Button button = makeButton(label, SURFACE_ALT, TEXT);
        button.setContentDescription(description);
        button.setOnClickListener(view -> submitPrompt(prompt, true));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                0,
                dp(32),
                1f);
        lp.setMargins(0, 0, dp(6), 0);
        button.setLayoutParams(lp);
        return button;
    }

    private void submitCurrentInput() {
        String text = mInput.getText().toString().trim();
        if (text.isEmpty()) {
            return;
        }
        mInput.setText("");
        submitPrompt(text, true);
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
                addSystemCard("Unbekannte Dev-Quick-Action: " + quick);
            }
        } else if (ACTION_STOP.equals(action)) {
            emergencyStop();
        } else if (ACTION_RETRY.equals(action)) {
            if (!mLastPrompt.isEmpty()) {
                submitPrompt(mLastPrompt, false);
            } else {
                addSystemCard("Kein letzter Auftrag fuer Retry vorhanden.");
            }
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
            mRetry.setEnabled(true);
            mRetry.setAlpha(1f);
        }
        mStreamingSpeechView = null;
        mStreamingSpeech = null;
        addUserCard(text);
        setState("Running", BLUE);
        setStatusLine("Auftrag laeuft.");
        if (mHans == null) {
            bindHans();
            refreshConnectionStatus();
        }
        if (mHans == null) {
            setState("Degraded", AMBER);
            setStatusLine("Core fehlt. Canvas bleibt im lokalen Fehlerpfad.");
            addEventCard("{\"type\":\"error\",\"message\":\"Hans Core fehlt. Starte Cuttlefish mit HansManagerService.\"}");
            return;
        }
        try {
            mHans.submitIntent(text, mCallback);
        } catch (RemoteException e) {
            setState("Error", ROSE);
            setStatusLine("Binder-Aufruf fehlgeschlagen.");
            addEventCard("{\"type\":\"error\",\"message\":\"Hans Fehler: " + escape(e.getMessage()) + "\"}");
        }
    }

    private void emergencyStop() {
        if (mHans == null) {
            bindHans();
            refreshConnectionStatus();
        }
        if (mHans == null) {
            setState("Degraded", AMBER);
            setStatusLine("Stop nicht moeglich, Core fehlt.");
            addSystemCard("Stop nicht moeglich: Core fehlt.");
            return;
        }
        try {
            mHans.emergencyStop();
            setState("Stopped", ROSE);
            setStatusLine("Alle laufenden Agent-Schritte wurden gestoppt.");
            addSystemCard("Emergency Stop aktiv.");
        } catch (RemoteException e) {
            setState("Error", ROSE);
            setStatusLine("Emergency Stop fehlgeschlagen.");
            addSystemCard("Stop fehlgeschlagen: " + e.getMessage());
        }
    }

    private void addUserCard(String text) {
        addCard("Command", text, BLUE);
    }

    private void addSystemCard(String text) {
        mStreamingSpeechView = null;
        mStreamingSpeech = null;
        addCard("System", text, MUTED);
    }

    private void addEventCard(String raw) {
        String type = "event";
        String message = raw;
        try {
            JSONObject event = new JSONObject(raw);
            type = event.optString("type", "event");
            message = event.optString("message", raw);
        } catch (JSONException ignored) {
            // Non-JSON system cards are still useful during early boot debugging.
        }

        int color = colorForType(type, message);
        updateStateForEvent(type, message, color);
        if ("speech".equals(type) && mStreamingSpeechView != null) {
            mStreamingSpeech.append(message);
            mStreamingSpeechView.setText(mStreamingSpeech.toString());
            mScroll.post(() -> mScroll.fullScroll(ScrollView.FOCUS_DOWN));
            return;
        }
        TextView messageView = addCard(labelForType(type, message), message, color);
        if ("speech".equals(type)) {
            mStreamingSpeechView = messageView;
            mStreamingSpeech = new StringBuilder(message);
        } else {
            mStreamingSpeechView = null;
            mStreamingSpeech = null;
        }
    }

    private TextView addCard(String label, String message, int accentColor) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(13), dp(16), dp(14));
        card.setBackground(makeRoundRect(SURFACE, darken(accentColor)));

        TextView labelView = new TextView(this);
        labelView.setText(label);
        labelView.setTextColor(accentColor);
        labelView.setTextSize(12f);
        labelView.setTypeface(Typeface.DEFAULT_BOLD);
        card.addView(labelView);

        TextView messageView = new TextView(this);
        messageView.setText(message);
        messageView.setTextColor(TEXT);
        messageView.setTextSize(16f);
        messageView.setLineSpacing(0f, 1.12f);
        LinearLayout.LayoutParams messageLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        messageLp.setMargins(0, dp(6), 0, 0);
        card.addView(messageView, messageLp);

        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, dp(10), 0, 0);
        mCards.addView(card, lp);
        mScroll.post(() -> mScroll.fullScroll(ScrollView.FOCUS_DOWN));
        return messageView;
    }

    private void updateStateForEvent(String type, String message, int color) {
        if ("error".equals(type) || "repair_suggestion".equals(type)) {
            setState("Needs attention", ROSE);
            setStatusLine("Hans braucht Aufmerksamkeit.");
        } else if (message != null && message.toLowerCase().contains("without runtime")) {
            setState("Degraded", AMBER);
            setStatusLine("Runtime fehlt. Core antwortet lokal degradiert.");
        } else if ("action_started".equals(type) || "app_control_started".equals(type)) {
            setState("Acting", AMBER);
            setStatusLine("Aktion wird ausgefuehrt.");
        } else if ("speech".equals(type)) {
            setState("Speaking", BLUE);
            setStatusLine("Antwort wird aufgebaut.");
        } else if ("thinking".equals(type) || "plan".equals(type)) {
            setState("Thinking", color);
            setStatusLine("Hans plant den naechsten Schritt.");
        } else if ("done".equals(type)) {
            setState("Ready", ACCENT);
            setStatusLine("Bereit fuer den naechsten Auftrag.");
        }
    }

    private String labelForType(String type, String message) {
        if (message != null && message.toLowerCase().contains("without runtime")) {
            return "Degraded";
        }
        if ("thinking".equals(type)) {
            return "Thinking";
        }
        if ("plan".equals(type)) {
            return "Plan";
        }
        if ("speech".equals(type)) {
            return "Speech";
        }
        if ("action_started".equals(type) || "app_control_started".equals(type)) {
            return "Action";
        }
        if ("action_completed".equals(type) || "app_control_completed".equals(type)) {
            return "Result";
        }
        if ("audit".equals(type)) {
            return "Audit";
        }
        if ("error".equals(type)) {
            return "Error";
        }
        if ("repair_suggestion".equals(type)) {
            return "Repair";
        }
        if ("done".equals(type)) {
            return "Done";
        }
        return "Hans";
    }

    private int colorForType(String type, String message) {
        if (message != null && message.toLowerCase().contains("without runtime")) {
            return AMBER;
        }
        if ("action_started".equals(type) || "action_completed".equals(type)
                || "app_control_started".equals(type) || "app_control_completed".equals(type)) {
            return AMBER;
        }
        if ("speech".equals(type) || "thinking".equals(type) || "plan".equals(type)) {
            return BLUE;
        }
        if ("error".equals(type) || "repair_suggestion".equals(type)) {
            return ROSE;
        }
        if ("done".equals(type)) {
            return ACCENT;
        }
        return MUTED;
    }

    private void refreshConnectionStatus() {
        if (mHans == null) {
            mConnection.setText("Core getrennt - Provider " + providerLabel());
            mConnection.setTextColor(AMBER);
            setState("Degraded", AMBER);
            setStatusLine("Core nicht erreichbar.");
        } else {
            mConnection.setText("Core verbunden - Provider " + providerLabel());
            mConnection.setTextColor(ACCENT);
            setState("Ready", ACCENT);
        }
    }

    private String providerLabel() {
        String provider = SystemProperties.get(PROVIDER_PROP, "fake");
        if ("openai".equals(provider)) {
            return "OpenAI";
        }
        return "Fake";
    }

    private void setState(String label, int color) {
        if (mStatePill == null) {
            return;
        }
        mStatePill.setText(label);
        mStatePill.setContentDescription("Hans state " + label);
        mStatePill.setTextColor(color);
        mStatePill.setBackground(makeRoundRect(darken(color), color));
    }

    private void setStatusLine(String text) {
        if (mStatusLine != null) {
            mStatusLine.setText(text);
        }
    }

    private Button makeButton(String text, int background, int foreground) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextColor(foreground);
        button.setTextSize(12f);
        button.setAllCaps(false);
        button.setMinHeight(0);
        button.setMinimumHeight(0);
        button.setMinWidth(0);
        button.setMinimumWidth(0);
        button.setSingleLine(true);
        button.setGravity(Gravity.CENTER);
        button.setPadding(dp(8), 0, dp(8), 0);
        button.setBackground(makeRoundRect(background, LINE));
        return button;
    }

    private GradientDrawable makeRoundRect(int fill, int stroke) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fill);
        drawable.setCornerRadius(dp(8));
        drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private int darken(int color) {
        return Color.rgb(
                Math.max(0, Color.red(color) / 4),
                Math.max(0, Color.green(color) / 4),
                Math.max(0, Color.blue(color) / 4));
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }

    private String escape(String value) {
        if (value == null) {
            return "";
        }
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
