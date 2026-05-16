package ai.hansos.runtime;

import android.app.NotificationManager;
import android.content.ContentUris;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.database.Cursor;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.os.BatteryManager;
import android.provider.CalendarContract;
import android.provider.Settings;
import android.telephony.TelephonyManager;
import android.util.Slog;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

final class SystemPhoneProvider {
    private static final String TAG = "HansSystemPhone";
    private static final long MORNING_LOOKAHEAD_MILLIS = 18L * 60L * 60L * 1000L;
    private static final int MAX_CALENDAR_ITEMS = 3;

    private final Context mContext;

    SystemPhoneProvider(Context context) {
        mContext = context;
    }

    String setFocusMode(boolean enabled) {
        String interruption = setInterruptionFilter(enabled);
        return "device_state.focus_mode=" + enabled
                + "; interruption_filter=" + interruption
                + "; " + buildDeviceStateSummary();
    }

    String buildMorningBrief() {
        StringBuilder builder = new StringBuilder();
        builder.append("Guten Morgen. ");
        builder.append(buildCalendarSummary()).append(' ');
        builder.append(HansNotificationListenerService.buildSummary(mContext)).append(' ');
        builder.append(buildDeviceStateSummary()).append('.');
        return builder.toString();
    }

    String triageNotifications() {
        return HansNotificationListenerService.buildSummary(mContext);
    }

    String inspectNetworkSettings() {
        launchSettings(Settings.ACTION_WIRELESS_SETTINGS);
        return "settings.network: " + buildNetworkSummary();
    }

    String buildDeviceStateSummary() {
        return "device_context: " + buildBatterySummary()
                + ", " + buildNetworkSummary()
                + ", " + buildTelephonySummary()
                + ", zen_mode=" + readZenMode();
    }

    private String buildBatterySummary() {
        Intent battery = mContext.registerReceiver(
                null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        if (battery == null) {
            return "battery=unknown";
        }
        int level = battery.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
        int scale = battery.getIntExtra(BatteryManager.EXTRA_SCALE, -1);
        int plugged = battery.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0);
        int percent = scale > 0 && level >= 0 ? Math.round((level * 100f) / scale) : -1;
        return "battery=" + (percent >= 0 ? percent + "%" : "unknown")
                + ", charging=" + (plugged != 0);
    }

    private String buildNetworkSummary() {
        ConnectivityManager connectivity =
                mContext.getSystemService(ConnectivityManager.class);
        if (connectivity == null) {
            return "network=unknown";
        }
        Network active = connectivity.getActiveNetwork();
        NetworkCapabilities capabilities = active == null
                ? null : connectivity.getNetworkCapabilities(active);
        if (capabilities == null) {
            return "network=offline";
        }
        StringBuilder builder = new StringBuilder("network=");
        if (capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) {
            builder.append("wifi");
        } else if (capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)) {
            builder.append("cellular");
        } else if (capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) {
            builder.append("vpn");
        } else {
            builder.append("other");
        }
        builder.append(", internet=")
                .append(capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET));
        builder.append(", validated=")
                .append(capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED));
        return builder.toString();
    }

    private String buildTelephonySummary() {
        TelephonyManager telephony = mContext.getSystemService(TelephonyManager.class);
        if (telephony == null) {
            return "sim=unknown";
        }
        String operator = "";
        try {
            operator = telephony.getNetworkOperatorName();
        } catch (SecurityException e) {
            Slog.v(TAG, "No permission for operator name", e);
        }
        return "sim=" + simStateToString(telephony.getSimState())
                + (operator == null || operator.isEmpty() ? "" : ", operator=" + operator);
    }

    private String buildCalendarSummary() {
        long now = System.currentTimeMillis();
        long end = now + MORNING_LOOKAHEAD_MILLIS;
        android.net.Uri.Builder builder = CalendarContract.Instances.CONTENT_URI.buildUpon();
        ContentUris.appendId(builder, now);
        ContentUris.appendId(builder, end);

        String[] projection = {
                CalendarContract.Instances.TITLE,
                CalendarContract.Instances.BEGIN,
                CalendarContract.Instances.EVENT_LOCATION,
                CalendarContract.Instances.ALL_DAY,
        };

        try (Cursor cursor = mContext.getContentResolver().query(
                builder.build(),
                projection,
                null,
                null,
                CalendarContract.Instances.BEGIN + " ASC")) {
            if (cursor == null || !cursor.moveToFirst()) {
                return "calendar: keine Termine in den naechsten 18 Stunden.";
            }
            SimpleDateFormat timeFormat = new SimpleDateFormat("HH:mm", Locale.GERMANY);
            StringBuilder summary = new StringBuilder("calendar: ");
            int count = 0;
            do {
                if (count > 0) {
                    summary.append(" | ");
                }
                String title = cursor.getString(0);
                long begin = cursor.getLong(1);
                String location = cursor.getString(2);
                boolean allDay = cursor.getInt(3) != 0;
                summary.append(allDay ? "ganztags" : timeFormat.format(new Date(begin)))
                        .append(' ')
                        .append(title == null || title.isEmpty() ? "Termin" : title);
                if (location != null && !location.isEmpty()) {
                    summary.append(" @ ").append(location);
                }
                count++;
            } while (count < MAX_CALENDAR_ITEMS && cursor.moveToNext());
            return summary.toString();
        } catch (SecurityException e) {
            return "calendar: keine Berechtigung fuer Kalenderzugriff.";
        } catch (RuntimeException e) {
            Slog.w(TAG, "Calendar query failed", e);
            return "calendar: nicht lesbar.";
        }
    }

    private String setInterruptionFilter(boolean enabled) {
        NotificationManager notificationManager =
                mContext.getSystemService(NotificationManager.class);
        String result = "unchanged";
        if (notificationManager != null) {
            try {
                notificationManager.setInterruptionFilter(enabled
                        ? NotificationManager.INTERRUPTION_FILTER_PRIORITY
                        : NotificationManager.INTERRUPTION_FILTER_ALL);
                result = String.valueOf(notificationManager.getCurrentInterruptionFilter());
            } catch (SecurityException e) {
                Slog.w(TAG, "Could not set interruption filter", e);
            }
        }
        try {
            Settings.Global.putInt(mContext.getContentResolver(), "zen_mode", enabled ? 1 : 0);
            result = result + ", zen_mode=" + readZenMode();
        } catch (SecurityException e) {
            Slog.w(TAG, "Could not write zen_mode", e);
        }
        return result;
    }

    private int readZenMode() {
        try {
            return Settings.Global.getInt(mContext.getContentResolver(), "zen_mode", 0);
        } catch (SecurityException e) {
            return -1;
        }
    }

    private void launchSettings(String action) {
        try {
            Intent intent = new Intent(action);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            mContext.startActivity(intent);
        } catch (RuntimeException e) {
            Slog.w(TAG, "Could not launch settings action " + action, e);
        }
    }

    private static String simStateToString(int state) {
        switch (state) {
            case TelephonyManager.SIM_STATE_READY:
                return "ready";
            case TelephonyManager.SIM_STATE_ABSENT:
                return "absent";
            case TelephonyManager.SIM_STATE_PIN_REQUIRED:
                return "pin_required";
            case TelephonyManager.SIM_STATE_PUK_REQUIRED:
                return "puk_required";
            case TelephonyManager.SIM_STATE_NETWORK_LOCKED:
                return "network_locked";
            default:
                return "state_" + state;
        }
    }
}
