package ai.hansos.agent;

public final class HansAgentStates {
    public static final int STARTING = 0;
    public static final int IDLE = 1;
    public static final int THINKING = 2;
    public static final int ACTING = 3;
    public static final int SPEAKING = 4;
    public static final int LISTENING = 5;
    public static final int TRANSCRIBING = 6;
    public static final int STOPPED = 7;
    public static final int ERROR = 8;

    private HansAgentStates() {
    }
}
