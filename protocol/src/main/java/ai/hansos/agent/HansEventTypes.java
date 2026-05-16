package ai.hansos.agent;

public final class HansEventTypes {
    public static final String THINKING = "thinking";
    public static final String PLAN = "plan";
    public static final String SPEECH = "speech";
    public static final String LISTENING_STARTED = "listening_started";
    public static final String LISTENING_FINISHED = "listening_finished";
    public static final String TRANSCRIPT_PARTIAL = "transcript_partial";
    public static final String TRANSCRIPT_FINAL = "transcript_final";
    public static final String SPEAKING_STARTED = "speaking_started";
    public static final String SPEAKING_FINISHED = "speaking_finished";
    public static final String CONFIRMATION_REQUIRED = "confirmation_required";
    public static final String CONFIRMATION_ACCEPTED = "confirmation_accepted";
    public static final String CONFIRMATION_REJECTED = "confirmation_rejected";
    public static final String VISUAL_STARTED = "visual_started";
    public static final String VISUAL_UPDATED = "visual_updated";
    public static final String MANUAL_MODE_REQUIRED = "manual_mode_required";
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
