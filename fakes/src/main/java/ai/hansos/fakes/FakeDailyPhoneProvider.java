package ai.hansos.fakes;

public final class FakeDailyPhoneProvider {
    private boolean mFocusMode;

    public String setFocusMode(boolean enabled) {
        mFocusMode = enabled;
        return "fake_device_state.focus_mode=" + mFocusMode;
    }

    public String buildMorningBrief() {
        return "Guten Morgen. Du hast um 10 Standup, eine Nachricht wartet, und der Akku steht bei 82 Prozent.";
    }

    public String triageNotifications() {
        return "fake_notifications: 3 grouped, 1 important";
    }
}
