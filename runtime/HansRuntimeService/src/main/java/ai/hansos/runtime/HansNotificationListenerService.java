package ai.hansos.runtime;

import android.app.Notification;
import android.content.ComponentName;
import android.content.Context;
import android.os.Bundle;
import android.provider.Settings;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.util.Slog;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class HansNotificationListenerService extends NotificationListenerService {
    private static final String TAG = "HansNotifications";
    private static final Map<String, NotificationSnapshot> SNAPSHOTS = new ConcurrentHashMap<>();
    private static volatile boolean sListenerConnected;

    @Override
    public void onListenerConnected() {
        sListenerConnected = true;
        try {
            StatusBarNotification[] activeNotifications = getActiveNotifications();
            SNAPSHOTS.clear();
            if (activeNotifications != null) {
                for (StatusBarNotification notification : activeNotifications) {
                    remember(notification);
                }
            }
        } catch (SecurityException e) {
            Slog.w(TAG, "Could not read active notifications on connect", e);
        }
    }

    @Override
    public void onListenerDisconnected() {
        sListenerConnected = false;
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        remember(sbn);
    }

    @Override
    public void onNotificationRemoved(StatusBarNotification sbn) {
        if (sbn != null) {
            SNAPSHOTS.remove(sbn.getKey());
        }
    }

    static void ensureEnabled(Context context) {
        ComponentName component = new ComponentName(context, HansNotificationListenerService.class);
        String flat = component.flattenToString();
        String enabled = Settings.Secure.getString(
                context.getContentResolver(), "enabled_notification_listeners");
        if (enabled != null && containsFlatComponent(enabled, flat)) {
            return;
        }
        String next = enabled == null || enabled.isEmpty() ? flat : enabled + ":" + flat;
        try {
            Settings.Secure.putString(
                    context.getContentResolver(), "enabled_notification_listeners", next);
        } catch (SecurityException e) {
            Slog.w(TAG, "Could not enable notification listener", e);
        }
    }

    static String buildSummary(Context context) {
        ensureEnabled(context);
        if (SNAPSHOTS.isEmpty()) {
            return "notifications: listener_connected=" + sListenerConnected + ", active=0";
        }

        List<NotificationSnapshot> snapshots = new ArrayList<>(SNAPSHOTS.values());
        Collections.sort(snapshots, Comparator.comparingLong(
                (NotificationSnapshot snapshot) -> snapshot.postTime).reversed());

        int important = 0;
        Map<String, Integer> byPackage = new ConcurrentHashMap<>();
        for (NotificationSnapshot snapshot : snapshots) {
            if (snapshot.important) {
                important++;
            }
            Integer count = byPackage.get(snapshot.packageName);
            byPackage.put(snapshot.packageName, count == null ? 1 : count + 1);
        }

        StringBuilder builder = new StringBuilder();
        builder.append("notifications: listener_connected=")
                .append(sListenerConnected)
                .append(", active=")
                .append(snapshots.size())
                .append(", important=")
                .append(important);
        builder.append(", packages=");
        int packageIndex = 0;
        for (Map.Entry<String, Integer> entry : byPackage.entrySet()) {
            if (packageIndex > 0) {
                builder.append('|');
            }
            builder.append(entry.getKey()).append(':').append(entry.getValue());
            packageIndex++;
            if (packageIndex >= 4) {
                break;
            }
        }
        builder.append(", latest=");
        int max = Math.min(3, snapshots.size());
        for (int index = 0; index < max; index++) {
            if (index > 0) {
                builder.append(" | ");
            }
            builder.append(snapshots.get(index).safeTitle());
        }
        return builder.toString();
    }

    private static boolean containsFlatComponent(String enabled, String flat) {
        String[] pieces = enabled.split(":");
        for (String piece : pieces) {
            if (flat.equals(piece)) {
                return true;
            }
        }
        return false;
    }

    private static void remember(StatusBarNotification sbn) {
        if (sbn == null || sbn.getNotification() == null) {
            return;
        }
        SNAPSHOTS.put(sbn.getKey(), NotificationSnapshot.from(sbn));
    }

    private static final class NotificationSnapshot {
        final String packageName;
        final String title;
        final long postTime;
        final boolean important;

        NotificationSnapshot(String packageName, String title, long postTime, boolean important) {
            this.packageName = packageName;
            this.title = title;
            this.postTime = postTime;
            this.important = important;
        }

        static NotificationSnapshot from(StatusBarNotification sbn) {
            Notification notification = sbn.getNotification();
            Bundle extras = notification.extras;
            CharSequence title = extras == null ? null
                    : extras.getCharSequence(Notification.EXTRA_TITLE);
            CharSequence text = extras == null ? null
                    : extras.getCharSequence(Notification.EXTRA_TEXT);
            String label = firstNonEmpty(title, text, sbn.getPackageName());
            boolean important = notification.priority >= Notification.PRIORITY_HIGH
                    || Notification.CATEGORY_CALL.equals(notification.category)
                    || Notification.CATEGORY_MESSAGE.equals(notification.category)
                    || Notification.CATEGORY_ALARM.equals(notification.category);
            return new NotificationSnapshot(
                    sbn.getPackageName(),
                    sanitize(label),
                    sbn.getPostTime(),
                    important);
        }

        String safeTitle() {
            if (title.isEmpty()) {
                return packageName;
            }
            return packageName + "/" + title;
        }

        private static String firstNonEmpty(CharSequence first, CharSequence second, String fallback) {
            if (first != null && first.length() > 0) {
                return first.toString();
            }
            if (second != null && second.length() > 0) {
                return second.toString();
            }
            return fallback == null ? "" : fallback;
        }

        private static String sanitize(String value) {
            if (value == null) {
                return "";
            }
            String normalized = value.replace('\n', ' ')
                    .replace('\r', ' ')
                    .trim();
            if (normalized.length() <= 48) {
                return normalized;
            }
            return normalized.substring(0, 45).trim().toLowerCase(Locale.ROOT) + "...";
        }
    }
}
