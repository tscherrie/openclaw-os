package ai.hansos.agent;

interface IHansStreamCallback {
    void onEvent(String requestId, String eventJson);
}
