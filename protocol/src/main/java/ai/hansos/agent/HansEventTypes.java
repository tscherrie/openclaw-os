package ai.hansos.agent;

public final class HansEventTypes {
    public static final String THINKING = "thinking";
    public static final String PLAN = "plan";
    public static final String SPEECH = "speech";
    public static final String ACTION_STARTED = "action_started";
    public static final String ACTION_COMPLETED = "action_completed";
    public static final String APP_CONTROL_STARTED = "app_control_started";
    public static final String APP_CONTROL_COMPLETED = "app_control_completed";
    public static final String AUDIT = "audit";
    public static final String ERROR = "error";
    public static final String REPAIR_SUGGESTION = "repair_suggestion";
    public static final String DONE = "done";

    private HansEventTypes() {
    }
}
