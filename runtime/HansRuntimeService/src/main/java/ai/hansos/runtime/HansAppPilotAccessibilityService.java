package ai.hansos.runtime;

import android.accessibilityservice.AccessibilityService;
import android.os.Bundle;
import android.os.SystemClock;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.Slog;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;

public final class HansAppPilotAccessibilityService extends AccessibilityService {
    private static final String TAG = "HansAppPilot";
    private static final int MAX_VISIBLE_TEXT_CHARS = 180;
    private static final int MAX_NODE_COUNT = 48;
    private static final long SCREEN_SETTLE_MS = 700;
    private static final String[] SAFE_PACKAGES = {
            "ai.hansos.canvas",
            "ai.hansos.runtime",
            "com.android.settings",
            "com.android.systemui",
    };

    private static volatile HansAppPilotAccessibilityService sInstance;
    private static volatile String sLastSummary = "app_pilot: service=disconnected";
    private static volatile long sLastEventUptimeMillis;

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        sInstance = this;
        refreshSummary("connected");
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        String reason = event == null ? "event" : "event_" + event.getEventType();
        refreshSummary(reason);
    }

    @Override
    public void onInterrupt() {
        sLastSummary = "app_pilot: service=interrupted";
        sLastEventUptimeMillis = SystemClock.uptimeMillis();
    }

    @Override
    public boolean onUnbind(Intent intent) {
        if (sInstance == this) {
            sInstance = null;
        }
        sLastSummary = "app_pilot: service=disconnected";
        sLastEventUptimeMillis = SystemClock.uptimeMillis();
        return super.onUnbind(intent);
    }

    static void ensureEnabled(Context context) {
        ComponentName component = new ComponentName(context, HansAppPilotAccessibilityService.class);
        String flat = component.flattenToString();
        String enabled = Settings.Secure.getString(
                context.getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        if (!containsEnabledService(enabled, flat)) {
            String value = enabled == null || enabled.isEmpty() ? flat : enabled + ":" + flat;
            Settings.Secure.putString(context.getContentResolver(),
                    Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES, value);
        }
        Settings.Secure.putInt(context.getContentResolver(),
                Settings.Secure.ACCESSIBILITY_ENABLED, 1);
    }

    static String openSettingsAndInspectNetwork(Context context, SystemPhoneProvider phone) {
        ensureEnabled(context);
        String network = phone.inspectNetworkSettings();
        waitForScreen();
        refreshActiveSummary();
        String summary = getLastSummary();
        performHome();
        return network + "; " + summary;
    }

    static String observeCurrentScreen(Context context) {
        ensureEnabled(context);
        waitForScreen();
        refreshActiveSummary();
        return getLastSummary();
    }

    static String getLastSummary() {
        return sLastSummary + "; last_event_uptime_ms=" + sLastEventUptimeMillis;
    }

    static boolean performHome() {
        HansAppPilotAccessibilityService service = sInstance;
        return service != null && service.performGlobalAction(GLOBAL_ACTION_HOME);
    }

    static boolean performBack() {
        HansAppPilotAccessibilityService service = sInstance;
        return service != null && service.performGlobalAction(GLOBAL_ACTION_BACK);
    }

    static boolean clickVisibleText(String text) {
        HansAppPilotAccessibilityService service = sInstance;
        if (service == null || text == null || text.isEmpty()) {
            return false;
        }
        AccessibilityNodeInfo root = service.getRootInActiveWindow();
        try {
            AccessibilityNodeInfo node = findNodeByText(root, text);
            if (node == null) {
                return false;
            }
            AccessibilityNodeInfo clickable = null;
            try {
                clickable = findClickableAncestor(node);
                return clickable != null && clickable.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            } finally {
                if (clickable != null) {
                    clickable.recycle();
                }
                node.recycle();
            }
        } finally {
            if (root != null) {
                root.recycle();
            }
        }
    }

    static boolean enterTextInFocusedField(String text) {
        HansAppPilotAccessibilityService service = sInstance;
        if (service == null) {
            return false;
        }
        AccessibilityNodeInfo root = service.getRootInActiveWindow();
        try {
            AccessibilityNodeInfo focused = findFocusedEditable(root);
            if (focused == null) {
                return false;
            }
            Bundle args = new Bundle();
            args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
            try {
                return focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
            } finally {
                focused.recycle();
            }
        } finally {
            if (root != null) {
                root.recycle();
            }
        }
    }

    static boolean scrollForward() {
        HansAppPilotAccessibilityService service = sInstance;
        if (service == null) {
            return false;
        }
        AccessibilityNodeInfo root = service.getRootInActiveWindow();
        try {
            AccessibilityNodeInfo scrollable = findScrollable(root);
            return scrollable != null
                    && scrollable.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD);
        } finally {
            if (root != null) {
                root.recycle();
            }
        }
    }

    static boolean isSafePackage(String packageName) {
        if (packageName == null) {
            return false;
        }
        for (String safePackage : SAFE_PACKAGES) {
            if (packageName.equals(safePackage)) {
                return true;
            }
        }
        return false;
    }

    private static void refreshActiveSummary() {
        HansAppPilotAccessibilityService service = sInstance;
        if (service != null) {
            service.refreshSummary("manual_refresh");
        }
    }

    private void refreshSummary(String reason) {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        try {
            sLastSummary = buildSummary(reason, root);
            sLastEventUptimeMillis = SystemClock.uptimeMillis();
        } catch (RuntimeException e) {
            Slog.w(TAG, "Could not inspect active window", e);
            sLastSummary = "app_pilot: service=connected, active=unknown, error="
                    + sanitize(e.getClass().getSimpleName());
            sLastEventUptimeMillis = SystemClock.uptimeMillis();
        } finally {
            if (root != null) {
                root.recycle();
            }
        }
    }

    private static String buildSummary(String reason, AccessibilityNodeInfo root) {
        if (root == null) {
            return "app_pilot: service=connected, active=unknown, reason=" + sanitize(reason);
        }
        CharSequence packageName = root.getPackageName();
        CharSequence className = root.getClassName();
        StringBuilder visibleText = new StringBuilder();
        int nodeCount = appendVisibleText(root, visibleText, 0, 0);
        String activePackage = packageName == null ? "unknown" : packageName.toString();
        return "app_pilot: service=connected"
                + ", active=" + sanitize(activePackage)
                + "/" + sanitize(className == null ? "unknown" : className.toString())
                + ", allowed=" + isSafePackage(activePackage)
                + ", nodes=" + nodeCount
                + ", reason=" + sanitize(reason)
                + ", text=" + sanitize(visibleText.toString());
    }

    private static int appendVisibleText(
            AccessibilityNodeInfo node, StringBuilder out, int depth, int seen) {
        if (node == null || seen >= MAX_NODE_COUNT) {
            return seen;
        }
        int current = seen + 1;
        appendText(out, node.getText());
        appendText(out, node.getContentDescription());
        if (depth >= 6 || out.length() >= MAX_VISIBLE_TEXT_CHARS) {
            return current;
        }
        int childCount = node.getChildCount();
        for (int i = 0; i < childCount && current < MAX_NODE_COUNT; i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            try {
                current = appendVisibleText(child, out, depth + 1, current);
            } finally {
                if (child != null) {
                    child.recycle();
                }
            }
        }
        return current;
    }

    private static void appendText(StringBuilder out, CharSequence value) {
        if (value == null || value.length() == 0 || out.length() >= MAX_VISIBLE_TEXT_CHARS) {
            return;
        }
        if (out.length() > 0) {
            out.append(" | ");
        }
        int remaining = MAX_VISIBLE_TEXT_CHARS - out.length();
        String text = value.toString().replace('\n', ' ').trim();
        out.append(text.length() > remaining ? text.substring(0, remaining) : text);
    }

    private static AccessibilityNodeInfo findNodeByText(
            AccessibilityNodeInfo node, String text) {
        if (node == null) {
            return null;
        }
        CharSequence nodeText = node.getText();
        CharSequence description = node.getContentDescription();
        if (containsIgnoreCase(nodeText, text) || containsIgnoreCase(description, text)) {
            return AccessibilityNodeInfo.obtain(node);
        }
        int childCount = node.getChildCount();
        for (int i = 0; i < childCount; i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            try {
                AccessibilityNodeInfo match = findNodeByText(child, text);
                if (match != null) {
                    return match;
                }
            } finally {
                if (child != null) {
                    child.recycle();
                }
            }
        }
        return null;
    }

    private static AccessibilityNodeInfo findClickableAncestor(AccessibilityNodeInfo node) {
        AccessibilityNodeInfo current = node == null ? null : AccessibilityNodeInfo.obtain(node);
        while (current != null) {
            if (current.isClickable()) {
                return current;
            }
            AccessibilityNodeInfo parent = current.getParent();
            current.recycle();
            current = parent;
        }
        return null;
    }

    private static AccessibilityNodeInfo findFocusedEditable(AccessibilityNodeInfo node) {
        if (node == null) {
            return null;
        }
        if (node.isFocused() && node.isEditable()) {
            return AccessibilityNodeInfo.obtain(node);
        }
        int childCount = node.getChildCount();
        for (int i = 0; i < childCount; i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            try {
                AccessibilityNodeInfo match = findFocusedEditable(child);
                if (match != null) {
                    return match;
                }
            } finally {
                if (child != null) {
                    child.recycle();
                }
            }
        }
        return null;
    }

    private static AccessibilityNodeInfo findScrollable(AccessibilityNodeInfo node) {
        if (node == null) {
            return null;
        }
        if (node.isScrollable()) {
            return AccessibilityNodeInfo.obtain(node);
        }
        int childCount = node.getChildCount();
        for (int i = 0; i < childCount; i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            try {
                AccessibilityNodeInfo match = findScrollable(child);
                if (match != null) {
                    return match;
                }
            } finally {
                if (child != null) {
                    child.recycle();
                }
            }
        }
        return null;
    }

    private static boolean containsIgnoreCase(CharSequence source, String needle) {
        return source != null && needle != null
                && source.toString().toLowerCase().contains(needle.toLowerCase());
    }

    private static boolean containsEnabledService(String enabled, String flat) {
        if (enabled == null || enabled.isEmpty()) {
            return false;
        }
        TextUtils.SimpleStringSplitter splitter = new TextUtils.SimpleStringSplitter(':');
        splitter.setString(enabled);
        for (String service : splitter) {
            if (flat.equals(service)) {
                return true;
            }
        }
        return false;
    }

    private static void waitForScreen() {
        SystemClock.sleep(SCREEN_SETTLE_MS);
    }

    private static String sanitize(String value) {
        if (value == null) {
            return "";
        }
        return value.replace('\n', ' ')
                .replace('\r', ' ')
                .replace(';', ',')
                .trim();
    }
}
